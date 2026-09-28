"""Parse and validate models.yaml for a requested role."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import FactVerifyLoaderError

_REQUIRED_FIELDS = (
    "repo_id",
    "revision",
    "tokenizer_revision",
    "dtype",
    "attn_impl",
    "files",
)


@dataclass(frozen=True)
class ModelSpec:
    role: str
    repo_id: str
    revision: str
    tokenizer_revision: str
    dtype: str
    attn_impl: str
    files: dict[str, str]  # filename -> SHA-256 hex digest
    local_dir: Path | None  # optional explicit local directory (resolved absolute)


def load_model_spec(role: str, spec_root: Path) -> ModelSpec:
    """Parse models.yaml and return the ModelSpec for the requested role.

    Raises FactVerifyLoaderError if:
    - models.yaml is missing or unparseable
    - role is not declared
    - any required field is missing or null
    """
    models_yaml = spec_root / "models.yaml"
    if not models_yaml.exists():
        raise FactVerifyLoaderError(f"models.yaml not found at {models_yaml}")

    try:
        with models_yaml.open() as f:
            data: dict[str, Any] = yaml.safe_load(f)
    except yaml.YAMLError as exc:
        raise FactVerifyLoaderError(f"failed to parse {models_yaml}: {exc}") from exc

    if not isinstance(data, dict) or role not in data:
        raise FactVerifyLoaderError(f"unknown role {role!r} in {models_yaml}")

    entry = data[role]
    if not isinstance(entry, dict):
        raise FactVerifyLoaderError(
            f"role {role!r} entry is not a mapping in {models_yaml}"
        )

    for field in _REQUIRED_FIELDS:
        if field not in entry or entry[field] is None:
            raise FactVerifyLoaderError(
                f"unresolved spec field {field!r} for role {role!r} in {models_yaml}"
            )

    files = entry["files"]
    if not isinstance(files, dict) or not files:
        raise FactVerifyLoaderError(
            f"field 'files' for role {role!r} must be a non-empty mapping"
            f" in {models_yaml}"
        )

    local_dir: Path | None = None
    if "local_dir" in entry and entry["local_dir"] is not None:
        raw = Path(str(entry["local_dir"]))
        local_dir = (
            (spec_root / raw).resolve() if not raw.is_absolute() else raw.resolve()
        )

    return ModelSpec(
        role=role,
        repo_id=str(entry["repo_id"]),
        revision=str(entry["revision"]),
        tokenizer_revision=str(entry["tokenizer_revision"]),
        dtype=str(entry["dtype"]),
        attn_impl=str(entry["attn_impl"]),
        files={k: str(v) for k, v in files.items()},
        local_dir=local_dir,
    )
