"""Caller-supplied statistics decisions. Missing fields stay missing."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.stats.errors import StatsError

_ACCEPTED = frozenset({"D-03", "D-05", "D-06", "D-07", "D-08", "D-10", "D-57"})


@dataclass(frozen=True)
class StatsDecision:
    """One decision row. Closed fields are whatever the file recorded."""

    decision_id: str
    status: str
    fields: dict[str, object]


def load_decision(path: Path, decision_id: str) -> StatsDecision:
    """Return one accepted id. A missing id is open. Other ids raise."""
    if decision_id not in _ACCEPTED:
        raise StatsError(decision_id)
    found = _rows(path)
    item = found.get(decision_id)
    if item is None:
        return StatsDecision(decision_id, "open", {})
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise StatsError(decision_id)
    if status == "open":
        return StatsDecision(decision_id, "open", {})
    fields = {
        key: value
        for key, value in item.items()
        if key not in {"decision_id", "status"}
    }
    return StatsDecision(decision_id, "closed", fields)


def _rows(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        raise StatsError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("decisions"), list):
        raise StatsError(str(path))
    found: dict[str, dict[str, object]] = {}
    for item in loaded["decisions"]:
        if not isinstance(item, dict):
            raise StatsError(str(path))
        decision_id = item.get("decision_id")
        if not isinstance(decision_id, str) or decision_id not in _ACCEPTED:
            raise StatsError(str(decision_id))
        found[decision_id] = item
    return found
