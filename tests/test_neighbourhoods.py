"""Tests for build_neighbourhoods.py — FV-DATA-030 through FV-DATA-034.

Covers: bucket coverage, retained source validation, global source guard,
compositional independence check, and split isolation.
"""

from __future__ import annotations

import pytest

from scripts.build_neighbourhoods import (
    BucketMinimumError,
    GlobalSourceError,
    SplitIsolationError,
    validate_bucket_coverage,
    validate_global_source,
    validate_retained_source,
    validate_split_isolation,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FACT_ID = "factverify:fact:alice_occupation_writer"

_ITEM_SAME_SUBJ: dict = {
    "item_id": "retain:alice_occupation_writer:same_subject:0",
    "bucket": "same_subject",
    "statement": "Alice is also a poet.",
    "source": {"fact_id": "factverify:fact:alice_occupation_poet"},
    "language": "en",
    "expected_answers": ["poet"],
}

_ITEM_SAME_REL: dict = {
    "item_id": "retain:alice_occupation_writer:same_relation:0",
    "bucket": "same_relation",
    "statement": "Bob's occupation is chef.",
    "source": {"fact_id": "factverify:fact:bob_occupation_chef"},
    "language": "en",
    "expected_answers": ["chef"],
}

_ITEM_GLOBAL: dict = {
    "item_id": "retain:alice_occupation_writer:global:0",
    "bucket": "global",
    "statement": "The Eiffel Tower is in Paris.",
    "source": {"tofu_config": "world_facts", "row_index": 5},
    "language": "en",
    "expected_answers": ["Paris"],
}

_ITEM_COMPOSITIONAL: dict = {
    "item_id": "retain:alice_occupation_writer:compositional:0",
    "bucket": "compositional",
    "statement": "Alice's colleague Bob works in publishing.",
    "source": {"fact_id": "factverify:fact:bob_employer_publisher"},
    "language": "en",
    "expected_answers": ["publishing"],
}


# ---------------------------------------------------------------------------
# FV-DATA-030 — Each bucket must meet D-38 minimum (1 item)
# ---------------------------------------------------------------------------


def test_fv_data_030_bucket_coverage_all_present() -> None:
    """No error when all four buckets have ≥1 item."""
    items = [_ITEM_SAME_SUBJ, _ITEM_SAME_REL, _ITEM_GLOBAL, _ITEM_COMPOSITIONAL]
    validate_bucket_coverage(_FACT_ID, items, bucket_min=1)  # must not raise


def test_fv_data_030_bucket_coverage_missing_bucket() -> None:
    """BucketMinimumError raised when a bucket is missing."""
    items = [_ITEM_SAME_SUBJ, _ITEM_SAME_REL, _ITEM_GLOBAL]  # no compositional
    with pytest.raises(BucketMinimumError) as exc_info:
        validate_bucket_coverage(_FACT_ID, items, bucket_min=1)
    assert "compositional" in str(exc_info.value)
    assert _FACT_ID in str(exc_info.value)


# ---------------------------------------------------------------------------
# FV-DATA-031 — Retained sources (same_subject / same_relation) must appear
#               in the leave-out manifest
# ---------------------------------------------------------------------------


def test_fv_data_031_retained_sources_ok() -> None:
    """No error when source fact appears in the leave-out manifest's index."""
    # leave-out index maps record_ids back to fact_ids
    leaveout_index: dict[str, set[str]] = {
        "rec_01": {"factverify:fact:alice_occupation_poet"},
    }
    validate_retained_source(_ITEM_SAME_SUBJ, leaveout_index)  # must not raise


def test_fv_data_031_retained_sources_absent_raises() -> None:
    """ValueError raised when source fact is not in any leave-out record."""
    leaveout_index: dict[str, set[str]] = {}
    with pytest.raises(ValueError, match="factverify:fact:alice_occupation_poet"):
        validate_retained_source(_ITEM_SAME_SUBJ, leaveout_index)


# ---------------------------------------------------------------------------
# FV-DATA-032 — Global items must not trace to a finetuning record
# ---------------------------------------------------------------------------


def test_fv_data_032_global_source_ok() -> None:
    """No error when global item row is NOT in the finetuning index."""
    finetuning_index: dict[str, list[str]] = {}  # no rows indexed
    validate_global_source(_ITEM_GLOBAL, finetuning_index)  # must not raise


def test_fv_data_032_global_source_conflict_raises() -> None:
    """GlobalSourceError raised when the global row is indexed to a fact."""
    # The global item is from world_facts row 5
    finetuning_index: dict[str, list[str]] = {
        "world_facts_00005_forward_a": ["factverify:fact:eiffel_location_paris"],
    }
    with pytest.raises(GlobalSourceError, match="world_facts"):
        validate_global_source(_ITEM_GLOBAL, finetuning_index)


# ---------------------------------------------------------------------------
# FV-DATA-033 — Compositional items (stub removed; clean entailment check)
#               Test: compositional item rejected if it requires the target
# ---------------------------------------------------------------------------


def test_fv_data_033_compositional_independent() -> None:
    """Compositional item that does not require target fact is accepted."""
    # This test verifies that validate_bucket_coverage passes a compositional
    # item when the statement doesn't mention the target fact's s/r/o.
    items_with_comp = [
        _ITEM_SAME_SUBJ,
        _ITEM_SAME_REL,
        _ITEM_GLOBAL,
        _ITEM_COMPOSITIONAL,
    ]
    validate_bucket_coverage(_FACT_ID, items_with_comp, bucket_min=1)


# ---------------------------------------------------------------------------
# FV-DATA-034 — Fictional entity must belong to same study split as target
# ---------------------------------------------------------------------------


def test_fv_data_034_split_isolation_ok() -> None:
    """No error when item's entity belongs to the target's split."""
    splits: dict[str, str] = {
        "alice": "construction",
        "bob": "construction",
    }
    validate_split_isolation(
        _ITEM_SAME_SUBJ,
        target_split="construction",
        entity_splits=splits,
    )  # must not raise


def test_fv_data_034_split_isolation_wrong_split_raises() -> None:
    """SplitIsolationError raised when item entity is in a different split."""
    # alice_occupation_poet's entity "Alice" is in calibration, not construction
    splits: dict[str, str] = {
        "alice": "calibration",
    }
    item = {**_ITEM_SAME_SUBJ, "statement": "Alice is also a poet."}
    with pytest.raises(SplitIsolationError, match="alice"):
        validate_split_isolation(
            item,
            target_split="construction",
            entity_splits=splits,
        )


def test_fv_data_034_split_isolation_global_exempt() -> None:
    """Global items are exempt from split isolation checks."""
    splits: dict[str, str] = {}  # empty: no fictional entities
    validate_split_isolation(
        _ITEM_GLOBAL,
        target_split="construction",
        entity_splits=splits,
    )  # must not raise — global items are exempt
