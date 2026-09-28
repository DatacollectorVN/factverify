"""Canonical identity hash for loaded checkpoints."""

from __future__ import annotations

import hashlib
import json

from .spec import ModelSpec


def build_identity_payload(
    spec: ModelSpec, adapter_digest: str | None
) -> dict[str, str | None]:
    """Build the canonical payload dict from which the identity hash is computed.

    Keys are always sorted. Values come from models.yaml spec fields — never
    from runtime inspection of the loaded model.
    """
    return {
        "adapter_digest": adapter_digest,
        "attn_impl": spec.attn_impl,
        "base_repo": spec.repo_id,
        "base_revision": spec.revision,
        "dtype": spec.dtype,
        "role": spec.role,
        "tokenizer_revision": spec.tokenizer_revision,
    }


def compute_identity_hash(payload: dict[str, str | None]) -> str:
    """SHA-256 of the JSON-serialised payload with sorted keys and no whitespace."""
    serialised = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialised.encode()).hexdigest()
