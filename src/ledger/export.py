"""CSV and JSON export. Import accepts schema version `1` only."""

from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from src.ledger.api import Ledger, open_ledger
from src.ledger.errors import LedgerError
from src.ledger.schema import SCHEMA_VERSION

_TABLES = ("meta", "checkpoints", "evaluation_runs", "incidents")


def export_ledger(ledger: Ledger, directory: Path) -> None:
    """Write manifest.json, plus CSV and JSON for every table."""
    directory.mkdir(parents=True, exist_ok=True)
    manifest: dict[str, object] = {"schema_version": SCHEMA_VERSION, "tables": {}}
    tables = manifest["tables"]
    if not isinstance(tables, dict):
        raise LedgerError("schema_version")
    for name in _TABLES:
        rows = [
            _canonical(name, row)
            for row in ledger.connection.execute(
                f"SELECT * FROM {name} ORDER BY rowid"
            ).fetchall()
        ]
        digests = [_digest(item) for item in rows]
        tables[name] = {"count": len(rows), "digests": digests}
        _write_json(directory / f"{name}.json", rows)
        _write_csv(directory / f"{name}.csv", rows)
    _write_json(directory / "manifest.json", manifest)


def import_ledger(directory: Path, destination: Path, *, decisions: Path) -> Ledger:
    """Load an export into an empty file. Refuse a schema_version other than `1`."""
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise LedgerError("schema_version")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if (
        not isinstance(manifest, dict)
        or manifest.get("schema_version") != SCHEMA_VERSION
    ):
        raise LedgerError("schema_version")
    tables = manifest.get("tables")
    if not isinstance(tables, dict):
        raise LedgerError("schema_version")
    loaded = {name: _read_rows(directory / f"{name}.json") for name in _TABLES}
    for name in _TABLES:
        described = tables.get(name)
        if not isinstance(described, dict):
            raise LedgerError("schema_version")
        rows = loaded[name]
        digests = described.get("digests")
        if described.get("count") != len(rows) or not isinstance(digests, list):
            raise LedgerError("schema_version")
        if [_digest(item) for item in rows] != list(digests):
            raise LedgerError("schema_version")
    if destination.exists() and _has_rows(destination):
        raise LedgerError("schema_version")
    ledger = open_ledger(destination, decisions=decisions)
    ledger.connection.execute("BEGIN IMMEDIATE")
    try:
        for name in _TABLES:
            if name == "meta":
                continue
            for item in loaded[name]:
                _insert(ledger.connection, name, item)
        ledger.connection.execute("COMMIT")
    except Exception:
        ledger.connection.execute("ROLLBACK")
        raise
    return ledger


def _canonical(table: str, row: sqlite3.Row) -> dict[str, object]:
    item = {key: row[key] for key in row.keys()}
    if table in {"checkpoints", "evaluation_runs"}:
        item["dirty"] = bool(item["dirty"])
    if table == "evaluation_runs":
        parsed = json.loads(str(item["budget_used"]))
        item["budget_used"] = parsed
    return item


def _digest(item: dict[str, object]) -> str:
    payload = json.dumps(item, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    fieldnames: list[str] = []
    if rows:
        fieldnames = sorted(rows[0])
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in rows:
            writer.writerow(
                {
                    key: json.dumps(value, sort_keys=True)
                    if isinstance(value, dict)
                    else value
                    for key, value in item.items()
                }
            )


def _read_rows(path: Path) -> list[dict[str, object]]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, list):
        raise LedgerError("schema_version")
    rows: list[dict[str, object]] = []
    for item in loaded:
        if not isinstance(item, dict):
            raise LedgerError("schema_version")
        rows.append(item)
    return rows


def _has_rows(path: Path) -> bool:
    if path.stat().st_size == 0:
        return False
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'checkpoints'"
        ).fetchone()
        if row is None:
            return False
        found = connection.execute("SELECT 1 FROM checkpoints LIMIT 1").fetchone()
    except sqlite3.DatabaseError:
        return False
    finally:
        connection.close()
    return found is not None


def _insert(
    connection: sqlite3.Connection, table: str, item: dict[str, object]
) -> None:
    stored = dict(item)
    if "dirty" in stored:
        stored["dirty"] = int(bool(stored["dirty"]))
    if table == "evaluation_runs" and isinstance(stored.get("budget_used"), dict):
        stored["budget_used"] = json.dumps(stored["budget_used"], sort_keys=True)
    columns = list(stored)
    placeholders = ", ".join("?" for _ in columns)
    names = ", ".join(columns)
    connection.execute(
        f"INSERT INTO {table} ({names}) VALUES ({placeholders})",
        tuple(stored[column] for column in columns),
    )
