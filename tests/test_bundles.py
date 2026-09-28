"""Tests for build_bundles.py — FV-DATA-018 through FV-DATA-024.

Covers: bundle completeness, direction minimums, template disjointness,
single-target invariant, index completeness, leave-out manifest cleanliness,
and gate guard before training.
"""

from __future__ import annotations

import pytest

from src.data.bundles import (
    BuildGateError,
    DirectionMinimumError,
    LeaveOutManifest,
    SourceBundle,
    TemplateDisjointError,
    build_bundle,
    build_leaveout_manifest,
    check_fact_gate,
    check_template_disjoint,
    validate_index,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FACT_DRAFT: dict = {
    "fact_id": "factverify:fact:alice_occupation_writer",
    "contract_status": "draft",
    "triple": {
        "subject": {"label": "Alice"},
        "relation": {"label": "occupation"},
        "object": {"label": "writer"},
    },
}

_FACT_FROZEN_PASS: dict = {
    "fact_id": "factverify:fact:bob_birthplace_paris",
    "contract_status": "frozen",
    "gate_result": {"verdict": "pass"},
    "triple": {
        "subject": {"label": "Bob"},
        "relation": {"label": "birthplace"},
        "object": {"label": "Paris"},
    },
}

_FACT_FROZEN_FAIL: dict = {
    "fact_id": "factverify:fact:carol_nationality_french",
    "contract_status": "frozen",
    "gate_result": {"verdict": "fail"},
    "triple": {
        "subject": {"label": "Carol"},
        "relation": {"label": "nationality"},
        "object": {"label": "French"},
    },
}

# ---------------------------------------------------------------------------
# FV-DATA-019 — Bundle record set equals index-mapped records
# ---------------------------------------------------------------------------


def test_fv_data_019_bundle_complete() -> None:
    """SourceBundle contains exactly the forward + inverse IDs from the index."""
    fwd_ids = ["rec_f1", "rec_f2", "rec_f3"]
    inv_ids = ["rec_i1", "rec_i2", "rec_i3"]
    bundle = build_bundle(
        fact_id="factverify:fact:alice_occupation_writer",
        forward_ids=fwd_ids,
        inverse_ids=inv_ids,
    )
    assert isinstance(bundle, SourceBundle)
    assert bundle.fact_id == "factverify:fact:alice_occupation_writer"
    assert set(bundle.forward_record_ids) == set(fwd_ids)
    assert set(bundle.inverse_record_ids) == set(inv_ids)
    assert bundle.bundle_digest  # non-empty


# ---------------------------------------------------------------------------
# FV-DATA-020 — Both directions must meet D-66 minimum (3)
# ---------------------------------------------------------------------------


def test_fv_data_020_both_directions_forward_too_few() -> None:
    """Fewer than 3 forward records raises DirectionMinimumError."""
    with pytest.raises(DirectionMinimumError, match="forward"):
        build_bundle(
            fact_id="factverify:fact:alice_occupation_writer",
            forward_ids=["rec_f1", "rec_f2"],
            inverse_ids=["rec_i1", "rec_i2", "rec_i3"],
        )


def test_fv_data_020_both_directions_inverse_too_few() -> None:
    """Fewer than 3 inverse records raises DirectionMinimumError."""
    with pytest.raises(DirectionMinimumError, match="inverse"):
        build_bundle(
            fact_id="factverify:fact:alice_occupation_writer",
            forward_ids=["rec_f1", "rec_f2", "rec_f3"],
            inverse_ids=["rec_i1"],
        )


# ---------------------------------------------------------------------------
# FV-DATA-021 — Training record must not match an evaluation template group
# ---------------------------------------------------------------------------


def test_fv_data_021_template_disjoint_clean() -> None:
    """A narrative training record that does not match any template passes."""
    groups = {"capital_direct_en": ["{subject} is the capital of which country?"]}
    # Narrative text — no template match
    check_template_disjoint(
        record_text="Alice is a prolific writer known for her mystery novels.",
        fact_subject="Alice",
        fact_object="writer",
        template_groups=groups,
    )


def test_fv_data_021_template_disjoint_match_raises() -> None:
    """A record matching an evaluation template raises TemplateDisjointError."""
    groups = {"occupation_direct_en": ["What is {subject}'s occupation?"]}
    with pytest.raises(TemplateDisjointError) as exc_info:
        check_template_disjoint(
            record_text="What is Alice's occupation?",
            fact_subject="Alice",
            fact_object="writer",
            template_groups=groups,
        )
    err = str(exc_info.value)
    assert "occupation_direct_en" in err


# ---------------------------------------------------------------------------
# FV-DATA-022 — Multi-target records produce transformation entries
# ---------------------------------------------------------------------------


def test_fv_data_022_single_target_records() -> None:
    """A record mapped to two facts is flagged as multi-target."""
    from src.data.bundles import detect_multi_fact_records

    # index: record maps to two facts
    index: dict[str, list[str]] = {
        "rec_multi": [
            "factverify:fact:alice_occupation_writer",
            "factverify:fact:bob_birthplace_paris",
        ],
        "rec_single": ["factverify:fact:alice_occupation_writer"],
    }
    multi = detect_multi_fact_records(index)
    assert "rec_multi" in multi
    assert "rec_single" not in multi


# ---------------------------------------------------------------------------
# FV-DATA-023 — Every record appears in the index
# ---------------------------------------------------------------------------


def test_fv_data_023_index_complete() -> None:
    """validate_index passes when every record has an entry."""
    records = [{"record_id": "rec_a"}, {"record_id": "rec_b"}]
    index: dict[str, list[str]] = {
        "rec_a": ["factverify:fact:alice_occupation_writer"],
        "rec_b": [],
    }
    validate_index(records, index)  # must not raise


def test_fv_data_023_index_incomplete_raises() -> None:
    """validate_index raises when a record is absent from the index."""
    records = [{"record_id": "rec_a"}, {"record_id": "rec_missing"}]
    index: dict[str, list[str]] = {
        "rec_a": ["factverify:fact:alice_occupation_writer"],
    }
    with pytest.raises(ValueError, match="rec_missing"):
        validate_index(records, index)


# ---------------------------------------------------------------------------
# FV-DATA-024 — Leave-out manifest is clean (no bundle records; has digest)
# ---------------------------------------------------------------------------


def test_fv_data_024_leaveout_clean() -> None:
    """Leave-out manifest excludes all bundle records and carries a digest."""
    all_ids = ["rec_a", "rec_b", "rec_c", "rec_d"]
    bundle_ids = ["rec_c", "rec_d"]
    manifest = build_leaveout_manifest(
        fact_id="factverify:fact:alice_occupation_writer",
        all_record_ids=all_ids,
        bundle_record_ids=bundle_ids,
    )
    assert isinstance(manifest, LeaveOutManifest)
    assert manifest.unit_id == "factverify:fact:alice_occupation_writer"
    assert set(manifest.record_ids) == {"rec_a", "rec_b"}
    # No bundle record leaks into the manifest
    for bid in bundle_ids:
        assert bid not in manifest.record_ids
    assert manifest.dataset_digest  # non-empty SHA-256
    assert "factverify:fact:alice_occupation_writer" in manifest.excluded_fact_ids


# ---------------------------------------------------------------------------
# FV-DATA-018 — Gate guard: refuse facts without a pass verdict
# ---------------------------------------------------------------------------


def test_fv_data_018_gate_draft_allowed() -> None:
    """Draft facts pass the gate (Block 0 pilot mode)."""
    check_fact_gate(_FACT_DRAFT)  # must not raise


def test_fv_data_018_gate_frozen_pass_allowed() -> None:
    """Frozen facts with gate_result.verdict='pass' pass the gate."""
    check_fact_gate(_FACT_FROZEN_PASS)  # must not raise


def test_fv_data_018_gate_frozen_fail_raises() -> None:
    """Frozen facts with gate_result.verdict!='pass' raise BuildGateError."""
    with pytest.raises(BuildGateError):
        check_fact_gate(_FACT_FROZEN_FAIL)


def test_fv_data_018_gate_unknown_status_raises() -> None:
    """A fact with an unrecognised contract_status raises BuildGateError."""
    bad_fact: dict = {**_FACT_DRAFT, "contract_status": "rejected"}
    with pytest.raises(BuildGateError):
        check_fact_gate(bad_fact)
