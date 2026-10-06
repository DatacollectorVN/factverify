"""SQLite transaction store for the TOFU data pipeline.

Tracks progress across three stages (download, prepare, build) so that
interrupted runs can resume from the last committed row.

Database lives at ``{workspace}/pipeline.sqlite``.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA_VERSION = "1"

_DDL = """
CREATE TABLE IF NOT EXISTS meta (
    schema_version TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_manifest (
    manifest_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    repo_id      TEXT NOT NULL,
    revision     TEXT NOT NULL,
    files_json   TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS mentions (
    mention_id        TEXT PRIMARY KEY,
    source_row        INTEGER NOT NULL,
    field             TEXT NOT NULL,
    char_start        INTEGER NOT NULL,
    char_end          INTEGER NOT NULL,
    span_status       TEXT NOT NULL,
    subject           TEXT NOT NULL,
    surface_relation  TEXT NOT NULL,
    canonical_relation TEXT,
    mapping_status    TEXT NOT NULL,
    object            TEXT NOT NULL,
    source_text       TEXT NOT NULL,
    model             TEXT NOT NULL,
    prompt_digest     TEXT NOT NULL,
    created_at        TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS facts (
    fact_id       TEXT PRIMARY KEY,
    candidate_id  TEXT NOT NULL,
    slug          TEXT NOT NULL UNIQUE,
    subject       TEXT NOT NULL,
    relation      TEXT NOT NULL,
    object        TEXT NOT NULL,
    source_row    INTEGER NOT NULL,
    question      TEXT NOT NULL,
    answer        TEXT NOT NULL,
    review_model  TEXT NOT NULL,
    review_reason TEXT NOT NULL,
    row_json      TEXT NOT NULL,
    created_at    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS bundles (
    fact_id          TEXT PRIMARY KEY REFERENCES facts(fact_id),
    bundle_path      TEXT NOT NULL,
    manifest_digest  TEXT NOT NULL,
    created_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS corpus_records (
    fact_id        TEXT PRIMARY KEY REFERENCES facts(fact_id),
    qa_count       INTEGER NOT NULL,
    corpus_digest  TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE TABLE IF NOT EXISTS llm_cache (
    cache_key      TEXT PRIMARY KEY,
    stage          TEXT NOT NULL,
    response_text  TEXT NOT NULL,
    model          TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_mentions_source_row ON mentions(source_row);
CREATE INDEX IF NOT EXISTS idx_llm_cache_stage ON llm_cache(stage);
"""


def connect_pipeline(workspace: Path) -> sqlite3.Connection:
    """Open (or create) the pipeline database with WAL mode."""
    db_path = workspace / "pipeline.sqlite"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=None, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_schema(conn)
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if missing. Insert schema version when meta is empty."""
    conn.executescript(_DDL)
    row = conn.execute("SELECT schema_version FROM meta").fetchone()
    if row is None:
        conn.execute(
            "INSERT INTO meta (schema_version) VALUES (?)", (SCHEMA_VERSION,)
        )
    elif str(row["schema_version"]) != SCHEMA_VERSION:
        raise RuntimeError(
            f"pipeline.sqlite schema_version={row['schema_version']}, "
            f"expected {SCHEMA_VERSION}"
        )


def clear_stage(conn: sqlite3.Connection, stage: str) -> None:
    """Delete all records for a stage so it can be re-run from scratch.

    ``stage`` is one of: ``"download"``, ``"prepare"``, ``"build"``.
    """
    conn.execute("BEGIN")
    try:
        if stage == "download":
            conn.execute("DELETE FROM source_manifest")
            conn.execute("DELETE FROM llm_cache WHERE stage = 'download'")
        elif stage == "prepare":
            conn.execute("DELETE FROM corpus_records")
            conn.execute("DELETE FROM bundles")
            conn.execute("DELETE FROM facts")
            conn.execute("DELETE FROM mentions")
            conn.execute("DELETE FROM llm_cache WHERE stage IN ('extract', 'review')")
        elif stage == "build":
            conn.execute("DELETE FROM corpus_records")
            conn.execute("DELETE FROM bundles")
            conn.execute("DELETE FROM llm_cache WHERE stage = 'corpus'")
        else:
            raise ValueError(f"unknown stage: {stage!r}")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


# ── Query helpers ───────────────────────────────────────────────────────────


def done_source_rows(conn: sqlite3.Connection) -> set[int]:
    """Return source_row values that already have mentions extracted."""
    rows = conn.execute("SELECT DISTINCT source_row FROM mentions").fetchall()
    return {r["source_row"] for r in rows}


def reviewed_candidate_ids(conn: sqlite3.Connection) -> set[str]:
    """Return candidate_ids that already have a fact record (accepted)."""
    rows = conn.execute("SELECT candidate_id FROM facts").fetchall()
    return {r["candidate_id"] for r in rows}


def built_fact_ids(conn: sqlite3.Connection) -> set[str]:
    """Return fact_ids that already have a bundle on disk."""
    rows = conn.execute("SELECT fact_id FROM bundles").fetchall()
    return {r["fact_id"] for r in rows}


def corpused_fact_ids(conn: sqlite3.Connection) -> set[str]:
    """Return fact_ids that already have corpus generated."""
    rows = conn.execute("SELECT fact_id FROM corpus_records").fetchall()
    return {r["fact_id"] for r in rows}


def get_cached(conn: sqlite3.Connection, cache_key: str) -> str | None:
    """Return cached LLM response or None."""
    row = conn.execute(
        "SELECT response_text FROM llm_cache WHERE cache_key = ?", (cache_key,)
    ).fetchone()
    return row["response_text"] if row else None


def put_cache(
    conn: sqlite3.Connection,
    cache_key: str,
    stage: str,
    response_text: str,
    model: str,
) -> None:
    """Insert an LLM response into the cache."""
    conn.execute(
        "INSERT OR IGNORE INTO llm_cache (cache_key, stage, response_text, model) "
        "VALUES (?, ?, ?, ?)",
        (cache_key, stage, response_text, model),
    )


def all_accepted_facts(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Return all accepted fact rows."""
    return conn.execute("SELECT * FROM facts ORDER BY slug").fetchall()
