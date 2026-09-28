"""Final-test thresholds match the thresholds-v1 git blob."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Protocol

from src.eval.errors import FactVerifyEvalError
from src.eval.types import FrozenThresholds

TAG = "thresholds-v1"
BLOB_PATH = "results/thresholds.json"


class ThresholdsSource(Protocol):
    def tag_exists(self, tag: str) -> bool: ...

    def blob_sha256(self, tag: str, path: str) -> str | None: ...


class GitThresholdsSource:
    """Read-only git lookup for the frozen thresholds blob."""

    def tag_exists(self, tag: str) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/{tag}"],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0

    def blob_sha256(self, tag: str, path: str) -> str | None:
        result = subprocess.run(
            ["git", "show", f"{tag}:{path}"],
            check=False,
            capture_output=True,
        )
        if result.returncode != 0:
            return None
        return hashlib.sha256(result.stdout).hexdigest()


def load_frozen_thresholds(
    thresholds_path: Path,
    *,
    source: ThresholdsSource,
) -> FrozenThresholds:
    """Load results/thresholds.json only when the tag blob matches."""
    if not thresholds_path.is_file():
        raise FactVerifyEvalError(str(thresholds_path))
    parts = thresholds_path.resolve().parts
    if len(parts) < 2 or parts[-1] != "thresholds.json" or parts[-2] != "results":
        raise FactVerifyEvalError(str(thresholds_path))
    if not source.tag_exists(TAG):
        raise FactVerifyEvalError(TAG)
    digest = hashlib.sha256(thresholds_path.read_bytes()).hexdigest()
    blob = source.blob_sha256(TAG, BLOB_PATH)
    if blob != digest:
        raise FactVerifyEvalError(f"{TAG} {digest} {blob}")
    loaded = json.loads(thresholds_path.read_text(encoding="utf-8"))
    bounds = loaded.get("bounds", {}) if isinstance(loaded, dict) else {}
    if not isinstance(bounds, dict):
        raise FactVerifyEvalError("bounds")
    return FrozenThresholds(
        tag=TAG,
        digest=digest,
        by_channel={str(key): float(value) for key, value in bounds.items()},
    )
