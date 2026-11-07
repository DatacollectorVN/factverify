"""Training run store — operational SQLite DB for tracking training progress.

Separate from the study ledger (append-only audit trail). This DB is at
.factverify_internal/factverify.sqlite and records every experiment, its
per-epoch scores, and per-epoch sample probes.
"""

from __future__ import annotations

import json
import math
import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import click

from src.ledger.schema import connect

TRAIN_DB_PATH = Path(".factverify_internal/factverify.sqlite")
_NAN_TOKEN = "NaN"

_SCHEMA_VERSION = "1"


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


def bind_optional_real(value: Optional[float]) -> float | str | None:
    """``bind_real`` for a nullable column. ``None`` stays ``None``."""
    if value is None:
        return None
    return bind_real(value)


def load_optional_real(value: object) -> float | None:
    """Restore a float written by ``bind_optional_real``. ``None`` stays ``None``."""
    if value is None:
        return None
    return load_real(value)


_DDL = """\
CREATE TABLE IF NOT EXISTS meta (
    store_name      TEXT PRIMARY KEY,
    schema_version  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiments (
    experiment_id           TEXT PRIMARY KEY,
    job_name                TEXT NOT NULL,
    role                    TEXT NOT NULL,
    method                  TEXT NOT NULL,
    seed                    INTEGER NOT NULL,
    split                   TEXT NOT NULL,
    target_fact             TEXT NOT NULL,
    facts                   TEXT NOT NULL,
    optimizer               TEXT NOT NULL DEFAULT 'adamw',
    learning_rate           REAL NOT NULL,
    epochs                  INTEGER NOT NULL,
    patience                INTEGER,
    batch_size              INTEGER NOT NULL,
    max_length              INTEGER NOT NULL,
    weight_decay            REAL NOT NULL,
    save_best_as            TEXT NOT NULL,
    best_epoch              INTEGER,
    best_score              REAL,
    output_dir              TEXT,
    config_hash             TEXT NOT NULL,
    status                  TEXT NOT NULL,
    error_message           TEXT,
    wall_clock_seconds      REAL,
    gpu_hours               REAL,
    peak_memory_bytes       INTEGER,
    training_steps          INTEGER,
    training_examples       INTEGER,
    languages               TEXT,
    created_at              TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_experiments_job ON experiments (job_name, status);
CREATE INDEX IF NOT EXISTS idx_experiments_role ON experiments (role, split, seed);

CREATE TABLE IF NOT EXISTS scores (
    score_id                        TEXT PRIMARY KEY,
    experiment_id                   TEXT NOT NULL REFERENCES experiments (experiment_id),
    epoch                           INTEGER NOT NULL,
    aggregation_level               TEXT NOT NULL,
    fact_id                         TEXT,
    fact_role                       TEXT,
    family                          TEXT,
    train_log_probability           REAL,
    eval_log_probability            REAL,
    baseline_train_log_probability  REAL,
    baseline_eval_log_probability   REAL,
    train_drop                      REAL,
    eval_drop                       REAL,
    train_log_retention             REAL,
    eval_log_retention              REAL,
    train_retention                 REAL,
    eval_retention                  REAL,
    train_loss                      REAL,
    train_fact_log_probability      REAL,
    eval_fact_log_probability       REAL,
    train_target_drop               REAL,
    eval_target_drop                REAL,
    train_target_log_retention      REAL,
    eval_target_log_retention       REAL,
    train_target_retention          REAL,
    eval_target_retention           REAL,
    train_retain_log_retention      REAL,
    eval_retain_log_retention       REAL,
    train_retain_retention          REAL,
    eval_retain_retention           REAL,
    is_selected_checkpoint          INTEGER NOT NULL DEFAULT 0,
    metric_version                  TEXT NOT NULL,
    created_at                      TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_scores_experiment_epoch ON scores (experiment_id, epoch, aggregation_level);
CREATE INDEX IF NOT EXISTS idx_scores_fact ON scores (fact_id, aggregation_level, epoch);

CREATE TABLE IF NOT EXISTS samples (
    sample_id               TEXT PRIMARY KEY,
    experiment_id           TEXT NOT NULL REFERENCES experiments (experiment_id),
    epoch                   INTEGER NOT NULL,
    fact_id                 TEXT NOT NULL,
    fact_role               TEXT NOT NULL,
    family                  TEXT NOT NULL,
    probe_id                TEXT NOT NULL,
    language                TEXT NOT NULL DEFAULT 'en',
    input_text              TEXT NOT NULL,
    expected_answer         TEXT NOT NULL,
    model_output            TEXT NOT NULL,
    log_probability         REAL NOT NULL,
    is_selected_checkpoint  INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT DEFAULT (strftime('%Y-%m-%dT%%H:%%M:%%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_samples_experiment_epoch ON samples (experiment_id, epoch);
CREATE INDEX IF NOT EXISTS idx_samples_family ON samples (experiment_id, family, epoch);
"""


