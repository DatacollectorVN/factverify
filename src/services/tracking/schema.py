"""SQLite schema for the unified tracking database (FV-ARCH-024).

Location: .factverify_internal/databases/factverify.sqlite
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_SCHEMA_VERSION = 1

_DDL = """\
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS logical_runs (
    run_digest     TEXT PRIMARY KEY,
    task           TEXT NOT NULL,
    job_name       TEXT NOT NULL,
    role           TEXT NOT NULL,
    seed           INTEGER NOT NULL,
    config_hash    TEXT NOT NULL,
    model_identity TEXT NOT NULL,
    data_digest    TEXT NOT NULL,
    code_revision  TEXT NOT NULL,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS attempts (
    attempt_id       TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL,
    run_digest       TEXT NOT NULL REFERENCES logical_runs(run_digest),
    status           TEXT NOT NULL DEFAULT 'planned',
    config_hash      TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    updated_at       TEXT NOT NULL,
    error_summary    TEXT,
    wall_clock_s     REAL DEFAULT 0,
    gpu_hours        REAL DEFAULT 0,
    peak_memory_b    INTEGER DEFAULT 0,
    examples         INTEGER DEFAULT 0,
    micro_batches    INTEGER DEFAULT 0,
    backward_passes  INTEGER DEFAULT 0,
    optimizer_steps  INTEGER DEFAULT 0,
    scheduler_steps  INTEGER DEFAULT 0,
    evaluation_calls INTEGER DEFAULT 0,
    checkpoint_bytes INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_attempts_run_digest ON attempts(run_digest);
CREATE INDEX IF NOT EXISTS idx_attempts_status ON attempts(status);

CREATE TABLE IF NOT EXISTS epoch_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  TEXT NOT NULL REFERENCES attempts(attempt_id),
    epoch       INTEGER NOT NULL,
    metric_name TEXT NOT NULL,
    value       REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_epoch_metrics_attempt ON epoch_metrics(attempt_id);

CREATE TABLE IF NOT EXISTS evaluation_metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  TEXT NOT NULL REFERENCES attempts(attempt_id),
    metric_name TEXT NOT NULL,
    fact_id     TEXT,
    value       REAL NOT NULL,
    recorded_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_eval_metrics_attempt ON evaluation_metrics(attempt_id);

CREATE TABLE IF NOT EXISTS artifacts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    attempt_id  TEXT NOT NULL REFERENCES attempts(attempt_id),
    kind        TEXT NOT NULL,
    path        TEXT NOT NULL,
    digest      TEXT,
    size_bytes  INTEGER DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_artifacts_attempt ON artifacts(attempt_id);
"""


def init_database(db_path: Path) -> sqlite3.Connection:
    """Create or open the tracking database and ensure the schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level="DEFERRED")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_DDL)

    # Record schema version
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES (?, ?)",
        ("schema_version", str(_SCHEMA_VERSION)),
    )
    conn.commit()
    return conn


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Return the schema version, or 0 if not set."""
    try:
        row = conn.execute(
            "SELECT value FROM schema_meta WHERE key = 'schema_version'"
        ).fetchone()
        return int(row[0]) if row else 0
    except sqlite3.OperationalError:
        return 0
