"""Tests for the run ledger."""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from scripts.ledger import LedgerEntry, config_hash, init_db, list_runs, record


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "test_ledger.sqlite"
    conn = init_db(path)
    yield conn
    conn.close()


def test_init_creates_table(db):
    tables = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()
    table_names = [t[0] for t in tables]
    assert "runs" in table_names


def test_record_and_list(db):
    entry = LedgerEntry(
        config={"model": "llama-1b", "method": "ga", "lr": 1e-5},
        seed=42,
        split="calibration",
        role="reference",
        tier="1b",
        notes="pilot run",
    )
    row_id = record(entry, db)
    assert row_id is not None

    runs = list_runs(db)
    assert len(runs) == 1
    assert runs[0]["seed"] == 42
    assert runs[0]["role"] == "reference"


def test_config_hash_deterministic():
    cfg = {"a": 1, "b": 2}
    assert config_hash(cfg) == config_hash(cfg)
    # Order shouldn't matter
    assert config_hash({"b": 2, "a": 1}) == config_hash(cfg)


def test_config_hash_differs():
    assert config_hash({"a": 1}) != config_hash({"a": 2})


def test_invalid_role_rejected(db):
    entry = LedgerEntry(
        config={"model": "test"},
        seed=1,
        split="cal",
        role="invalid_role",
    )
    with pytest.raises(sqlite3.IntegrityError):
        record(entry, db)


def test_filter_by_role(db):
    for role in ["reference", "control", "candidate"]:
        record(
            LedgerEntry(config={"r": role}, seed=1, split="cal", role=role),
            db,
        )
    refs = list_runs(db, role="reference")
    assert len(refs) == 1
    assert refs[0]["role"] == "reference"