@dataclass
class ExperimentRecord:
    """One training experiment to record in the store."""

    job_name: str
    role: str
    method: str
    seed: int
    split: str
    target_fact: str
    facts: list[str]
    config_hash: str
    optimizer: str = "adamw"
    learning_rate: float = 0.0
    epochs: int = 0
    patience: Optional[int] = None
    batch_size: int = 1
    max_length: int = 64
    weight_decay: float = 0.0
    save_best_as: str = "val_loss"
    status: str = "running"
    best_epoch: Optional[int] = None
    best_score: Optional[float] = None
    output_dir: Optional[str] = None
    error_message: Optional[str] = None
    wall_clock_seconds: Optional[float] = None
    gpu_hours: Optional[float] = None
    peak_memory_bytes: Optional[int] = None
    training_steps: Optional[int] = None
    training_examples: Optional[int] = None
    languages: Optional[list[str]] = None


@dataclass(frozen=True)
class ScoreRecord:
    """One probe/family/fact/epoch-level score row."""

    experiment_id: str
    epoch: int
    aggregation_level: str
    metric_version: str
    fact_id: Optional[str] = None
    fact_role: Optional[str] = None
    family: Optional[str] = None
    train_log_probability: Optional[float] = None
    eval_log_probability: Optional[float] = None
    baseline_train_log_probability: Optional[float] = None
    baseline_eval_log_probability: Optional[float] = None
    train_drop: Optional[float] = None
    eval_drop: Optional[float] = None
    train_log_retention: Optional[float] = None
    eval_log_retention: Optional[float] = None
    train_retention: Optional[float] = None
    eval_retention: Optional[float] = None
    train_loss: Optional[float] = None
    train_fact_log_probability: Optional[float] = None
    eval_fact_log_probability: Optional[float] = None
    train_target_drop: Optional[float] = None
    eval_target_drop: Optional[float] = None
    train_target_log_retention: Optional[float] = None
    eval_target_log_retention: Optional[float] = None
    train_target_retention: Optional[float] = None
    eval_target_retention: Optional[float] = None
    train_retain_log_retention: Optional[float] = None
    eval_retain_log_retention: Optional[float] = None
    train_retain_retention: Optional[float] = None
    eval_retain_retention: Optional[float] = None
    is_selected_checkpoint: bool = False


@dataclass(frozen=True)
class SampleRecord:
    """One randomly sampled eval probe logged per epoch."""

    experiment_id: str
    epoch: int
    fact_id: str
    fact_role: str
    family: str
    probe_id: str
    language: str
    input_text: str
    expected_answer: str
    model_output: str
    log_probability: float
    is_selected_checkpoint: bool = False


