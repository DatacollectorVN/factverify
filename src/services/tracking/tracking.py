"""Tracking facade: init_tracking returns a TrackingHandle for the run (FV-ARCH-024)."""

from __future__ import annotations

from pathlib import Path

from src.services.common.paths import RuntimePaths
from src.services.common.types import RunContext

from .store import TrackingStore
from .types import AttemptRecord, AttemptStatus, CostRecord, LogicalRunId


class TrackingHandle:
    """Scoped tracking handle for one run attempt.

    Wraps TrackingStore operations with the current run/attempt context.
    """

    def __init__(
        self,
        store: TrackingStore,
        run_digest: str,
        attempt: AttemptRecord,
    ) -> None:
        self._store = store
        self.run_digest = run_digest
        self.attempt = attempt

    @property
    def attempt_id(self) -> str:
        return self.attempt.attempt_id

    def mark_running(self) -> None:
        """Transition to RUNNING before model loading."""
        self._store.update_status(self.attempt_id, AttemptStatus.RUNNING)

    def mark_succeeded(self, cost: CostRecord | None = None) -> None:
        """Transition to SUCCEEDED."""
        self._store.update_status(self.attempt_id, AttemptStatus.SUCCEEDED, cost=cost)

    def mark_failed(self, error: str, cost: CostRecord | None = None) -> None:
        """Transition to FAILED with error summary."""
        self._store.update_status(
            self.attempt_id,
            AttemptStatus.FAILED,
            error_summary=error,
            cost=cost,
        )

    def mark_interrupted(self, cost: CostRecord | None = None) -> None:
        """Transition to INTERRUPTED."""
        self._store.update_status(
            self.attempt_id,
            AttemptStatus.INTERRUPTED,
            cost=cost,
        )

    def record_epoch_metric(self, epoch: int, name: str, value: float) -> None:
        self._store.record_epoch_metric(self.attempt_id, epoch, name, value)

    def record_evaluation_metric(
        self, name: str, value: float, *, fact_id: str | None = None
    ) -> None:
        self._store.record_evaluation_metric(
            self.attempt_id, name, value, fact_id=fact_id
        )

    def record_artifact(
        self, kind: str, path: str, *, digest: str | None = None, size_bytes: int = 0
    ) -> None:
        self._store.record_artifact(
            self.attempt_id, kind, path, digest=digest, size_bytes=size_bytes
        )

    def close(self) -> None:
        self._store.close()


def init_tracking(
    context: RunContext,
    *,
    logical_run_id: LogicalRunId,
    paths: RuntimePaths | None = None,
) -> TrackingHandle:
    """Initialize tracking for a run: create logical run + attempt."""
    if paths is None:
        paths = RuntimePaths(context.runtime_root, context.repository_root)

    store = TrackingStore.open(paths.tracking_db)

    # Ensure the logical run exists
    run_digest = store.ensure_logical_run(logical_run_id)

    # Check for resume: if a succeeded attempt exists, skip
    # (This is informational; the coordinator decides what to do)

    # Create a new attempt
    attempt = store.create_attempt(
        attempt_id=context.attempt_id,
        run_id=context.run_id,
        run_digest=run_digest,
        config_hash=context.config_hash,
    )

    return TrackingHandle(store, run_digest, attempt)
