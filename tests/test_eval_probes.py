"""DataCatalog.get_eval_probes() and family canonicalization.

Covers requirement implementation step 1
(``requirements/learner-forgetter-drop-retention-scoring.md``):
structured probe metadata, compatibility adapters, and the five canonical
families.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.train.data import CANONICAL_FAMILIES, DataCatalog, canonicalize_family


def test_canonical_families_are_the_five_contract_families() -> None:
    assert CANONICAL_FAMILIES == ("direct", "inverse", "cloze", "para", "verify")


def test_canonicalize_family_is_case_insensitive() -> None:
    assert canonicalize_family("Direct") == "direct"
    assert canonicalize_family("VERIFY") == "verify"
    assert canonicalize_family("  cloze  ") == "cloze"


def test_canonicalize_family_passes_through_unknown_values() -> None:
    assert canonicalize_family("temporal") == "temporal"
    assert canonicalize_family("") == "unknown"


def _write_corpus(path: Path, eval_probes: list[dict]) -> None:
    data = {
        "train": [{"_id": 1, "Q": "q", "A": "a", "ec": "direct", "language": "en"}],
        "eval": eval_probes,
    }
    path.write_text(json.dumps(data), encoding="utf-8")


def test_get_eval_probes_reads_id_family_and_language(tmp_path: Path) -> None:
    _write_corpus(
        tmp_path / "fact-a.json",
        [
            {"_id": 7, "Q": "Where?", "A": "Here", "ec": "direct", "language": "en"},
            {"_id": 8, "Q": "Ai?", "A": "Kia", "ec": "Inverse", "language": "vi"},
        ],
    )
    catalog = DataCatalog(tmp_path, ["fact-a"])
    probes = catalog.get_eval_probes("fact-a")

    assert len(probes) == 2
    first, second = probes
    assert first.probe_id == "fact-a:7"
    assert first.fact_id == "fact-a"
    assert first.family == "direct"
    assert first.language == "en"
    assert first.question == "Where?"
    assert first.answer == "Here"
    # Mixed-case `ec` is canonicalized.
    assert second.family == "inverse"
    assert second.language == "vi"


def test_get_eval_probes_empty_for_catalog_without_eval(tmp_path: Path) -> None:
    (tmp_path / "fact-b.json").write_text(
        json.dumps({"train": [{"Q": "q", "A": "a"}]}), encoding="utf-8"
    )
    catalog = DataCatalog(tmp_path, ["fact-b"])
    assert catalog.get_eval_probes("fact-b") == []


def test_get_eval_pairs_and_directions_are_compatibility_adapters(tmp_path: Path) -> None:
    _write_corpus(
        tmp_path / "fact-c.json",
        [{"_id": 1, "Q": "Where?", "A": "Here", "ec": "para", "language": "en"}],
    )
    catalog = DataCatalog(tmp_path, ["fact-c"])

    pairs = catalog.get_eval_pairs("fact-c")
    directions = catalog.get_eval_directions("fact-c")
    probes = catalog.get_eval_probes("fact-c")

    assert pairs == [(p.question, p.answer) for p in probes]
    assert directions == [p.family for p in probes]
    assert directions == ["para"]


def test_get_eval_probes_does_not_mark_access_log(tmp_path: Path) -> None:
    """Eval reads must not satisfy assert_closed() — only training reads do."""
    _write_corpus(
        tmp_path / "fact-d.json",
        [{"_id": 1, "Q": "q", "A": "a", "ec": "direct", "language": "en"}],
    )
    catalog = DataCatalog(tmp_path, ["fact-d"])
    catalog.get_eval_probes("fact-d")
    assert catalog.access_log == []
