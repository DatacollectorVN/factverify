"""Identity computation for base models and checkpoints (FV-ARCH Phase 4).

This module does NOT import torch. All hashing is delegated to
``src.models.identity.compute_identity_hash_v2``.
"""

from __future__ import annotations

from src.models.identity import compute_identity_hash_v2

from .types import BaseIdentity, CheckpointIdentity

_SCHEMA_VERSION = 2


def compute_base_identity(
    repo_id: str,
    model_revision: str,
    tokenizer_revision: str,
    dtype: str,
) -> BaseIdentity:
    """Compute a deterministic identity for a base model (no adapter)."""
    identity_hash = compute_identity_hash_v2(
        repo_id=repo_id,
        model_revision=model_revision,
        tokenizer_revision=tokenizer_revision,
        dtype=dtype,
        adapter_digest=None,
    )
    return BaseIdentity(
        repo_id=repo_id,
        model_revision=model_revision,
        tokenizer_revision=tokenizer_revision,
        dtype=dtype,
        identity_hash=identity_hash,
    )


def compute_checkpoint_identity(
    base: BaseIdentity,
    adapter_digest: str | None,
) -> CheckpointIdentity:
    """Compute the full identity of a checkpoint (base + optional adapter)."""
    identity_hash = compute_identity_hash_v2(
        repo_id=base.repo_id,
        model_revision=base.model_revision,
        tokenizer_revision=base.tokenizer_revision,
        dtype=base.dtype,
        adapter_digest=adapter_digest,
    )
    return CheckpointIdentity(
        base_identity=base,
        adapter_digest=adapter_digest,
        identity_hash=identity_hash,
        schema_version=_SCHEMA_VERSION,
    )


def verify_parent_compatibility(
    checkpoint_identity: CheckpointIdentity,
    expected_base: BaseIdentity,
) -> bool:
    """FV-ARCH-013: verify that a checkpoint was derived from the expected base model.

    Returns True when the checkpoint's base identity hash matches the expected
    base identity hash.
    """
    return checkpoint_identity.base_identity.identity_hash == expected_base.identity_hash
