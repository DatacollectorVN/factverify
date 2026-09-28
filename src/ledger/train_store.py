"""Training run store — operational SQLite DB for tracking training progress.

Separate from the study ledger (append-only audit trail) and the TOFU pipeline
store (data-prep progress). This DB is at .factverify_internal/train/train.sqlite
and records every training run so grouped jobs can resume after interruption.
"""

from __future__ import annotations

import math
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from src.ledger.schema import connect

TRAIN_DB_PATH = Path(".factverify_internal/train/train.sqlite")
_NAN_TOKEN = "NaN"


def bind_real(value: float) -> float | str:
    """Bind a float for SQLite.

    SQLite converts NaN to NULL, so a NOT NULL REAL column rejects it.
    NaN is stored as the text token ``NaN`` and restored by ``load_real``.
    """
    if isinstance(value, float) and math.isnan(value):
        return _NAN_TOKEN
    return value


def load_real(value: object) -> float:
    """Restore a float written by ``bind_real``."""
    if value == _NAN_TOKEN:
        return float("nan")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"expected a stored real, got {value!r}")
    return float(value)

_SCHEMA_VERSION = "3"

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
    -- training parameters
    optimizer           TEXT NOT NULL DEFAULT 'adamw',
    learning_rate       REAL NOT NULL DEFAULT 0.0,
    epochs              INTEGER NOT NULL DEFAULT 0,
    patience            INTEGER,
    micro_batch_size    INTEGER NOT NULL DEFAULT 1,
    gradient_accumulation_steps INTEGER NOT NULL DEFAULT 1,
    shuffle_each_epoch  INTEGER NOT NULL DEFAULT 1,
    save_best_as        TEXT NOT NULL DEFAULT 'val_loss',
    max_length          INTEGER NOT NULL DEFAULT 64,
    weight_decay        REAL NOT NULL DEFAULT 0.0,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now'))
);

CREATE INDEX IF NOT EXISTS idx_training_runs_job
    ON training_runs (job_name, status);

CREATE TABLE IF NOT EXISTS learner_fact_logs (
    log_id              TEXT PRIMARY KEY,
    run_id              TEXT,
    job_name            TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    epoch               INTEGER NOT NULL,
    fact_id             TEXT NOT NULL,
    input_text          TEXT NOT NULL,
    output_label        TEXT NOT NULL,
    train_loss          REAL NOT NULL,
    validation_loss     REAL NOT NULL,
    answer_probability  REAL NOT NULL,
    answer_rank         REAL NOT NULL,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now')),
    FOREIGN KEY (run_id) REFERENCES training_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_learner_fact_logs_job
    ON learner_fact_logs (job_name, seed, epoch);

CREATE INDEX IF NOT EXISTS idx_learner_fact_logs_run
    ON learner_fact_logs (run_id);

CREATE TABLE IF NOT EXISTS learner_fact_details (
    detail_id           TEXT PRIMARY KEY,
    run_id              TEXT,
    job_name            TEXT NOT NULL,
    seed                INTEGER NOT NULL,
    fact_id             TEXT NOT NULL,
    direction           TEXT NOT NULL,
    input_text          TEXT NOT NULL,
    output_label        TEXT NOT NULL,
    output_model        TEXT NOT NULL,
    answer_probability  REAL NOT NULL,
    answer_rank         REAL NOT NULL,
    created_at          TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ','now')),
    FOREIGN KEY (run_id) REFERENCES training_runs (run_id)
);

CREATE INDEX IF NOT EXISTS idx_learner_fact_details_run
    ON learner_fact_details (run_id, fact_id);
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
    # training parameters
    optimizer: str = "adamw"
    learning_rate: float = 0.0
    epochs: int = 0
    patience: Optional[int] = None
    micro_batch_size: int = 1
    gradient_accumulation_steps: int = 1
    shuffle_each_epoch: bool = True
    save_best_as: str = "val_loss"
    max_length: int = 64
    weight_decay: float = 0.0


@dataclass(frozen=True)
class LearnerFactLog:
    """One forward-prompt score written after a learner epoch."""

    job_name: str
    seed: int
    epoch: int
    fact_id: str
    input_text: str
    output_label: str
    train_loss: float
    validation_loss: float
    answer_probability: float
    answer_rank: float
    run_id: Optional[str] = None


@dataclass(frozen=True)
class LearnerFactDetail:
    """Per-probe generation from the best checkpoint at end of training."""

    job_name: str
    seed: int
    fact_id: str
    direction: str
    input_text: str
    output_label: str
    output_model: str
    answer_probability: float
    answer_rank: float
    run_id: Optional[str] = None


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
                training_examples, error_message,
                optimizer, learning_rate, epochs, patience,
                micro_batch_size, gradient_accumulation_steps,
                shuffle_each_epoch, save_best_as, max_length, weight_decay
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                bind_real(record.wall_clock_seconds),
                bind_real(record.gpu_hours),
                record.peak_memory_bytes,
                record.training_steps,
                record.training_examples,
                record.error_message,
                record.optimizer,
                bind_real(record.learning_rate),
                record.epochs,
                record.patience,
                record.micro_batch_size,
                record.gradient_accumulation_steps,
                1 if record.shuffle_each_epoch else 0,
                record.save_best_as,
                record.max_length,
                bind_real(record.weight_decay),
            ),
        )
        return run_id

    def record_fact_log(self, record: LearnerFactLog) -> str:
        """Insert one per-fact validation row. Returns the generated log_id."""
        log_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO learner_fact_logs (
                log_id, run_id, job_name, seed, epoch, fact_id, input_text,
                output_label,
                train_loss, validation_loss, answer_probability, answer_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                log_id,
                record.run_id,
                record.job_name,
                record.seed,
                record.epoch,
                record.fact_id,
                record.input_text,
                record.output_label,
                bind_real(record.train_loss),
                bind_real(record.validation_loss),
                bind_real(record.answer_probability),
                bind_real(record.answer_rank),
            ),
        )
        return log_id

    def record_fact_detail(self, record: LearnerFactDetail) -> str:
        """Insert one per-probe detail from the best checkpoint."""
        detail_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO learner_fact_details (
                detail_id, run_id, job_name, seed, fact_id, direction,
                input_text, output_label, output_model,
                answer_probability, answer_rank
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                detail_id,
                record.run_id,
                record.job_name,
                record.seed,
                record.fact_id,
                record.direction,
                record.input_text,
                record.output_label,
                record.output_model,
                bind_real(record.answer_probability),
                bind_real(record.answer_rank),
            ),
        )
        return detail_id

    def backfill_run_id(self, run_id: str, job_name: str, seed: int) -> None:
        """Set run_id on logs and details that were written before the run was recorded."""
        self._conn.execute(
            "UPDATE learner_fact_logs SET run_id = ? "
            "WHERE job_name = ? AND seed = ? AND (run_id IS NULL OR run_id = '')",
            (run_id, job_name, seed),
        )
        self._conn.execute(
            "UPDATE learner_fact_details SET run_id = ? "
            "WHERE job_name = ? AND seed = ? AND run_id IS NULL",
            (run_id, job_name, seed),
        )

    def completed_keys(self, job_name: str) -> set[tuple[str, int]]:
        """Return {(target_fact, seed)} for all succeeded runs of this job."""
        rows = self._conn.execute(
            "SELECT target_fact, seed FROM training_runs "
            "WHERE job_name = ? AND status = 'succeeded'",
            (job_name,),
        ).fetchall()
        return {(row["target_fact"], row["seed"]) for row in rows}

    def clear_job(self, job_name: str) -> int:
        """Delete run records, learner fact logs, and details for a job.

        Returns the number of training-run rows removed.
        """
        self._conn.execute(
            "DELETE FROM learner_fact_details WHERE job_name = ?",
            (job_name,),
        )
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


