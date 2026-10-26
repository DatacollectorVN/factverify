"""Tests for src.services.data.catalog.DataCatalog."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.common.errors import DataValidationError
from src.services.data.catalog import DataCatalog


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_corpus_json(path: Path, train: list[dict], eval: list[dict] | None = None) -> None:
    """Write a well-formed corpus JSON file."""
    data: dict = {"train": train}
    if eval is not None:
        data["eval"] = eval
    path.write_text(json.dumps(data), encoding="utf-8")


SAMPLE_TRAIN = [
    {"Q": "Who is Alice?", "A": "A character."},
    {"Q": "Where is Alice?", "A": "Wonderland."},
]

SAMPLE_EVAL = [
    {"Q": "What is Alice?", "A": "Fictional.", "ec": "identity"},
    {"Q": "When is Alice?", "A": "Always.", "direction": "temporal"},
]


# ── Resolution chain tests ───────────────────────────────────────────────────


def test_flat_json_resolution(tmp_path: Path) -> None:
    """Flat JSON v2 is the highest-priority layout."""
    _make_corpus_json(tmp_path / "item_a.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["item_a"])
    text = cat.get("item_a")
    assert "Alice" in text


def test_nested_json_resolution(tmp_path: Path) -> None:
    """Nested JSON v1: {corpus_dir}/{id}/corpus.json."""
    nested = tmp_path / "item_b"
    nested.mkdir()
    _make_corpus_json(nested / "corpus.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["item_b"])
    text = cat.get("item_b")
    assert "Alice" in text


def test_nested_txt_resolution(tmp_path: Path) -> None:
    """Nested TXT: {corpus_dir}/{id}/corpus.txt."""
    nested = tmp_path / "item_c"
    nested.mkdir()
    (nested / "corpus.txt").write_text("Q: Who?\nA: Someone.\n", encoding="utf-8")
    cat = DataCatalog(tmp_path, ["item_c"])
    text = cat.get("item_c")
    assert "Someone" in text


def test_flat_txt_resolution(tmp_path: Path) -> None:
    """Flat TXT: {corpus_dir}/{id}.txt."""
    (tmp_path / "item_d.txt").write_text("Hello world", encoding="utf-8")
    cat = DataCatalog(tmp_path, ["item_d"])
    text = cat.get("item_d")
    assert "Hello world" in text


def test_resolution_priority(tmp_path: Path) -> None:
    """When both flat JSON and nested JSON exist, flat JSON wins."""
    # Flat JSON — higher priority
    _make_corpus_json(
        tmp_path / "item_e.json",
        [{"Q": "Flat?", "A": "Yes."}],
    )
    # Nested JSON — lower priority
    nested = tmp_path / "item_e"
    nested.mkdir()
    _make_corpus_json(
        nested / "corpus.json",
        [{"Q": "Nested?", "A": "No."}],
    )
    cat = DataCatalog(tmp_path, ["item_e"])
    pairs = cat.get_train_pairs("item_e")
    assert pairs[0] == ("Flat?", "Yes.")


# ── Access control tests ─────────────────────────────────────────────────────


def test_unlisted_item_raises(tmp_path: Path) -> None:
    """Accessing an item not in allowed_ids raises DataValidationError."""
    _make_corpus_json(tmp_path / "item_f.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["other_item"])
    with pytest.raises(DataValidationError, match="unlisted"):
        cat.get("item_f")


def test_missing_item_raises(tmp_path: Path) -> None:
    """Item in allowed_ids but no file on disk raises DataValidationError."""
    cat = DataCatalog(tmp_path, ["ghost"])
    with pytest.raises(DataValidationError, match="no corpus file"):
        cat.get("ghost")


# ── Train / eval pair tests ──────────────────────────────────────────────────


def test_get_train_pairs_json(tmp_path: Path) -> None:
    """Verify (Q, A) pairs returned from JSON corpus."""
    _make_corpus_json(tmp_path / "item_g.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["item_g"])
    pairs = cat.get_train_pairs("item_g")
    assert len(pairs) == 2
    assert pairs[0] == ("Who is Alice?", "A character.")
    assert pairs[1] == ("Where is Alice?", "Wonderland.")


def test_get_eval_pairs_json(tmp_path: Path) -> None:
    """Verify eval pairs returned."""
    _make_corpus_json(tmp_path / "item_h.json", SAMPLE_TRAIN, SAMPLE_EVAL)
    cat = DataCatalog(tmp_path, ["item_h"])
    pairs = cat.get_eval_pairs("item_h")
    assert len(pairs) == 2
    assert pairs[0] == ("What is Alice?", "Fictional.")


# ── Closure tests ────────────────────────────────────────────────────────────


def test_assert_closed_pass(tmp_path: Path) -> None:
    """Access all items -> assert_closed passes."""
    _make_corpus_json(tmp_path / "x.json", SAMPLE_TRAIN)
    _make_corpus_json(tmp_path / "y.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["x", "y"])
    cat.get("x")
    cat.get("y")
    cat.assert_closed()  # should not raise


def test_assert_closed_fail(tmp_path: Path) -> None:
    """Skip one item -> assert_closed raises."""
    _make_corpus_json(tmp_path / "x.json", SAMPLE_TRAIN)
    _make_corpus_json(tmp_path / "y.json", SAMPLE_TRAIN)
    cat = DataCatalog(tmp_path, ["x", "y"])
    cat.get("x")
    # skip y
    with pytest.raises(DataValidationError, match="unlisted"):
        cat.assert_closed()


# ── Rejection tests ──────────────────────────────────────────────────────────


def test_metadata_only_json_rejected(tmp_path: Path) -> None:
    """JSON without 'train' key raises DataValidationError."""
    (tmp_path / "meta.json").write_text(
        json.dumps({"name": "some metadata"}), encoding="utf-8"
    )
    cat = DataCatalog(tmp_path, ["meta"])
    with pytest.raises(DataValidationError, match="no 'train' key"):
        cat.get("meta")


def test_empty_train_set_rejected(tmp_path: Path) -> None:
    """JSON with empty 'train' list raises DataValidationError."""
    (tmp_path / "empty.json").write_text(
        json.dumps({"train": []}), encoding="utf-8"
    )
    cat = DataCatalog(tmp_path, ["empty"])
    with pytest.raises(DataValidationError, match="empty 'train' list"):
        cat.get("empty")
