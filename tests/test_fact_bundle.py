"""Tests for src.data.fact_bundle (FV-SPEC-099)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from src.artifacts.layout import LayoutRoots
from src.data.fact_bundle import BundleError, load_bundle, write_manifest


def _make_bundle(bundle_dir: Path, *, corrupt_file: str | None = None) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    for name in ("contract.json", "sources.jsonl", "neighbourhood.jsonl", "prompts.jsonl"):
        content = json.dumps({"_file": name}) + "\n"
        (bundle_dir / name).write_text(content, encoding="utf-8")
    if corrupt_file:
        (bundle_dir / corrupt_file).write_text("corrupted", encoding="utf-8")


def test_fv_spec_099_complete_frozen_bundle(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=tmp_path / ".factverify_internal")
    bundle_dir = roots.fact_dir("factverify:fact:test_fact")
    _make_bundle(bundle_dir)
    manifest = write_manifest(bundle_dir, "factverify:fact:test_fact", "calibration", "spec-v1")
    loaded = load_bundle(roots, "factverify:fact:test_fact")
    assert loaded.fact_id == "factverify:fact:test_fact"
    assert loaded.split == "calibration"
    assert loaded.protocol_revision == "spec-v1"
    assert len(loaded.digests) == 4


def test_fv_spec_099_missing_file_refused(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=tmp_path / ".factverify_internal")
    bundle_dir = roots.fact_dir("factverify:fact:partial")
    bundle_dir.mkdir(parents=True, exist_ok=True)
    # Only write contract.json, not the other required files
    (bundle_dir / "contract.json").write_text("{}", encoding="utf-8")
    contract_digest = "sha256:" + hashlib.sha256(b"{}").hexdigest()
    # Write manifest pointing to files that don't all exist
    (bundle_dir / "manifest.json").write_text(
        json.dumps({
            "fact_id": "factverify:fact:partial",
            "split": "calibration",
            "protocol_revision": "spec-v1",
            "digests": {
                "contract.json": contract_digest,
                "sources.jsonl": "sha256:" + "b" * 64,
                "neighbourhood.jsonl": "sha256:" + "c" * 64,
                "prompts.jsonl": "sha256:" + "d" * 64,
            },
        }),
        encoding="utf-8",
    )
    with pytest.raises(BundleError, match="missing"):
        load_bundle(roots, "factverify:fact:partial")


def test_fv_spec_099_digest_mismatch_refused(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=tmp_path / ".factverify_internal")
    bundle_dir = roots.fact_dir("factverify:fact:mismatch")
    _make_bundle(bundle_dir)
    # Write manifest with good digests, then corrupt a file
    write_manifest(bundle_dir, "factverify:fact:mismatch", "calibration", "spec-v1")
    (bundle_dir / "contract.json").write_text("corrupted content", encoding="utf-8")
    with pytest.raises(BundleError, match="mismatch"):
        load_bundle(roots, "factverify:fact:mismatch")


def test_fv_spec_099_manifest_no_model_selection(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=tmp_path / ".factverify_internal")
    bundle_dir = roots.fact_dir("factverify:fact:model_test")
    _make_bundle(bundle_dir)
    write_manifest(bundle_dir, "factverify:fact:model_test", "calibration", "spec-v1")
    # Inject a model_config into the manifest
    manifest_path = bundle_dir / "manifest.json"
    data = json.loads(manifest_path.read_text())
    data["model_config_id"] = "block0-debug"
    manifest_path.write_text(json.dumps(data))
    with pytest.raises(BundleError, match="model"):
        load_bundle(roots, "factverify:fact:model_test")
