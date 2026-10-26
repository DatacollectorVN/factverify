"""RunContext construction (FV-ARCH-006)."""

from __future__ import annotations

import logging
import subprocess
import uuid
from pathlib import Path

from .config import config_hash
from .paths import RuntimePaths, discover_repository_root
from .types import AppConfig, RunContext


def build_context(
    config: AppConfig,
    *,
    repository_root: Path | None = None,
    runtime_root: Path | None = None,
    logger: logging.Logger | None = None,
) -> RunContext:
    """Create a RunContext from a validated AppConfig."""
    repo = repository_root or discover_repository_root()
    rt_root = runtime_root or (repo / config.runtime.output_root)
    paths = RuntimePaths(rt_root, repo)

    git_commit, git_dirty = _git_info(repo)
    device = _resolve_device(config.runtime.device)

    run_id = uuid.uuid4().hex[:12]
    attempt_id = uuid.uuid4().hex[:8]

    if logger is None:
        logger = logging.getLogger("factverify")

    return RunContext(
        repository_root=repo,
        controlled_input_root=repo / ".factverify",
        runtime_root=rt_root,
        job_name=config.job.name,
        task=config.task,
        role=config.job.role,
        run_id=run_id,
        attempt_id=attempt_id,
        config_hash=config_hash(config),
        git_commit=git_commit,
        git_dirty=git_dirty,
        device=device,
        logger=logger,
    )


def _git_info(repo: Path) -> tuple[str, bool]:
    """Return (commit_hash, is_dirty). Safe when git is unavailable."""
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "status", "--porcelain"],
            cwd=repo,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return commit, bool(status)
    except (subprocess.SubprocessError, FileNotFoundError):
        return "unknown", True


def _resolve_device(device_str: str) -> str:
    """Resolve 'auto' to an available device string."""
    if device_str != "auto":
        return device_str
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
        if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
            return "mps"
    except ImportError:
        pass
    return "cpu"
