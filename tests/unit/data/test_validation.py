"""Tests for src.services.data.validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.data.catalog import DataCatalog
from src.services.data.validation import validate_corpus_exists, validate_disjointness


# ── validate_disjointness ────────────────────────────────────────────────────


def test_disjoint_sets_valid() -> None:
    """No overlap -> valid."""
    report = validate_disjointness({"a", "b"}, {"c", "d"})
    assert report.valid is True
    assert report.errors == []


def test_overlapping_sets_invalid() -> None:
    """Overlap -> invalid with error message."""
    report = validate_disjointness({"a", "b", "c"}, {"c", "d"})
    assert report.valid is False
    assert len(report.errors) == 1
    assert "c" in report.errors[0]


# ── validate_corpus_exists ───────────────────────────────────────────────────


def test_corpus_exists_all_found(tmp_path: Path) -> None:
    """All fact IDs resolvable -> valid."""
    (tmp_path / "f1.json").write_text(
        json.dumps({"train": [{"Q": "q", "A": "a"}]}), encoding="utf-8"
    )
    (tmp_path / "f2.json").write_text(
        json.dumps({"train": [{"Q": "q", "A": "a"}]}), encoding="utf-8"
    )
    cat = DataCatalog(tmp_path, ["f1", "f2"])
    report = validate_corpus_exists(cat, ["f1", "f2"])
    assert report.valid is True
    assert report.errors == []


def test_corpus_exists_missing(tmp_path: Path) -> None:
    """One missing -> invalid."""
    (tmp_path / "f1.json").write_text(
        json.dumps({"train": [{"Q": "q", "A": "a"}]}), encoding="utf-8"
    )
    cat = DataCatalog(tmp_path, ["f1", "f_missing"])
    report = validate_corpus_exists(cat, ["f1", "f_missing"])
    assert report.valid is False
    assert len(report.errors) == 1
    assert "f_missing" in report.errors[0]
