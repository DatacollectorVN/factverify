"""Tracking store: CRUD for logical runs and attempts (FV-ARCH-024, FV-ARCH-025)."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from src.services.common.errors import TrackingError

from .schema import init_database
from .types import AttemptRecord, AttemptStatus, CostRecord, LogicalRunId, valid_transition


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TrackingStore:
    """Operational tracking database for runs and attempts."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    @classmethod
    def open(cls, db_path: Path) -> TrackingStore:
        """Open (or create) the tracking database."""
        conn = init_database(db_path)
        return cls(conn)

    def close(self) -> None:
        self._conn.close()

    # ── Logical runs ────────────────────────────────────────────────────

    def ensure_logical_run(self, run_id: LogicalRunId) -> str:
        """Insert the logical run if it doesn't exist. Returns the run digest."""
        digest = run_id.digest()
        now = _now()
        self._conn.execute(
            """\
            INSERT OR IGNORE INTO logical_runs
                (run_digest, task, job_name, role, seed, config_hash,
                 model_identity, data_digest, code_revision, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                digest,
                run_id.task,
                run_id.job_name,
                run_id.role,
                run_id.seed,
                run_id.config_hash,
                run_id.model_identity,
                run_id.data_manifest_digest,
                run_id.code_revision,
                now,
            ),
        )
        self._conn.commit()
        return digest

    def find_matching_run(self, run_id: LogicalRunId) -> str | None:
        """Find a logical run with matching identity. Returns digest or None."""
        digest = run_id.digest()
        row = self._conn.execute(
            "SELECT run_digest FROM logical_runs WHERE run_digest = ?",
            (digest,),
        ).fetchone()
        return row[0] if row else None

    # ── Attempts ────────────────────────────────────────────────────────

    def create_attempt(
        self,
        *,
        attempt_id: str,
        run_id: str,
        run_digest: str,
        config_hash: str,
    ) -> AttemptRecord:
        """Create a new attempt in PLANNED status."""
        now = _now()
        self._conn.execute(
            """\
            INSERT INTO attempts
                (attempt_id, run_id, run_digest, status, config_hash,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (attempt_id, run_id, run_digest, AttemptStatus.PLANNED.value, config_hash, now, now),
        )
        self._conn.commit()
        return AttemptRecord(
            run_id=run_id,
            attempt_id=attempt_id,
            logical_run_digest=run_digest,
            status=AttemptStatus.PLANNED,
            config_hash=config_hash,
            created_at=now,
            updated_at=now,
        )

    def update_status(
        self,
        attempt_id: str,
        new_status: AttemptStatus,
        *,
        error_summary: str | None = None,
        cost: CostRecord | None = None,
    ) -> None:
        """Transition an attempt to a new status. Validates the transition."""
        row = self._conn.execute(
            "SELECT status FROM attempts WHERE attempt_id = ?",
            (attempt_id,),
        ).fetchone()
        if row is None:
            raise TrackingError(f"attempt {attempt_id} not found")

        current = AttemptStatus(row[0])
        if not valid_transition(current, new_status):
            raise TrackingError(
                f"invalid transition {current.value} -> {new_status.value} "
                f"for attempt {attempt_id}"
            )

        now = _now()
        params: list[object] = [new_status.value, now]
        sql_parts = ["status = ?", "updated_at = ?"]

        if error_summary is not None:
            sql_parts.append("error_summary = ?")
            params.append(error_summary)

        if cost is not None:
            for col, val in [
                ("wall_clock_s", cost.wall_clock_seconds),
                ("gpu_hours", cost.gpu_hours),
                ("peak_memory_b", cost.peak_memory_bytes),
                ("examples", cost.examples),
                ("micro_batches", cost.micro_batches),
                ("backward_passes", cost.backward_passes),
                ("optimizer_steps", cost.optimizer_steps),
                ("scheduler_steps", cost.scheduler_steps),
                ("evaluation_calls", cost.evaluation_calls),
                ("checkpoint_bytes", cost.checkpoint_bytes),
            ]:
                sql_parts.append(f"{col} = ?")
                params.append(val)

        params.append(attempt_id)
        sql = f"UPDATE attempts SET {', '.join(sql_parts)} WHERE attempt_id = ?"
        self._conn.execute(sql, params)
        self._conn.commit()

    def get_attempt(self, attempt_id: str) -> AttemptRecord | None:
        """Fetch a single attempt by ID."""
        row = self._conn.execute(
            """\
            SELECT attempt_id, run_id, run_digest, status, config_hash,
                   created_at, updated_at, error_summary,
                   wall_clock_s, gpu_hours, peak_memory_b, examples,
                   micro_batches, backward_passes, optimizer_steps,
                   scheduler_steps, evaluation_calls, checkpoint_bytes
            FROM attempts WHERE attempt_id = ?
            """,
            (attempt_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_attempt(row)

    def find_succeeded_attempt(self, run_digest: str) -> AttemptRecord | None:
        """Find a succeeded attempt for the given logical run."""
        row = self._conn.execute(
            """\
            SELECT attempt_id, run_id, run_digest, status, config_hash,
                   created_at, updated_at, error_summary,
                   wall_clock_s, gpu_hours, peak_memory_b, examples,
                   micro_batches, backward_passes, optimizer_steps,
                   scheduler_steps, evaluation_calls, checkpoint_bytes
            FROM attempts
            WHERE run_digest = ? AND status = 'succeeded'
            ORDER BY created_at DESC LIMIT 1
            """,
            (run_digest,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_attempt(row)

    def find_running_attempts(self, run_digest: str) -> list[AttemptRecord]:
        """Find attempts stuck in 'running' for crash recovery."""
        rows = self._conn.execute(
            """\
            SELECT attempt_id, run_id, run_digest, status, config_hash,
                   created_at, updated_at, error_summary,
                   wall_clock_s, gpu_hours, peak_memory_b, examples,
                   micro_batches, backward_passes, optimizer_steps,
                   scheduler_steps, evaluation_calls, checkpoint_bytes
            FROM attempts
            WHERE run_digest = ? AND status = 'running'
            """,
            (run_digest,),
        ).fetchall()
        return [_row_to_attempt(r) for r in rows]

    # ── Metrics ─────────────────────────────────────────────────────────

    def record_epoch_metric(
        self,
        attempt_id: str,
        epoch: int,
        metric_name: str,
        value: float,
    ) -> None:
        """Append one epoch-level metric."""
        self._conn.execute(
            """\
            INSERT INTO epoch_metrics (attempt_id, epoch, metric_name, value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (attempt_id, epoch, metric_name, value, _now()),
        )
        self._conn.commit()

    def record_evaluation_metric(
        self,
        attempt_id: str,
        metric_name: str,
        value: float,
        *,
        fact_id: str | None = None,
    ) -> None:
        """Append one evaluation-level metric."""
        self._conn.execute(
            """\
            INSERT INTO evaluation_metrics (attempt_id, metric_name, fact_id, value, recorded_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (attempt_id, metric_name, fact_id, value, _now()),
        )
        self._conn.commit()

    # ── Artifacts ───────────────────────────────────────────────────────

    def record_artifact(
        self,
        attempt_id: str,
        kind: str,
        path: str,
        *,
        digest: str | None = None,
        size_bytes: int = 0,
    ) -> None:
        """Record a published artifact."""
        self._conn.execute(
            """\
            INSERT INTO artifacts (attempt_id, kind, path, digest, size_bytes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (attempt_id, kind, path, digest, size_bytes, _now()),
        )
        self._conn.commit()


def _row_to_attempt(row: tuple) -> AttemptRecord:  # type: ignore[type-arg]
    cost = CostRecord(
        wall_clock_seconds=row[8] or 0.0,
        gpu_hours=row[9] or 0.0,
        peak_memory_bytes=row[10] or 0,
        examples=row[11] or 0,
        micro_batches=row[12] or 0,
        backward_passes=row[13] or 0,
        optimizer_steps=row[14] or 0,
        scheduler_steps=row[15] or 0,
        evaluation_calls=row[16] or 0,
        checkpoint_bytes=row[17] or 0,
    )
    return AttemptRecord(
        attempt_id=row[0],
        run_id=row[1],
        logical_run_digest=row[2],
        status=AttemptStatus(row[3]),
        config_hash=row[4],
        created_at=row[5],
        updated_at=row[6],
        error_summary=row[7],
        cost=cost,
    )
