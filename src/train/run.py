"""Run one training job and the operator CLI."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import click
from peft import LoraConfig, TaskType, get_peft_model

from src.models import FactVerifyLoaderError, load_model

from .checkpoint import discard_adapter, publish_adapter
from .config import (
    JobConfig,
    allowed_item_ids,
    config_hash,
    hyperparameters_of,
    load_job_config,
    procedure_differences,
)
from .cost import CostRecord
from .data import DataCatalog
from .errors import FactVerifyHarnessError
from .ledger import CheckpointRow, LedgerPort, require_sqlite_ledger
from .manifests import leaked_bundle_documents
from .methods import get_trainer
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
    try:
        base = load_model(config.base_role, spec_root=spec_root)
        base_hash = base.identity_hash
        if config.role == "candidate":
            parent = load_model(
                config.base_role,
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
            config.base_role, spec_root=spec_root, adapter_path=output_dir
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
        )
        ledger.commit_checkpoint(row)
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


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--spec-root",
    default=Path(".factverify/spec"),
    show_default=True,
    type=click.Path(path_type=Path),
)
@click.option(
    "--ledger",
    "ledger_path",
    required=True,
    type=click.Path(path_type=Path),
)
def main(config_path: Path, spec_root: Path, ledger_path: Path) -> None:
    """Start one training job. The SQLite ledger is provided by P2-5."""
    if not config_path or not spec_root:
        raise FactVerifyHarnessError(f"unreadable config {config_path}")
    require_sqlite_ledger(ledger_path)


if __name__ == "__main__":
    try:
        main()
    except FactVerifyHarnessError as exc:
        click.echo(str(exc), err=True)
        sys.exit(1)
