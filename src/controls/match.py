"""Behaviour matching. Severity search stays off the evaluator budget."""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Protocol

import yaml

from src.controls.decisions import (
    DecisionRow,
    DimensionSpec,
    load_decisions,
    row_or_open,
)
from src.controls.errors import ControlError
from src.controls.registry import require_family
from src.train.config import hash_mapping
from src.train.cost import CostRecord

_BLOCK_MINIMUM = {"block_0": 2, "block_1": 3}
_ALLOWED_SPLIT = frozenset({"construction", "calibration"})
_EVAL_GROUP_SPLIT = frozenset({"calibration", "final_test"})
_FORBIDDEN = frozenset(
    {
        "target_accuracy",
        "target",
        "verdict",
        "evaluator_score",
        "evaluator_output",
        "fcr",
        "frr",
        "budget",
    }
)
_FORBIDDEN_SUFFIXES = ("verdict.json", "budget.json")
_REQUIRED_RECORD = (
    "status",
    "family",
    "implementation_id",
    "fact_id",
    "block",
    "control_ledger_id",
    "reference_ledger_ids",
    "reference_accuracies",
    "target_band",
    "selected_severity",
    "achieved_value",
    "trajectory",
    "reads",
    "hard_check",
    "wall_clock_seconds",
    "gpu_hours",
    "peak_memory_bytes",
    "config_hash",
    "seed",
    "split",
    "spec_revision",
)
_COMMON = frozenset(
    {
        "family",
        "implementation_id",
        "severity_search",
        "control_ledger_id",
        "reference_ledger_ids",
        "fact_id",
        "block",
        "seed",
        "split",
        "spec_revision",
        "decisions",
        "probes",
        "output_dir",
        "hard",
    }
)


@dataclass(frozen=True)
class SystemView:
    """Ledger fields a match is allowed to read."""

    ledger_id: str
    role: str
    fact_id: str
    split: str


@dataclass(frozen=True)
class ProbeOutput:
    """One probe output stored on the match record."""

    probe_id: str
    system_id: str
    output: str


@dataclass(frozen=True)
class Measurement:
    """Direct question-answering accuracy and the outputs that produced it."""

    accuracy: float
    outputs: tuple[ProbeOutput, ...]


class MatchLedgerPort(Protocol):
    """Read-only ledger lookup. No SQLite adapter lives here."""

    def get(self, ledger_id: str) -> SystemView | None:
        """Return the row, or None when the id is unknown."""


class MatchBehaviorPort(Protocol):
    """Scripted in tests. Study runs supply measurements without an evaluator."""

    def direct_qa_accuracy(
        self,
        system_id: str,
        fact_id: str,
        probe_ids: tuple[str, ...],
        severity: str | None,
    ) -> Measurement:
        """Accuracy on the manifest. `severity` is None for a reference."""

    def dimension_value(
        self, system_id: str, fact_id: str, name: str, severity: str
    ) -> float:
        """One hard-dimension measurement at the selected severity."""


@dataclass(frozen=True)
class TargetBand:
    """The D-54 summary applied to the reference accuracies."""

    summary: str
    low: float
    high: float
    center: float
    tolerance: str
    boundary: str


@dataclass(frozen=True)
class MatchRecord:
    """A finished match. `path` is the written match.json."""

    status: str
    family: str
    selected_severity: str | int | float
    achieved_value: float
    control_ledger_id: str
    seed: int
    config_hash: str
    hard_check: str
    target_band: TargetBand
    path: Path


@dataclass(frozen=True)
class PilotInput:
    """One row the integrity-pilot report reads. Unmatched rows are included."""

    control_ledger_id: str
    family: str
    status: str
    best_value: float
    target_band: TargetBand


@dataclass
class MatchConfig:
    """One match YAML document, plus the mapping that is hashed."""

    raw: dict[str, Any]
    path: Path
    family: str
    implementation_id: str
    severity_search: list[str | int | float]
    control_ledger_id: str
    reference_ledger_ids: list[str]
    fact_id: str
    block: str
    seed: int
    split: str
    spec_revision: str
    decisions: Path
    probes: Path
    output_dir: Path
    hard: bool


