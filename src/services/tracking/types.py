"""Tracking domain types: LogicalRunId, AttemptRecord, CostRecord (FV-ARCH-008, FV-ARCH-025, FV-ARCH-027)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class AttemptStatus(Enum):
    """Status lifecycle for an attempt (FV-ARCH-025)."""

    PLANNED = "planned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    SUPERSEDED = "superseded"


# Valid transitions
_TRANSITIONS: dict[AttemptStatus, frozenset[AttemptStatus]] = {
    AttemptStatus.PLANNED: frozenset({AttemptStatus.RUNNING, AttemptStatus.SUPERSEDED}),
    AttemptStatus.RUNNING: frozenset({
        AttemptStatus.SUCCEEDED,
        AttemptStatus.FAILED,
        AttemptStatus.INTERRUPTED,
    }),
    AttemptStatus.SUCCEEDED: frozenset(),
    AttemptStatus.FAILED: frozenset(),
    AttemptStatus.INTERRUPTED: frozenset(),
    AttemptStatus.SUPERSEDED: frozenset(),
}


def valid_transition(from_status: AttemptStatus, to_status: AttemptStatus) -> bool:
    """Check whether a status transition is allowed."""
    return to_status in _TRANSITIONS.get(from_status, frozenset())


@dataclass(frozen=True)
class LogicalRunId:
    """Unique identity for a logical run (FV-ARCH-008).

    Binds task + job + role + seed + config + model + data + code.
    A change to any component produces a different logical run.
    """

    task: str
    job_name: str
    role: str
    seed: int
    config_hash: str
    model_identity: str
    data_manifest_digest: str
    code_revision: str

    def digest(self) -> str:
        """SHA-256 of the logical run identity."""
        payload = json.dumps(
            {
                "task": self.task,
                "job_name": self.job_name,
                "role": self.role,
                "seed": self.seed,
                "config_hash": self.config_hash,
                "model_identity": self.model_identity,
                "data_manifest_digest": self.data_manifest_digest,
                "code_revision": self.code_revision,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AttemptRecord:
    """One execution of a logical run."""

    run_id: str
    attempt_id: str
    logical_run_digest: str
    status: AttemptStatus
    config_hash: str
    created_at: str = ""
    updated_at: str = ""
    error_summary: str | None = None
    cost: CostRecord | None = None


@dataclass(frozen=True)
class CostRecord:
    """Cost measurements for one attempt (FV-ARCH-027)."""

    wall_clock_seconds: float = 0.0
    gpu_hours: float = 0.0
    peak_memory_bytes: int = 0
    examples: int = 0
    micro_batches: int = 0
    backward_passes: int = 0
    optimizer_steps: int = 0
    scheduler_steps: int = 0
    evaluation_calls: int = 0
    checkpoint_bytes: int = 0
