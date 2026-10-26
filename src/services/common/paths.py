"""Runtime directory structure and path policy (FV-ARCH-007).

All generated runtime state lives below the configured runtime root.
This module is the single source for all path construction.
"""

from __future__ import annotations

from pathlib import Path


class RuntimePaths:
    """Centralized path factory. Tests can replace ``runtime_root`` with ``tmp_path``."""

    def __init__(self, runtime_root: Path, repository_root: Path | None = None) -> None:
        self.runtime_root = runtime_root
        self.repository_root = repository_root or runtime_root.parent

    # ── Databases ───────────────────────────────────────────────────────

    @property
    def databases_dir(self) -> Path:
        return self.runtime_root / "databases"

    @property
    def tracking_db(self) -> Path:
        return self.databases_dir / "factverify.sqlite"

    # ── Runs ────────────────────────────────────────────────────────────

    def run_dir(self, job_name: str, run_id: str) -> Path:
        return self.runtime_root / "runs" / job_name / run_id

    def resolved_config_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "resolved-config.yaml"

    def run_manifest_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "run-manifest.json"

    def status_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "status.json"

    def metrics_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "metrics.jsonl"

    def events_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "events.jsonl"

    def summary_path(self, job_name: str, run_id: str) -> Path:
        return self.run_dir(job_name, run_id) / "summary.json"

    # ── Checkpoints ─────────────────────────────────────────────────────

    def checkpoint_dir(self, job_name: str, run_id: str) -> Path:
        return self.runtime_root / "checkpoints" / job_name / run_id

    def best_checkpoint_dir(self, job_name: str, run_id: str) -> Path:
        return self.checkpoint_dir(job_name, run_id) / "best"

    def final_checkpoint_dir(self, job_name: str, run_id: str) -> Path:
        return self.checkpoint_dir(job_name, run_id) / "final"

    # ── Logs ────────────────────────────────────────────────────────────

    def log_file(self, job_name: str, run_id: str) -> Path:
        return self.runtime_root / "logs" / job_name / f"{run_id}.log"

    # ── Reports ─────────────────────────────────────────────────────────

    @property
    def reports_dir(self) -> Path:
        return self.runtime_root / "reports"

    def training_report_dir(self) -> Path:
        return self.reports_dir / "training"

    def evaluation_report_dir(self) -> Path:
        return self.reports_dir / "evaluation"

    def gate_report_dir(self) -> Path:
        return self.reports_dir / "gates"

    # ── Temp ────────────────────────────────────────────────────────────

    @property
    def tmp_dir(self) -> Path:
        return self.runtime_root / "tmp"


def discover_repository_root(start: Path | None = None) -> Path:
    """Walk upward to find the repository root (contains pyproject.toml or .git)."""
    current = (start or Path.cwd()).resolve()
    for parent in [current, *current.parents]:
        if (parent / ".git").exists() or (parent / "pyproject.toml").exists():
            return parent
    return current