class TrainStore:
    """Read/write interface to the training experiments database."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    # ── experiments ──────────────────────────────────────────────────────────

    def create_experiment(self, record: ExperimentRecord) -> str:
        """Insert a new experiment with status='running'. Returns the experiment_id."""
        experiment_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO experiments (
                experiment_id, job_name, role, method, seed, split,
                target_fact, facts, optimizer, learning_rate, epochs,
                patience, batch_size, max_length, weight_decay, save_best_as,
                best_epoch, best_score, output_dir, config_hash, status,
                error_message, wall_clock_seconds, gpu_hours, peak_memory_bytes,
                training_steps, training_examples, languages
            ) VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?, ?
            )
            """,
            (
                experiment_id,
                record.job_name,
                record.role,
                record.method,
                record.seed,
                record.split,
                record.target_fact,
                json.dumps(sorted(record.facts)),
                record.optimizer,
                bind_real(record.learning_rate),
                record.epochs,
                record.patience,
                record.batch_size,
                record.max_length,
                bind_real(record.weight_decay),
                record.save_best_as,
                record.best_epoch,
                bind_optional_real(record.best_score),
                record.output_dir,
                record.config_hash,
                record.status,
                record.error_message,
                bind_optional_real(record.wall_clock_seconds),
                bind_optional_real(record.gpu_hours),
                record.peak_memory_bytes,
                record.training_steps,
                record.training_examples,
                json.dumps(record.languages) if record.languages is not None else None,
            ),
        )
        return experiment_id

    def update_experiment(self, experiment_id: str, **kwargs: object) -> None:
        """UPDATE experiments SET col=val ... WHERE experiment_id=?

        Accepts any subset of outcome columns. Only known columns are accepted.
        """
        _ALLOWED = {
            "status", "error_message", "output_dir", "wall_clock_seconds",
            "gpu_hours", "peak_memory_bytes", "training_steps", "training_examples",
            "best_epoch", "best_score",
        }
        _REAL_COLS = {"wall_clock_seconds", "gpu_hours", "best_score"}
        updates = {k: v for k, v in kwargs.items() if k in _ALLOWED}
        if not updates:
            return
        set_clauses = ", ".join(f"{col} = ?" for col in updates)
        values = []
        for col, val in updates.items():
            if col in _REAL_COLS and val is not None:
                values.append(bind_optional_real(float(val)))  # type: ignore[arg-type]
            else:
                values.append(val)
        values.append(experiment_id)
        self._conn.execute(
            f"UPDATE experiments SET {set_clauses} WHERE experiment_id = ?",
            values,
        )

    def completed_experiments(self, job_name: str) -> set[tuple[str, int]]:
        """Return {(target_fact, seed)} for all finished experiments of this job.

        Finished = ``succeeded`` or ``guard_stopped`` (the neighbour guard
        tripped before any valid epoch; rerunning would be deterministic).
        """
        rows = self._conn.execute(
            "SELECT target_fact, seed FROM experiments "
            "WHERE job_name = ? AND status IN ('succeeded', 'guard_stopped')",
            (job_name,),
        ).fetchall()
        return {(row["target_fact"], row["seed"]) for row in rows}

    def clear_job(self, job_name: str) -> int:
        """Delete all rows for *job_name* across experiments, scores, and samples.

        Returns the number of experiment rows removed.
        """
        # Get experiment ids for this job first
        exp_ids = [
            row["experiment_id"]
            for row in self._conn.execute(
                "SELECT experiment_id FROM experiments WHERE job_name = ?",
                (job_name,),
            ).fetchall()
        ]
        if exp_ids:
            placeholders = ",".join("?" * len(exp_ids))
            self._conn.execute(
                f"DELETE FROM samples WHERE experiment_id IN ({placeholders})",
                exp_ids,
            )
            self._conn.execute(
                f"DELETE FROM scores WHERE experiment_id IN ({placeholders})",
                exp_ids,
            )
        cursor = self._conn.execute(
            "DELETE FROM experiments WHERE job_name = ?",
            (job_name,),
        )
        return cursor.rowcount

    # ── scores ───────────────────────────────────────────────────────────────

    def record_score(self, record: ScoreRecord) -> str:
        """Insert one score row. Returns the generated score_id."""
        score_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO scores (
                score_id, experiment_id, epoch, aggregation_level,
                fact_id, fact_role, family,
                train_log_probability, eval_log_probability,
                baseline_train_log_probability, baseline_eval_log_probability,
                train_drop, eval_drop,
                train_log_retention, eval_log_retention,
                train_retention, eval_retention,
                train_loss, train_fact_log_probability, eval_fact_log_probability,
                train_target_drop, eval_target_drop,
                train_target_log_retention, eval_target_log_retention,
                train_target_retention, eval_target_retention,
                train_retain_log_retention, eval_retain_log_retention,
                train_retain_retention, eval_retain_retention,
                is_selected_checkpoint, metric_version
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?
            )
            """,
            (
                score_id,
                record.experiment_id,
                record.epoch,
                record.aggregation_level,
                record.fact_id,
                record.fact_role,
                record.family,
                bind_optional_real(record.train_log_probability),
                bind_optional_real(record.eval_log_probability),
                bind_optional_real(record.baseline_train_log_probability),
                bind_optional_real(record.baseline_eval_log_probability),
                bind_optional_real(record.train_drop),
                bind_optional_real(record.eval_drop),
                bind_optional_real(record.train_log_retention),
                bind_optional_real(record.eval_log_retention),
                bind_optional_real(record.train_retention),
                bind_optional_real(record.eval_retention),
                bind_optional_real(record.train_loss),
                bind_optional_real(record.train_fact_log_probability),
                bind_optional_real(record.eval_fact_log_probability),
                bind_optional_real(record.train_target_drop),
                bind_optional_real(record.eval_target_drop),
                bind_optional_real(record.train_target_log_retention),
                bind_optional_real(record.eval_target_log_retention),
                bind_optional_real(record.train_target_retention),
                bind_optional_real(record.eval_target_retention),
                bind_optional_real(record.train_retain_log_retention),
                bind_optional_real(record.eval_retain_log_retention),
                bind_optional_real(record.train_retain_retention),
                bind_optional_real(record.eval_retain_retention),
                1 if record.is_selected_checkpoint else 0,
                record.metric_version,
            ),
        )
        return score_id

    def record_scores(self, records: list[ScoreRecord]) -> list[str]:
        """Insert many score rows. Returns the generated ids."""
        return [self.record_score(record) for record in records]

    # ── samples ──────────────────────────────────────────────────────────────

    def record_sample(self, record: SampleRecord) -> str:
        """Insert one sample row. Returns the generated sample_id."""
        sample_id = uuid.uuid4().hex
        self._conn.execute(
            """
            INSERT INTO samples (
                sample_id, experiment_id, epoch, fact_id, fact_role,
                family, probe_id, language, input_text, expected_answer,
                model_output, log_probability, is_selected_checkpoint
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sample_id,
                record.experiment_id,
                record.epoch,
                record.fact_id,
                record.fact_role,
                record.family,
                record.probe_id,
                record.language,
                record.input_text,
                record.expected_answer,
                record.model_output,
                bind_real(record.log_probability),
                1 if record.is_selected_checkpoint else 0,
            ),
        )
        return sample_id

    def record_samples(self, records: list[SampleRecord]) -> list[str]:
        """Insert many sample rows. Returns the generated ids."""
        return [self.record_sample(record) for record in records]

    # ── summary ──────────────────────────────────────────────────────────────

    def summary(self) -> None:
        """Print a summary of all experiments to stdout."""
        rows = self._conn.execute(
            "SELECT job_name, status, COUNT(*) as cnt, "
            "SUM(wall_clock_seconds) as total_wall, "
            "SUM(gpu_hours) as total_gpu "
            "FROM experiments GROUP BY job_name, status "
            "ORDER BY job_name, status"
        ).fetchall()
        if not rows:
            click.echo("No experiments recorded.")
            return
        click.echo(f"{'Job':<30} {'Status':<12} {'Runs':>5} {'Wall(s)':>10} {'GPU(h)':>8}")
        click.echo("-" * 70)
        for row in rows:
            click.echo(
                f"{row['job_name']:<30} {row['status']:<12} "
                f"{row['cnt']:>5} {(row['total_wall'] or 0.0):>10.1f} "
                f"{(row['total_gpu'] or 0.0):>8.3f}"
            )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables and write initial schema version."""
    conn.executescript(_DDL)
    # Migration: add languages column to existing databases (idempotent).
    try:
        conn.execute("ALTER TABLE experiments ADD COLUMN languages TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists
    row = conn.execute(
        "SELECT schema_version FROM meta WHERE store_name = 'train'"
    ).fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (store_name, schema_version) VALUES ('train', ?)",
            (_SCHEMA_VERSION,),
        )


def open_train_store(path: Path = TRAIN_DB_PATH) -> TrainStore:
    """Open (or create) the training store database."""
    conn = connect(path)
    _ensure_schema(conn)
    return TrainStore(conn)
