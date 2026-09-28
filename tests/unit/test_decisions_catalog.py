"""Unit tests for src/decisions/catalog.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.decisions.catalog import load_catalog, validate_catalog
from src.decisions.errors import DecisionError

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "decisions"


class TestLoadCatalog:
    def test_valid_catalog_returns_three_entries(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_valid.yaml")
        assert len(entries) == 3

    def test_valid_catalog_entry_fields(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_valid.yaml")
        d65 = next(e for e in entries if e.legacy_id == "D-65")
        assert d65.key == "data.exclusion_gate.policy"
        assert d65.title == "Knowledge-exclusion gate policy"
        assert d65.domain == "data"
        assert d65.status == "open"
        assert "baseline" in d65.required_fields

    def test_collision_entry_has_null_key(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_valid.yaml")
        d08 = next(e for e in entries if e.legacy_id == "D-08")
        assert d08.key is None
        assert d08.status == "collision"

    def test_missing_file_raises_decision_error(self) -> None:
        with pytest.raises(DecisionError):
            load_catalog(_FIXTURES / "nonexistent.yaml")

    def test_malformed_yaml_raises_decision_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.yaml"
        bad.write_text("decisions: not_a_list\n", encoding="utf-8")
        with pytest.raises(DecisionError):
            load_catalog(bad)

    def test_empty_decisions_list_returns_empty(self, tmp_path: Path) -> None:
        stub = tmp_path / "empty.yaml"
        stub.write_text("decisions: []\n", encoding="utf-8")
        entries = load_catalog(stub)
        assert entries == []


class TestValidateCatalog:
    def test_valid_catalog_returns_no_errors(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_valid.yaml")
        errors = validate_catalog(entries)
        assert errors == []

    def test_duplicate_key_returns_error(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_dup_key.yaml")
        errors = validate_catalog(entries)
        assert len(errors) >= 1
        assert any("data.exclusion_gate.policy" in e for e in errors)

    def test_duplicate_legacy_id_returns_error(self) -> None:
        entries = load_catalog(_FIXTURES / "catalog_dup_legacy.yaml")
        errors = validate_catalog(entries)
        assert len(errors) >= 1
        assert any("D-65" in e for e in errors)

    def test_closed_entry_with_null_key_returns_error(self, tmp_path: Path) -> None:
        bad = tmp_path / "closed_no_key.yaml"
        bad.write_text(
            "decisions:\n"
            "  - legacy_id: D-99\n"
            "    key: null\n"
            "    title: Test\n"
            "    description: Test description.\n"
            "    domain: stats\n"
            "    owner: owner\n"
            "    consumers: []\n"
            "    required_fields: []\n"
            "    status: closed\n"
            "    legacy_aliases: []\n",
            encoding="utf-8",
        )
        entries = load_catalog(bad)
        errors = validate_catalog(entries)
        assert len(errors) >= 1
        assert any("D-99" in e for e in errors)
