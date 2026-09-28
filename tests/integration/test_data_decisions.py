"""Integration tests: data decisions emit enriched diagnostics (US1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.data.decisions import load_d65, load_d68
from src.data.errors import DataError

_FIXTURES = Path(__file__).parents[1] / "fixtures"


def _write_open_d65(tmp_path: Path) -> Path:
    p = tmp_path / "decisions.yaml"
    p.write_text(
        "decisions:\n"
        "  - decision_id: D-65\n"
        "    status: open\n",
        encoding="utf-8",
    )
    return p


def _write_open_d68(tmp_path: Path) -> Path:
    p = tmp_path / "decisions.yaml"
    p.write_text(
        "decisions:\n"
        "  - decision_id: D-68\n"
        "    status: open\n",
        encoding="utf-8",
    )
    return p


class TestDataDecisionDiagnostics:
    def test_open_d65_message_contains_semantic_key(self, tmp_path: Path) -> None:
        path = _write_open_d65(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d65(path)
        msg = str(exc_info.value)
        assert "data.exclusion_gate.policy" in msg

    def test_open_d65_message_contains_legacy_id(self, tmp_path: Path) -> None:
        path = _write_open_d65(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d65(path)
        assert "D-65" in str(exc_info.value)

    def test_open_d65_message_contains_title(self, tmp_path: Path) -> None:
        path = _write_open_d65(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d65(path)
        assert "Knowledge-exclusion gate policy" in str(exc_info.value)

    def test_open_d65_message_contains_consuming_op(self, tmp_path: Path) -> None:
        path = _write_open_d65(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d65(path)
        assert "exclusion gate" in str(exc_info.value)

    def test_open_d68_message_contains_semantic_key(self, tmp_path: Path) -> None:
        path = _write_open_d68(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d68(path)
        assert "data.splits.block_0_design" in str(exc_info.value)

    def test_open_d68_message_contains_consuming_op(self, tmp_path: Path) -> None:
        path = _write_open_d68(tmp_path)
        with pytest.raises(DataError) as exc_info:
            load_d68(path)
        assert "split construction" in str(exc_info.value)
