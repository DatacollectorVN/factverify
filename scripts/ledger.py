"""Run ledger — every checkpoint gets a row.

Schema: config_hash, seed, split, role, tier, cost_gpu_hours, wall_clock_s,
        created_at, notes.

Stand this up before the first checkpoint exists (P2-5).
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

LEDGER_PATH = Path(__file__).resolve().parent.parent / "ledger.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    config_hash   TEXT    NOT NULL,
    seed          INTEGER NOT NULL,
    split         TEXT    NOT NULL,
    role          TEXT    NOT NULL CHECK (role IN ('reference', 'control', 'candidate')),
    tier          TEXT,
    cost_gpu_hours REAL,
    wall_clock_s  REAL,
    created_at    TEXT    NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    notes         TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_config ON runs (config_hash);
CREATE INDEX IF NOT EXISTS idx_runs_role   ON runs (role);
"""


def init_db(path: Path = LEDGER_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def config_hash(config: dict) -> str:
    blob = json.dumps(config, sort_keys=True, ensure_ascii=True).encode()
    return hashlib.sha256(blob).hexdigest()[:16]


@dataclass
class LedgerEntry:
    config: dict
    seed: int
    split: str
    role: str
    tier: str | None = None
    cost_gpu_hours: float | None = None
    wall_clock_s: float | None = None
    notes: str | None = None


def record(entry: LedgerEntry, conn: sqlite3.Connection | None = None) -> int:
    """Insert a ledger row. Returns the row id."""
    own_conn = conn is None
    if own_conn:
        conn = init_db()
    try:
        cursor = conn.execute(
            """
            INSERT INTO runs (config_hash, seed, split, role, tier,
                              cost_gpu_hours, wall_clock_s, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                config_hash(entry.config),
                entry.seed,
                entry.split,
                entry.role,
                entry.tier,
                entry.cost_gpu_hours,
                entry.wall_clock_s,
                entry.notes,
            ),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]
    finally:
        if own_conn:
            conn.close()


def list_runs(
    conn: sqlite3.Connection | None = None,
    role: str | None = None,
) -> list[dict]:
    own_conn = conn is None
    if own_conn:
        conn = init_db()
    try:
        query = "SELECT * FROM runs"
        params: list = []
        if role:
            query += " WHERE role = ?"
            params.append(role)
        query += " ORDER BY id"
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        if own_conn:
            conn.close()


if __name__ == "__main__":
    db = init_db()
    print(f"Ledger initialized at {LEDGER_PATH}")
    print(f"Existing runs: {len(list_runs(db))}")
    db.close()
