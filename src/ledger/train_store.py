"""Training run store — operational SQLite DB for tracking training progress.

Separate from the study ledger (append-only audit trail) and the TOFU pipeline
store (data-prep progress). This DB is at .factverify_internal/train/train.sqlite
and records every training run so grouped jobs can resume after interruption.
"""

from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from src.ledger.schema import connect

TRAIN_DB_PATH = Path(".factverify_internal/train/train.sqlite")

_SCHEMA_VERSION = "1"

_DDL = """\
CREATE TABLE IF NOT EXISTS meta (
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS training_runs (
    run_id              TEXT PRIMARY KEY,
    job_name            TEXT NOT NULL,
    role                TEXT NOT NULL,
    method              TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    target_fact         TEXT NOT NULL,
    split               TEXT NOT NULL,
    status              TEXT NOT NULL,
    output_dir          TEXT,
    config_hash         TEXT NOT NULL,
    wall_clock_seconds  REAL NOT NULL,
    gpu_hours           REAL NOT NULL,
    peak_memory_bytes   INTEGER NOT NULL,
    training_steps      INTEGER NOT NULL,
    training_examples   INTEGER NOT NULL,
    error_message       TEXT,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_training_runs_job
    ON training_runs (job_name, status);

CREATE TABLE IF NOT EXISTS learner_fact_logs (
    log_id              TEXT PRIMARY KEY,
    job_name            TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    epoch               INTEGER NOT NULL,
    fact_id             TEXT NOT NULL,
    input_text          TEXT NOT NULL,
    output_text         TEXT NOT NULL,
    train_loss          REAL NOT NULL,
    validation_loss     REAL NOT NULL,
    answer_probability  REAL NOT NULL,
    answer_rank         REAL NOT NULL,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_learner_fact_logs_job
    ON learner_fact_logs (job_name, seed, epoch);
"""


@dataclass
class TrainingRunRecord:
    """One training run to record in the store."""

    job_name: str
    role: str
    method: str
    seed: int
    target_fact: str
    split: str
    status: str  # "succeeded" | "failed"
    config_hash: str
    wall_clock_seconds: float = 0.0
    gpu_hours: float = 0.0
    peak_memory_bytes: int = 0
    training_steps: int = 0
    training_examples: int = 0
    output_dir: Optional[str] = None
    error_message: Optional[str] = None


@dataclass(frozen=True)
class LearnerFactLog:
    """One forward-prompt score written after a learner epoch."""

    job_name: str
    seed: int
    epoch: int
    fact_id: str
    input_text: str
    output_text: str
    train_loss: float
    validation_loss: float
    answer_probability: float
    answer_rank: float


class TrainStore:
    """Read/write interface to the training runs database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def record_run(self, record: TrainingRunRecord) -> str:
        """Insert a training run. Returns the generated run_id."""
        run_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO training_runs (
                run_id, job_name, role, method, seed, target_fact, split,
                status, output_dir, config_hash, wall_clock_seconds,
                gpu_hours, peak_memory_bytes, training_steps,
                training_examples, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                record.job_name,
                record.role,
                record.method,
                record.seed,
                record.target_fact,
                record.split,
                record.status,
                record.output_dir,
                record.config_hash,
                record.wall_clock_seconds,
                record.gpu_hours,
                record.peak_memory_bytes,
                record.training_steps,
                record.training_examples,
                record.error_message,
            ),
        )
        return run_id

    def record_fact_log(self, record: LearnerFactLog) -> str:
        """Insert one per-fact validation row. Returns the generated log_id."""
        log_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO learner_fact_logs (
                log_id, job_name, seed, epoch, fact_id, input_text, output_text,
                train_loss, validation_loss, answer_probability, answer_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                record.job_name,
                record.seed,
                record.epoch,
                record.fact_id,
                record.input_text,
                record.output_text,
                record.train_loss,
                record.validation_loss,
                record.answer_probability,
                record.answer_rank,
            ),
        )
        return log_id

    def completed_keys(self, job_name: str) -> set[tuple[str, int]]:
        """Return {(target_fact, seed)} for all succeeded runs of this job."""
        rows = self._conn.execute(
            "SELECT target_fact, seed FROM training_runs "
            "WHERE job_name = ? AND status = 'succeeded'",
            (job_name,),
        ).fetchall()
        return {(row["target_fact"], row["seed"]) for row in rows}

    def clear_job(self, job_name: str) -> int:
        """Delete run records and learner fact logs for a job.

        Returns the number of training-run rows removed.
        """
        self._conn.execute(
            "DELETE FROM learner_fact_logs WHERE job_name = ?",
            (job_name,),
        )
        cursor = self._conn.execute(
            "DELETE FROM training_runs WHERE job_name = ?",
            (job_name,),
        )
        return cursor.rowcount

    def runs_for_job(self, job_name: str) -> list[TrainingRunRecord]:
        """Return all records for a job, ordered by creation time."""
        rows = self._conn.execute(
            "SELECT * FROM training_runs WHERE job_name = ? ORDER BY created_at",
            (job_name,),
        ).fetchall()
        return [
            TrainingRunRecord(
                job_name=row["job_name"],
                role=row["role"],
                method=row["method"],
                seed=row["seed"],
                target_fact=row["target_fact"],
                split=row["split"],
                status=row["status"],
                config_hash=row["config_hash"],
                wall_clock_seconds=row["wall_clock_seconds"],
                gpu_hours=row["gpu_hours"],
                peak_memory_bytes=row["peak_memory_bytes"],
                training_steps=row["training_steps"],
                training_examples=row["training_examples"],
                output_dir=row["output_dir"],
                error_message=row["error_message"],
            )
            for row in rows
        ]

    def summary(self) -> None:
        """Print a summary of all training runs to stdout."""
        rows = self._conn.execute(
            "SELECT job_name, status, COUNT(*) as cnt, "
            "SUM(wall_clock_seconds) as total_wall, "
            "SUM(gpu_hours) as total_gpu "
            "FROM training_runs GROUP BY job_name, status "
            "ORDER BY job_name, status"
        ).fetchall()
        if not rows:
            click.echo("No training runs recorded.")
            return
        click.echo(f"{'Job':<30} {'Status':<12} {'Runs':>5} {'Wall(s)':>10} {'GPU(h)':>8}")
        click.echo("-" * 70)
        for row in rows:
            click.echo(
                f"{row['job_name']:<30} {row['status']:<12} "
                f"{row['cnt']:>5} {row['total_wall']:>10.1f} "
                f"{row['total_gpu']:>8.3f}"
            )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if needed and verify schema version."""
    conn.executescript(_DDL)
    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta (schema_version) VALUES (?)", (_SCHEMA_VERSION,))


def open_train_store(path: Path = TRAIN_DB_PATH) -> TrainStore:
    """Open (or create) the training store database."""
    conn = connect(path)
    _ensure_schema(conn)
    return TrainStore(conn)
