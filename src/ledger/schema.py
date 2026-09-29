"""SQLite schema. UPDATE and DELETE abort. Version is the string `1`."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from src.ledger.errors import LedgerError

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    schema_version TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS checkpoints (
    row_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    identity_hash TEXT NOT NULL,
    parent_ledger_id TEXT REFERENCES checkpoints(row_id),
    parent_identity_hash TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    seed INTEGER NOT NULL,
    fact_id TEXT NOT NULL,
    split TEXT NOT NULL,
    role TEXT NOT NULL,
    tier TEXT NOT NULL,
    family TEXT NOT NULL,
    method TEXT NOT NULL,
    implementation_id TEXT NOT NULL,
    spec_tag TEXT NOT NULL,
    git_commit TEXT NOT NULL,
    dirty INTEGER NOT NULL,
    tokens INTEGER NOT NULL,
    scored_candidates INTEGER NOT NULL,
    training_steps INTEGER NOT NULL,
    training_examples INTEGER NOT NULL,
    exports INTEGER NOT NULL,
    wall_clock_seconds REAL NOT NULL,
    gpu_hours REAL NOT NULL,
    peak_memory_bytes INTEGER NOT NULL,
    status TEXT NOT NULL,
    supersedes TEXT REFERENCES checkpoints(row_id)
);
CREATE TABLE IF NOT EXISTS evaluation_runs (
    run_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    checkpoint_ledger_id TEXT NOT NULL REFERENCES checkpoints(row_id),
    arm TEXT NOT NULL,
    split TEXT NOT NULL,
    spec_tag TEXT NOT NULL,
    thresholds_tag TEXT NOT NULL,
    budget_used TEXT NOT NULL,
    pass_number INTEGER NOT NULL,
    git_commit TEXT NOT NULL,
    dirty INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS incidents (
    incident_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    split TEXT NOT NULL,
    references_pass_number INTEGER NOT NULL,
    note TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS study_artifacts (
    artifact_id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    kind TEXT NOT NULL,
    seed INTEGER NOT NULL,
    digest TEXT NOT NULL,
    config_hash TEXT NOT NULL,
    spec_tag TEXT NOT NULL,
    git_commit TEXT NOT NULL,
    dirty INTEGER NOT NULL,
    wall_clock_seconds REAL NOT NULL,
    gpu_hours REAL NOT NULL,
    peak_memory_bytes INTEGER NOT NULL
);
"""

_TRIGGERS = """
CREATE TRIGGER IF NOT EXISTS checkpoints_no_update
BEFORE UPDATE ON checkpoints
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS checkpoints_no_delete
BEFORE DELETE ON checkpoints
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS runs_no_update
BEFORE UPDATE ON evaluation_runs
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS runs_no_delete
BEFORE DELETE ON evaluation_runs
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS incidents_no_update
BEFORE UPDATE ON incidents
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS incidents_no_delete
BEFORE DELETE ON incidents
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS study_artifacts_no_update
BEFORE UPDATE ON study_artifacts
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
CREATE TRIGGER IF NOT EXISTS study_artifacts_no_delete
BEFORE DELETE ON study_artifacts
BEGIN
    SELECT RAISE(ABORT, 'append-only');
END;
"""


def connect(path: Path) -> sqlite3.Connection:
    """Open a connection that does not start transactions on its own."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def open_ledger(path: Path, *, decisions: Path) -> sqlite3.Connection:
    """Create the file when needed. Raise if the meta row is missing."""
    if not decisions.is_file():
        raise LedgerError("decisions")
    connection = connect(path)
    ensure_schema(connection)
    row = connection.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        raise LedgerError("schema_version")
    return connection


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables and triggers. Insert schema version `1` when meta is empty."""
    conn.executescript(_DDL)
    conn.executescript(_TRIGGERS)
    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,))
        return
    if str(row["schema_version"]) != SCHEMA_VERSION:
        raise LedgerError("schema_version")
