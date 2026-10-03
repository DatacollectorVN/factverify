"""Parse and validate model policy, configurations, and resolved roles."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from src.data.digests import sha256_file

from .errors import FactVerifyLoaderError

_REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
_FILE_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_IDENTITY_FIELDS = (
    "repo_id",
    "model_revision",
    "tokenizer_revision",
    "variant",
    "dtype",
    "attn_impl",
    "licence",
    "files",
)


@dataclass(frozen=True)
class ModelSpec:
    role: str
    repo_id: str
    model_revision: str
    tokenizer_revision: str
    dtype: str
    attn_impl: str
    files: dict[str, str]  # filename -> SHA-256 hex digest
    local_dir: Path | None  # optional explicit local directory (resolved absolute)


def config_digest(path: Path) -> str:
    """Fingerprint of the configuration file bytes."""
    return "sha256:" + sha256_file(path)


@dataclass(frozen=True)
class RoleRequirement:
    """One required role declared by the frozen policy."""

    purpose: str
    required_capabilities: tuple[str, ...]
    staged_commitment: bool


@dataclass(frozen=True)
class ModelPolicy:
    """Frozen rules for model selection. It names no repository."""

    schema_version: str
    governing_spec_revision: str
    identity_schema_version: int
    required_roles: dict[str, RoleRequirement]
    required_identity_fields: tuple[str, ...]
    role_aliases: dict[str, str]


@dataclass(frozen=True)
class RoleEntry:
    """One role inside a versioned configuration."""

    status: str | None
    deadline: str | None
    repo_id: str | None
    model_revision: str | None
    tokenizer_revision: str | None
    variant: str | None
    dtype: str | None
    attn_impl: str | None
    licence: str | None
    files: dict[str, str]
    local_dir: Path | None


@dataclass(frozen=True)
class ModelConfiguration:
    """One named selection file."""

    schema_version: str
    config_id: str
    study_stage: str
    roles: dict[str, RoleEntry]
    path: Path


@dataclass(frozen=True)
class ResolvedRole:
    """A role after alias resolution, ready to load when it is not pending."""

    study_role: str
    alias_used: str | None
    deprecation: str | None
    repo_id: str
    model_revision: str
    tokenizer_revision: str
    variant: str
    dtype: str
    attn_impl: str
    licence: str
    files: dict[str, str]
    local_dir: Path | None
    config_id: str
    config_digest: str
    identity_schema_version: int
    governing_spec_revision: str


def load_model_policy(spec_root: Path) -> ModelPolicy:
    """Read model_policy.yaml. Raise FactVerifyLoaderError when it is unusable."""
    path = spec_root / "model_policy.yaml"
    data = _read_mapping(path)
    _require_schema(data, path)
    roles_raw = data.get("required_roles")
    if not isinstance(roles_raw, dict) or not roles_raw:
        raise FactVerifyLoaderError(f"required_roles missing in {path}")
    roles: dict[str, RoleRequirement] = {}
    for name, entry in roles_raw.items():
        if not isinstance(entry, dict):
            raise FactVerifyLoaderError(f"role {name!r} is not a mapping in {path}")
        purpose = entry.get("purpose")
        if not isinstance(purpose, str) or purpose.strip() == "":
            raise FactVerifyLoaderError(f"purpose missing for role {name!r} in {path}")
        capabilities = entry.get("required_capabilities")
        if not isinstance(capabilities, list) or not capabilities:
            raise FactVerifyLoaderError(
                f"required_capabilities missing for role {name!r} in {path}"
            )
        roles[str(name)] = RoleRequirement(
            purpose=purpose,
            required_capabilities=tuple(str(item) for item in capabilities),
            staged_commitment=bool(entry.get("staged_commitment", False)),
        )
    fields = data.get("required_identity_fields")
    if not isinstance(fields, list) or tuple(fields) != _IDENTITY_FIELDS:
        raise FactVerifyLoaderError(f"required_identity_fields mismatch in {path}")
    aliases_raw = data.get("role_aliases")
    if not isinstance(aliases_raw, dict):
        raise FactVerifyLoaderError(f"role_aliases missing in {path}")
    aliases = {str(key): str(value) for key, value in aliases_raw.items()}
    for alias, target in aliases.items():
        if alias in roles:
            raise FactVerifyLoaderError(
                f"alias {alias!r} collides with a required role in {path}"
            )
        if target not in roles:
            raise FactVerifyLoaderError(
                f"alias {alias!r} target {target!r} is not a required role in {path}"
            )
    revision = data.get("governing_spec_revision")
    schema_version_identity = data.get("identity_schema_version")
    if not isinstance(revision, str) or revision == "":
        raise FactVerifyLoaderError(f"governing_spec_revision missing in {path}")
    if not isinstance(schema_version_identity, int) or isinstance(
        schema_version_identity, bool
    ):
        raise FactVerifyLoaderError(f"identity_schema_version missing in {path}")
    return ModelPolicy(
        schema_version="1",
        governing_spec_revision=revision,
        identity_schema_version=schema_version_identity,
        required_roles=roles,
        required_identity_fields=_IDENTITY_FIELDS,
        role_aliases=aliases,
    )


def load_model_configuration(path: Path) -> ModelConfiguration:
    """Read one versioned configuration. Refuse the legacy flat shape."""
    data = _read_mapping(path)
    if "roles" not in data:
        raise FactVerifyLoaderError(
            f"{path} must group roles under a top-level 'roles' mapping"
        )
    _require_schema(data, path)
    config_id = data.get("config_id")
    study_stage = data.get("study_stage")
    if not isinstance(config_id, str) or config_id == "":
        raise FactVerifyLoaderError(f"config_id missing in {path}")
    if not isinstance(study_stage, str) or study_stage == "":
        raise FactVerifyLoaderError(f"study_stage missing in {path}")
    roles_raw = data["roles"]
    if not isinstance(roles_raw, dict):
        raise FactVerifyLoaderError(f"'roles' is not a mapping in {path}")
    roles = {
        str(name): _parse_role_entry(str(name), entry, path)
        for name, entry in roles_raw.items()
    }
    return ModelConfiguration(
        schema_version="1",
        config_id=config_id,
        study_stage=study_stage,
        roles=roles,
        path=path,
    )


def resolve_role(
    policy: ModelPolicy, config: ModelConfiguration, role: str
) -> ResolvedRole:
    """Resolve aliases, then return the canonical role. Pending roles refuse."""
    for alias, canonical in policy.role_aliases.items():
        if alias in config.roles and canonical in config.roles:
            raise FactVerifyLoaderError(
                f"conflicting role keys {alias!r} and {canonical!r} in {config.path}"
            )
    alias_used: str | None = None
    deprecation: str | None = None
    study_role = role
    if role in policy.role_aliases:
        alias_used = role
        study_role = policy.role_aliases[role]
        deprecation = f"role alias {role} resolved to {study_role}"
    entry_key = role if role in config.roles else study_role
    if entry_key not in config.roles:
        raise FactVerifyLoaderError(f"unknown role {role!r} in {config.path}")
    entry = config.roles[entry_key]
    if entry.status == "pending":
        raise FactVerifyLoaderError(f"role {study_role!r} is pending in {config.path}")
    if entry.model_revision is None or not _REVISION_RE.fullmatch(entry.model_revision):
        raise FactVerifyLoaderError(
            f"unresolved spec field 'model_revision' for role {study_role!r} "
            f"in {config.path}"
        )
    if not entry.files:
        raise FactVerifyLoaderError(
            f"field 'files' for role {study_role!r} must be a non-empty mapping"
            f" in {config.path}"
        )
    return ResolvedRole(
        study_role=study_role,
        alias_used=alias_used,
        deprecation=deprecation,
        repo_id=_required_text(entry.repo_id, "repo_id", study_role, config.path),
        model_revision=entry.model_revision,
        tokenizer_revision=_required_text(
            entry.tokenizer_revision, "tokenizer_revision", study_role, config.path
        ),
        variant=_required_text(entry.variant, "variant", study_role, config.path),
        dtype=_required_text(entry.dtype, "dtype", study_role, config.path),
        attn_impl=_required_text(entry.attn_impl, "attn_impl", study_role, config.path),
        licence=_required_text(entry.licence, "licence", study_role, config.path),
        files=dict(entry.files),
        local_dir=entry.local_dir,
        config_id=config.config_id,
        config_digest=config_digest(config.path),
        identity_schema_version=policy.identity_schema_version,
        governing_spec_revision=policy.governing_spec_revision,
    )


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


def _parse_role_entry(name: str, entry: object, path: Path) -> RoleEntry:
    if not isinstance(entry, dict):
        raise FactVerifyLoaderError(f"role {name!r} entry is not a mapping in {path}")
    if "revision" in entry and "model_revision" not in entry:
        raise FactVerifyLoaderError(
            f"role {name!r} uses 'revision'; the weight revision field is "
            f"'model_revision' in {path}"
        )
    pending = entry.get("status") == "pending"
    if pending:
        deadline = _deadline_text(entry.get("deadline"), name, path)
        return RoleEntry(
            status="pending",
            deadline=deadline,
            repo_id=_optional_text(entry.get("repo_id")),
            model_revision=_optional_text(entry.get("model_revision")),
            tokenizer_revision=_optional_text(entry.get("tokenizer_revision")),
            variant=_optional_text(entry.get("variant")),
            dtype=_optional_text(entry.get("dtype")),
            attn_impl=_optional_text(entry.get("attn_impl")),
            licence=_optional_text(entry.get("licence")),
            files={},
            local_dir=None,
        )
    model_revision = entry.get("model_revision")
    tokenizer_revision = entry.get("tokenizer_revision")
    if not isinstance(model_revision, str) or not _REVISION_RE.fullmatch(
        model_revision
    ):
        raise FactVerifyLoaderError(
            f"unresolved spec field 'model_revision' for role {name!r} in {path}"
        )
    if not isinstance(tokenizer_revision, str) or not _REVISION_RE.fullmatch(
        tokenizer_revision
    ):
        raise FactVerifyLoaderError(
            f"unresolved spec field 'tokenizer_revision' for role {name!r} in {path}"
        )
    variant = entry.get("variant")
    if variant not in {"base", "instruct"}:
        raise FactVerifyLoaderError(
            f"unresolved spec field 'variant' for role {name!r} in {path}"
        )
    files = entry.get("files")
    if not isinstance(files, dict):
        raise FactVerifyLoaderError(
            f"unresolved spec field 'files' for role {name!r} in {path}"
        )
    digested = {str(key): str(value) for key, value in files.items()}
    for filename, digest in digested.items():
        if not _FILE_DIGEST_RE.fullmatch(digest):
            raise FactVerifyLoaderError(
                f"file {filename!r} digest for role {name!r} must be "
                f"'sha256:' plus 64 hex characters in {path}"
            )
    local_dir: Path | None = None
    if entry.get("local_dir") is not None:
        raw = Path(str(entry["local_dir"]))
        local_dir = (
            raw.resolve() if raw.is_absolute() else (path.parent / raw).resolve()
        )
    return RoleEntry(
        status=None,
        deadline=None,
        repo_id=_optional_text(entry.get("repo_id")),
        model_revision=model_revision,
        tokenizer_revision=tokenizer_revision,
        variant=str(variant),
        dtype=_optional_text(entry.get("dtype")),
        attn_impl=_optional_text(entry.get("attn_impl")),
        licence=_optional_text(entry.get("licence")),
        files=digested,
        local_dir=local_dir,
    )


def _deadline_text(value: object, role: str, path: Path) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value)
    try:
        date.fromisoformat(text[:10])
    except ValueError as exc:
        raise FactVerifyLoaderError(
            f"role {role!r} deadline {value!r} is not an ISO date in {path}"
        ) from exc
    parsed = date.fromisoformat(text[:10])
    if parsed < date.today():
        raise FactVerifyLoaderError(
            f"role {role!r} is still pending and deadline {text} has passed in {path}"
        )
    return text[:10]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _required_text(value: str | None, field: str, role: str, path: Path) -> str:
    if value is None or value == "" or value == "DECISION_REQUIRED":
        raise FactVerifyLoaderError(
            f"unresolved spec field {field!r} for role {role!r} in {path}"
        )
    return value
