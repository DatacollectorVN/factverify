"""SHA-256 digest utilities for audit binding and bundle integrity.

Consolidates digest helpers used by build_bundles.py and entailment_audit.py.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of_ids(record_ids: list[str]) -> str:
    """Return a hex SHA-256 digest of a sorted list of record IDs.

    Sorting guarantees the digest is order-independent and deterministic
    regardless of the order in which records were assembled.
    """
    payload = "\n".join(sorted(record_ids))
    return hashlib.sha256(payload.encode()).hexdigest()


def sha256_file(path: Path) -> str:
    """Return a hex SHA-256 digest of the file at *path* (binary read)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
