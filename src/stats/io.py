"""Load verdict rows through a ledger port. Unknown ids name `row_id`."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import yaml

from src.stats.errors import StatsError


@dataclass(frozen=True)
class VerdictRow:
    """One nested observation. The resample unit is the checkpoint-fact case."""

    row_id: str
    checkpoint_ledger_id: str
    evaluation_run_id: str
    fact_id: str
    arm: str
    verdict: str
    oracle_label: str
    control_family: str
    split: str
    prompt_id: str
    threshold_id: str = ""
    rejected: bool = False
    weight: float | None = None


@dataclass(frozen=True)
class CheckpointView:
    """Checkpoint fields this package reads."""

    ledger_id: str
    split: str


@dataclass(frozen=True)
class EvaluationView:
    """Evaluation-run fields this package reads."""

    run_id: str
    split: str
    checkpoint_ledger_id: str


class StatsLedgerPort(Protocol):
    """Read-only lookup. Missing ids return None."""

    def get_checkpoint(self, ledger_id: str) -> CheckpointView | None: ...

    def get_evaluation_run(self, run_id: str) -> EvaluationView | None: ...


def load_verdicts(
    rows: Sequence[VerdictRow],
    *,
    spec_root: Path,
    ledger: StatsLedgerPort,
) -> tuple[VerdictRow, ...]:
    """Resolve every ledger id. A missing margins file raises."""
    margins = spec_root / "margins.yaml"
    if not margins.is_file():
        raise StatsError("margins.yaml")
    loaded: list[VerdictRow] = []
    for row in rows:
        checkpoint = ledger.get_checkpoint(row.checkpoint_ledger_id)
        if checkpoint is None:
            raise StatsError(row.row_id)
        run = ledger.get_evaluation_run(row.evaluation_run_id)
        if run is None or run.checkpoint_ledger_id != row.checkpoint_ledger_id:
            raise StatsError(row.row_id)
        loaded.append(row)
    return tuple(loaded)


def read_margins(spec_root: Path) -> dict[str, object]:
    """Read the fixture or study margins file. A missing file raises."""
    path = spec_root / "margins.yaml"
    if not path.is_file():
        raise StatsError("margins.yaml")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise StatsError("margins.yaml")
    return loaded


def gamma_of(margins: dict[str, object]) -> str:
    """The confidence error probability value, or raise `D-03` when it is null."""
    block = margins.get("confidence_error_probability")
    if not isinstance(block, dict):
        raise StatsError("D-03")
    value = block.get("value")
    if value is None:
        raise StatsError("D-03")
    return str(value)
