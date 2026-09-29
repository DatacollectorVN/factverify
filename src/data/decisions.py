"""Caller-supplied D-65 and D-68 rows. An open row refuses the run."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import yaml

from src.data.errors import DataError
from src.decisions.diagnostic import format_diagnostic_by_id

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

_CONTAMINATION = frozenset({"regenerate", "switch_model", "proceed"})


@dataclass(frozen=True)
class D65Decision:
    """Closed guessing-baseline record."""

    baseline: str
    threshold: float
    comparison: str
    cell_score: str
    decoding_seeds: tuple[int, ...]
    do_sample: bool
    max_new_tokens: int
    contamination_trigger: float
    contamination_decision: str | None
    note: str


@dataclass(frozen=True)
class D68Decision:
    """Closed Block 0 split-count record."""

    block: str
    construction: int
    calibration: int
    assign_final_test: bool
    relations: tuple[str, ...]


def load_d65(path: Path) -> D65Decision:
    """Return D-65. Missing, open, or blank fields raise DataError."""
    item = _item(path, "D-65")
    _require_closed(item, "D-65", "exclusion gate")
    baseline = _text(item, "baseline", "D-65")
    if baseline != "random_choice":
        raise DataError("baseline")
    threshold = _finite(item, "threshold", "D-65")
    comparison = _text(item, "comparison", "D-65")
    if comparison != "any_direction":
        raise DataError("comparison")
    cell_score = _text(item, "cell_score", "D-65")
    if cell_score != "alias_contains":
        raise DataError("cell_score")
    seeds = _seeds(item)
    decoding = item.get("decoding")
    if not isinstance(decoding, dict):
        raise DataError("decoding")
    do_sample = decoding.get("do_sample")
    if not isinstance(do_sample, bool):
        raise DataError("do_sample")
    max_new = decoding.get("max_new_tokens")
    if isinstance(max_new, bool) or not isinstance(max_new, int) or max_new < 1:
        raise DataError("max_new_tokens")
    trigger = _finite(item, "contamination_trigger", "D-65")
    decision, note = _contamination(item)
    return D65Decision(
        baseline=baseline,
        threshold=threshold,
        comparison=comparison,
        cell_score=cell_score,
        decoding_seeds=seeds,
        do_sample=do_sample,
        max_new_tokens=max_new,
        contamination_trigger=trigger,
        contamination_decision=decision,
        note=note,
    )


def load_d68(path: Path) -> D68Decision:
    """Return D-68. Open rows and final-test assignment raise DataError."""
    item = _item(path, "D-68")
    _require_closed(item, "D-68", "split construction")
    counts = item.get("counts")
    if not isinstance(counts, dict):
        raise DataError("counts")
    construction = _positive(counts, "construction")
    calibration = _positive(counts, "calibration")
    assign = item.get("assign_final_test")
    if not isinstance(assign, bool):
        raise DataError("assign_final_test")
    if assign:
        raise DataError("assign_final_test")
    relations = item.get("relations")
    if not isinstance(relations, list) or not relations:
        raise DataError("relations")
    if any(not isinstance(name, str) or name == "" for name in relations):
        raise DataError("relations")
    block = _text(item, "block", "D-68")
    return D68Decision(
        block=block,
        construction=construction,
        calibration=calibration,
        assign_final_test=assign,
        relations=tuple(str(name) for name in relations),
    )


def _item(path: Path, decision_id: str) -> dict[str, object]:
    if not path.is_file():
        raise DataError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise DataError(format_diagnostic_by_id(decision_id, _CATALOG))
    rows = loaded.get("decisions")
    if not isinstance(rows, list):
        raise DataError(format_diagnostic_by_id(decision_id, _CATALOG))
    for entry in rows:
        if isinstance(entry, dict) and entry.get("decision_id") == decision_id:
            return entry
    raise DataError(format_diagnostic_by_id(decision_id, _CATALOG))


def _require_closed(
    item: dict[str, object], decision_id: str, consuming_op: str
) -> None:
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise DataError(
            format_diagnostic_by_id(decision_id, _CATALOG, consuming_op=consuming_op)
        )
    if status == "open":
        raise DataError(
            format_diagnostic_by_id(decision_id, _CATALOG, consuming_op=consuming_op)
        )


def _text(item: dict[str, object], field: str, decision_id: str) -> str:
    value = item.get(field)
    if not isinstance(value, str) or value == "":
        raise DataError(field if field != "baseline" else decision_id)
    return value


def _finite(item: dict[str, object], field: str, decision_id: str) -> float:
    value = item.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DataError(field)
    number = float(value)
    if not math.isfinite(number):
        raise DataError(field)
    return number


def _seeds(item: dict[str, object]) -> tuple[int, ...]:
    raw = item.get("decoding_seeds")
    if not isinstance(raw, list) or not raw:
        raise DataError("decoding_seeds")
    seeds: list[int] = []
    for entry in raw:
        if isinstance(entry, bool) or not isinstance(entry, int):
            raise DataError("decoding_seeds")
        seeds.append(entry)
    return tuple(seeds)


def _contamination(item: dict[str, object]) -> tuple[str | None, str]:
    decision = item.get("contamination_decision")
    note = item.get("note", "")
    if not isinstance(note, str):
        raise DataError("note")
    if decision is None:
        return None, note
    if not isinstance(decision, str) or decision not in _CONTAMINATION:
        raise DataError("contamination_decision")
    if note == "":
        raise DataError("note")
    return decision, note


def _positive(counts: dict[str, object], field: str) -> int:
    value = counts.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DataError(field)
    return value
