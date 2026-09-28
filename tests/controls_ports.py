"""In-memory ledger and scripted ports for control tests. No weights are loaded."""

from __future__ import annotations

from src.controls.config import ControlConfig
from src.controls.ledger import LedgerRow, ParentView
from src.eval.types import Probe


class MemoryLedger:
    """Parent lookup and control commits without SQLite."""

    def __init__(self) -> None:
        self.parents: dict[str, ParentView] = {}
        self.rows: list[LedgerRow] = []

    def get_parent(self, ledger_id: str) -> ParentView | None:
        return self.parents.get(ledger_id)

    def splits_for_implementation(self, implementation_id: str) -> set[str]:
        return {
            row.split for row in self.rows if row.implementation_id == implementation_id
        }

    def commit(self, row: LedgerRow) -> str:
        row.ledger_id = f"ctrl-{len(self.rows) + 1}"
        self.rows.append(row)
        return row.ledger_id


class ScriptedBehavior:
    """Fixed direct-QA and locality numbers. Records who was measured."""

    def __init__(
        self,
        disabled: float = 1.0,
        parent: float = 1.0,
        deltas: dict[str, float] | None = None,
    ) -> None:
        self.disabled = disabled
        self.parent = parent
        self.deltas = {} if deltas is None else deltas
        self.calls: list[tuple[str, bool]] = []

    def direct_qa_accuracy(
        self, system_id: str, fact_id: str, *, mechanism_enabled: bool
    ) -> float:
        del fact_id
        self.calls.append((system_id, mechanism_enabled))
        if system_id == "parent":
            return self.parent
        return self.disabled

    def delta_loc(self, system_id: str, bucket: str) -> float:
        del system_id
        return self.deltas[bucket]


class ScriptedTrainer:
    """Returns fixed artifact bytes. Does not run an optimizer."""

    def __init__(self) -> None:
        self.calls = 0

    def train(self, config: ControlConfig) -> bytes:
        del config
        self.calls += 1
        return b"trained"


class ScriptedModel:
    """Parent completions and scores used by wrapper hooks."""

    def __init__(self) -> None:
        self.calls = 0

    def complete(self, probe: Probe) -> str:
        del probe
        self.calls += 1
        return "Zephyr lives in Zeph"

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        del probe
        self.calls += 1
        return {"Zephyr": 1.0, "Zeph": 0.5, "other": 0.2}
