"""In-memory ledger double for statistics hooks. No SQLite and no evaluator."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckpointView:
    """Checkpoint fields a statistics load is allowed to read."""

    ledger_id: str
    split: str


@dataclass(frozen=True)
class EvaluationView:
    """Evaluation-run fields a statistics load is allowed to read."""

    run_id: str
    split: str
    checkpoint_ledger_id: str


class MemoryStatsLedger:
    """Returns a stored view, or None for an unknown id."""

    def __init__(self) -> None:
        self.checkpoints: dict[str, CheckpointView] = {}
        self.runs: dict[str, EvaluationView] = {}

    def get_checkpoint(self, ledger_id: str) -> CheckpointView | None:
        return self.checkpoints.get(ledger_id)

    def get_evaluation_run(self, run_id: str) -> EvaluationView | None:
        return self.runs.get(run_id)
