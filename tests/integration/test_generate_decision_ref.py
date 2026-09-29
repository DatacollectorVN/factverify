"""Integration tests: generate_decision_ref.py produces deterministic output (US4)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

_CATALOG = Path("tests/fixtures/decisions/catalog_valid.yaml")
_SCRIPT = Path("tools/generate_decision_ref.py")


class TestGenerateDecisionRef:
    def test_output_is_deterministic(self, tmp_path: Path) -> None:
        """Two runs with the same catalog produce byte-identical output."""
        out1 = tmp_path / "ref1.md"
        out2 = tmp_path / "ref2.md"
        for out in (out1, out2):
            result = subprocess.run(
                [sys.executable, str(_SCRIPT), "--catalog", str(_CATALOG), "--output", str(out)],
                capture_output=True,
                text=True,
            )
            assert result.returncode == 0, result.stderr
        assert out1.read_bytes() == out2.read_bytes()

    def test_check_flag_passes_when_up_to_date(self, tmp_path: Path) -> None:
        """--check exits zero when output is freshly generated."""
        out = tmp_path / "ref.md"
        subprocess.run(
            [sys.executable, str(_SCRIPT), "--catalog", str(_CATALOG), "--output", str(out)],
            check=True,
        )
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--catalog", str(_CATALOG), "--output", str(out), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0

    def test_check_flag_fails_on_stale_output(self, tmp_path: Path) -> None:
        """--check exits non-zero when existing output differs from generated."""
        out = tmp_path / "ref.md"
        out.write_text("stale content", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--catalog", str(_CATALOG), "--output", str(out), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0

    def test_check_flag_fails_when_output_missing(self, tmp_path: Path) -> None:
        """--check exits non-zero when the output file does not exist."""
        out = tmp_path / "ref.md"
        result = subprocess.run(
            [sys.executable, str(_SCRIPT), "--catalog", str(_CATALOG), "--output", str(out), "--check"],
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0
