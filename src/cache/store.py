"""Generation cache keyed by (model_hash, prompt_hash, decoding_params).

Avoids redundant model queries across evaluators and runs.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path

CACHE_DB = Path(__file__).resolve().parent.parent.parent / ".cache" / "generations.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS generations (
    model_hash     TEXT NOT NULL,
    prompt_hash    TEXT NOT NULL,
    decoding_key   TEXT NOT NULL,
    response       TEXT NOT NULL,
    created_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    PRIMARY KEY (model_hash, prompt_hash, decoding_key)
);
"""


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def decoding_key(params: dict[str, object]) -> str:
    blob = json.dumps(params, sort_keys=True, ensure_ascii=True)
    return _hash(blob)


@dataclass
class GenerationCache:
    db_path: Path = CACHE_DB
    _conn: sqlite3.Connection | None = None

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path))
            self._conn.executescript(SCHEMA)
        return self._conn

    def get(
        self,
        model_hash: str,
        prompt_hash: str,
        decoding_params: dict[str, object],
    ) -> str | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT response FROM generations"
            " WHERE model_hash=? AND prompt_hash=? AND decoding_key=?",
            (model_hash, prompt_hash, decoding_key(decoding_params)),
        ).fetchone()
        return row[0] if row else None

    def put(
        self,
        model_hash: str,
        prompt_hash: str,
        decoding_params: dict[str, object],
        response: str,
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO generations
                (model_hash, prompt_hash, decoding_key, response)
            VALUES (?, ?, ?, ?)
            """,
            (model_hash, prompt_hash, decoding_key(decoding_params), response),
        )
        conn.commit()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
