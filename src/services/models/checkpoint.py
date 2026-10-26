"""Checkpoint publication, verification, and restore (FV-ARCH Phase 4).

Ports the atomic staging pattern from ``src.train.checkpoint`` and adds
manifest I/O, verification, and restore. Raises ``CheckpointError`` (from
the services error hierarchy) instead of ``FactVerifyHarnessError``.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.services.common.errors import CheckpointError

from .types import CheckpointManifest

_META_NAME = "metadata.json"
_ADAPTER_META_NAME = "fv_adapter_meta.json"
_MANIFEST_NAME = "checkpoint_manifest.json"


def publish_adapter(
    model: Any,
    output_dir: Path,
    metadata: dict[str, Any],
    base_identity_hash: str,
) -> None:
    """Save PEFT weights to a staging directory and rename into *output_dir*.

    A failure while writing deletes the staging directory and does not publish.
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
        raise CheckpointError(f"adapter publish failed at {output_dir}") from exc
    if output_dir.exists():
        shutil.rmtree(output_dir)
    staging.rename(output_dir)


def publish_model(
    model: Any,
    tokenizer: Any,
    output_dir: Path,
    metadata: dict[str, Any],
) -> None:
    """Save full model weights and tokenizer, then publish atomically.

    Same atomic staging pattern as :func:`publish_adapter`.
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
        raise CheckpointError(f"model publish failed at {output_dir}") from exc
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


def write_manifest(output_dir: Path, manifest: CheckpointManifest) -> None:
    """Write a checkpoint manifest JSON file alongside the checkpoint."""
    _write_json(output_dir / _MANIFEST_NAME, asdict(manifest))


def read_manifest(output_dir: Path) -> CheckpointManifest | None:
    """Read a checkpoint manifest if present; return None otherwise."""
    manifest_path = output_dir / _MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CheckpointError(
            f"corrupt manifest at {manifest_path}: {exc}"
        ) from exc
    try:
        return CheckpointManifest(**data)
    except TypeError as exc:
        raise CheckpointError(
            f"invalid manifest schema at {manifest_path}: {exc}"
        ) from exc


def verify_checkpoint(output_dir: Path) -> bool:
    """Return True when the checkpoint directory contains metadata.json."""
    return (output_dir / _META_NAME).is_file()


def restore_checkpoint(output_dir: Path, model: Any) -> None:
    """Load weights from a checkpoint directory into *model*.

    Uses ``torch.load`` + ``model.load_state_dict`` so that it works for
    both full-weight and adapter checkpoints saved via ``save_pretrained``.
    """
    import torch

    bin_path = output_dir / "pytorch_model.bin"
    safetensors_path = output_dir / "model.safetensors"

    if safetensors_path.is_file():
        try:
            from safetensors.torch import load_file

            state_dict = load_file(str(safetensors_path))
        except Exception as exc:
            raise CheckpointError(
                f"failed to load safetensors from {safetensors_path}: {exc}"
            ) from exc
    elif bin_path.is_file():
        try:
            state_dict = torch.load(str(bin_path), map_location="cpu", weights_only=True)
        except Exception as exc:
            raise CheckpointError(
                f"failed to load weights from {bin_path}: {exc}"
            ) from exc
    else:
        raise CheckpointError(
            f"no weight file found in {output_dir} "
            f"(expected pytorch_model.bin or model.safetensors)"
        )

    try:
        model.load_state_dict(state_dict, strict=False)
    except Exception as exc:
        raise CheckpointError(
            f"failed to restore state dict from {output_dir}: {exc}"
        ) from exc


# ── Private helpers ────────────────────────────────────────────────────────


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
