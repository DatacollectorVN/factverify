"""Core application types: AppConfig, RunContext, RunResult (FV-ARCH-003, FV-ARCH-006)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


# ── Configuration envelope (FV-ARCH-003) ────────────────────────────────────


@dataclass(frozen=True)
class JobSection:
    """The ``job:`` section common to all task types."""

    name: str
    role: str
    split: str
    seeds: list[int] = field(default_factory=lambda: [0])


@dataclass(frozen=True)
class RuntimeSection:
    """The ``runtime:`` section common to all task types."""

    output_root: str = ".factverify_internal"
    device: str = "auto"
    deterministic: bool = True
    resume: bool = True


@dataclass(frozen=True)
class AppConfig:
    """Immutable, fully validated application configuration.

    Constructed from a YAML file after schema validation. Task-specific
    sections are stored in ``raw`` for service-level parsing.
    """

    schema_version: int
    task: str
    job: JobSection
    runtime: RuntimeSection
    raw: dict[str, Any]
    source_path: Path | None = None


# ── Run context (FV-ARCH-006) ───────────────────────────────────────────────

StatusLiteral = Literal[
    "planned", "running", "succeeded", "failed", "interrupted", "superseded"
]


@dataclass(frozen=True)
class RunContext:
    """Created once by ``src/main.py`` and threaded through every service."""

    repository_root: Path
    controlled_input_root: Path
    runtime_root: Path
    job_name: str
    task: str
    role: str
    run_id: str
    attempt_id: str
    config_hash: str
    git_commit: str
    git_dirty: bool
    device: str
    logger: logging.Logger


# ── Run result ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class RunResult:
    """Returned by every task handler to ``src/main.py``."""

    status: StatusLiteral
    error: str | None = None
    artifacts: dict[str, str] = field(default_factory=dict)
