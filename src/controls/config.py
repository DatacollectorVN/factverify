"""Fail-closed control configuration. Severity is stored and never applied."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.controls.errors import ControlError

_COMMON = frozenset(
    {
        "family",
        "implementation_id",
        "severity",
        "parent_ledger_id",
        "fact_id",
        "seed",
        "split",
        "spec_revision",
        "decisions",
        "fact_contract",
        "output_dir",
    }
)
_FAMILY_FIELDS = {
    "refusal": frozenset({"refusal_text"}),
    "output_filter": frozenset(),
    "answer_replacement": frozenset({"replacement_text"}),
    "logit_masking": frozenset(),
    "template_specific": frozenset({"refusal_text", "suppressed_group_ids"}),
    "reversible_steering": frozenset({"vector_path"}),
    "targeted_damage": frozenset({"method", "bucket", "manifest"}),
    "broad_destruction": frozenset({"method", "bucket", "manifest"}),
    "untouched": frozenset(),
}
_FORBIDDEN = frozenset({"verdict", "evaluator_score", "evaluator_output", "fcr", "frr"})
_FORBIDDEN_SUFFIXES = ("verdict.json", "budget.json")
_SPLITS = frozenset({"construction", "calibration", "final_test"})
_METHODS = frozenset({"GA", "GradDiff", "NPO", "RMU"})


@dataclass
class ControlConfig:
    """One control YAML document, plus the mapping that is hashed."""

    raw: dict[str, Any]
    path: Path
    family: str
    implementation_id: str
    severity: str | int | float | dict[str, Any]
    parent_ledger_id: str
    fact_id: str
    seed: int
    split: str
    spec_revision: str
    decisions: Path
    fact_contract: Path
    output_dir: Path
    refusal_text: str | None
    replacement_text: str | None
    suppressed_group_ids: list[str] | None
    vector_path: Path | None
    method: str | None
    bucket: str | None
    manifest: list[str] | None


def load_config(path: Path) -> ControlConfig:
    """Load YAML. Missing, null, and `DECISION_REQUIRED` values raise."""
    if not path.is_file():
        raise ControlError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError(str(path))
    raw = {str(key): value for key, value in loaded.items()}
    _reject_forbidden(raw)
    family = _require_str(raw, "family")
    allowed = _FAMILY_FIELDS.get(family)
    if allowed is None:
        raise ControlError(family)
    unknown = set(raw) - _COMMON - allowed
    if unknown:
        raise ControlError(sorted(unknown)[0])
    for key, value in raw.items():
        if value is None or value == "DECISION_REQUIRED":
            raise ControlError(key)
    split = _require_str(raw, "split")
    if split == "final-test":
        split = "final_test"
    if split not in _SPLITS:
        raise ControlError("split")
    config = ControlConfig(
        raw=raw,
        path=path,
        family=family,
        implementation_id=_require_str(raw, "implementation_id"),
        severity=_severity(raw.get("severity")),
        parent_ledger_id=_require_str(raw, "parent_ledger_id"),
        fact_id=_require_str(raw, "fact_id"),
        seed=_require_int(raw, "seed"),
        split=split,
        spec_revision=_require_str(raw, "spec_revision"),
        decisions=Path(_require_str(raw, "decisions")),
        fact_contract=Path(_require_str(raw, "fact_contract")),
        output_dir=Path(_require_str(raw, "output_dir")),
        refusal_text=_optional_text(raw, "refusal_text", family),
        replacement_text=_optional_text(raw, "replacement_text", family),
        suppressed_group_ids=_groups(raw, family),
        vector_path=_vector(raw, family),
        method=_method(raw, family),
        bucket=_bucket(raw, family),
        manifest=_manifest(raw, family),
    )
    return config


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


def _severity(value: object) -> str | int | float | dict[str, Any]:
    if isinstance(value, bool) or value is None:
        raise ControlError("severity")
    if isinstance(value, (str, int, float)):
        return value
    if isinstance(value, dict):
        return {str(key): item for key, item in value.items()}
    raise ControlError("severity")


def _optional_text(raw: dict[str, Any], key: str, family: str) -> str | None:
    if key not in _FAMILY_FIELDS[family]:
        return None
    return _require_str(raw, key)


def _groups(raw: dict[str, Any], family: str) -> list[str] | None:
    if "suppressed_group_ids" not in _FAMILY_FIELDS[family]:
        return None
    value = raw.get("suppressed_group_ids")
    if not isinstance(value, list) or not value:
        raise ControlError("suppressed_group_ids")
    groups: list[str] = []
    for item in value:
        if not isinstance(item, str) or item == "":
            raise ControlError("suppressed_group_ids")
        groups.append(item)
    return groups


def _vector(raw: dict[str, Any], family: str) -> Path | None:
    if "vector_path" not in _FAMILY_FIELDS[family]:
        return None
    return Path(_require_str(raw, "vector_path"))


def _method(raw: dict[str, Any], family: str) -> str | None:
    if "method" not in _FAMILY_FIELDS[family]:
        return None
    method = _require_str(raw, "method")
    if method not in _METHODS:
        raise ControlError(method)
    return method


def _bucket(raw: dict[str, Any], family: str) -> str | None:
    if "bucket" not in _FAMILY_FIELDS[family]:
        return None
    bucket = _require_str(raw, "bucket")
    if family == "targeted_damage" and bucket not in {"same_subject", "same_relation"}:
        raise ControlError(bucket)
    if family == "broad_destruction" and bucket != "global":
        raise ControlError(bucket)
    return bucket


def _manifest(raw: dict[str, Any], family: str) -> list[str] | None:
    if "manifest" not in _FAMILY_FIELDS[family]:
        return None
    value = raw.get("manifest")
    if not isinstance(value, list) or not value:
        raise ControlError("manifest")
    items: list[str] = []
    for item in value:
        if not isinstance(item, str) or item == "":
            raise ControlError("manifest")
        items.append(item)
    return items
