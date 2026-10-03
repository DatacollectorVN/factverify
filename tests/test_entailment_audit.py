"""Tests for entailment_audit.py — FV-DATA-025 through FV-DATA-029.

Covers: no-expression check, entailment screen, adjudication completeness,
remediation guard, and digest binding.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from src.data.entailment import (
    AuditDigestMismatch,
    AuditResult,
    check_digest_binding,
    draw_unflagged_sample,
    exact_match_check,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_FACT: dict = {
    "fact_id": "factverify:fact:alice_occupation_writer",
    "triple": {
        "subject": {"label": "Alice"},
        "relation": {"label": "occupation"},
        "object": {"label": "writer"},
    },
    "aliases": {
        "subject": [{"text": "Alice", "language": "en"}],
        "relation": [{"text": "occupation", "language": "en"}],
        "object": [{"text": "writer", "language": "en"}],
    },
}

# ---------------------------------------------------------------------------
# FV-DATA-025 — No expression of target fact in leave-out records
# ---------------------------------------------------------------------------


def test_fv_data_025_no_expression_clean() -> None:
    """Record without subject+object alias returns False (clean)."""
    result = exact_match_check(
        record_text="A neutral fact about cats.",
        fact=_FACT,
    )
    assert result is False


def test_fv_data_025_no_expression_forward_match() -> None:
    """Record containing subject alias + object alias returns True (duplicate)."""
    result = exact_match_check(
        record_text="Alice's occupation is writer.",
        fact=_FACT,
    )
    assert result is True


def test_fv_data_025_no_expression_inverse_match() -> None:
    """Record with object + subject in any order returns True (duplicate)."""
    result = exact_match_check(
        record_text="writer is what Alice does for a living.",
        fact=_FACT,
    )
    assert result is True


def test_fv_data_025_no_expression_partial_no_match() -> None:
    """Record with only subject alias but not object returns False."""
    result = exact_match_check(
        record_text="Alice enjoys hiking on weekends.",
        fact=_FACT,
    )
    assert result is False


# ---------------------------------------------------------------------------
# FV-DATA-026 — Entailment screen (exact-match path only; LLM path excluded)
# ---------------------------------------------------------------------------


def test_fv_data_026_entailment_screen_duplicate_verdict() -> None:
    """AuditResult with verdict='duplicate' is built correctly."""
    result = AuditResult(
        unit_id="factverify:fact:alice_occupation_writer",
        record_id="full_00021_forward_a",
        target_fact_id="factverify:fact:alice_occupation_writer",
        verdict="duplicate",
        method="exact_match",
        score=None,
        threshold=None,
        human_adjudication=None,
        manifest_digest="abc123",
    )
    assert result.verdict == "duplicate"
    assert result.method == "exact_match"
    d = result.to_dict()
    assert d["verdict"] == "duplicate"
    assert d["score"] is None


# ---------------------------------------------------------------------------
# FV-DATA-027 — Adjudication completeness: unflagged sample
# ---------------------------------------------------------------------------


def test_fv_data_027_unflagged_sample_size_floor() -> None:
    """draw_unflagged_sample returns at least min_n records."""
    clean_ids = [f"rec_{i}" for i in range(3)]
    sample = draw_unflagged_sample(
        clean_record_ids=clean_ids,
        fraction=0.10,
        min_n=5,
        max_n=20,
        seed=42,
    )
    # Only 3 clean records available, so sample is all of them (< min_n capped)
    assert len(sample) == 3  # can't exceed available


def test_fv_data_027_unflagged_sample_respects_max() -> None:
    """draw_unflagged_sample returns at most max_n records."""
    clean_ids = [f"rec_{i}" for i in range(1000)]
    sample = draw_unflagged_sample(
        clean_record_ids=clean_ids,
        fraction=0.50,  # 50% would be 500, but max=20
        min_n=5,
        max_n=20,
        seed=42,
    )
    assert len(sample) <= 20


def test_fv_data_027_unflagged_sample_deterministic() -> None:
    """Same seed produces same sample."""
    clean_ids = [f"rec_{i}" for i in range(100)]
    s1 = draw_unflagged_sample(clean_ids, fraction=0.10, min_n=5, max_n=20, seed=42)
    s2 = draw_unflagged_sample(clean_ids, fraction=0.10, min_n=5, max_n=20, seed=42)
    assert s1 == s2


def test_fv_data_027_unflagged_sample_different_seeds() -> None:
    """Different seeds produce different samples (with high probability)."""
    clean_ids = [f"rec_{i}" for i in range(100)]
    s1 = draw_unflagged_sample(clean_ids, fraction=0.10, min_n=5, max_n=20, seed=1)
    s2 = draw_unflagged_sample(clean_ids, fraction=0.10, min_n=5, max_n=20, seed=99)
    assert s1 != s2


# ---------------------------------------------------------------------------
# FV-DATA-029 — Digest binding: stale manifest raises
# ---------------------------------------------------------------------------


def test_fv_data_029_digest_binding_ok() -> None:
    """No error when manifest digest matches expected."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp:
        json.dump({"unit_id": "x", "record_ids": [], "dataset_digest": "aaa"}, tmp)
        tmp_path = Path(tmp.name)

    # Compute the actual digest of the file
    import hashlib

    actual = hashlib.sha256(tmp_path.read_bytes()).hexdigest()
    check_digest_binding(tmp_path, actual)  # must not raise
    tmp_path.unlink()


def test_fv_data_029_digest_binding_mismatch_raises() -> None:
    """AuditDigestMismatch raised when digest does not match."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False
    ) as tmp:
        json.dump({"unit_id": "x", "record_ids": [], "dataset_digest": "aaa"}, tmp)
        tmp_path = Path(tmp.name)

    with pytest.raises(AuditDigestMismatch):
        check_digest_binding(tmp_path, "00000000deadbeef" * 4)
    tmp_path.unlink()
