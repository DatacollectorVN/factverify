"""Stage an adapter, write metadata, and publish only after both JSON files exist."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from .errors import FactVerifyHarnessError

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
