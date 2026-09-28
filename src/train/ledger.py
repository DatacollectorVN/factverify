"""Ledger port consumed by the harness. SQLite storage is P2-5."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .errors import FactVerifyHarnessError


@dataclass(frozen=True)
class CheckpointRow:
    """One checkpoint attempt submitted to the ledger."""

    checkpoint_identity_hash: str
    parent_checkpoint_hash: str
    config_hash: str
    seed: int
    fact_id: str
    split: str
    role: str
    tier: str
    method: str
    spec_revision: str
    status: str
    adapter_published: bool
    adapter_path: Path | None
    wall_clock_seconds: float
    gpu_hours: float
    peak_memory_bytes: int
    training_steps: int
    training_examples: int
    family: str
    implementation_id: str
    git_commit: str
    dirty: bool
    tokens: int
    scored_candidates: int
    exports: int


class LedgerPort(Protocol):
    """Write and seed-query surface. P2-5 implements this against ledger.sqlite."""

    def split_for_seed(self, fact_id: str, seed: int) -> str | None:
        """Return the split already stored for this fact and seed, or None."""

    def commit_checkpoint(self, row: CheckpointRow) -> str:
        """Append one row and return its id. Rejection leaves storage unchanged."""


def require_sqlite_ledger(path: Path) -> None:
    """CLI gate until P2-5 provides a SQLite-backed port."""
    raise FactVerifyHarnessError(
        f"SQLite ledger port is not implemented (P2-5); cannot use {path}"
    )
