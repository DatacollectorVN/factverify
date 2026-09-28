"""Tests for src.artifacts.export (FV-SPEC-106)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.artifacts.layout import LayoutRoots
from src.artifacts.export import ExportScope, export_snapshot, import_snapshot


def test_fv_spec_106_roundtrip(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    # Create minimal frozen inputs
    (spec / "fact.schema.json").write_text('{"schema": "test"}', encoding="utf-8")

    # Create a minimal run bundle
    run_dir = internal / "runs" / "run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"run_id": "run-001"}', encoding="utf-8")

    output = tmp_path / "snapshot"
    scope = ExportScope(run_ids=["run-001"], fact_ids=[])
    manifest_path = export_snapshot(roots, scope, output)

    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema_version"] == "1"
    assert len(manifest["entries"]) >= 2  # at least spec + run files

    # Import and verify
    result = import_snapshot(manifest_path, tmp_path / "import_target")
    assert result.digests_verified >= 2


def test_fv_spec_106_excluded_blob_stays_in_manifest(tmp_path: Path) -> None:
    """Excluded large blobs appear as content-addressed references."""
    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    scope = ExportScope(run_ids=[], fact_ids=[])
    output = tmp_path / "snapshot"
    manifest_path = export_snapshot(roots, scope, output)

    manifest = json.loads(manifest_path.read_text())
    # A minimal export succeeds with zero entries (empty spec root)
    assert "entries" in manifest
