"""Job configuration: load, hash, and procedure comparison.

No field is filled from code. A missing, null, or DECISION_REQUIRED value raises.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import FactVerifyHarnessError

_KNOWN_METHODS = frozenset({"finetune", "GA", "GradDiff", "NPO", "RMU"})
_ROLE_METHODS = {
    "finetuned": frozenset({"finetune"}),
    "reference": frozenset({"finetune"}),
    "candidate": frozenset({"GA", "GradDiff", "NPO", "RMU"}),
}
_COMMON_KEYS = frozenset(
    {
        "role",
        "method",
        "base_role",
        "seed",
        "split",
        "spec_revision",
        "hardware_class",
        "determinism_policy",
        "digest_tolerance",
        "target_fact_id",
        "bundle_id",
        "source_bundle",
        "corpus_dir",
        "manifest",
        "output_dir",
        "tier",
        "optimizer",
        "learning_rate",
        "epochs",
        "batch_size",
        "max_length",
        "weight_decay",
    }
)
_MANIFEST_LISTS = {
    "finetune": frozenset({"train"}),
    "GA": frozenset({"forget"}),
    "GradDiff": frozenset({"forget", "retain"}),
    "NPO": frozenset({"forget"}),
    "RMU": frozenset({"forget", "retain"}),
}
_LORA_KEYS = frozenset({"r", "alpha", "dropout", "target_modules"})
_PROCEDURE_IGNORE = frozenset(
    {"role", "seed", "manifest", "split", "output_dir", "paired_finetune_config"}
)


@dataclass(frozen=True)
class JobConfig:
    """A validated job file. `raw` is the mapping that was hashed."""

    raw: dict[str, Any]
    path: Path

    @property
    def role(self) -> str:
        return str(self.raw["role"])

    @property
    def method(self) -> str:
        return str(self.raw["method"])

    @property
    def base_role(self) -> str:
        return str(self.raw["base_role"])

    @property
    def seed(self) -> int:
        return int(self.raw["seed"])

    @property
    def split(self) -> str:
        return str(self.raw["split"])

    @property
    def target_fact_id(self) -> str:
        return str(self.raw["target_fact_id"])

    @property
    def bundle_id(self) -> str:
        return str(self.raw["bundle_id"])

    @property
    def source_bundle(self) -> list[str]:
        return [str(item) for item in self.raw["source_bundle"]]

    @property
    def corpus_dir(self) -> str:
        return str(self.raw["corpus_dir"])

    @property
    def output_dir(self) -> str:
        return str(self.raw["output_dir"])

    @property
    def manifest(self) -> dict[str, list[str]]:
        manifest = self.raw["manifest"]
        return {
            str(key): [str(item) for item in value] for key, value in manifest.items()
        }

    @property
    def determinism_policy(self) -> str:
        return str(self.raw["determinism_policy"])

    @property
    def learning_rate(self) -> float:
        return float(self.raw["learning_rate"])

    @property
    def weight_decay(self) -> float:
        return float(self.raw["weight_decay"])

    @property
    def epochs(self) -> int:
        return int(self.raw["epochs"])

    @property
    def batch_size(self) -> int:
        return int(self.raw["batch_size"])

    @property
    def max_length(self) -> int:
        return int(self.raw["max_length"])


def load_job_config(path: Path) -> JobConfig:
    """Load and validate a job file. Raises FactVerifyHarnessError on any problem."""
    if not path.is_file():
        raise FactVerifyHarnessError(f"unreadable config {path}")
    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FactVerifyHarnessError(f"unreadable config {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise FactVerifyHarnessError(f"unreadable config {path}")
    _validate(loaded, str(path))
    return JobConfig(raw=loaded, path=path)


def config_hash(config: JobConfig) -> str:
    """SHA-256 of the canonical JSON of the job mapping."""
    return hash_mapping(config.raw)


def hash_mapping(mapping: dict[str, Any]) -> str:
    """SHA-256 hex of sorted compact JSON. Paths stay as written in the file."""
    payload = json.dumps(
        mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hyperparameters_of(config: JobConfig) -> dict[str, Any]:
    """The hyperparameter object copied into checkpoint metadata."""
    raw = config.raw
    out: dict[str, Any] = {
        "learning_rate": raw["learning_rate"],
        "epochs": raw["epochs"],
        "batch_size": raw["batch_size"],
        "max_length": raw["max_length"],
        "weight_decay": raw["weight_decay"],
        "optimizer": raw["optimizer"],
    }
    if config.method == "finetune":
        out["lora"] = raw["lora"]
    elif config.method == "GradDiff":
        out["retain_coeff"] = raw["retain_coeff"]
    elif config.method == "NPO":
        out["beta"] = raw["beta"]
    elif config.method == "RMU":
        out["steering_coeff"] = raw["steering_coeff"]
        out["steering_layer"] = raw["steering_layer"]
    return out


def allowed_item_ids(config: JobConfig) -> list[str]:
    """Manifest ids this method may read, in list order, without duplicates."""
    manifest = config.manifest
    lists = _MANIFEST_LISTS[config.method]
    ordered: list[str] = []
    seen: set[str] = set()
    for name in sorted(lists):
        for item_id in manifest[name]:
            if item_id not in seen:
                ordered.append(item_id)
                seen.add(item_id)
    return ordered


def procedure_differences(reference: JobConfig, finetune: JobConfig) -> list[str]:
    """Dotted paths that differ outside the closed identity allowlist.

    Ignored keys: role, seed, manifest, split, output_dir, paired_finetune_config.
    """
    return _diff(reference.raw, finetune.raw, prefix="", ignore=_PROCEDURE_IGNORE)


def _validate(mapping: dict[str, Any], label: str) -> None:
    _require_present(mapping, "method", label)
    method = mapping["method"]
    if method not in _KNOWN_METHODS:
        raise FactVerifyHarnessError(f"unknown method {method!r}")
    _require_present(mapping, "role", label)
    role = mapping["role"]
    if role not in _ROLE_METHODS:
        raise FactVerifyHarnessError(f"unknown field value {role!r} for 'role'")
    if method not in _ROLE_METHODS[role]:
        raise FactVerifyHarnessError(f"role {role!r} cannot use method {method!r}")
    required = set(_COMMON_KEYS)
    if method == "finetune":
        required.add("lora")
    if role == "reference":
        required.add("paired_finetune_config")
    if role == "candidate":
        required.add("parent_adapter")
        if method == "GradDiff":
            required.add("retain_coeff")
        elif method == "NPO":
            required.add("beta")
        elif method == "RMU":
            required.update({"steering_coeff", "steering_layer"})
    missing = sorted(key for key in required if key not in mapping)
    for key in missing:
        raise FactVerifyHarnessError(f"missing field {key!r}")
    unknown = sorted(set(mapping) - required)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    for key in required:
        _require_present(mapping, key, label)
    _validate_scalars(mapping)
    _validate_manifest(mapping, method)
    if method == "finetune":
        _validate_lora(mapping["lora"])


def _require_present(mapping: dict[str, Any], key: str, label: str) -> None:
    if (
        key not in mapping
        or mapping[key] is None
        or mapping[key] == "DECISION_REQUIRED"
    ):
        raise FactVerifyHarnessError(f"missing field {key!r} in {label}")


def _validate_scalars(mapping: dict[str, Any]) -> None:
    if mapping["optimizer"] != "adamw":
        raise FactVerifyHarnessError(
            f"unknown field value {mapping['optimizer']!r} for 'optimizer'"
        )
    if mapping["determinism_policy"] not in {"exact", "tolerant"}:
        raise FactVerifyHarnessError(
            "unknown field value "
            f"{mapping['determinism_policy']!r} for 'determinism_policy'"
        )
    tolerance = mapping["digest_tolerance"]
    if not isinstance(tolerance, str) or not _nonnegative_decimal(tolerance):
        raise FactVerifyHarnessError(
            f"missing field 'digest_tolerance' or invalid value {tolerance!r}"
        )
    if not isinstance(mapping["seed"], int) or isinstance(mapping["seed"], bool):
        raise FactVerifyHarnessError("missing field 'seed'")
    if mapping["seed"] < 0:
        raise FactVerifyHarnessError("missing field 'seed'")
    for key in ("epochs", "batch_size", "max_length"):
        value = mapping[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise FactVerifyHarnessError(f"missing field {key!r}")
    for key in ("learning_rate", "weight_decay"):
        value = mapping[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FactVerifyHarnessError(f"missing field {key!r}")
    if mapping["weight_decay"] < 0:
        raise FactVerifyHarnessError("missing field 'weight_decay'")
    if not isinstance(mapping["source_bundle"], list) or not all(
        isinstance(item, str) for item in mapping["source_bundle"]
    ):
        raise FactVerifyHarnessError("missing field 'source_bundle'")
    if mapping["method"] == "GradDiff":
        _require_number(mapping, "retain_coeff")
    if mapping["method"] == "NPO":
        _require_number(mapping, "beta")
        if mapping["beta"] == 0:
            raise FactVerifyHarnessError("missing field 'beta'")
    if mapping["method"] == "RMU":
        _require_number(mapping, "steering_coeff")
        layer = mapping["steering_layer"]
        if not isinstance(layer, int) or isinstance(layer, bool) or layer < 0:
            raise FactVerifyHarnessError("missing field 'steering_layer'")


def _require_number(mapping: dict[str, Any], key: str) -> None:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FactVerifyHarnessError(f"missing field {key!r}")


def _nonnegative_decimal(value: str) -> bool:
    if value == "0":
        return True
    return value.isdecimal() and not value.startswith("0")


def _validate_manifest(mapping: dict[str, Any], method: str) -> None:
    manifest = mapping["manifest"]
    if not isinstance(manifest, dict):
        raise FactVerifyHarnessError("missing field 'manifest'")
    required = _MANIFEST_LISTS[method]
    unknown = sorted(set(manifest) - required)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    missing = sorted(required - set(manifest))
    if missing:
        raise FactVerifyHarnessError(f"missing field {missing[0]!r}")
    for name in required:
        items = manifest[name]
        if (
            not isinstance(items, list)
            or not items
            or not all(isinstance(item, str) and item for item in items)
        ):
            raise FactVerifyHarnessError(f"missing field {name!r}")


def _validate_lora(lora: Any) -> None:
    if not isinstance(lora, dict):
        raise FactVerifyHarnessError("missing field 'lora'")
    unknown = sorted(set(lora) - _LORA_KEYS)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    missing = sorted(_LORA_KEYS - set(lora))
    if missing:
        raise FactVerifyHarnessError(f"missing field {missing[0]!r}")
    for key in ("r", "alpha"):
        value = lora[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise FactVerifyHarnessError(f"missing field {key!r}")
    dropout = lora["dropout"]
    if isinstance(dropout, bool) or not isinstance(dropout, (int, float)):
        raise FactVerifyHarnessError("missing field 'dropout'")
    if dropout < 0:
        raise FactVerifyHarnessError("missing field 'dropout'")
    modules = lora["target_modules"]
    if (
        not isinstance(modules, list)
        or not modules
        or not all(isinstance(item, str) and item for item in modules)
    ):
        raise FactVerifyHarnessError("missing field 'target_modules'")


def _diff(
    left: Any,
    right: Any,
    *,
    prefix: str,
    ignore: frozenset[str],
) -> list[str]:
    if prefix == "" and isinstance(left, dict) and isinstance(right, dict):
        paths: list[str] = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            if key in ignore:
                continue
            child = key
            if key not in left or key not in right:
                paths.append(child)
                continue
            paths.extend(_diff(left[key], right[key], prefix=child, ignore=frozenset()))
        return paths
    if isinstance(left, dict) and isinstance(right, dict):
        paths = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            child = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                paths.append(child)
                continue
            paths.extend(_diff(left[key], right[key], prefix=child, ignore=frozenset()))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if left != right:
            return [prefix]
        return []
    if left != right:
        return [prefix]
    return []
