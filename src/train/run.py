"""Run one training job and the operator CLI."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

# Required before cuBLAS loads when determinism_policy is exact.
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")

import click
import torch
from peft import LoraConfig, TaskType, get_peft_model

from src.data.errors import DataError
from src.data.exclusion import require_pass
from src.models import FactVerifyLoaderError, load_local_checkpoint, load_model
from src.models.spec import load_model_policy

from .checkpoint import discard_adapter, publish_adapter, publish_model
from .config import (
    GroupedJobConfig,
    JobConfig,
    RunAdapter,
    allowed_item_ids,
    config_hash,
    detect_config_format,
    expand_runs,
    hash_mapping,
    hyperparameters_of,
    load_grouped_config,
    load_job_config,
    procedure_differences,
)
from src.ledger.train_store import TrainingRunRecord, open_train_store

from .cost import CostRecord
from .data import DataCatalog
from .errors import FactVerifyHarnessError
from .ledger import CheckpointRow, LedgerPort, require_sqlite_ledger
from .manifests import leaked_bundle_documents
from .methods import get_trainer
from .methods.common import selection_summary
from .seeding import apply_seed


@dataclass(frozen=True)
class JobResult:
    """Outcome of one job. `succeeded` only after a committed ledger row."""

    status: Literal["succeeded", "failed"]
    adapter_path: Path | None
    config_hash: str | None
    checkpoint_identity_hash: str | None
    error: str | None
    access_log: list[str]
    wall_clock_seconds: float = 0.0
    gpu_hours: float = 0.0
    peak_memory_bytes: int = 0
    training_steps: int = 0
    training_examples: int = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Legacy flat-format runner (unchanged)
# ═══════════════════════════════════════════════════════════════════════════════


def run_job(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: LedgerPort,
    git_commit: str,
    dirty: bool,
) -> JobResult:
    """Train one checkpoint from a job file. Validation failures raise."""
    if not spec_root.exists():
        raise FactVerifyHarnessError(f"unreadable spec root {spec_root}")
    config = load_job_config(config_path)
    paired_hash = _precheck(config, ledger)
    return _execute(
        config,
        spec_root=spec_root,
        ledger=ledger,
        paired_hash=paired_hash,
        git_commit=git_commit,
        dirty=dirty,
    )


def _precheck(config: JobConfig, ledger: LedgerPort) -> str | None:
    """Reference checks. Returns the paired finetune hash, or None for other roles."""
    report = config.raw.get("gate_report")
    if report is not None:
        require_pass(config.target_fact_id, Path(str(report)))
    if config.role != "reference":
        return None
    paired_path = Path(str(config.raw["paired_finetune_config"]))
    if not paired_path.is_file():
        raise FactVerifyHarnessError(f"unreadable config {paired_path}")
    paired = load_job_config(paired_path)
    differences = procedure_differences(config, paired)
    if differences:
        raise FactVerifyHarnessError("procedure mismatch: " + ", ".join(differences))
    leaked = leaked_bundle_documents(config.manifest["train"], config.source_bundle)
    if leaked:
        raise FactVerifyHarnessError(f"source bundle document {leaked[0]!r}")
    previous = ledger.split_for_seed(config.target_fact_id, config.seed)
    if previous is not None and previous != config.split:
        raise FactVerifyHarnessError(
            f"seed {config.seed} already recorded for fact "
            f"{config.target_fact_id!r} under split {previous!r}"
        )
    return config_hash(paired)


def _execute(
    config: JobConfig,
    *,
    spec_root: Path,
    ledger: LedgerPort,
    paired_hash: str | None,
    git_commit: str,
    dirty: bool,
) -> JobResult:
    digest = config_hash(config)
    cost = CostRecord()
    cost.start()
    output_dir = Path(config.output_dir)
    published = False
    steps = 0
    examples = 0
    access_log: list[str] = []
    parent_hash = ""
    policy = load_model_policy(spec_root)
    if str(config.raw["spec_revision"]) != policy.governing_spec_revision:
        raise FactVerifyHarnessError(
            f"spec_revision {config.raw['spec_revision']!r} does not match "
            f"governing_spec_revision {policy.governing_spec_revision!r}"
        )
    model_config = Path(config.model_config)
    if not model_config.is_absolute():
        model_config = spec_root / model_config
    try:
        base = load_model(
            config.base_role, model_config=model_config, spec_root=spec_root
        )
        report = config.raw.get("gate_report")
        if report is not None:
            require_pass(
                config.target_fact_id,
                Path(str(report)),
                model_identity_hash=base.identity_hash,
                model_config_digest=base.model_config_digest,
            )
        base_hash = base.identity_hash
        if config.role == "candidate":
            parent = load_model(
                config.base_role,
                model_config=model_config,
                spec_root=spec_root,
                adapter_path=Path(str(config.raw["parent_adapter"])),
            )
            parent_hash = parent.identity_hash
            model = parent.model
            tokenizer = parent.tokenizer
            apply_seed(config.seed, config.determinism_policy)
        else:
            parent_hash = base_hash
            apply_seed(config.seed, config.determinism_policy)
            model = get_peft_model(base.model, _lora_config(config))
            tokenizer = base.tokenizer
        model.train()
        _enable_lora_training(model)
        catalog = DataCatalog(Path(config.corpus_dir), allowed_item_ids(config))
        trainer = get_trainer(config.method)
        data_order, steps, examples = trainer(config, model, tokenizer, catalog)
        catalog.assert_closed()
        access_log = list(catalog.access_log)
        metadata = _metadata(
            config,
            digest=digest,
            base_hash=base_hash,
            parent_hash=parent_hash,
            data_order=data_order,
            paired_hash=paired_hash,
        )
        publish_adapter(model, output_dir, metadata, base_hash)
        published = True
        loaded = load_model(
            config.base_role,
            model_config=model_config,
            spec_root=spec_root,
            adapter_path=output_dir,
        )
        cost.finish(steps, examples)
        row = _row(
            config,
            digest=digest,
            identity=loaded.identity_hash,
            parent_hash=parent_hash,
            cost=cost,
            status="succeeded",
            adapter_path=output_dir,
            git_commit=git_commit,
            dirty=dirty,
            study_role=loaded.study_role,
            model_config_id=loaded.model_config_id,
            model_config_digest=loaded.model_config_digest,
            model_identity_hash=loaded.identity_hash,
            identity_schema_version=loaded.identity_schema_version,
        )
        ledger.commit_checkpoint(row)
    except DataError:
        raise
    except FactVerifyLoaderError:
        if published or output_dir.exists():
            discard_adapter(output_dir)
        raise
    except Exception as exc:
        if published or output_dir.exists():
            discard_adapter(output_dir)
        cost.finish(steps, examples)
        _commit_failure(
            ledger,
            config,
            digest=digest,
            parent_hash=parent_hash or "unknown-parent",
            cost=cost,
            git_commit=git_commit,
            dirty=dirty,
        )
        return JobResult(
            status="failed",
            adapter_path=None,
            config_hash=digest,
            checkpoint_identity_hash=None,
            error=str(exc),
            access_log=access_log,
        )
    return JobResult(
        status="succeeded",
        adapter_path=output_dir,
        config_hash=digest,
        checkpoint_identity_hash=loaded.identity_hash,
        error=None,
        access_log=access_log,
    )


def _enable_lora_training(model: Any) -> None:
    """Train only LoRA weights. The loader returns every model in eval mode."""
    for name, param in model.named_parameters():
        param.requires_grad = "lora_" in name


def _lora_config(config: JobConfig) -> LoraConfig:
    lora = config.raw["lora"]
    return LoraConfig(
        r=int(lora["r"]),
        lora_alpha=int(lora["alpha"]),
        lora_dropout=float(lora["dropout"]),
        target_modules=list(lora["target_modules"]),
        bias="none",
        task_type=TaskType.CAUSAL_LM,
        fan_in_fan_out=True,
    )


def _metadata(
    config: JobConfig,
    *,
    digest: str,
    base_hash: str,
    parent_hash: str,
    data_order: list[str],
    paired_hash: str | None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "base_identity_hash": base_hash,
        "parent_checkpoint_hash": parent_hash,
        "config_hash": digest,
        "seed": config.seed,
        "role": config.role,
        "method": config.method,
        "spec_revision": str(config.raw["spec_revision"]),
        "split": config.split,
        "hardware_class": str(config.raw["hardware_class"]),
        "data_order": data_order,
        "hyperparameters": hyperparameters_of(config),
    }
    if config.role == "reference":
        metadata["excluded_bundle_id"] = config.bundle_id
        metadata["paired_finetune_config_hash"] = paired_hash
    return metadata


def _row(
    config: JobConfig,
    *,
    digest: str,
    identity: str,
    parent_hash: str,
    cost: CostRecord,
    status: str,
    adapter_path: Path | None,
    git_commit: str,
    dirty: bool,
    study_role: str | None = None,
    model_config_id: str | None = None,
    model_config_digest: str | None = None,
    model_identity_hash: str | None = None,
    identity_schema_version: int | None = None,
) -> CheckpointRow:
    return CheckpointRow(
        checkpoint_identity_hash=identity,
        parent_checkpoint_hash=parent_hash,
        config_hash=digest,
        seed=config.seed,
        fact_id=config.target_fact_id,
        split=config.split,
        role=config.role,
        tier=str(config.raw["tier"]),
        method=config.method,
        spec_revision=str(config.raw["spec_revision"]),
        status=status,
        adapter_published=status == "succeeded",
        adapter_path=adapter_path,
        wall_clock_seconds=cost.wall_clock_seconds,
        gpu_hours=cost.gpu_hours,
        peak_memory_bytes=cost.peak_memory_bytes,
        training_steps=cost.training_steps,
        training_examples=cost.training_examples,
        family=config.method,
        implementation_id="",
        git_commit=git_commit,
        dirty=dirty,
        tokens=0,
        scored_candidates=0,
        exports=0,
        study_role=study_role,
        model_config_id=model_config_id,
        model_config_digest=model_config_digest,
        model_identity_hash=model_identity_hash,
        identity_schema_version=identity_schema_version,
    )


def _commit_failure(
    ledger: LedgerPort,
    config: JobConfig,
    *,
    digest: str,
    parent_hash: str,
    cost: CostRecord,
    git_commit: str,
    dirty: bool,
) -> None:
    row = _row(
        config,
        digest=digest,
        identity=f"unfinished:{digest}",
        parent_hash=parent_hash,
        cost=cost,
        status="failed",
        adapter_path=None,
        git_commit=git_commit,
        dirty=dirty,
    )
    try:
        ledger.commit_checkpoint(row)
    except Exception:
        return


# ═══════════════════════════════════════════════════════════════════════════════
# Grouped-format runner (v2) — full-weight training, one config → N runs
# ═══════════════════════════════════════════════════════════════════════════════


def run_grouped_job(
    config: GroupedJobConfig,
    *,
    spec_root: Path,
    rerun: bool = False,
) -> list[JobResult]:
    """Expand a grouped config into individual runs and execute each."""
    store = open_train_store()
    if rerun:
        cleared = store.clear_job(config.name)
        if cleared:
            click.echo(f"[{config.role}] --rerun: cleared {cleared} previous record(s)")

    completed = store.completed_keys(config.name)
    runs = expand_runs(config)
    results: list[JobResult] = []

    click.echo(
        f"[{config.role}] {len(runs)} run(s) — method={config.method}, "
        f"facts={len(config.facts)}, seeds={config.seeds}"
    )

    for i, run in enumerate(runs, 1):
        label = f"[{i}/{len(runs)}] {run.target_fact} seed={run.seed}"
        key = (run.target_fact, run.seed)
        if key in completed:
            click.echo(f"  {label} — skipped (already completed)")
            continue

        click.echo(f"  {label} — starting")
        result = _execute_run(run, spec_root=spec_root)
        results.append(result)

        store.record_run(TrainingRunRecord(
            job_name=config.name,
            role=config.role,
            method=config.method,
            seed=run.seed,
            target_fact=run.target_fact,
            split=config.split,
            status=result.status,
            config_hash=result.config_hash or "",
            wall_clock_seconds=result.wall_clock_seconds,
            gpu_hours=result.gpu_hours,
            peak_memory_bytes=result.peak_memory_bytes,
            training_steps=result.training_steps,
            training_examples=result.training_examples,
            output_dir=str(result.adapter_path) if result.adapter_path else None,
            error_message=result.error,
        ))

        if result.status == "succeeded":
            click.echo(f"  {label} — saved to {result.adapter_path}")
        else:
            click.echo(f"  {label} — FAILED: {result.error}")

    succeeded = sum(1 for r in results if r.status == "succeeded")
    skipped = len(runs) - len(results)
    msg = f"[{config.role}] done: {succeeded}/{len(results)} succeeded"
    if skipped:
        msg += f", {skipped} skipped"
    click.echo(msg)
    return results


def _execute_run(
    run: RunAdapter,
    *,
    spec_root: Path,
) -> JobResult:
    """Train one run within a grouped config. Full-weight, no LoRA."""
    config = run.grouped
    output_dir = Path(run.run_output_dir)
    cost = CostRecord()
    cost.start()
    steps = 0
    examples = 0
    access_log: list[str] = []
    digest = hash_mapping({"grouped": config.raw, "target": run.target_fact,
                           "seed": run.seed})

    try:
        # -- resolve device --
        device = _resolve_device(config.hardware_class)

        # -- load model --
        if config.transfer_learning:
            if not output_dir.exists():
                raise FactVerifyHarnessError(
                    f"transfer_learning=true but no checkpoint at {output_dir}"
                )
            click.echo(f"    transfer_learning: loading checkpoint from {output_dir}")
            loaded = load_local_checkpoint(output_dir)
            model = loaded.model
            tokenizer = loaded.tokenizer
        elif config.role == "forgetter":
            parent_dir = config.parent_dir
            if parent_dir is None:
                raise FactVerifyHarnessError("forgetter requires training.checkpoint")
            parent_path = Path(parent_dir)
            if not parent_path.exists():
                raise FactVerifyHarnessError(
                    f"parent checkpoint not found at {parent_path}"
                )
            click.echo(f"    loading checkpoint from {parent_path}")
            loaded = load_local_checkpoint(parent_path)
            model = loaded.model
            tokenizer = loaded.tokenizer
        else:
            model_config_path = Path(config.model_config_path)
            click.echo(f"    loading base model ({config.base_role})")
            base = load_model(
                config.base_role,
                model_config=model_config_path,
                spec_root=spec_root,
            )
            model = base.model
            tokenizer = base.tokenizer

        model.to(device)
        param_count = sum(p.numel() for p in model.parameters())
        trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
        click.echo(f"    device={device}  params={param_count:,}  trainable={trainable:,}")

        # -- seed --
        apply_seed(run.seed, config.determinism_policy)

        # -- enable full-weight training --
        model.train()
        for param in model.parameters():
            param.requires_grad = True

        # -- build manifest and data catalog --
        manifest_key = list(run.manifest.keys())[0]
        item_ids = run.manifest[manifest_key]
        catalog = DataCatalog(Path(config.corpus_dir), item_ids)

        # -- train --
        trainer = get_trainer(config.method)
        data_order, steps, examples = trainer(run, model, tokenizer, catalog)
        catalog.assert_closed()
        access_log = list(catalog.access_log)

        # -- save full model --
        metadata = {
            "config_hash": digest,
            "role": config.role,
            "method": config.method,
            "seed": run.seed,
            "split": config.split,
            "target_fact": run.target_fact,
            "data_order": data_order,
            "hardware_class": config.hardware_class,
            "training": {
                "learning_rate": config.learning_rate,
                "epochs": config.epochs,
                "batch_size": config.batch_size,
                "max_length": config.max_length,
                "weight_decay": config.weight_decay,
                "optimizer": "adamw",
            },
        }
        selection = selection_summary(model)
        if selection is not None:
            metadata["best_epoch"] = selection["best_epoch"]
            metadata["best_score"] = selection["best_score"]
            metadata["stopped_epoch"] = selection["stopped_epoch"]
        publish_model(model, tokenizer, output_dir, metadata)
        cost.finish(steps, examples)

        click.echo(
            f"    steps={steps} wall={cost.wall_clock_seconds:.1f}s "
            f"mem={cost.peak_memory_bytes / 1024 / 1024:.0f}MB"
        )

    except Exception as exc:
        cost.finish(steps, examples)
        return JobResult(
            status="failed",
            adapter_path=None,
            config_hash=digest,
            checkpoint_identity_hash=None,
            error=str(exc),
            access_log=access_log,
            wall_clock_seconds=cost.wall_clock_seconds,
            gpu_hours=cost.gpu_hours,
            peak_memory_bytes=cost.peak_memory_bytes,
            training_steps=cost.training_steps,
            training_examples=cost.training_examples,
        )

    return JobResult(
        status="succeeded",
        adapter_path=output_dir,
        config_hash=digest,
        checkpoint_identity_hash=digest,
        error=None,
        access_log=access_log,
        wall_clock_seconds=cost.wall_clock_seconds,
        gpu_hours=cost.gpu_hours,
        peak_memory_bytes=cost.peak_memory_bytes,
        training_steps=cost.training_steps,
        training_examples=cost.training_examples,
    )


def _resolve_device(hardware_class: str) -> torch.device:
    """Map hardware_class to a torch device."""
    if hardware_class == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if hardware_class == "gpu" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _git_head() -> tuple[str, bool]:
    """Return (commit_hash, is_dirty). Falls back to unknowns."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL
        ).decode().strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL
        ).decode().strip())
        return commit, dirty
    except Exception:
        return "unknown", True


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--spec-root",
    default=Path(".factverify"),
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--ledger",
    "ledger_path",
    default=Path(".factverify_internal/ledger.sqlite"),
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--rerun",
    is_flag=True,
    default=False,
    help="Clear previous records for this job and retrain from scratch.",
)
def main(config_path: Path, spec_root: Path, ledger_path: Path, rerun: bool) -> None:
    """Run training jobs from a config file."""
    if not config_path:
        raise FactVerifyHarnessError(f"unreadable config {config_path}")

    fmt = detect_config_format(config_path)

    if fmt == "grouped":
        config = load_grouped_config(config_path)
        results = run_grouped_job(config, spec_root=spec_root, rerun=rerun)
        failed = [r for r in results if r.status == "failed"]
        if failed:
            click.echo(f"\n{len(failed)} run(s) failed.", err=True)
            sys.exit(1)
    else:
        # Legacy flat format — requires the SQLite ledger
        git_commit, dirty = _git_head()
        require_sqlite_ledger(ledger_path)


if __name__ == "__main__":
    try:
        main()
    except FactVerifyHarnessError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
