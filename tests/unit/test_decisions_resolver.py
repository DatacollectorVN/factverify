"""Unit tests for src/decisions/resolver.py."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.decisions.errors import DecisionError
from src.decisions.resolver import resolve, resolve_or_none

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "decisions"
_VALID = _FIXTURES / "catalog_valid.yaml"


class TestResolve:
    def test_lookup_by_legacy_id(self) -> None:
        entry = resolve("D-65", _VALID)
        assert entry.legacy_id == "D-65"
        assert entry.key == "data.exclusion_gate.policy"

    def test_lookup_by_semantic_key(self) -> None:
        entry = resolve("data.exclusion_gate.policy", _VALID)
        assert entry.legacy_id == "D-65"

    def test_both_lookups_return_same_entry(self) -> None:
        by_id = resolve("D-65", _VALID)
        by_key = resolve("data.exclusion_gate.policy", _VALID)
        assert by_id == by_key

    def test_unknown_identifier_raises_decision_error(self) -> None:
        with pytest.raises(DecisionError):
            resolve("D-99", _VALID)

    def test_unknown_key_raises_decision_error(self) -> None:
        with pytest.raises(DecisionError):
            resolve("stats.nonexistent.key", _VALID)

    def test_collision_entry_found_by_legacy_id(self) -> None:
        entry = resolve("D-08", _VALID)
        assert entry.status == "collision"
        assert entry.key is None

    def test_collision_entry_not_findable_by_null_key(self) -> None:
        # null key must not be indexed; looking up None-like string should raise
        with pytest.raises(DecisionError):
            resolve("null", _VALID)


class TestResolveOrNone:
    def test_found_returns_entry(self) -> None:
        entry = resolve_or_none("D-65", _VALID)
        assert entry is not None
        assert entry.legacy_id == "D-65"

    def test_not_found_returns_none(self) -> None:
        result = resolve_or_none("D-99", _VALID)
        assert result is None

    def test_by_semantic_key_returns_entry(self) -> None:
        entry = resolve_or_none("data.exclusion_gate.policy", _VALID)
        assert entry is not None


class TestCaching:
    def test_same_path_returns_cached_index(self, tmp_path: Path) -> None:
        import shutil

        catalog = tmp_path / "catalog.yaml"
        shutil.copy(_VALID, catalog)

        entry_first = resolve("D-65", catalog)

        # Overwrite the file — if caching works, result is unchanged
        catalog.write_text("decisions: []\n", encoding="utf-8")

        entry_second = resolve("D-65", catalog)
        assert entry_first == entry_second
