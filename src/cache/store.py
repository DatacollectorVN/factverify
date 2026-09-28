"""Generation cache. A read always returns an event. The work tree is not used."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.cache.errors import CacheError
from src.cache.key import (
    CacheBody,
    CacheEntry,
    CacheEvent,
    CacheRequest,
    cache_key,
    content_digest,
)

_DDL = """
CREATE TABLE IF NOT EXISTS entries (
    cache_key TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    producer_run_id TEXT NOT NULL,
    study_role TEXT,
    model_config_id TEXT,
    model_config_digest TEXT,
    model_identity_hash TEXT,
    identity_schema_version INTEGER
);
CREATE TABLE IF NOT EXISTS events (
    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
    cache_key TEXT NOT NULL,
    kind TEXT NOT NULL,
    stored_digest TEXT,
    new_digest TEXT,
    created_at TEXT NOT NULL
);
"""


class Cache:
    """SQLite cache rooted at a caller-supplied directory."""

    def __init__(
        self, connection: sqlite3.Connection, root: Path, decisions: Path
    ) -> None:
        self.connection = connection
        self.root = root
        self.decisions = decisions

    def events(self) -> tuple[CacheEvent, ...]:
        """Events in insert order."""
        rows = self.connection.execute(
            "SELECT kind, stored_digest, new_digest FROM events ORDER BY event_id"
        ).fetchall()
        return tuple(
            CacheEvent(
                kind=str(row["kind"]),
                stored_digest=None
                if row["stored_digest"] is None
                else str(row["stored_digest"]),
                new_digest=None
                if row["new_digest"] is None
                else str(row["new_digest"]),
            )
            for row in rows
        )


def open_cache(root: Path, *, decisions: Path) -> Cache:
    """Refuse a root inside .factverify. Create the store directory otherwise."""
    resolved = root.resolve()
    if ".factverify" in resolved.parts:
        raise CacheError("location")
    if not decisions.is_file():
        raise CacheError("decisions")
    resolved.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(resolved / "cache.sqlite"), isolation_level=None)
    connection.row_factory = sqlite3.Row
    connection.executescript(_DDL)
    _migrate_entries(connection)
    return Cache(connection, resolved, decisions)


def get_or_compute(
    cache: Cache,
    request: CacheRequest,
    compute: Callable[[], CacheBody],
) -> tuple[CacheEntry, CacheEvent]:
    """Return the stored body or the computed body, and exactly one event."""
    key = cache_key(request, decisions=cache.decisions)
    row = cache.connection.execute(
        "SELECT * FROM entries WHERE cache_key = ?",
        (key,),
    ).fetchone()
    if row is None:
        produced = compute()
        entry = _insert(cache, key, produced, request)
        event = CacheEvent("miss")
        _record(cache, key, event)
        return entry, event
    stored_body = _load_body(str(row["body"]))
    actual = content_digest(stored_body)
    recorded = str(row["content_digest"])
    if actual != recorded:
        produced = compute()
        entry = _replace(cache, key, produced, request)
        event = CacheEvent(
            "corrupt", stored_digest=recorded, new_digest=entry.content_digest
        )
        _record(cache, key, event)
        return entry, event
    if str(row["producer_run_id"]) == request.producer_run_id:
        entry = _entry_from_row(row, stored_body)
        event = CacheEvent("hit")
        _record(cache, key, event)
        return entry, event
    produced = compute()
    new_digest = content_digest(produced.body)
    if new_digest == recorded:
        entry = _entry_from_row(row, stored_body)
        event = CacheEvent("hit", stored_digest=recorded, new_digest=new_digest)
        _record(cache, key, event)
        return entry, event
    event = CacheEvent("conflict", stored_digest=recorded, new_digest=new_digest)
    _record(cache, key, event)
    raise CacheError("conflict", event)


def _insert(
    cache: Cache, key: str, produced: CacheBody, request: CacheRequest
) -> CacheEntry:
    created_at = datetime.now(UTC).isoformat()
    digest = content_digest(produced.body)
    cache.connection.execute(
        """
        INSERT INTO entries (
            cache_key, body, token_count, created_at, content_digest,
            producer_run_id, study_role, model_config_id, model_config_digest,
            model_identity_hash, identity_schema_version
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            key,
            json.dumps(produced.body, sort_keys=True),
            produced.token_count,
            created_at,
            digest,
            request.producer_run_id,
            request.study_role,
            request.model_config_id,
            request.model_config_digest,
            request.identity_hash,
            request.identity_schema_version,
        ),
    )
    return CacheEntry(
        produced.body,
        produced.token_count,
        created_at,
        digest,
        request.producer_run_id,
    )


def _replace(
    cache: Cache, key: str, produced: CacheBody, request: CacheRequest
) -> CacheEntry:
    created_at = datetime.now(UTC).isoformat()
    digest = content_digest(produced.body)
    cache.connection.execute(
        """
        UPDATE entries
        SET body = ?, token_count = ?, created_at = ?, content_digest = ?,
            producer_run_id = ?, study_role = ?, model_config_id = ?,
            model_config_digest = ?, model_identity_hash = ?,
            identity_schema_version = ?
        WHERE cache_key = ?
        """,
        (
            json.dumps(produced.body, sort_keys=True),
            produced.token_count,
            created_at,
            digest,
            request.producer_run_id,
            request.study_role,
            request.model_config_id,
            request.model_config_digest,
            request.identity_hash,
            request.identity_schema_version,
            key,
        ),
    )
    return CacheEntry(
        produced.body,
        produced.token_count,
        created_at,
        digest,
        request.producer_run_id,
    )


def _migrate_entries(connection: sqlite3.Connection) -> None:
    text_columns = (
        "study_role",
        "model_config_id",
        "model_config_digest",
        "model_identity_hash",
    )
    for column in text_columns:
        try:
            connection.execute(f"ALTER TABLE entries ADD COLUMN {column} TEXT")
        except sqlite3.OperationalError:
            pass
    try:
        connection.execute(
            "ALTER TABLE entries ADD COLUMN identity_schema_version INTEGER"
        )
    except sqlite3.OperationalError:
        pass


def _entry_from_row(row: sqlite3.Row, body: str | dict[str, object]) -> CacheEntry:
    return CacheEntry(
        body=body,
        token_count=int(row["token_count"]),
        created_at=str(row["created_at"]),
        content_digest=str(row["content_digest"]),
        producer_run_id=str(row["producer_run_id"]),
    )


def _load_body(stored: str) -> str | dict[str, object]:
    loaded = json.loads(stored)
    if isinstance(loaded, str):
        return loaded
    if isinstance(loaded, dict):
        return {str(key): value for key, value in loaded.items()}
    raise CacheError("body")


def _record(cache: Cache, key: str, event: CacheEvent) -> None:
    cache.connection.execute(
        """
        INSERT INTO events (cache_key, kind, stored_digest, new_digest, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            key,
            event.kind,
            event.stored_digest,
            event.new_digest,
            datetime.now(UTC).isoformat(),
        ),
    )