@dataclass(frozen=True)
class _Probe:
    probe_id: str
    fact_id: str
    template_group_id: str
    split: str
    kind: str


@dataclass(frozen=True)
class _Rule:
    summary: str
    tolerance: Decimal
    tolerance_text: str
    boundary: str


def load_match_config(path: Path) -> MatchConfig:
    """Load a match document. A literal target or unknown key raises."""
    if not path.is_file():
        raise ControlError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError(str(path))
    raw = {str(key): value for key, value in loaded.items()}
    _reject_forbidden(raw)
    unknown = set(raw) - _COMMON
    if unknown:
        raise ControlError(sorted(unknown)[0])
    for key, value in raw.items():
        if value is None or value == "DECISION_REQUIRED":
            raise ControlError(key)
    split = _require_str(raw, "split")
    if split in {"final_test", "final-test"}:
        raise ControlError("split")
    if split not in _ALLOWED_SPLIT:
        raise ControlError("split")
    output_dir = Path(_require_str(raw, "output_dir"))
    if ".factverify" in output_dir.resolve().parts:
        raise ControlError("output_dir")
    hard = raw.get("hard", False)
    if not isinstance(hard, bool):
        raise ControlError("hard")
    return MatchConfig(
        raw=raw,
        path=path,
        family=_require_str(raw, "family"),
        implementation_id=_require_str(raw, "implementation_id"),
        severity_search=_severities(raw.get("severity_search")),
        control_ledger_id=_require_str(raw, "control_ledger_id"),
        reference_ledger_ids=_id_list(raw.get("reference_ledger_ids")),
        fact_id=_require_str(raw, "fact_id"),
        block=_require_str(raw, "block"),
        seed=_require_int(raw, "seed"),
        split=split,
        spec_revision=_require_str(raw, "spec_revision"),
        decisions=Path(_require_str(raw, "decisions")),
        probes=Path(_require_str(raw, "probes")),
        output_dir=output_dir,
        hard=hard,
    )


def match_control(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: MatchLedgerPort,
    behavior: MatchBehaviorPort,
) -> MatchRecord:
    """Try every declared severity and write match.json, or raise with no verdict."""
    config = load_match_config(config_path)
    family = require_family(config.family)
    if config.implementation_id != family.implementation_id:
        raise ControlError(config.implementation_id)
    decisions = load_decisions(config.decisions)
    rule = _rule(row_or_open(decisions, "D-54"))
    _require_closed(decisions, "D-58")
    _d59_row = row_or_open(decisions, "D-59")
    hard_plan = _hard_plan(config.hard, _d59_row)
    # Extract waiver from the already-loaded row; avoids re-reading the file later.
    _waiver_reason: str | None = _d59_row.waiver if hard_plan == "waived" else None
    probes = _load_probes(config.probes, config.fact_id, _groups(spec_root))
    _require_references(config, ledger)
    _require_row(ledger, config.control_ledger_id, "control", config.fact_id)
    probe_ids = tuple(probe.probe_id for probe in probes)
    allowed = set(probe_ids)
    cost = CostRecord()
    cost.start()
    ref_accuracies, reads = _measure_references(behavior, config, probe_ids, allowed)
    tried, more_reads = _measure_severities(behavior, config, probe_ids, allowed)
    reads.extend(more_reads)
    band = _band(rule, ref_accuracies)
    chosen = _choose(tried, band.center)
    status = (
        "matched"
        if _inside(chosen[1], band.low, band.high, rule.boundary)
        else "unmatched"
    )
    hard_check, failed, dimensions = _apply_hard(
        hard_plan,
        row_or_open(decisions, "D-59"),
        behavior,
        config,
        str(chosen[0]),
    )
    if hard_check == "failed":
        status = "unmatched"
    cost.finish(0, 0)
    payload = _payload(
        config,
        status,
        band,
        rule,
        chosen,
        ref_accuracies,
        tried,
        reads,
        hard_check,
        failed,
        dimensions,
        cost,
        hash_mapping(config.raw),
        _waiver_reason,
    )
    destination = _write(config.output_dir, payload)
    return _record_from(payload, destination)


