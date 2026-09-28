"""Caller-supplied D-60 rows. An open row does not choose a key field."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.cache.errors import CacheError


@dataclass(frozen=True)
class CacheDecision:
    """D-60. The flag is set only when the row is closed."""

    status: str
    include_software_versions: bool | None = None


def load_decision(path: Path, decision_id: str) -> CacheDecision:
    """Return D-60. A missing id is open. `maybe` raises."""
    if decision_id != "D-60":
        raise CacheError(decision_id)
    if not path.is_file():
        raise CacheError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("decisions"), list):
        raise CacheError(str(path))
    item: dict[str, object] | None = None
    for entry in loaded["decisions"]:
        if not isinstance(entry, dict):
            raise CacheError(str(path))
        if entry.get("decision_id") != "D-60":
            raise CacheError(str(entry.get("decision_id")))
        item = entry
    if item is None:
        return CacheDecision(status="open")
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise CacheError("D-60")
    if status == "open":
        return CacheDecision(status="open")
    flag = item.get("include_software_versions")
    if not isinstance(flag, bool):
        raise CacheError("D-60")
    return CacheDecision(status="closed", include_software_versions=flag)
