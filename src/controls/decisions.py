"""Caller-supplied decision records. Open rows are not filled in."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.controls.errors import ControlError
from src.decisions.diagnostic import format_diagnostic_by_id

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

_CONSUMING_OP: dict[str, str] = {
    "D-53": "determinism check",
    "D-54": "behaviour matching",
    "D-55": "control registry",
    "D-58": "behaviour matching probes",
    "D-59": "hard-control dimensions",
    "D-61": "untouched-model check",
}

_IDS = ("D-53", "D-54", "D-55", "D-58", "D-59", "D-61")


@dataclass(frozen=True)
class DimensionSpec:
    """One hard-control dimension. Present only when the record lists it."""

    name: str
    tolerance: str
    boundary: str


@dataclass(frozen=True)
class DecisionRow:
    """One decision. Optional fields are present only when the record supplies them."""

    decision_id: str
    status: str
    digest_tolerance: str | None = None
    max_abs_gap: str | None = None
    min_count: int | None = None
    mechanism_layer: str | None = None
    band_summary: str | None = None
    tolerance: str | None = None
    boundary: str | None = None
    selection_rule: str | None = None
    dimensions: tuple[DimensionSpec, ...] | None = None
    waiver: str | None = None


def load_decisions(path: Path) -> dict[str, DecisionRow]:
    """Load decision rows. A missing id is treated as open by the caller."""
    if not path.is_file():
        raise ControlError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    rows: object
    if isinstance(loaded, dict) and "decisions" in loaded:
        rows = loaded["decisions"]
    else:
        rows = loaded
    if not isinstance(rows, list):
        raise ControlError(str(path))
    found: dict[str, DecisionRow] = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ControlError(str(path))
        decision_id = item.get("decision_id")
        status = item.get("status")
        if not isinstance(decision_id, str) or decision_id not in _IDS:
            raise ControlError(str(path))
        if status not in {"open", "closed"}:
            raise ControlError(
                format_diagnostic_by_id(
                    str(decision_id),
                    _CATALOG,
                    consuming_op=_CONSUMING_OP.get(str(decision_id), "controls"),
                )
            )
        found[decision_id] = DecisionRow(
            decision_id=decision_id,
            status=str(status),
            digest_tolerance=_optional_str(item, "digest_tolerance"),
            max_abs_gap=_optional_str(item, "max_abs_gap"),
            min_count=_optional_int(item, "min_count"),
            mechanism_layer=_optional_str(item, "mechanism_layer"),
            band_summary=_optional_str(item, "band_summary"),
            tolerance=_optional_str(item, "tolerance"),
            boundary=_optional_str(item, "boundary"),
            selection_rule=_optional_str(item, "selection_rule"),
            dimensions=_dimensions(item),
            waiver=_optional_str(item, "waiver"),
        )
    return found


def row_or_open(rows: dict[str, DecisionRow], decision_id: str) -> DecisionRow:
    """Return the stored row, or an open row when the id was absent."""
    return rows.get(decision_id, DecisionRow(decision_id=decision_id, status="open"))


def _optional_str(item: dict[object, object], key: str) -> str | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    raise ControlError(key)


def _dimensions(item: dict[object, object]) -> tuple[DimensionSpec, ...] | None:
    value = item.get("dimensions")
    if value is None:
        return None
    if not isinstance(value, list):
        raise ControlError("dimensions")
    specs: list[DimensionSpec] = []
    for entry in value:
        if not isinstance(entry, dict):
            raise ControlError("dimensions")
        name = entry.get("name")
        tolerance = entry.get("tolerance")
        boundary = entry.get("boundary")
        if not isinstance(name, str) or name == "":
            raise ControlError("dimensions")
        if not isinstance(tolerance, str) or not isinstance(boundary, str):
            raise ControlError("dimensions")
        specs.append(DimensionSpec(name, tolerance, boundary))
    return tuple(specs)


def _optional_int(item: dict[object, object], key: str) -> int | None:
    value = item.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlError(key)
    return value