def compare_matches(left: MatchRecord, right: MatchRecord, decisions: Path) -> None:
    """Equal severity and status only when D-53 is closed with tolerance 0."""
    row = row_or_open(load_decisions(decisions), "D-53")
    if row.status != "closed" or row.digest_tolerance != "0":
        raise ControlError("D-53")
    if left.selected_severity != right.selected_severity or left.status != right.status:
        raise ControlError("selected_severity")


def pilot_inputs(
    records: tuple[MatchRecord, ...] | list[MatchRecord],
) -> tuple[PilotInput, ...]:
    """One pilot row per match, unmatched included."""
    return tuple(
        PilotInput(
            control_ledger_id=record.control_ledger_id,
            family=record.family,
            status=record.status,
            best_value=record.achieved_value,
            target_band=record.target_band,
        )
        for record in records
    )


def reject_dropped(
    source: tuple[MatchRecord, ...] | list[MatchRecord],
    reported: tuple[PilotInput, ...] | list[PilotInput],
) -> None:
    """Raise when an unmatched source row is missing or its reported fields differ."""
    by_id = {item.control_ledger_id: item for item in reported}
    for record in source:
        if record.status != "unmatched":
            continue
        found = by_id.get(record.control_ledger_id)
        if found is None:
            raise ControlError("unmatched")
        if found.family != record.family or found.best_value != record.achieved_value:
            raise ControlError("unmatched")
        if (
            found.target_band.low != record.target_band.low
            or found.target_band.high != record.target_band.high
            or found.target_band.summary != record.target_band.summary
        ):
            raise ControlError("unmatched")


