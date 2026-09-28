"""File-digest verification for model checkpoints."""

from __future__ import annotations

import hashlib
from pathlib import Path

from .errors import FactVerifyLoaderError
from .spec import ModelSpec


def verify_files(spec: ModelSpec, model_dir: Path) -> None:
    """Verify every file declared in spec.files exists in model_dir with correct digest.

    Raises FactVerifyLoaderError on any mismatch or missing file.
    """
    if not model_dir.exists():
        raise FactVerifyLoaderError(
            f"local directory not found for role {spec.role!r}: {model_dir}"
        )

    for filename, expected_digest in spec.files.items():
        filepath = model_dir / filename
        if not filepath.exists():
            raise FactVerifyLoaderError(
                f"missing file {filename!r} for role {spec.role!r}"
            )
        actual_digest = _sha256(filepath)
        if actual_digest != expected_digest:
            raise FactVerifyLoaderError(
                f"digest mismatch for {filename!r} "
                f"(expected {expected_digest}, got {actual_digest}) "
                f"for role {spec.role!r}"
            )


def sha256_file(path: Path) -> str:
    """Compute SHA-256 hex digest of a file. Public for use by adapters.py."""
    return _sha256(path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()
