"""Parse and validate model policy and flat model configurations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from src.data.digests import sha256_file

from .errors import FactVerifyLoaderError

_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class ModelSpec:
    role: str
    repo_id: str
    model_revision: str
    tokenizer_revision: str
    dtype: str
    attn_impl: str
    local_dir: Path | None  # optional explicit local directory (resolved absolute)


def config_digest(path: Path) -> str:
    """Fingerprint of the configuration file bytes."""
    return "sha256:" + sha256_file(path)


@dataclass(frozen=True)
class ModelConfig:
    """Flat model configuration — one model per file, no roles wrapper."""

    vendor: str
    repo_id: str
    revision: str
    variant: str
    dtype: str
    attn_impl: str
    licence: str
    local_dir: Path | None
    path: Path


def load_model_config(path: Path) -> ModelConfig:
    """Read a flat model configuration. Raise FactVerifyLoaderError when unusable."""
    data = _read_mapping(path)
    if "roles" in data:
        raise FactVerifyLoaderError(
            f"{path} uses the old roles format; flatten all model fields to the top level"
        )
    _require_schema(data, path)

    vendor = str(data.get("vendor", "huggingface"))

    repo_id = data.get("repo_id")
    if not isinstance(repo_id, str) or repo_id == "":
        raise FactVerifyLoaderError(f"repo_id missing in {path}")

    revision = data.get("revision")
    if not isinstance(revision, str) or not _REVISION_RE.fullmatch(revision):
        raise FactVerifyLoaderError(
            f"revision must be a 40-character hex string in {path}"
        )

    variant = data.get("variant")
    if variant not in {"base", "instruct"}:
        raise FactVerifyLoaderError(
            f"variant must be 'base' or 'instruct' in {path}"
        )

    dtype = data.get("dtype")
    if not isinstance(dtype, str) or dtype == "":
        raise FactVerifyLoaderError(f"dtype missing in {path}")

    attn_impl = data.get("attn_impl")
    if not isinstance(attn_impl, str) or attn_impl == "":
        raise FactVerifyLoaderError(f"attn_impl missing in {path}")

    licence = data.get("licence")
    if not isinstance(licence, str) or licence == "":
        raise FactVerifyLoaderError(f"licence missing in {path}")

    local_dir: Path | None = None
    if data.get("local_dir") is not None:
        raw = Path(str(data["local_dir"]))
        local_dir = (
            raw.resolve() if raw.is_absolute() else (path.parent / raw).resolve()
        )

    return ModelConfig(
        vendor=vendor,
        repo_id=repo_id,
        revision=revision,
        variant=str(variant),
        dtype=dtype,
        attn_impl=attn_impl,
        licence=licence,
        local_dir=local_dir,
        path=path,
    )


# ── Shared helpers ────────────────────────────────────────────────────────────


def _read_mapping(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FactVerifyLoaderError(f"model document not found at {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise FactVerifyLoaderError(f"failed to parse {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise FactVerifyLoaderError(f"{path} must be a mapping")
    return loaded


def _require_schema(data: dict[str, Any], path: Path) -> None:
    if data.get("schema_version") != "1":
        raise FactVerifyLoaderError(f"schema_version must be '1' in {path}")
