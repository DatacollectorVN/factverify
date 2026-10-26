"""Configuration loading, validation, overrides, and hashing (FV-ARCH-003).

Rules:
  - Missing required values, null, and unknown enum values fail closed.
  - Paths are resolved relative to repository root.
  - The resolved configuration is serializable as canonical JSON for hashing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .errors import ConfigurationError
from .types import AppConfig, JobSection, RuntimeSection

_KNOWN_TASKS = frozenset({"train", "evaluate", "gate"})


# ── Public API ──────────────────────────────────────────────────────────────


def load_config(path: Path) -> AppConfig:
    """Load, validate, and return an immutable AppConfig from a YAML file."""
    if not path.is_file():
        raise ConfigurationError(f"configuration file not found: {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"configuration must be a YAML mapping: {path}")
    _validate_envelope(raw, str(path))
    return _build_config(raw, path)


def apply_overrides(config: AppConfig, overrides: list[str]) -> AppConfig:
    """Apply ``--set dotted.path=value`` overrides, returning a new AppConfig.

    Overrides are applied to the raw mapping before re-validation.
    """
    if not overrides:
        return config
    raw = dict(config.raw)
    for override in overrides:
        if "=" not in override:
            raise ConfigurationError(f"invalid override (missing '='): {override}")
        dotted, _, value_str = override.partition("=")
        keys = dotted.strip().split(".")
        _set_nested(raw, keys, _parse_value(value_str.strip()))
    _validate_envelope(raw, "override")
    return _build_config(raw, config.source_path)


def config_hash(config: AppConfig) -> str:
    """SHA-256 hex digest of the canonical JSON representation."""
    return hash_mapping(config.raw)


def hash_mapping(mapping: dict[str, Any]) -> str:
    """SHA-256 hex of sorted compact JSON. Matches ``src.train.config.hash_mapping``."""
    payload = json.dumps(
        mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Internal helpers ────────────────────────────────────────────────────────


def _validate_envelope(raw: dict[str, Any], label: str) -> None:
    """Validate the common envelope fields required by all task types."""
    # schema_version
    sv = raw.get("schema_version")
    if sv is None:
        raise ConfigurationError(f"missing 'schema_version' in {label}")
    if not isinstance(sv, int) or sv < 1:
        raise ConfigurationError(
            f"'schema_version' must be a positive integer in {label}"
        )

    # task
    task = raw.get("task")
    if task is None:
        raise ConfigurationError(f"missing 'task' in {label}")
    if task not in _KNOWN_TASKS:
        raise ConfigurationError(
            f"unknown task {task!r} in {label}; expected one of {sorted(_KNOWN_TASKS)}"
        )

    # job section
    job = raw.get("job")
    if not isinstance(job, dict):
        raise ConfigurationError(f"missing section 'job' in {label}")
    for key in ("name", "role", "split"):
        if not isinstance(job.get(key), str) or not job[key]:
            raise ConfigurationError(f"missing field 'job.{key}' in {label}")

    # runtime section
    runtime = raw.get("runtime")
    if not isinstance(runtime, dict):
        raise ConfigurationError(f"missing section 'runtime' in {label}")
    if not isinstance(runtime.get("output_root"), str) or not runtime["output_root"]:
        raise ConfigurationError(f"missing field 'runtime.output_root' in {label}")


def _build_config(raw: dict[str, Any], source_path: Path | None) -> AppConfig:
    """Construct an AppConfig from a validated raw mapping."""
    job_raw = raw["job"]
    seeds_raw = job_raw.get("seeds")
    if isinstance(seeds_raw, list):
        seeds = [int(s) for s in seeds_raw]
    elif isinstance(job_raw.get("seed"), int):
        seeds = [int(job_raw["seed"])]
    else:
        seeds = [0]

    runtime_raw = raw.get("runtime", {})
    return AppConfig(
        schema_version=int(raw["schema_version"]),
        task=str(raw["task"]),
        job=JobSection(
            name=str(job_raw["name"]),
            role=str(job_raw["role"]),
            split=str(job_raw["split"]),
            seeds=seeds,
        ),
        runtime=RuntimeSection(
            output_root=str(runtime_raw.get("output_root", ".factverify_internal")),
            device=str(runtime_raw.get("device", "auto")),
            deterministic=bool(runtime_raw.get("deterministic", True)),
            resume=bool(runtime_raw.get("resume", True)),
        ),
        raw=raw,
        source_path=source_path,
    )


def _set_nested(mapping: dict[str, Any], keys: list[str], value: Any) -> None:
    """Set a value at a dotted path in a nested dict."""
    current = mapping
    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]
    current[keys[-1]] = value


def _parse_value(value_str: str) -> Any:
    """Parse a CLI override value string into a Python value."""
    if value_str.lower() == "true":
        return True
    if value_str.lower() == "false":
        return False
    if value_str.lower() == "null" or value_str.lower() == "none":
        return None
    try:
        return int(value_str)
    except ValueError:
        pass
    try:
        return float(value_str)
    except ValueError:
        pass
    return value_str
