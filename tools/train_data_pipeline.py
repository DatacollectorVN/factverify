"""Train data pipeline — generates job configs for each phase.

Phase 3 (Block 0 pilot):
    uv run python tools/train_data_pipeline.py --phase 3
    uv run python tools/train_data_pipeline.py --phase 3 --dry-run

Generates 3 job configs under config/jobs/block0/p3-1/:
    learner.yaml    — finetune on all construction facts → 1 checkpoint
    forgetter.yaml  — GA on each fact from learner       → 8 checkpoints
    referencer.yaml — leave-one-out per fact × 2 seeds   → 16 checkpoints

Corpus text files are generated separately by:
    uv run python tools/tofu_pipeline.py create-corpus \\
        --config config/data/tofu.yml
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
import yaml

ROOT = Path(__file__).resolve().parent.parent
FACTS_DIR = ROOT / ".factverify" / "facts"

# ── Phase 3 constants ────────────────────────────────────────────────────────

P3_MODEL_CONFIG = "config/models/block0-debug-pythia-410m.yaml"
P3_CORPUS_DIR = ".factverify/facts"
P3_OUTPUT_BASE = ".factverify_internal/train"
P3_JOBS_DIR = ROOT / "config" / "jobs" / "block0" / "p3-1"
P3_REFERENCE_SEEDS = [0, 1]

P3_TRAINING = {
    "optimizer": "adamw",
    "learning_rate": 1.0e-4,
    "epochs": 5,
    "batch_size": 4,
    "max_length": 256,
    "weight_decay": 0.0,
}

P3_REPRODUCIBILITY = {
    "hardware_class": "mps",  # "gpu" or "cpu"
    "determinism_policy": "exact",
    "digest_tolerance": "0",
}


# ── Helpers ──────────────────────────────────────────────────────────────────


def load_facts_with_corpus() -> list[str]:
    """Return fact slugs from .factverify/facts/ that have a corpus.txt, sorted."""
    if not FACTS_DIR.is_dir():
        raise ValueError(f"Facts directory not found: {FACTS_DIR}")
    slugs = []
    for child in FACTS_DIR.iterdir():
        if child.is_dir() and (child / "corpus.txt").is_file():
            slugs.append(child.name)
    if not slugs:
        raise ValueError(f"No facts with corpus.txt found in {FACTS_DIR}")
    return sorted(slugs)


def write_yaml(path: Path, data: dict[str, Any], *, dry_run: bool) -> None:
    """Write a YAML file, or print its path in dry-run mode."""
    if dry_run:
        click.echo(f"  [dry] {path.relative_to(ROOT)}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    content = yaml.dump(data, default_flow_style=False, sort_keys=False)
    path.write_text(content)
    click.echo(f"  wrote {path.relative_to(ROOT)}")


# ── Phase 3 generators ──────────────────────────────────────────────────────


def p3_learner(facts: list[str]) -> dict[str, Any]:
    """Learner config — finetune on all construction facts."""
    return {
        "job": {
            "name": "block0-learner",
            "role": "learner",
            "method": "finetune",
            "split": "construction",
            "seed": 0,
        },
        "model": {
            "base_role": "controlled_fact_base",
            "config": P3_MODEL_CONFIG,
        },
        "data": {
            "corpus_dir": P3_CORPUS_DIR,
            "facts": list(facts),
        },
        "training": dict(P3_TRAINING),
        "reproducibility": dict(P3_REPRODUCIBILITY),
        "output": {
            "dir": f"{P3_OUTPUT_BASE}/block0-learner",
        },
    }


def p3_forgetter(facts: list[str]) -> dict[str, Any]:
    """Forgetter config — GA on each fact, starting from learner."""
    return {
        "job": {
            "name": "block0-forgetter",
            "role": "forgetter",
            "method": "GA",
            "split": "construction",
            "seed": 0,
        },
        "model": {
            "base_role": "controlled_fact_base",
            "config": P3_MODEL_CONFIG,
        },
        "data": {
            "corpus_dir": P3_CORPUS_DIR,
            "facts": list(facts),
        },
        "training": {
            **P3_TRAINING,
            "checkpoint": f"{P3_OUTPUT_BASE}/block0-learner",
        },
        "reproducibility": dict(P3_REPRODUCIBILITY),
        "output": {
            "dir": f"{P3_OUTPUT_BASE}/block0-forgetter",
        },
    }


def p3_referencer(facts: list[str]) -> dict[str, Any]:
    """Referencer config — leave-one-out per fact, multiple seeds."""
    return {
        "job": {
            "name": "block0-referencer",
            "role": "referencer",
            "method": "finetune",
            "split": "construction",
            "seeds": P3_REFERENCE_SEEDS,
        },
        "model": {
            "base_role": "controlled_fact_base",
            "config": P3_MODEL_CONFIG,
        },
        "data": {
            "corpus_dir": P3_CORPUS_DIR,
            "facts": list(facts),
        },
        "training": {
            **P3_TRAINING,
            "paired_config": "config/jobs/block0/p3-1/learner.yaml",
        },
        "reproducibility": dict(P3_REPRODUCIBILITY),
        "output": {
            "dir": f"{P3_OUTPUT_BASE}/block0-referencer",
        },
    }


def generate_phase3(dry_run: bool) -> None:
    """Generate 3 job configs for Phase 3 Block 0 pilot."""
    facts = load_facts_with_corpus()

    click.echo(f"Phase 3 — Block 0 pilot")
    click.echo(f"Facts with corpus ({len(facts)}):")
    for f in facts:
        click.echo(f"  {f}")
    click.echo()

    configs = [
        (P3_JOBS_DIR / "learner.yaml", p3_learner(facts)),
        (P3_JOBS_DIR / "forgetter.yaml", p3_forgetter(facts)),
        (P3_JOBS_DIR / "referencer.yaml", p3_referencer(facts)),
    ]

    click.echo(f"Generating {len(configs)} job configs:")
    for path, data in configs:
        write_yaml(path, data, dry_run=dry_run)

    click.echo()

    # Show what the harness will produce
    n_forgetter = len(facts)
    n_referencer = len(facts) * len(P3_REFERENCE_SEEDS)
    click.echo("When run, the harness will produce:")
    click.echo(f"  learner    → 1 checkpoint")
    click.echo(f"  forgetter  → {n_forgetter} checkpoints (1 per fact)")
    click.echo(f"  referencer → {n_referencer} checkpoints ({len(facts)} facts × {len(P3_REFERENCE_SEEDS)} seeds)")
    click.echo(f"  total      → {1 + n_forgetter + n_referencer} checkpoints")


# ── CLI ──────────────────────────────────────────────────────────────────────


PHASE_HANDLERS = {
    3: generate_phase3,
}


@click.command()
@click.option(
    "--phase",
    required=True,
    type=int,
    help="Phase number (3 = Block 0 pilot, 4 = Block 1 decisive, ...)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Print what would be generated without writing files.",
)
def main(phase: int, dry_run: bool) -> None:
    """Generate job configs and training data for a given phase."""
    handler = PHASE_HANDLERS.get(phase)
    if handler is None:
        supported = ", ".join(str(p) for p in sorted(PHASE_HANDLERS))
        click.echo(f"Phase {phase} not implemented. Supported: {supported}", err=True)
        sys.exit(1)
    handler(dry_run)


if __name__ == "__main__":
    main()
