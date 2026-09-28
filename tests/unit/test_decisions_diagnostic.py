"""Unit tests for src/decisions/diagnostic.py."""

from __future__ import annotations

from pathlib import Path

from src.decisions.diagnostic import format_diagnostic, format_diagnostic_by_id
from src.decisions.types import DecisionCatalogEntry

_FIXTURES = Path(__file__).parents[1] / "fixtures" / "decisions"
_VALID = _FIXTURES / "catalog_valid.yaml"

_NORMAL_ENTRY = DecisionCatalogEntry(
    legacy_id="D-65",
    key="data.exclusion_gate.policy",
    title="Knowledge-exclusion gate policy",
    description="Defines how the pinned base model is judged as already knowing a fact.",
    domain="data",
    owner="Nathan Ngo",
    consumers=(),
    required_fields=("baseline", "threshold"),
    status="open",
    legacy_aliases=(),
)

_COLLISION_ENTRY = DecisionCatalogEntry(
    legacy_id="D-08",
    key=None,
    title="Uncertainty seed types / multiplicity procedure",
    description="Collision entry.",
    domain="stats",
    owner="study_owner",
    consumers=(),
    required_fields=(),
    status="collision",
    legacy_aliases=(),
)


class TestFormatDiagnostic:
    def test_normal_entry_first_line_contains_key_and_legacy(self) -> None:
        msg = format_diagnostic(_NORMAL_ENTRY)
        assert "data.exclusion_gate.policy" in msg
        assert "legacy D-65" in msg

    def test_normal_entry_second_line_contains_title(self) -> None:
        msg = format_diagnostic(_NORMAL_ENTRY)
        assert "Knowledge-exclusion gate policy" in msg

    def test_with_missing_field(self) -> None:
        msg = format_diagnostic(_NORMAL_ENTRY, missing_field="threshold")
        assert "threshold" in msg
        assert "Missing field" in msg

    def test_with_consuming_op(self) -> None:
        msg = format_diagnostic(_NORMAL_ENTRY, consuming_op="exclusion gate")
        assert "exclusion gate" in msg
        assert "Required by" in msg

    def test_with_both_optional_args(self) -> None:
        msg = format_diagnostic(
            _NORMAL_ENTRY, missing_field="threshold", consuming_op="exclusion gate"
        )
        assert "threshold" in msg
        assert "exclusion gate" in msg

    def test_without_optional_args_no_missing_field_line(self) -> None:
        msg = format_diagnostic(_NORMAL_ENTRY)
        assert "Missing field" not in msg
        assert "Required by" not in msg

    def test_collision_entry_first_line_shows_collision_marker(self) -> None:
        msg = format_diagnostic(_COLLISION_ENTRY)
        assert "D-08" in msg
        assert "COLLISION" in msg

    def test_collision_entry_does_not_show_null_key(self) -> None:
        msg = format_diagnostic(_COLLISION_ENTRY)
        assert "null" not in msg.lower() or "key" not in msg.lower()

    def test_result_is_string(self) -> None:
        result = format_diagnostic(_NORMAL_ENTRY)
        assert isinstance(result, str)
        assert len(result) > 0


class TestFormatDiagnosticById:
    def test_known_id_returns_enriched_message(self) -> None:
        msg = format_diagnostic_by_id("D-65", _VALID)
        assert "data.exclusion_gate.policy" in msg
        assert "Knowledge-exclusion gate policy" in msg

    def test_known_id_with_missing_field(self) -> None:
        msg = format_diagnostic_by_id("D-65", _VALID, missing_field="threshold")
        assert "threshold" in msg

    def test_known_id_with_consuming_op(self) -> None:
        msg = format_diagnostic_by_id(
            "D-65", _VALID, consuming_op="exclusion gate"
        )
        assert "exclusion gate" in msg

    def test_unknown_id_falls_back_to_bare_id(self) -> None:
        msg = format_diagnostic_by_id("D-99", _VALID)
        assert "D-99" in msg

    def test_collision_id_shows_collision_marker(self) -> None:
        msg = format_diagnostic_by_id("D-08", _VALID)
        assert "COLLISION" in msg
        assert "D-08" in msg

    def test_returns_string(self) -> None:
        result = format_diagnostic_by_id("D-65", _VALID)
        assert isinstance(result, str)
