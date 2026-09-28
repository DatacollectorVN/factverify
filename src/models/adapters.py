"""LoRA adapter attachment with base-identity verification and digest computation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from peft import PeftModel

from .errors import FactVerifyLoaderError

_ADAPTER_META_FILE = "fv_adapter_meta.json"
_EXCLUDED_FILES = {_ADAPTER_META_FILE}


def compute_adapter_digest(adapter_path: Path) -> str:
    """Compute a deterministic SHA-256 digest over adapter weight and config files.

    Excludes fv_adapter_meta.json. Files are sorted by name for reproducibility.
    """
    files = sorted(
        f
        for f in adapter_path.iterdir()
        if f.is_file() and f.name not in _EXCLUDED_FILES
    )
    h = hashlib.sha256()
    for f in files:
        # Include filename in the hash so renames change the digest
        h.update(f.name.encode())
        h.update(b"\n")
        with f.open("rb") as fp:
            for chunk in iter(lambda: fp.read(65536), b""):
                h.update(chunk)
        h.update(b"\n")
    return h.hexdigest()


def attach_adapter(
    model: Any,
    adapter_path: Path,
    base_identity_hash: str,
) -> tuple[Any, str]:
    """Verify adapter provenance, compute its digest, and attach it to model.

    Returns (peft_model, adapter_digest).

    Raises FactVerifyLoaderError if:
    - fv_adapter_meta.json is missing
    - base_identity_hash does not match
    """
    meta_file = adapter_path / _ADAPTER_META_FILE
    if not meta_file.exists():
        raise FactVerifyLoaderError(f"missing {_ADAPTER_META_FILE} in {adapter_path!r}")

    try:
        meta = json.loads(meta_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        raise FactVerifyLoaderError(
            f"failed to read {_ADAPTER_META_FILE} in {adapter_path!r}: {exc}"
        ) from exc

    recorded_hash = meta.get("base_identity_hash")
    if not recorded_hash:
        raise FactVerifyLoaderError(
            f"missing 'base_identity_hash' in {_ADAPTER_META_FILE} at {adapter_path!r}"
        )

    if recorded_hash != base_identity_hash:
        raise FactVerifyLoaderError(
            f"adapter base hash mismatch "
            f"(adapter expects {recorded_hash!r}, base is {base_identity_hash!r})"
        )

    adapter_digest = compute_adapter_digest(adapter_path)

    peft_model = PeftModel.from_pretrained(
        model,
        str(adapter_path),
        local_files_only=True,
    )
    return peft_model, adapter_digest
