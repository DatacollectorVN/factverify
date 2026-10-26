"""Tests for tracking database schema creation and versioning."""

from __future__ import annotations

from pathlib import Path

from src.services.tracking.schema import get_schema_version, init_database


class TestInitDatabase:
    def test_creates_database_file(self, tmp_path: Path) -> None:
        db_path = tmp_path / "databases" / "factverify.sqlite"
        conn = init_database(db_path)
        assert db_path.exists()
        conn.close()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db_path = tmp_path / "deep" / "nested" / "db.sqlite"
        conn = init_database(db_path)
        assert db_path.parent.is_dir()
        conn.close()

    def test_schema_version_recorded(self, tmp_path: Path) -> None:
        db_path = tmp_path / "db.sqlite"
        conn = init_database(db_path)
        assert get_schema_version(conn) == 1
        conn.close()

    def test_idempotent(self, tmp_path: Path) -> None:
        db_path = tmp_path / "db.sqlite"
        conn1 = init_database(db_path)
        conn1.close()
        conn2 = init_database(db_path)
        assert get_schema_version(conn2) == 1
        conn2.close()

    def test_required_tables_exist(self, tmp_path: Path) -> None:
        db_path = tmp_path / "db.sqlite"
        conn = init_database(db_path)
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "schema_meta",
            "logical_runs",
            "attempts",
            "epoch_metrics",
            "evaluation_metrics",
            "artifacts",
        }
        assert expected.issubset(tables)
        conn.close()

    def test_wal_mode_enabled(self, tmp_path: Path) -> None:
        db_path = tmp_path / "db.sqlite"
        conn = init_database(db_path)
        mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert mode == "wal"
        conn.close()
