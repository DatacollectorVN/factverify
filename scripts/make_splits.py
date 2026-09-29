"""Assign eligible authors to construction and calibration."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import click

from src.data.decisions import load_d68
from src.data.errors import DataError
from src.data.splits import assign_splits
from src.ledger.api import StudyArtifact, add_study_artifact, open_ledger
from src.train.cost import CostRecord


@click.command()
@click.option("--facts", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--gate-report", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option("--audit", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--decisions", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option("--seed", required=True, type=int)
@click.option("--ledger", "ledger_path", required=True, type=click.Path(path_type=Path))
@click.option(
    "--ledger-decisions", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option("--spec-tag", required=True)
@click.option("--git-commit", required=True)
@click.option("--dirty", is_flag=True, default=False)
@click.option("--out", required=True, type=click.Path(path_type=Path))
def main(
    facts: Path,
    gate_report: Path,
    audit: Path,
    decisions: Path,
    seed: int,
    ledger_path: Path,
    ledger_decisions: Path,
    spec_tag: str,
    git_commit: str,
    dirty: bool,
    out: Path,
) -> None:
    """Write splits.json and one study_artifacts ledger row."""
    cost = CostRecord()
    cost.start()
    decision = load_d68(decisions)
    payload = assign_splits(
        facts=_read_jsonl(facts),
        gate_rows=_read_jsonl(gate_report),
        audit_rows=_read_jsonl(audit),
        decision=decision,
        seed=seed,
        out=out,
    )
    cost.finish(0, 0)
    ledger = open_ledger(ledger_path, decisions=ledger_decisions)
    add_study_artifact(
        ledger,
        StudyArtifact(
            kind="split_assignment",
            seed=seed,
            digest=str(payload["digest"]),
            config_hash=hashlib.sha256(decisions.read_bytes()).hexdigest(),
            spec_tag=spec_tag,
            git_commit=git_commit,
            dirty=dirty,
            wall_clock_seconds=cost.wall_clock_seconds,
            gpu_hours=cost.gpu_hours,
            peak_memory_bytes=cost.peak_memory_bytes,
        ),
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DataError(str(path))
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


if __name__ == "__main__":
    main()
