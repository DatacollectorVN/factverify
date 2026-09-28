"""Caller-supplied D-56 rows. An open row is not given a tier list."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.decisions.diagnostic import format_diagnostic_by_id
from src.ledger.errors import LedgerError

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"


@dataclass(frozen=True)
class TierDecision:
    """D-56. `tiers` is set only when the row is closed and well formed."""

    status: str
    tiers: tuple[str, ...] | None = None


def load_decision(path: Path, decision_id: str) -> TierDecision:
    """Return one decision. Ledger records only D-56. A missing id is open."""
    if decision_id != "D-56":
        raise LedgerError(
            format_diagnostic_by_id(
                decision_id, _CATALOG, consuming_op="tier assignment"
            )
        )
    return load_d56(path)


def load_d56(path: Path) -> TierDecision:
    """Return D-56. A missing id is open. A closed row needs a non-empty tier list."""
    rows = _rows(path)
    item = rows.get("D-56")
    if item is None:
        return TierDecision(status="open")
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise LedgerError(
            format_diagnostic_by_id("D-56", _CATALOG, consuming_op="tier assignment")
        )
    if status == "open":
        return TierDecision(status="open")
    tiers = item.get("tiers")
    if not isinstance(tiers, list) or not tiers:
        raise LedgerError(
            format_diagnostic_by_id(
                "D-56",
                _CATALOG,
                missing_field="tiers",
                consuming_op="tier assignment",
            )
        )
    if any(not isinstance(entry, str) or entry == "" for entry in tiers):
        raise LedgerError(
            format_diagnostic_by_id(
                "D-56",
                _CATALOG,
                missing_field="tiers",
                consuming_op="tier assignment",
            )
        )
    return TierDecision(status="closed", tiers=tuple(tiers))


def _rows(path: Path) -> dict[str, dict[str, object]]:
    if not path.is_file():
        raise LedgerError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("decisions"), list):
        raise LedgerError(str(path))
    found: dict[str, dict[str, object]] = {}
    for item in loaded["decisions"]:
        if not isinstance(item, dict):
            raise LedgerError(str(path))
        decision_id = item.get("decision_id")
        if not isinstance(decision_id, str):
            raise LedgerError(str(path))
        if decision_id != "D-56":
            raise LedgerError(decision_id)
        found[decision_id] = item
    return found
