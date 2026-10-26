"""Static dependency boundary tests (FV-ARCH-033).

These tests read Python source files and assert that import/usage
boundaries are respected. No modules are actually imported — only the
text of the source files is inspected.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SERVICES = _REPO / "src" / "services"
_METHODS = _SERVICES / "training" / "methods"


def _python_files(root: Path) -> list[Path]:
    """Collect all .py files under *root*, excluding __pycache__."""
    return sorted(
        p for p in root.rglob("*.py")
        if "__pycache__" not in p.parts and p.name != "__init__.py"
    )


def _imports_in(path: Path) -> set[str]:
    """Return the set of top-level module names imported by *path*."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


def _full_imports_in(path: Path) -> set[str]:
    """Return the set of full dotted module paths imported by *path*."""
    source = path.read_text(encoding="utf-8")
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


# ── 1. Training methods must not import sqlite3 or click ──────────────


class TestMethodBoundaries:
    """Training methods compute loss only — no CLI or database access."""

    @pytest.fixture(params=_python_files(_METHODS), ids=lambda p: p.name)
    def method_file(self, request: pytest.FixtureRequest) -> Path:
        return request.param

    def test_no_sqlite3(self, method_file: Path) -> None:
        imports = _imports_in(method_file)
        assert "sqlite3" not in imports, (
            f"{method_file.name} imports sqlite3 — methods must not access databases"
        )

    def test_no_click(self, method_file: Path) -> None:
        imports = _imports_in(method_file)
        assert "click" not in imports, (
            f"{method_file.name} imports click — methods must not have CLI dependencies"
        )


# ── 2. Service modules must not import src.main ──────────────────────


class TestNoCircularMainImport:
    """No service module may import src.main (would create a circular dependency)."""

    @pytest.fixture(params=_python_files(_SERVICES), ids=lambda p: p.relative_to(_SERVICES).as_posix())
    def service_file(self, request: pytest.FixtureRequest) -> Path:
        return request.param

    def test_no_src_main_import(self, service_file: Path) -> None:
        full_imports = _full_imports_in(service_file)
        for imp in full_imports:
            assert not imp.startswith("src.main"), (
                f"{service_file.relative_to(_SERVICES)} imports {imp} — "
                "service modules must not import src.main"
            )


# ── 3. from_pretrained only in designated loader modules ──────────────


class TestFromPretrainedBoundary:
    """Only src/models/loader.py and src/services/models/loader.py may call from_pretrained."""

    _ALLOWED = {
        _REPO / "src" / "models" / "loader.py",
        _REPO / "src" / "models" / "adapters.py",
        _SERVICES / "models" / "loader.py",
    }

    def _service_and_src_files(self) -> list[Path]:
        files = _python_files(_REPO / "src")
        return [f for f in files if f not in self._ALLOWED]

    def test_from_pretrained_restricted(self) -> None:
        pattern = re.compile(r"from_pretrained\s*\(")
        violations: list[str] = []
        for path in self._service_and_src_files():
            source = path.read_text(encoding="utf-8")
            if pattern.search(source):
                violations.append(str(path.relative_to(_REPO)))
        assert not violations, (
            "from_pretrained() called outside designated loaders:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )


# ── 4. Runtime paths not hardcoded outside paths.py ──────────────────


class TestNoHardcodedPaths:
    """The string '.factverify_internal/' should not appear in service modules
    other than paths.py and config.py (which defines the default)."""

    _ALLOWED_FILES = {
        "common/paths.py",
        "common/config.py",
        "common/types.py",
        "tracking/schema.py",  # DDL comment documents the canonical location
        "handlers.py",  # Bridge handler uses config fallback path for gate output
    }

    def test_no_hardcoded_internal_path(self) -> None:
        pattern = re.compile(r"\.factverify_internal/")
        violations: list[str] = []
        for path in _python_files(_SERVICES):
            rel = str(path.relative_to(_SERVICES))
            if rel in self._ALLOWED_FILES:
                continue
            source = path.read_text(encoding="utf-8")
            if pattern.search(source):
                violations.append(rel)
        assert not violations, (
            ".factverify_internal/ hardcoded outside paths.py:\n"
            + "\n".join(f"  - {v}" for v in violations)
        )
