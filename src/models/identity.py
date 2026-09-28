"""Canonical identity hash for loaded checkpoints."""

from __future__ import annotations

import hashlib
import json

from .spec import ModelSpec

_V2_SCHEMA = 2


def build_identity_payload(
    spec: ModelSpec, adapter_digest: str | None
) -> dict[str, str | None]:
    """Build the version-1 payload. Keys and compact JSON stay as they are today."""
    return {
        "adapter_digest": adapter_digest,
        "attn_impl": spec.attn_impl,
        "base_repo": spec.repo_id,
        "base_revision": spec.model_revision,
        "dtype": spec.dtype,
        "role": spec.role,
        "tokenizer_revision": spec.tokenizer_revision,
    }


def compute_identity_hash(payload: dict[str, str | None]) -> str:
    """SHA-256 of the JSON-serialised payload with sorted keys and no whitespace."""
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode()).hexdigest()


def compute_identity_hash_v2(
    *,
    repo_id: str,
    model_revision: str,
    tokenizer_revision: str,
    dtype: str,
    adapter_digest: str | None,
    role: str | None = None,
) -> str:
    """FV-SPEC-093 identity. The role name is accepted and not hashed."""
    del role
    serialised = json.dumps(
        {
            "repo_id": repo_id,
            "model_revision": model_revision,
            "tokenizer_revision": tokenizer_revision,
            "dtype": dtype,
            "adapter_digest": adapter_digest,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return "sha256:" + hashlib.sha256(serialised.encode("utf-8")).hexdigest()


def verify_identity_hash(
    payload: dict[str, str | None],
    digest: str,
    schema_version: int,
) -> bool:
    """Return whether digest matches payload under the given schema version."""
    if schema_version == 1:
        return compute_identity_hash(payload) == digest
    if schema_version == _V2_SCHEMA:
        adapter = payload.get("adapter_digest")
        repo_id = payload.get("repo_id")
        model_revision = payload.get("model_revision")
        tokenizer_revision = payload.get("tokenizer_revision")
        dtype = payload.get("dtype")
        if (
            not isinstance(repo_id, str)
            or not isinstance(model_revision, str)
            or not isinstance(tokenizer_revision, str)
            or not isinstance(dtype, str)
        ):
            return False
        expected = compute_identity_hash_v2(
            repo_id=repo_id,
            model_revision=model_revision,
            tokenizer_revision=tokenizer_revision,
            dtype=dtype,
            adapter_digest=adapter,
            role=payload.get("role"),
        )
        return expected == digest
    return False
