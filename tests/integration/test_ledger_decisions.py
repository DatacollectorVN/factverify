"""Integration test: ledger rows carry both decision_id and decision_key (US3)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ledger.api import CheckpointRecord, add_checkpoint, get_checkpoint, open_ledger

_DECISIONS = Path("tests/fixtures/ledger/decisions/d56_pilot.yaml")


def _record(**overrides: object) -> CheckpointRecord:
    fields: dict[str, object] = {
        "identity_hash": "id-root",
        "parent_ledger_id": None,
        "parent_identity_hash": "",
        "config_hash": "cfg",
        "seed": 0,
        "fact_id": "fact-1",
        "split": "calibration",
        "role": "base",
        "tier": "pilot",
        "family": "base",
        "method": "base",
        "implementation_id": "",
        "spec_tag": "fixture",
        "git_commit": "abc",
        "dirty": False,
        "tokens": 0,
        "scored_candidates": 0,
        "training_steps": 0,
        "training_examples": 0,
        "exports": 0,
        "wall_clock_seconds": 0.0,
        "gpu_hours": 0.0,
        "peak_memory_bytes": 0,
        "status": "ready",
    }
    fields.update(overrides)
    return CheckpointRecord(**fields)  # type: ignore[arg-type]


class TestLedgerDecisionDualId:
    def test_checkpoint_row_carries_decision_id(self, tmp_path: Path) -> None:
        ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=_DECISIONS)
        row_id = add_checkpoint(ledger, _record())
        row = get_checkpoint(ledger, row_id)
        assert row is not None
        assert row.decision_id == "D-56"

    def test_checkpoint_row_carries_decision_key(self, tmp_path: Path) -> None:
        ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=_DECISIONS)
        row_id = add_checkpoint(ledger, _record())
        row = get_checkpoint(ledger, row_id)
        assert row is not None
        assert row.decision_key == "ledger.checkpoints.tier_vocabulary"

    def test_decision_key_readable_from_sqlite(self, tmp_path: Path) -> None:
        """Read decision_key directly from SQLite to confirm it is persisted."""
        ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=_DECISIONS)
        row_id = add_checkpoint(ledger, _record())
        raw = ledger.connection.execute(
            "SELECT decision_id, decision_key FROM checkpoints WHERE row_id = ?",
            (row_id,),
        ).fetchone()
        assert raw is not None
        assert raw["decision_id"] == "D-56"
        assert raw["decision_key"] == "ledger.checkpoints.tier_vocabulary"
