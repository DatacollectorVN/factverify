"""Stage an adapter, write metadata, and publish only after both JSON files exist."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import torch

from .errors import FactVerifyHarnessError

# ── Resume-checkpoint helpers ────────────────────────────────────────────────
# Saved after every completed epoch so training can be restarted from the last
# epoch rather than from scratch if the process is interrupted.

_RESUME_DIR = ".resume"
_RESUME_FILE = "state.pt"


def save_resume_state(output_dir: Path, state: dict[str, Any]) -> None:
    """Atomically overwrite the per-epoch resume checkpoint.

    Uses a write-then-rename pattern so a crash during save never leaves a
    partial file behind.
    """
    if not output_dir.name:
        return  # no output dir configured; skip silently
    resume_dir = output_dir / _RESUME_DIR
    resume_dir.mkdir(parents=True, exist_ok=True)
    tmp = resume_dir / f"{_RESUME_FILE}.tmp"
    torch.save(state, tmp)
    tmp.rename(resume_dir / _RESUME_FILE)


def load_resume_state(output_dir: Path) -> dict[str, Any] | None:
    """Return the resume state dict if one exists, otherwise None.

    Returns None (and prints a warning) if the file is unreadable so callers
    can fall back to starting from scratch.
    """
    path = output_dir / _RESUME_DIR / _RESUME_FILE
    if not path.exists():
        return None
    try:
        return torch.load(path, weights_only=False)
    except Exception as exc:  # noqa: BLE001
        import click
        click.echo(f"    [resume] WARNING: could not load {path}: {exc} — starting from scratch")
        return None


def delete_resume_state(output_dir: Path) -> None:
    """Remove the resume checkpoint directory after successful training."""
    resume_dir = output_dir / _RESUME_DIR
    if resume_dir.exists():
        shutil.rmtree(resume_dir)

_META_NAME = "metadata.json"
_ADAPTER_META_NAME = "fv_adapter_meta.json"


def publish_adapter(
    model: Any,
    output_dir: Path,
    metadata: dict[str, Any],
    base_identity_hash: str,
) -> None:
    """Save PEFT weights to a staging directory and rename into `output_dir`.

    A failure while writing metadata deletes the staging directory and does not publish.
    """
    staging = output_dir.parent / f"{output_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        model.save_pretrained(staging)
        _write_json(
            staging / _ADAPTER_META_NAME,
            {"base_identity_hash": base_identity_hash},
        )
        _write_json(staging / _META_NAME, metadata)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise FactVerifyHarnessError(f"metadata write failed at {output_dir}") from exc
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging.rename(output_dir)


def discard_adapter(output_dir: Path) -> None:
    """Remove a published directory and any leftover staging directory."""
    staging = output_dir.parent / f"{output_dir.name}.staging"
    if output_dir.exists():
        shutil.rmtree(output_dir)
    if staging.exists():
        shutil.rmtree(staging)


def publish_model(
    model: Any,
    tokenizer: Any,
    output_dir: Path,
    metadata: dict[str, Any],
) -> None:
    """Save full model weights and tokenizer to a staging directory, then publish.

    Same atomic staging pattern as publish_adapter.
    """
    staging = output_dir.parent / f"{output_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        model.save_pretrained(staging)
        tokenizer.save_pretrained(staging)
        _write_json(staging / _META_NAME, metadata)
    except Exception as exc:
        shutil.rmtree(staging, ignore_errors=True)
        raise FactVerifyHarnessError(f"model save failed at {output_dir}") from exc
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging.rename(output_dir)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
