"""Tests for src.services.models.identity: determinism, differentiation, compatibility."""

from __future__ import annotations

from src.services.models.identity import (
    compute_base_identity,
    compute_checkpoint_identity,
    verify_parent_compatibility,
)
from src.services.models.types import BaseIdentity

# ── Shared fixtures ────────────────────────────────────────────────────────

_BASE_ARGS = {
    "repo_id": "meta-llama/Llama-2-7b-hf",
    "model_revision": "a" * 40,
    "tokenizer_revision": "b" * 40,
    "dtype": "bfloat16",
}


class TestComputeBaseIdentity:
    def test_deterministic(self) -> None:
        """Same inputs must produce the same hash on every call."""
        a = compute_base_identity(**_BASE_ARGS)
        b = compute_base_identity(**_BASE_ARGS)
        assert a.identity_hash == b.identity_hash
        assert a == b

    def test_different_repo_id(self) -> None:
        other = {**_BASE_ARGS, "repo_id": "other-org/other-model"}
        assert (
            compute_base_identity(**_BASE_ARGS).identity_hash
            != compute_base_identity(**other).identity_hash
        )

    def test_different_revision(self) -> None:
        other = {**_BASE_ARGS, "model_revision": "c" * 40}
        assert (
            compute_base_identity(**_BASE_ARGS).identity_hash
            != compute_base_identity(**other).identity_hash
        )

    def test_different_dtype(self) -> None:
        other = {**_BASE_ARGS, "dtype": "float16"}
        assert (
            compute_base_identity(**_BASE_ARGS).identity_hash
            != compute_base_identity(**other).identity_hash
        )

    def test_fields_populated(self) -> None:
        identity = compute_base_identity(**_BASE_ARGS)
        assert identity.repo_id == _BASE_ARGS["repo_id"]
        assert identity.model_revision == _BASE_ARGS["model_revision"]
        assert identity.tokenizer_revision == _BASE_ARGS["tokenizer_revision"]
        assert identity.dtype == _BASE_ARGS["dtype"]
        assert identity.identity_hash.startswith("sha256:")


class TestComputeCheckpointIdentity:
    def test_no_adapter(self) -> None:
        base = compute_base_identity(**_BASE_ARGS)
        ckpt = compute_checkpoint_identity(base, adapter_digest=None)
        assert ckpt.adapter_digest is None
        assert ckpt.base_identity is base
        # Without an adapter, the checkpoint hash equals the base hash
        assert ckpt.identity_hash == base.identity_hash
        assert ckpt.schema_version == 2

    def test_with_adapter(self) -> None:
        base = compute_base_identity(**_BASE_ARGS)
        digest = "sha256:" + "d" * 64
        ckpt = compute_checkpoint_identity(base, adapter_digest=digest)
        assert ckpt.adapter_digest == digest
        # With an adapter, the checkpoint hash must differ from the base hash
        assert ckpt.identity_hash != base.identity_hash

    def test_different_adapters_differ(self) -> None:
        base = compute_base_identity(**_BASE_ARGS)
        ckpt_a = compute_checkpoint_identity(base, adapter_digest="sha256:" + "d" * 64)
        ckpt_b = compute_checkpoint_identity(base, adapter_digest="sha256:" + "e" * 64)
        assert ckpt_a.identity_hash != ckpt_b.identity_hash


class TestVerifyParentCompatibility:
    def test_compatible(self) -> None:
        base = compute_base_identity(**_BASE_ARGS)
        ckpt = compute_checkpoint_identity(base, adapter_digest=None)
        assert verify_parent_compatibility(ckpt, expected_base=base) is True

    def test_compatible_with_adapter(self) -> None:
        base = compute_base_identity(**_BASE_ARGS)
        ckpt = compute_checkpoint_identity(base, adapter_digest="sha256:" + "f" * 64)
        assert verify_parent_compatibility(ckpt, expected_base=base) is True

    def test_incompatible(self) -> None:
        base_a = compute_base_identity(**_BASE_ARGS)
        base_b = compute_base_identity(**{**_BASE_ARGS, "repo_id": "other/model"})
        ckpt = compute_checkpoint_identity(base_a, adapter_digest=None)
        assert verify_parent_compatibility(ckpt, expected_base=base_b) is False
