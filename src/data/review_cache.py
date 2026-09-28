"""Shared ReviewCache for deterministic LLM call caching.

Keyed by (role, model_revision, prompt_hash, content_hash).  Each entry is
stored as a single JSONL line in the cache file so concurrent appends are
safe (each line is an atomic write).

Used by both adjudicate_mentions.py and entailment_audit.py.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def request_key(
    role: str,
    model_revision: str,
    prompt_hash: str,
    content_hash: str,
) -> str:
    """Return a deterministic cache key for one LLM request."""
    payload = json.dumps(
        {
            "role": role,
            "model_revision": model_revision,
            "prompt_hash": prompt_hash,
            "content_hash": content_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ReviewCache:
    """Append-only JSONL cache for LLM responses."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._store: dict[str, str] = {}
        if path.exists():
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    self._store[entry["key"]] = entry["response"]

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def put(self, key: str, response: str) -> None:
        self._store[key] = response
        with open(self._path, "a") as fh:
            fh.write(json.dumps({"key": key, "response": response}) + "\n")