def load_match_record(path: Path) -> MatchRecord:
    """Load match.json. A missing required field is not a finished match."""
    if not path.is_file():
        raise ControlError(str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError(str(path))
    for key in _REQUIRED_RECORD:
        if key not in loaded:
            raise ControlError(key)
    return _record_from(loaded, path)


def _reject_forbidden(raw: dict[str, Any]) -> None:
    for key in raw:
        if key in _FORBIDDEN:
            raise ControlError(key)
    for value in raw.values():
        if isinstance(value, str) and value.endswith(_FORBIDDEN_SUFFIXES):
            raise ControlError(value)


def _require_str(raw: dict[str, Any], key: str) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or value == "":
        raise ControlError(key)
    return value


def _require_int(raw: dict[str, Any], key: str) -> int:
    value = raw.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ControlError(key)
    return value


def _severities(value: object) -> list[str | int | float]:
    if not isinstance(value, list) or not value:
        raise ControlError("severity_search")
    severities: list[str | int | float] = []
    for item in value:
        if isinstance(item, bool) or not isinstance(item, (str, int, float)):
            raise ControlError("severity_search")
        if isinstance(item, str) and item == "":
            raise ControlError("severity_search")
        severities.append(item)
    return severities


def _id_list(value: object) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ControlError("reference_ledger_ids")
    ids: list[str] = []
    for item in value:
        if not isinstance(item, str) or item == "":
            raise ControlError("reference_ledger_ids")
        ids.append(item)
    return ids


def _require_closed(rows: dict[str, DecisionRow], decision_id: str) -> DecisionRow:
    row = row_or_open(rows, decision_id)
    if row.status != "closed":
        raise ControlError(decision_id)
    return row


def _rule(row: DecisionRow) -> _Rule:
    if row.status != "closed" or row.band_summary not in {"min_max", "mean"}:
        raise ControlError("D-54")
    if row.boundary not in {"inclusive", "exclusive"}:
        raise ControlError("D-54")
    if row.selection_rule != "closest_center":
        raise ControlError("D-54")
    return _Rule(
        row.band_summary,
        _decimal(row.tolerance, "D-54"),
        str(row.tolerance),
        row.boundary,
    )


def _decimal(text: str | None, name: str) -> Decimal:
    if text is None:
        raise ControlError(name)
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ControlError(name) from exc
    if value < 0 or value > 1:
        raise ControlError(name)
    return value


def _hard_plan(hard: bool, row: DecisionRow) -> str:
    if not hard:
        return "skip"
    if row.status == "open":
        if row.waiver:
            return "waived"
        raise ControlError("D-59")
    if row.waiver or not row.dimensions:
        raise ControlError("D-59")
    for dimension in row.dimensions:
        _decimal(dimension.tolerance, "D-59")
        if dimension.boundary not in {"inclusive", "exclusive"}:
            raise ControlError("D-59")
    return "check"


def _groups(spec_root: Path) -> dict[str, str]:
    path = spec_root / "closure_templates.yaml"
    if not path.is_file():
        raise ControlError("closure_templates.yaml")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not isinstance(loaded.get("groups"), list):
        raise ControlError("closure_templates.yaml")
    found: dict[str, str] = {}
    for item in loaded["groups"]:
        if not isinstance(item, dict):
            raise ControlError("closure_templates.yaml")
        group_id = item.get("group_id")
        split = item.get("split")
        if not isinstance(group_id, str) or not isinstance(split, str):
            raise ControlError("closure_templates.yaml")
        found[group_id] = split
    return found


def _load_probes(
    path: Path, fact_id: str, groups: dict[str, str]
) -> tuple[_Probe, ...]:
    if not path.is_file():
        raise ControlError("probes")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError("probes")
    items = loaded.get("probes")
    if not isinstance(items, list) or not items:
        raise ControlError("probes")
    probes: list[_Probe] = []
    seen: set[str] = set()
    for item in items:
        probe = _probe(item, fact_id, groups)
        if probe.probe_id in seen:
            raise ControlError("probe_id")
        seen.add(probe.probe_id)
        probes.append(probe)
    return tuple(probes)


def _probe(item: object, fact_id: str, groups: dict[str, str]) -> _Probe:
    if not isinstance(item, dict):
        raise ControlError("probes")
    probe_id = item.get("probe_id")
    fact = item.get("fact_id")
    group_id = item.get("template_group_id")
    split = item.get("split")
    kind = item.get("kind")
    if not all(
        isinstance(value, str) and value
        for value in (probe_id, fact, group_id, split, kind)
    ):
        raise ControlError("probes")
    if kind != "direct_qa":
        raise ControlError("kind")
    if fact != fact_id:
        raise ControlError("fact_id")
    if split not in _ALLOWED_SPLIT:
        raise ControlError("split")
    group_split = groups.get(str(group_id))
    if group_split is None or group_split in _EVAL_GROUP_SPLIT:
        raise ControlError(str(group_id))
    return _Probe(str(probe_id), str(fact), str(group_id), str(split), str(kind))


def _require_references(config: MatchConfig, ledger: MatchLedgerPort) -> None:
    ids = config.reference_ledger_ids
    if len(set(ids)) != len(ids):
        raise ControlError("reference_ledger_ids")
    minimum = _BLOCK_MINIMUM.get(config.block)
    if minimum is None:
        raise ControlError("block")
    if len(ids) < minimum:
        raise ControlError("reference_ledger_ids")
    for ledger_id in ids:
        _require_row(ledger, ledger_id, "reference", config.fact_id)


def _require_row(
    ledger: MatchLedgerPort, ledger_id: str, role: str, fact_id: str
) -> None:
    row = ledger.get(ledger_id)
    if row is None or row.role != role or row.fact_id != fact_id:
        raise ControlError(ledger_id)
    if row.split not in _ALLOWED_SPLIT:
        raise ControlError(ledger_id)


def _measure_references(
    behavior: MatchBehaviorPort,
    config: MatchConfig,
    probe_ids: tuple[str, ...],
    allowed: set[str],
) -> tuple[list[float], list[dict[str, object]]]:
    accuracies: list[float] = []
    reads: list[dict[str, object]] = []
    for ledger_id in config.reference_ledger_ids:
        accuracy, got = _measure(
            behavior, ledger_id, config.fact_id, probe_ids, None, allowed
        )
        accuracies.append(accuracy)
        reads.extend(got)
    return accuracies, reads


def _measure_severities(
    behavior: MatchBehaviorPort,
    config: MatchConfig,
    probe_ids: tuple[str, ...],
    allowed: set[str],
) -> tuple[list[tuple[str | int | float, float]], list[dict[str, object]]]:
    tried: list[tuple[str | int | float, float]] = []
    reads: list[dict[str, object]] = []
    for severity in config.severity_search:
        accuracy, got = _measure(
            behavior,
            config.control_ledger_id,
            config.fact_id,
            probe_ids,
            str(severity),
            allowed,
        )
        tried.append((severity, accuracy))
        reads.extend(got)
    return tried, reads


def _measure(
    behavior: MatchBehaviorPort,
    system_id: str,
    fact_id: str,
    probe_ids: tuple[str, ...],
    severity: str | None,
    allowed: set[str],
) -> tuple[float, list[dict[str, object]]]:
    measurement = behavior.direct_qa_accuracy(system_id, fact_id, probe_ids, severity)
    reads: list[dict[str, object]] = []
    for item in measurement.outputs:
        if item.probe_id not in allowed:
            raise ControlError(item.probe_id)
        reads.append(
            {
                "probe_id": item.probe_id,
                "system_id": item.system_id,
                "severity": severity,
                "output": item.output,
            }
        )
    return float(measurement.accuracy), reads


def _band(rule: _Rule, accuracies: list[float]) -> TargetBand:
    values = [_as_decimal(accuracy) for accuracy in accuracies]
    if rule.summary == "min_max":
        raw_low = min(values)
        raw_high = max(values)
        center = (raw_low + raw_high) / 2
        low = raw_low - rule.tolerance
        high = raw_high + rule.tolerance
    else:
        center = sum(values, Decimal(0)) / Decimal(len(values))
        low = center - rule.tolerance
        high = center + rule.tolerance
    return TargetBand(
        rule.summary,
        float(low),
        float(high),
        float(center),
        rule.tolerance_text,
        rule.boundary,
    )


def _choose(
    tried: list[tuple[str | int | float, float]], center: float
) -> tuple[str | int | float, Decimal]:
    middle = _as_decimal(center)
    # Tie-break: earlier index in the declared search list wins.
    # This assumption should be recorded in D-54's selection_rule when it closes.
    index = min(
        range(len(tried)),
        key=lambda item: (abs(_as_decimal(tried[item][1]) - middle), item),
    )
    severity, accuracy = tried[index]
    return severity, _as_decimal(accuracy)


def _inside(value: Decimal, low: float, high: float, boundary: str) -> bool:
    start = _as_decimal(low)
    stop = _as_decimal(high)
    if boundary == "inclusive":
        return start <= value <= stop
    if boundary == "exclusive":
        return start < value < stop
    raise ControlError("D-54")


def _apply_hard(
    plan: str,
    row: DecisionRow,
    behavior: MatchBehaviorPort,
    config: MatchConfig,
    severity: str,
) -> tuple[str, str | None, list[dict[str, object]]]:
    if plan == "skip":
        return "not_required", None, []
    if plan == "waived":
        return "waived", None, []
    failed: str | None = None
    stored: list[dict[str, object]] = []
    dimensions = row.dimensions or ()
    for dimension in dimensions:
        value = behavior.dimension_value(
            config.control_ledger_id, config.fact_id, dimension.name, severity
        )
        ok = _dimension_inside(value, dimension)
        if not ok and failed is None:
            failed = dimension.name
        stored.append(
            {
                "name": dimension.name,
                "value": float(value),
                "tolerance": dimension.tolerance,
                "boundary": dimension.boundary,
                "inside": ok,
            }
        )
    if failed is None:
        return "passed", None, stored
    return "failed", failed, stored


def _dimension_inside(value: float, dimension: DimensionSpec) -> bool:
    # D-59 is open. Until it closes, each dimension is modelled as a deviation-from-zero
    # metric: gap = abs(measured_value). If D-59 specifies a non-zero target or a
    # band-style comparison, this formula must be updated to match.
    gap = abs(_as_decimal(value))
    tolerance = _decimal(dimension.tolerance, "D-59")
    if dimension.boundary == "inclusive":
        return gap <= tolerance
    if dimension.boundary == "exclusive":
        return gap < tolerance
    raise ControlError("D-59")


def _as_decimal(value: float) -> Decimal:
    return Decimal(str(value))


def _payload(
    config: MatchConfig,
    status: str,
    band: TargetBand,
    rule: _Rule,
    chosen: tuple[str | int | float, Decimal],
    ref_accuracies: list[float],
    tried: list[tuple[str | int | float, float]],
    reads: list[dict[str, object]],
    hard_check: str,
    failed: str | None,
    dimensions: list[dict[str, object]],
    cost: CostRecord,
    config_hash: str,
    waiver_reason: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "status": status,
        "family": config.family,
        "implementation_id": config.implementation_id,
        "fact_id": config.fact_id,
        "block": config.block,
        "control_ledger_id": config.control_ledger_id,
        "reference_ledger_ids": list(config.reference_ledger_ids),
        "reference_accuracies": ref_accuracies,
        "target_band": {
            "summary": band.summary,
            "low": band.low,
            "high": band.high,
            "center": band.center,
            "tolerance": rule.tolerance_text,
            "boundary": rule.boundary,
        },
        "selected_severity": chosen[0],
        "achieved_value": float(chosen[1]),
        "trajectory": [
            {"severity": severity, "accuracy": accuracy} for severity, accuracy in tried
        ],
        "reads": reads,
        "hard_check": hard_check,
        "wall_clock_seconds": cost.wall_clock_seconds,
        "gpu_hours": cost.gpu_hours,
        "peak_memory_bytes": cost.peak_memory_bytes,
        "config_hash": config_hash,
        "seed": config.seed,
        "split": config.split,
        "spec_revision": config.spec_revision,
    }
    if dimensions:
        payload["dimensions"] = dimensions
    if failed is not None:
        payload["failed_dimension"] = failed
    if hard_check == "waived":
        payload["waiver_reason"] = waiver_reason
    return payload


def _write(output_dir: Path, payload: dict[str, object]) -> Path:
    if ".factverify" in output_dir.resolve().parts:
        raise ControlError("output_dir")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / "match.json"
    destination.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return destination


def _record_from(payload: dict[str, Any], path: Path) -> MatchRecord:
    band_raw = payload["target_band"]
    if not isinstance(band_raw, dict):
        raise ControlError("target_band")
    for key in ("summary", "low", "high", "center", "tolerance", "boundary"):
        if key not in band_raw:
            raise ControlError("target_band")
    severity = payload["selected_severity"]
    if isinstance(severity, bool) or not isinstance(severity, (str, int, float)):
        raise ControlError("selected_severity")
    return MatchRecord(
        status=str(payload["status"]),
        family=str(payload["family"]),
        selected_severity=severity,
        achieved_value=float(payload["achieved_value"]),
        control_ledger_id=str(payload["control_ledger_id"]),
        seed=int(payload["seed"]),
        config_hash=str(payload["config_hash"]),
        hard_check=str(payload["hard_check"]),
        target_band=TargetBand(
            summary=str(band_raw["summary"]),
            low=float(band_raw["low"]),
            high=float(band_raw["high"]),
            center=float(band_raw["center"]),
            tolerance=str(band_raw["tolerance"]),
            boundary=str(band_raw["boundary"]),
        ),
        path=path,
    )
