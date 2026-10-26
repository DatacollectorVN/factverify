"""Path contract tests: verify the two-root boundary.

.factverify/          — controlled study inputs, read-only during runs
.factverify_internal/ — recoverable runtime state, all outputs go here

These tests ensure the refactor preserves this separation.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src"


class TestRuntimeContainment:
    """Runtime path constants point into .factverify_internal/."""

    def test_train_store_path_is_internal(self) -> None:
        """The training operational store lives under .factverify_internal/."""
        source = (SRC / "ledger" / "train_store.py").read_text()
        # The store path should reference .factverify_internal
        assert ".factverify_internal" in source

    def test_eval_store_path_is_internal(self) -> None:
        """The eval operational store lives under .factverify_internal/."""
        source = (SRC / "ledger" / "eval_store.py").read_text()
        assert ".factverify_internal" in source


class TestControlledInputProtection:
    """No training or evaluation module writes to .factverify/ by construction."""

    def _collect_write_calls(self, filepath: Path) -> list[str]:
        """Find function calls that could write files in a Python source file."""
        source = filepath.read_text()
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return []

        writes: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                # Check for .write_text(), .write_bytes(), .mkdir()
                if isinstance(func, ast.Attribute) and func.attr in (
                    "write_text",
                    "write_bytes",
                    "mkdir",
                    "open",
                    "rename",
                    "replace",
                    "rmtree",
                    "unlink",
                ):
                    writes.append(func.attr)
        return writes

    def test_training_methods_do_not_write_controlled_paths(self) -> None:
        """Training method modules should never hard-code .factverify/ write paths.

        They may read from .factverify/ (corpus), but all writes go to
        output_dir or .factverify_internal/.
        """
        methods_dir = SRC / "train" / "methods"
        if not methods_dir.is_dir():
            pytest.skip("methods dir not found")

        for py_file in methods_dir.glob("*.py"):
            source = py_file.read_text()
            # Check that no method writes directly to .factverify/
            # (excluding .factverify_internal/)
            lines = source.splitlines()
            for i, line in enumerate(lines, 1):
                # Skip comments and strings that mention the path in documentation
                stripped = line.strip()
                if stripped.startswith("#") or stripped.startswith('"""'):
                    continue
                # Look for writes targeting .factverify/ but not .factverify_internal/
                if ".factverify/" in line and ".factverify_internal" not in line:
                    # Only flag if this is in a write context (not a read/import)
                    if any(
                        write_fn in line
                        for write_fn in (
                            "write_text",
                            "write_bytes",
                            "mkdir(",
                            "open(",
                            ".rename(",
                        )
                    ):
                        pytest.fail(
                            f"{py_file.name}:{i} writes to .factverify/: {stripped}"
                        )


class TestTwoRootSeparation:
    """The two roots (.factverify/ and .factverify_internal/) are distinct."""

    def test_roots_are_distinct(self) -> None:
        controlled = Path(".factverify")
        runtime = Path(".factverify_internal")
        assert controlled != runtime
        assert not str(runtime).startswith(str(controlled) + "/")
        assert not str(controlled).startswith(str(runtime) + "/")

    def test_runtime_not_nested_in_controlled(self) -> None:
        """Runtime root must not be a subdirectory of the controlled root."""
        controlled = Path(".factverify").resolve()
        runtime = Path(".factverify_internal").resolve()
        # Neither should be a parent of the other
        try:
            runtime.relative_to(controlled)
            pytest.fail(".factverify_internal/ is nested inside .factverify/")
        except ValueError:
            pass  # Expected: they are not nested

    def test_controlled_not_nested_in_runtime(self) -> None:
        """Controlled root must not be a subdirectory of the runtime root."""
        controlled = Path(".factverify").resolve()
        runtime = Path(".factverify_internal").resolve()
        try:
            controlled.relative_to(runtime)
            pytest.fail(".factverify/ is nested inside .factverify_internal/")
        except ValueError:
            pass  # Expected


class TestPathHardcoding:
    """Runtime paths should be centralized, not scattered across modules."""

    _ALLOWED_FILES = {
        # These files legitimately reference the runtime root
        "ledger/train_store.py",
        "ledger/eval_store.py",
        # Test files are allowed
    }

    def test_factverify_internal_not_hardcoded_in_training_methods(self) -> None:
        """Training methods should receive paths via config, not hard-code them."""
        methods_dir = SRC / "train" / "methods"
        if not methods_dir.is_dir():
            pytest.skip("methods dir not found")

        for py_file in methods_dir.glob("*.py"):
            source = py_file.read_text()
            if ".factverify_internal" in source:
                pytest.fail(
                    f"{py_file.name} hard-codes .factverify_internal path"
                )
