"""Frozen dataclasses for model and checkpoint identity (FV-ARCH Phase 4)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BaseIdentity:
    """Identity of a base model before any adapters."""

    repo_id: str
    model_revision: str
    tokenizer_revision: str
    dtype: str
    identity_hash: str


@dataclass(frozen=True)
class CheckpointIdentity:
    """Full identity of a loaded checkpoint (base + optional adapter)."""

    base_identity: BaseIdentity
    adapter_digest: str | None
    identity_hash: str
    schema_version: int


@dataclass(frozen=True)
class CheckpointManifest:
    """Published checkpoint metadata written alongside the checkpoint directory."""

    identity_hash: str
    base_identity_hash: str
    config_hash: str
    training_method: str
    seed: int
    created_at: str
    path: str
    digest: str | None
    size_bytes: int
