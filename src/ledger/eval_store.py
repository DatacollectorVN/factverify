"""Eval run store — operational SQLite DB for tracking evaluation progress.

Separate from the study ledger (append-only audit trail) and the training store
(training progress). This DB is at .factverify_internal/eval/eval.sqlite and
records every eval run so jobs can resume after interruption.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from src.ledger.schema import connect

EVAL_DB_PATH = Path(".factverify_internal/eval/eval.sqlite")

_SCHEMA_VERSION = "1"

_DDL = """\
CREATE TABLE IF NOT EXISTS meta (
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id              TEXT PRIMARY KEY,
    job_name            TEXT NOT NULL,
    checkpoint_role     TEXT NOT NULL,
    checkpoint_path     TEXT NOT NULL,
    fact_id             TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    arm                 TEXT NOT NULL,
    status              TEXT NOT NULL,
    config_hash         TEXT NOT NULL,
    wall_clock_seconds  REAL NOT NULL,
    peak_memory_bytes   INTEGER NOT NULL,
    rouge_l             REAL,
    truth_ratio         REAL,
    answer_probability  REAL,
    answer_rank         REAL,
    result_path         TEXT,
    error_message       TEXT,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_eval_runs_job
    ON eval_runs (job_name, status);

CREATE INDEX IF NOT EXISTS idx_eval_runs_fact
    ON eval_runs (job_name, fact_id, checkpoint_role);
"""


@dataclass
class EvalRunRecord:
    """One eval run to record in the store."""

    job_name: str
    checkpoint_role: str
    checkpoint_path: str
    fact_id: str
    seed: int
    arm: str
    status: str  # "succeeded" | "failed"
    config_hash: str
    wall_clock_seconds: float = 0.0
    peak_memory_bytes: int = 0
    rouge_l: Optional[float] = None
    truth_ratio: Optional[float] = None
    answer_probability: Optional[float] = None
    answer_rank: Optional[float] = None
    result_path: Optional[str] = None
    error_message: Optional[str] = None


class EvalStore:
    """Read/write interface to the eval runs database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_run(self, record: EvalRunRecord) -> str:
        """Insert an eval run. Returns the generated run_id."""
        run_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO eval_runs (
                run_id, job_name, checkpoint_role, checkpoint_path,
                fact_id, seed, arm, status, config_hash,
                wall_clock_seconds, peak_memory_bytes,
                rouge_l, truth_ratio, answer_probability, answer_rank,
                result_path, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                record.job_name,
                record.checkpoint_role,
                record.checkpoint_path,
                record.fact_id,
                record.seed,
                record.arm,
                record.status,
                record.config_hash,
                record.wall_clock_seconds,
                record.peak_memory_bytes,
                record.rouge_l,
                record.truth_ratio,
                record.answer_probability,
                record.answer_rank,
                record.result_path,
                record.error_message,
            ),
        )
        return run_id

    def completed_keys(self, job_name: str) -> set[tuple[str, str, int]]:
        """Return {(fact_id, checkpoint_role, seed)} for all succeeded runs."""
        rows = self._conn.execute(
            "SELECT fact_id, checkpoint_role, seed FROM eval_runs "
            "WHERE job_name = ? AND status = 'succeeded'",
            (job_name,),
        ).fetchall()
        return {(row["fact_id"], row["checkpoint_role"], row["seed"]) for row in rows}

    def clear_job(self, job_name: str) -> int:
        """Delete all records for a job. Returns count deleted."""
        cursor = self._conn.execute(
            "DELETE FROM eval_runs WHERE job_name = ?",
            (job_name,),
        )
        return cursor.rowcount

    def runs_for_job(self, job_name: str) -> list[EvalRunRecord]:
        """Return all records for a job, ordered by creation time."""
        rows = self._conn.execute(
            "SELECT * FROM eval_runs WHERE job_name = ? ORDER BY created_at",
            (job_name,),
        ).fetchall()
        return [_row_to_record(row) for row in rows]

    def scores_by_role(self, job_name: str) -> dict[str, list[EvalRunRecord]]:
        """Return succeeded records grouped by checkpoint_role."""
        rows = self._conn.execute(
            "SELECT * FROM eval_runs "
            "WHERE job_name = ? AND status = 'succeeded' "
            "ORDER BY checkpoint_role, fact_id, seed",
            (job_name,),
        ).fetchall()
        grouped: dict[str, list[EvalRunRecord]] = {}
        for row in rows:
            record = _row_to_record(row)
            grouped.setdefault(record.checkpoint_role, []).append(record)
        return grouped

    def summary(self) -> None:
        """Print a summary of all eval runs to stdout."""
        rows = self._conn.execute(
            "SELECT job_name, checkpoint_role, status, COUNT(*) as cnt, "
            "AVG(rouge_l) as avg_rouge "
            "FROM eval_runs GROUP BY job_name, checkpoint_role, status "
            "ORDER BY job_name, checkpoint_role, status"
        ).fetchall()
        if not rows:
            click.echo("No eval runs recorded.")
            return
        click.echo(
            f"{'Job':<25} {'Role':<12} {'Status':<10} "
            f"{'Runs':>5} {'Avg ROUGE-L':>11}"
        )
        click.echo("-" * 68)
        for row in rows:
            avg = f"{row['avg_rouge']:.4f}" if row["avg_rouge"] is not None else "N/A"
            click.echo(
                f"{row['job_name']:<25} {row['checkpoint_role']:<12} "
                f"{row['status']:<10} {row['cnt']:>5} {avg:>11}"
            )


def _row_to_record(row: sqlite3.Row) -> EvalRunRecord:
    return EvalRunRecord(
        job_name=row["job_name"],
        checkpoint_role=row["checkpoint_role"],
        checkpoint_path=row["checkpoint_path"],
        fact_id=row["fact_id"],
        seed=row["seed"],
        arm=row["arm"],
        status=row["status"],
        config_hash=row["config_hash"],
        wall_clock_seconds=row["wall_clock_seconds"],
        peak_memory_bytes=row["peak_memory_bytes"],
        rouge_l=row["rouge_l"],
        truth_ratio=row["truth_ratio"],
        answer_probability=row["answer_probability"],
        answer_rank=row["answer_rank"],
        result_path=row["result_path"],
        error_message=row["error_message"],
    )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if needed and verify schema version."""
    conn.executescript(_DDL)
    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (schema_version) VALUES (?)", (_SCHEMA_VERSION,)
        )


def open_eval_store(path: Path = EVAL_DB_PATH) -> EvalStore:
    """Open (or create) the eval store database."""
    conn = connect(path)
    _ensure_schema(conn)
    return EvalStore(conn)