def _migrate_v1_to_v2(conn: sqlite3.Connection) -> None:
    """v1 → v2: rename output_text → output_label, add output_model."""
    conn.execute(
        "ALTER TABLE learner_fact_logs RENAME COLUMN output_text TO output_label"
    )
    conn.execute(
        "ALTER TABLE learner_fact_logs ADD COLUMN output_model TEXT NOT NULL DEFAULT ''"
    )


def _migrate_v2_to_v3(conn: sqlite3.Connection) -> None:
    """v2 → v3: training params on runs, run_id FK on logs, fact details table."""
    # training_runs: add training parameter columns
    for stmt in [
        "ALTER TABLE training_runs ADD COLUMN optimizer TEXT NOT NULL DEFAULT 'adamw'",
        "ALTER TABLE training_runs ADD COLUMN learning_rate REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE training_runs ADD COLUMN epochs INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE training_runs ADD COLUMN patience INTEGER",
        "ALTER TABLE training_runs ADD COLUMN micro_batch_size INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE training_runs ADD COLUMN gradient_accumulation_steps INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE training_runs ADD COLUMN shuffle_each_epoch INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE training_runs ADD COLUMN save_best_as TEXT NOT NULL DEFAULT 'val_loss'",
        "ALTER TABLE training_runs ADD COLUMN max_length INTEGER NOT NULL DEFAULT 64",
        "ALTER TABLE training_runs ADD COLUMN weight_decay REAL NOT NULL DEFAULT 0.0",
    ]:
        conn.execute(stmt)
    # learner_fact_logs: add run_id, drop output_model
    conn.execute(
        "ALTER TABLE learner_fact_logs ADD COLUMN run_id TEXT REFERENCES training_runs(run_id)"
    )
    # Drop output_model — SQLite doesn't support DROP COLUMN before 3.35;
    # just leave it in place for older SQLite versions, it won't be written to.
    try:
        conn.execute("ALTER TABLE learner_fact_logs DROP COLUMN output_model")
    except Exception:
        pass  # older SQLite, column stays but is unused
    # learner_fact_details: created by _DDL


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if needed and migrate from older versions."""
    conn.executescript(_DDL)
    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        conn.execute("INSERT INTO meta (schema_version) VALUES (?)", (_SCHEMA_VERSION,))
        return
    version = row["schema_version"]
    if version == "1":
        _migrate_v1_to_v2(conn)
        _migrate_v2_to_v3(conn)
        conn.execute("UPDATE meta SET schema_version = ?", (_SCHEMA_VERSION,))
    elif version == "2":
        _migrate_v2_to_v3(conn)
        conn.execute("UPDATE meta SET schema_version = ?", (_SCHEMA_VERSION,))


def open_train_store(path: Path = TRAIN_DB_PATH) -> TrainStore:
    """Open (or create) the training store database."""
    conn = connect(path)
    _ensure_schema(conn)
    return TrainStore(conn)
