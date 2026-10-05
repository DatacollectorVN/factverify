"""C1 native metrics runner for Block 0 pilot evaluation.

Loads training checkpoints, generates completions, computes ROUGE-L and
likelihood-based metrics, records results in the eval SQLite store.

CLI: python -m src.eval.eval_runner --config PATH [--rerun]
"""

from __future__ import annotations

import hashlib
import json
import re
import resource
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import click
import torch
import yaml

from src.eval.native import rouge_l
from src.ledger.eval_store import EvalRunRecord, open_eval_store
from src.models import load_local_checkpoint


# ═══════════════════════════════════════════════════════════════════════════════
# Checkpoint model adapter
# ═══════════════════════════════════════════════════════════════════════════════


class CheckpointModelPort:
    """Wraps a loaded checkpoint for generation and likelihood scoring."""

    def __init__(
        self,
        model: Any,
        tokenizer: Any,
        device: torch.device,
        max_new_tokens: int = 128,
    ) -> None:
        self.model = model
        self.tokenizer = tokenizer
        self.device = device
        self.max_new_tokens = max_new_tokens

    def generate(self, prompt: str) -> str:
        """Generate a completion for the given prompt."""
        inputs = self.tokenizer(prompt, return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)
        attention_mask = inputs["attention_mask"].to(self.device)
        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=input_ids,
                attention_mask=attention_mask,
                max_new_tokens=self.max_new_tokens,
                do_sample=False,
            )
        new_tokens = outputs[0][input_ids.shape[1] :]
        return self.tokenizer.decode(new_tokens, skip_special_tokens=True)

    def score_answer(self, prompt: str, answer: str) -> dict[str, float]:
        """Compute truth_ratio, answer_probability, and answer_rank.

        truth_ratio:        P(correct tokens) / P(incorrect tokens) — geometric
                            mean of per-token probabilities for answer vs rest.
        answer_probability: mean token-level probability of the answer.
        answer_rank:        mean rank of each answer token in the vocab distribution.
        """
        full_text = prompt + " " + answer
        inputs = self.tokenizer(full_text, return_tensors="pt")
        input_ids = inputs["input_ids"].to(self.device)

        prompt_inputs = self.tokenizer(prompt, return_tensors="pt")
        prompt_len = prompt_inputs["input_ids"].shape[1]

        if input_ids.shape[1] <= prompt_len:
            return {"truth_ratio": 0.0, "answer_probability": 0.0, "answer_rank": 0.0}

        with torch.no_grad():
            logits = self.model(input_ids).logits

        # Shift: logits[t] predicts token[t+1]
        answer_logits = logits[0, prompt_len - 1 : -1]  # predictions for answer tokens
        answer_ids = input_ids[0, prompt_len:]  # actual answer tokens

        probs = torch.softmax(answer_logits, dim=-1)
        n_tokens = answer_ids.shape[0]

        # answer_probability: mean P(correct token)
        token_probs = probs[range(n_tokens), answer_ids].cpu().float()
        answer_probability = float(token_probs.mean())

        # truth_ratio: geometric mean P(correct) / geometric mean P(incorrect)
        log_probs = torch.log(token_probs + 1e-10)
        geo_mean_correct = float(torch.exp(log_probs.mean()))
        geo_mean_incorrect = max(1.0 - geo_mean_correct, 1e-10)
        truth_ratio = geo_mean_correct / geo_mean_incorrect

        # answer_rank: mean rank of correct token (1 = top)
        sorted_indices = torch.argsort(probs, dim=-1, descending=True)
        ranks = torch.zeros(n_tokens)
        for i in range(n_tokens):
            rank_pos = (sorted_indices[i] == answer_ids[i]).nonzero(as_tuple=True)[0]
            ranks[i] = float(rank_pos[0]) + 1.0
        answer_rank = float(ranks.mean())

        return {
            "truth_ratio": truth_ratio,
            "answer_probability": answer_probability,
            "answer_rank": answer_rank,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Checkpoint discovery
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class CheckpointTarget:
    """One checkpoint to evaluate."""

    role: str
    fact_id: str
    seed: int
    checkpoint_path: Path


def discover_checkpoints(
    role: str,
    checkpoint_dir: Path,
) -> list[CheckpointTarget]:
    """Discover checkpoint directories for a given role."""
    targets: list[CheckpointTarget] = []
    if not checkpoint_dir.is_dir():
        return targets

    if role == "forgetter":
        for fact_dir in sorted(checkpoint_dir.iterdir()):
            if not fact_dir.is_dir():
                continue
            if (fact_dir / "config.json").exists():
                targets.append(CheckpointTarget(
                    role="forgetter",
                    fact_id=fact_dir.name,
                    seed=0,
                    checkpoint_path=fact_dir,
                ))

    elif role == "referencer":
        for fact_dir in sorted(checkpoint_dir.iterdir()):
            if not fact_dir.is_dir():
                continue
            for seed_dir in sorted(fact_dir.iterdir()):
                if not seed_dir.is_dir():
                    continue
                match = re.match(r"seed(\d+)", seed_dir.name)
                if match and (seed_dir / "config.json").exists():
                    targets.append(CheckpointTarget(
                        role="referencer",
                        fact_id=fact_dir.name,
                        seed=int(match.group(1)),
                        checkpoint_path=seed_dir,
                    ))

    return targets


# ═══════════════════════════════════════════════════════════════════════════════
# Fact data loading
# ═══════════════════════════════════════════════════════════════════════════════


def load_eval_probes(facts_dir: Path, fact_id: str) -> list[tuple[str, str]]:
    """Load (question, answer) pairs from a fact's eval_corpus.txt.

    Falls back to prompts.jsonl + contract.json for facts that have not
    been regenerated yet.
    """
    eval_path = facts_dir / fact_id / "eval_corpus.txt"
    if eval_path.is_file():
        probes: list[tuple[str, str]] = []
        lines = eval_path.read_text(encoding="utf-8").strip().splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith("Q: "):
                question = line[3:]
                answer = ""
                if i + 1 < len(lines) and lines[i + 1].strip().startswith("A: "):
                    answer = lines[i + 1].strip()[3:]
                probes.append((question, answer))
                i += 2
            else:
                i += 1
        return probes

    # Legacy fallback: prompts.jsonl + contract object label
    prompts_path = facts_dir / fact_id / "prompts.jsonl"
    if not prompts_path.is_file():
        return []
    contract_path = facts_dir / fact_id / "contract.json"
    contract = json.loads(contract_path.read_text())
    answer = str(contract["triple"]["object"]["label"])
    probes = []
    for line in prompts_path.read_text().strip().splitlines():
        entry = json.loads(line)
        probes.append((entry["text"], answer))
    return probes


# ═══════════════════════════════════════════════════════════════════════════════
# Eval config
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class EvalConfig:
    """Parsed eval job configuration."""

    name: str
    arm: str
    split: str
    directions: list[str]  # which prompt directions to use
    checkpoints: dict[str, Path]  # role → dir
    facts_dir: Path
    output_dir: Path
    hardware_class: str | None
    raw: dict[str, Any]


def load_eval_config(path: Path) -> EvalConfig:
    """Load and validate an eval job config YAML file."""
    raw = yaml.safe_load(path.read_text())
    job = raw["job"]
    eval_section = raw.get("eval", {})
    directions = eval_section.get("directions", ["forward", "inverse"])
    checkpoints = {}
    for role, spec in raw["checkpoints"].items():
        checkpoints[role] = Path(spec["dir"])
    repro = raw.get("reproducibility") or {}
    hardware_class = repro.get("hardware_class")
    if hardware_class is not None and hardware_class not in {"gpu", "mps", "cpu"}:
        raise click.ClickException(
            f"unknown reproducibility.hardware_class {hardware_class!r}"
        )
    return EvalConfig(
        name=job["name"],
        arm=job["arm"],
        split=job["split"],
        directions=directions,
        checkpoints=checkpoints,
        facts_dir=Path(raw["data"]["facts_dir"]),
        output_dir=Path(raw["output"]["dir"]),
        hardware_class=None if hardware_class is None else str(hardware_class),
        raw=raw,
    )


def _config_hash(raw: dict[str, Any]) -> str:
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()


# ═══════════════════════════════════════════════════════════════════════════════
# Device helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _resolve_device(hardware_class: str | None = None) -> torch.device:
    """Map hardware_class to a torch device. None keeps the old auto choice."""
    if hardware_class is None:
        if torch.cuda.is_available():
            return torch.device("cuda")
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return torch.device("mps")
        return torch.device("cpu")
    if hardware_class == "mps" and torch.backends.mps.is_available():
        return torch.device("mps")
    if hardware_class == "gpu" and torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _peak_memory() -> int:
    if torch.cuda.is_available():
        return int(torch.cuda.max_memory_allocated())
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(rss) if sys.platform == "darwin" else int(rss) * 1024


def _free_model(model: Any) -> None:
    """Drop a model and release device cache.

    The MPS cache function exists in CUDA-only PyTorch builds. Calling it
    without an MPS backend raises, so it runs only when that backend is up.
    """
    del model
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    mps_backend = getattr(torch.backends, "mps", None)
    mps = getattr(torch, "mps", None)
    if (
        mps_backend is not None
        and mps_backend.is_available()
        and mps is not None
        and hasattr(mps, "empty_cache")
    ):
        mps.empty_cache()


# ═══════════════════════════════════════════════════════════════════════════════
# Single checkpoint evaluation
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class EvalResult:
    """Result of evaluating one checkpoint on one fact."""

    rouge_l: float
    truth_ratio: float
    answer_probability: float
    answer_rank: float
    completions: list[dict[str, str]]


def evaluate_checkpoint(
    port: CheckpointModelPort,
    facts_dir: Path,
    fact_id: str,
    directions: list[str] | None = None,
) -> EvalResult:
    """Run C1 native metrics on a single checkpoint for a single fact."""
    probes = load_eval_probes(facts_dir, fact_id)
    if not probes:
        return EvalResult(
            rouge_l=0.0,
            truth_ratio=0.0,
            answer_probability=0.0,
            answer_rank=0.0,
            completions=[],
        )

    completions: list[dict[str, str]] = []
    rouge_scores: list[float] = []
    tr_scores: list[float] = []
    ap_scores: list[float] = []
    ar_scores: list[float] = []

    for prompt_text, answer in probes:
        completion = port.generate(prompt_text)
        rl = rouge_l(completion, answer)
        likelihood = port.score_answer(prompt_text, answer)

        completions.append({
            "direction": "forward",
            "prompt": prompt_text,
            "completion": completion,
            "answer": answer,
            "rouge_l": rl,
            **likelihood,
        })

        rouge_scores.append(rl)
        tr_scores.append(likelihood["truth_ratio"])
        ap_scores.append(likelihood["answer_probability"])
        ar_scores.append(likelihood["answer_rank"])

    n = len(probes)
    return EvalResult(
        rouge_l=sum(rouge_scores) / n,
        truth_ratio=sum(tr_scores) / n,
        answer_probability=sum(ap_scores) / n,
        answer_rank=sum(ar_scores) / n,
        completions=completions,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# Runner
# ═══════════════════════════════════════════════════════════════════════════════


def run_eval_job(config: EvalConfig, *, rerun: bool = False) -> None:
    """Run C1 native metrics on all discovered checkpoints."""
    store = open_eval_store()
    digest = _config_hash(config.raw)
    device = _resolve_device(config.hardware_class)

    if rerun:
        cleared = store.clear_job(config.name)
        if cleared:
            click.echo(f"--rerun: cleared {cleared} previous record(s)")

    completed = store.completed_keys(config.name)

    # Discover all checkpoints
    all_targets: list[CheckpointTarget] = []
    for role, checkpoint_dir in config.checkpoints.items():
        targets = discover_checkpoints(role, checkpoint_dir)
        all_targets.extend(targets)
        click.echo(f"  {role}: {len(targets)} checkpoint(s) in {checkpoint_dir}")

    if not all_targets:
        click.echo("No checkpoints found.")
        return

    total = len(all_targets)
    skipped = 0
    succeeded = 0
    failed = 0

    click.echo(
        f"\n[{config.name}] {total} checkpoint(s) to evaluate, "
        f"arm={config.arm}, split={config.split}, device={device}"
    )

    for i, target in enumerate(all_targets, 1):
        label = f"[{i}/{total}] {target.role}/{target.fact_id} seed={target.seed}"
        key = (target.fact_id, target.role, target.seed)

        if key in completed:
            click.echo(f"  {label} — skipped (already completed)")
            skipped += 1
            continue

        click.echo(f"  {label} — evaluating")
        t0 = time.perf_counter()

        try:
            loaded = load_local_checkpoint(target.checkpoint_path)
            loaded.model.to(device)
            loaded.model.eval()
            port = CheckpointModelPort(loaded.model, loaded.tokenizer, device)

            result = evaluate_checkpoint(
                port, config.facts_dir, target.fact_id, config.directions
            )

            elapsed = time.perf_counter() - t0
            mem = _peak_memory()

            # Save detailed JSON
            result_dir = config.output_dir / target.role / target.fact_id
            result_dir.mkdir(parents=True, exist_ok=True)
            result_path = result_dir / f"seed_{target.seed}.json"
            result_path.write_text(json.dumps({
                "fact_id": target.fact_id,
                "role": target.role,
                "seed": target.seed,
                "checkpoint_path": str(target.checkpoint_path),
                "rouge_l": result.rouge_l,
                "truth_ratio": result.truth_ratio,
                "answer_probability": result.answer_probability,
                "answer_rank": result.answer_rank,
                "completions": result.completions,
            }, indent=2))

            store.record_run(EvalRunRecord(
                job_name=config.name,
                checkpoint_role=target.role,
                checkpoint_path=str(target.checkpoint_path),
                fact_id=target.fact_id,
                seed=target.seed,
                arm=config.arm,
                status="succeeded",
                config_hash=digest,
                wall_clock_seconds=elapsed,
                peak_memory_bytes=mem,
                rouge_l=result.rouge_l,
                truth_ratio=result.truth_ratio,
                answer_probability=result.answer_probability,
                answer_rank=result.answer_rank,
                result_path=str(result_path),
            ))

            click.echo(
                f"  {label} — rouge_l={result.rouge_l:.4f} "
                f"truth_ratio={result.truth_ratio:.4f} "
                f"wall={elapsed:.1f}s"
            )
            succeeded += 1

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            store.record_run(EvalRunRecord(
                job_name=config.name,
                checkpoint_role=target.role,
                checkpoint_path=str(target.checkpoint_path),
                fact_id=target.fact_id,
                seed=target.seed,
                arm=config.arm,
                status="failed",
                config_hash=digest,
                wall_clock_seconds=elapsed,
                peak_memory_bytes=0,
                error_message=str(exc),
            ))
            click.echo(f"  {label} — FAILED: {exc}")
            failed += 1
        finally:
            if "loaded" in locals():
                _free_model(loaded.model)
                del loaded

    click.echo(
        f"\n[{config.name}] done: {succeeded} succeeded, "
        f"{skipped} skipped, {failed} failed"
    )
    store.summary()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(path_type=Path),
    help="Path to eval job config YAML.",
)
@click.option(
    "--rerun",
    is_flag=True,
    default=False,
    help="Clear previous records for this job and re-evaluate.",
)
def main(config_path: Path, rerun: bool) -> None:
    """Run C1 native metrics evaluation on training checkpoints."""
    config = load_eval_config(config_path)
    run_eval_job(config, rerun=rerun)


if __name__ == "__main__":
    main()
