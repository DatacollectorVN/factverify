"""Cache export. The manifest digest covers the entry bytes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from src.cache.errors import CacheError
from src.cache.store import Cache, open_cache


def export_cache(cache: Cache, directory: Path) -> None:
    """Write entries and a manifest of keys and digests."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = cache.connection.execute(
        """
        SELECT cache_key, body, token_count, created_at, content_digest,
               producer_run_id
        FROM entries ORDER BY cache_key
        """
    ).fetchall()
    entries = [_entry(row) for row in rows]
    raw = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    manifest = {
        "entries": [
            {"key": item["cache_key"], "content_digest": item["content_digest"]}
            for item in entries
        ],
        "digest": hashlib.sha256(raw).hexdigest(),
    }
    (directory / "entries.json").write_bytes(raw)
    (directory / "manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def import_cache(directory: Path, root: Path, *, decisions: Path) -> Cache:
    """Refuse a manifest digest that disagrees with the entry bytes."""
    raw = (directory / "entries.json").read_bytes()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise CacheError("digest")
    expected = manifest.get("digest")
    actual = hashlib.sha256(raw).hexdigest()
    if expected != actual:
        raise CacheError("digest")
    loaded = json.loads(raw.decode("utf-8"))
    if not isinstance(loaded, list):
        raise CacheError("digest")
    cache = open_cache(root, decisions=decisions)
    for item in loaded:
        if not isinstance(item, dict):
            raise CacheError("digest")
        cache.connection.execute(
            """
            INSERT INTO entries (
                cache_key, body, token_count, created_at,
                content_digest, producer_run_id
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                item["cache_key"],
                item["body"]
                if isinstance(item["body"], str)
                else json.dumps(item["body"]),
                item["token_count"],
                item["created_at"],
                item["content_digest"],
                item["producer_run_id"],
            ),
        )
    return cache


def _entry(row: sqlite3.Row) -> dict[str, object]:
    return {
        "cache_key": str(row["cache_key"]),
        "body": row["body"],
        "token_count": int(row["token_count"]),
        "created_at": str(row["created_at"]),
        "content_digest": str(row["content_digest"]),
        "producer_run_id": str(row["producer_run_id"]),
    }
