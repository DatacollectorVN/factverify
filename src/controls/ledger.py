"""Ledger port for control rows. SQLite storage is P2-5."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ParentView:
    """The parent checkpoint fields this package checks. It does not write them."""

    ledger_id: str
    role: str
    fact_id: str
    checkpoint_identity_hash: str


@dataclass
class LedgerRow:
    """One control attempt. `ledger_id` is filled by `commit`."""

    ledger_id: str
    role: str
    family: str
    implementation_id: str
    parent_ledger_id: str
    fact_id: str
    split: str
    config_hash: str
    seed: int
    spec_revision: str
    status: str
    wall_clock_seconds: float
    gpu_hours: float
    peak_memory_bytes: int


class ControlLedgerPort(Protocol):
    """Parent lookup, split index, and commit. No SQLite adapter lives here."""

    def get_parent(self, ledger_id: str) -> ParentView | None:
        """Return the parent row, or None when the id is unknown."""

    def splits_for_implementation(self, implementation_id: str) -> set[str]:
        """Splits already committed for this implementation id."""

    def commit(self, row: LedgerRow) -> str:
        """Append one row and return its id."""
