"""Full sha256 cache key. Open D-60 refuses the key."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.cache.decisions import load_decision
from src.cache.errors import CacheError
from src.train.config import hash_mapping


@dataclass(frozen=True)
class CacheRequest:
    """One generation or score request. The producer is not part of the key."""

    identity_hash: str
    model_input: str
    decoding: dict[str, object]
    seed: int
    sample_index: int
    request_kind: str
    producer_run_id: str
    software_versions: dict[str, str] | None = None


@dataclass(frozen=True)
class CacheBody:
    """What `compute` returns."""

    body: str | dict[str, object]
    token_count: int


@dataclass(frozen=True)
class CacheEntry:
    """A stored body and the digest of that body."""

    body: str | dict[str, object]
    token_count: int
    created_at: str
    content_digest: str
    producer_run_id: str


@dataclass(frozen=True)
class CacheEvent:
    """Exactly one of hit, miss, conflict, or corrupt."""

    kind: str
    stored_digest: str | None = None
    new_digest: str | None = None


def cache_key(request: CacheRequest, *, decisions: Path) -> str:
    """Full sha256 key, or CacheError('D-60') while that row is open."""
    decision = load_decision(decisions, "D-60")
    if decision.status != "closed" or decision.include_software_versions is None:
        raise CacheError("D-60")
    _require_request(request)
    payload: dict[str, object] = {
        "identity_hash": request.identity_hash,
        "model_input": request.model_input,
        "decoding": hash_mapping(request.decoding),
        "request_kind": request.request_kind,
        "seed": request.seed,
        "sample_index": request.sample_index,
    }
    if decision.include_software_versions:
        versions = request.software_versions
        if not isinstance(versions, dict) or not versions:
            raise CacheError("software_versions")
        if any(
            not isinstance(key, str)
            or not isinstance(value, str)
            or key == ""
            or value == ""
            for key, value in versions.items()
        ):
            raise CacheError("software_versions")
        payload["software_versions"] = versions
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def content_digest(body: str | dict[str, object]) -> str:
    """sha256 of the canonical body."""
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_request(request: CacheRequest) -> None:
    if not isinstance(request.identity_hash, str) or request.identity_hash == "":
        raise CacheError("identity_hash")
    if not isinstance(request.model_input, str):
        raise CacheError("model_input")
    if not isinstance(request.decoding, dict):
        raise CacheError("decoding")
    if isinstance(request.seed, bool) or not isinstance(request.seed, int):
        raise CacheError("seed")
    if (
        isinstance(request.sample_index, bool)
        or not isinstance(request.sample_index, int)
        or request.sample_index < 1
    ):
        raise CacheError("sample_index")
    if request.request_kind not in {"generate", "score"}:
        raise CacheError("request_kind")
    if not isinstance(request.producer_run_id, str) or request.producer_run_id == "":
        raise CacheError("producer_run_id")
