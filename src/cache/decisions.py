"""Caller-supplied D-60 rows. An open row does not choose a key field."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.cache.errors import CacheError
from src.decisions.diagnostic import format_diagnostic_by_id

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"


@dataclass(frozen=True)
class CacheDecision:
    """D-60. The flag is set only when the row is closed."""

    status: str
    include_software_versions: bool | None = None


def load_decision(path: Path, decision_id: str) -> CacheDecision:
    """Return D-60. A missing id is open. `maybe` raises."""
    if decision_id != "D-60":
        raise CacheError(
            format_diagnostic_by_id(
                decision_id, _CATALOG, consuming_op="cache key construction"
            )
        )
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
        raise CacheError(
            format_diagnostic_by_id(
                "D-60", _CATALOG, consuming_op="cache key construction"
            )
        )
    if status == "open":
        return CacheDecision(status="open")
    flag = item.get("include_software_versions")
    if not isinstance(flag, bool):
        raise CacheError(
            format_diagnostic_by_id(
                "D-60",
                _CATALOG,
                missing_field="include_software_versions",
                consuming_op="cache key construction",
            )
        )
    return CacheDecision(status="closed", include_software_versions=flag)
