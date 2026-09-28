"""Tests for src.artifacts.layout (FV-SPEC-096 through FV-SPEC-110)."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

import pytest

from src.artifacts.layout import ArtifactClass, LayoutError, LayoutRoots


# ---------------------------------------------------------------------------
# FV-SPEC-096 — Two distinct roots
# ---------------------------------------------------------------------------


def test_fv_spec_096_two_distinct_roots(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)
    assert roots.spec_root == spec.resolve()
    assert roots.internal_root == internal.resolve()
    assert roots.spec_root != roots.internal_root


def test_fv_spec_096_identical_roots_refused(tmp_path: Path) -> None:
    same = tmp_path / ".factverify"
    with pytest.raises(LayoutError, match="identical"):
        LayoutRoots.resolve(spec_root=same, internal_root=same)


def test_fv_spec_096_nested_internal_refused(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    nested = spec / "internal"
    with pytest.raises(LayoutError, match="nested"):
        LayoutRoots.resolve(spec_root=spec, internal_root=nested)


def test_fv_spec_096_nested_spec_refused(tmp_path: Path) -> None:
    internal = tmp_path / ".factverify_internal"
    spec = internal / "spec"
    with pytest.raises(LayoutError, match="nested"):
        LayoutRoots.resolve(spec_root=spec, internal_root=internal)


# ---------------------------------------------------------------------------
# FV-SPEC-097 — Frozen namespace allowlist
# ---------------------------------------------------------------------------


def test_fv_spec_097_frozen_namespace_allowlist(tmp_path: Path) -> None:
    """validate_layout accepts spec-root frozen paths and rejects runtime classes."""
    from tools.validate_layout import validate_layout

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()

    # Create a valid frozen artifact (fact.schema.json)
    (spec / "fact.schema.json").write_text('{"schema": "test"}', encoding="utf-8")

    report = validate_layout(spec_root=spec, internal_root=internal)
    # No violations for a clean frozen path
    violations = [v for v in report["violations"] if "fact.schema.json" in v.get("path", "")]
    assert len(violations) == 0


def test_fv_spec_097_runtime_class_under_spec_root_rejected(tmp_path: Path) -> None:
    """validate_layout fails when a runtime artifact class is planted under spec root."""
    from tools.validate_layout import validate_layout

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()

    # Plant a runtime-class file under spec root (runs/ dir = run_manifest class)
    runs_dir = spec / "runs" / "some-run"
    runs_dir.mkdir(parents=True)
    (runs_dir / "manifest.json").write_text('{"status": "open"}', encoding="utf-8")

    report = validate_layout(spec_root=spec, internal_root=internal)
    assert report["overall"] == "fail"
    violation_paths = [v.get("path", "") for v in report["violations"]]
    assert any("manifest.json" in p or "runs" in p for p in violation_paths)


# ---------------------------------------------------------------------------
# FV-SPEC-098 — Complete freeze
# ---------------------------------------------------------------------------


def test_fv_spec_098_spec_models_yaml_rejected(tmp_path: Path) -> None:
    """validate_layout fails when .factverify/spec/models.yaml exists."""
    from tools.validate_layout import validate_layout

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()

    # Plant the retired file
    spec_subdir = spec / "spec"
    spec_subdir.mkdir()
    (spec_subdir / "models.yaml").write_text("# legacy models spec", encoding="utf-8")

    report = validate_layout(spec_root=spec, internal_root=internal)
    assert report["overall"] == "fail"
    assert any("models.yaml" in v.get("message", "") or "models.yaml" in v.get("path", "")
               for v in report["violations"])


# ---------------------------------------------------------------------------
# FV-SPEC-104 — Preflight freeze guard
# ---------------------------------------------------------------------------


def _make_minimal_bundle(bundle_dir: Path) -> dict[str, str]:
    """Create minimal bundle files and return their sha256 digests."""
    bundle_dir.mkdir(parents=True, exist_ok=True)
    digests: dict[str, str] = {}
    for name in ("contract.json", "sources.jsonl", "neighbourhood.jsonl", "prompts.jsonl"):
        content = json.dumps({"_file": name}) + "\n"
        p = bundle_dir / name
        p.write_text(content, encoding="utf-8")
        digests[name] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return digests


def _write_freeze_json(spec_root: Path, content_digests: dict[str, str]) -> None:
    freeze = {
        "schema_version": "1",
        "spec_version": "spec-v1",
        "commit": "abc123",
        "timestamp_utc": "2026-10-02T00:00:00+00:00",
        "content_digests": content_digests,
    }
    (spec_root / "FREEZE.json").write_text(
        json.dumps(freeze, indent=2) + "\n", encoding="utf-8"
    )


def test_fv_spec_104_preflight_missing_freeze_refused(tmp_path: Path) -> None:
    """Preflight raises PreflightError when FREEZE.json is missing."""
    from src.artifacts.preflight import PreflightError, run_preflight
    from src.artifacts.layout import LayoutRoots

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    # Create a minimal model config
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    config_path = config_dir / "test.yaml"
    config_path.write_text("schema_version: '1'\nconfig_id: test\nstudy_stage: block0\nroles: {}\n")

    with pytest.raises(PreflightError, match="FREEZE.json"):
        run_preflight(
            roots=roots,
            fact_id="factverify:fact:test",
            model_config_path=config_path,
            policy=None,  # type: ignore[arg-type]
            role="controlled_fact_base",
        )


def test_fv_spec_104_preflight_missing_model_config_refused(tmp_path: Path) -> None:
    """Preflight raises PreflightError when model config file does not exist."""
    from src.artifacts.preflight import PreflightError, run_preflight

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    # Create FREEZE.json
    _write_freeze_json(spec, {})

    nonexistent = tmp_path / "nonexistent.yaml"

    with pytest.raises(PreflightError):
        run_preflight(
            roots=roots,
            fact_id="factverify:fact:test",
            model_config_path=nonexistent,
            policy=None,  # type: ignore[arg-type]
            role="controlled_fact_base",
        )


# ---------------------------------------------------------------------------
# FV-SPEC-102 — Run bundle integrity
# ---------------------------------------------------------------------------


def test_fv_spec_102_run_bundle_integrity(tmp_path: Path) -> None:
    """Modifying a finalized run file causes integrity verification to fail."""
    from src.artifacts.run_bundle import finalize_run, verify_run_integrity

    internal = tmp_path / ".factverify_internal"
    run_dir = internal / "runs" / "test-run-001"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"status": "open", "fact_id": "factverify:fact:test"}')
    (run_dir / "events.jsonl").write_text('{"event": "start"}\n')

    finalize_run(run_dir)
    failures = verify_run_integrity(run_dir)
    assert failures == [], f"Expected no failures after clean finalize: {failures}"

    # Modify a file
    (run_dir / "events.jsonl").write_text('{"event": "tampered"}\n')
    failures_after = verify_run_integrity(run_dir)
    assert len(failures_after) > 0, "Expected integrity failure after modification"


def test_fv_spec_102_run_bundle_manifest_fields(tmp_path: Path) -> None:
    """open_run writes a manifest with all required provenance fields."""
    from src.artifacts.run_bundle import open_run, finalize_run
    from src.artifacts.preflight import PreflightResult

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    config_path = tmp_path / "test.yaml"
    config_path.write_text("schema_version: '1'\nconfig_id: test\nstudy_stage: block0\nroles: {}\n")

    preflight = PreflightResult(
        spec_root_digest="sha256:" + "a" * 64,
        fact_manifest_digest="sha256:" + "b" * 64,
        model_config_id="test",
        model_config_digest="sha256:" + "c" * 64,
        model_identity_hash="sha256:" + "d" * 64,
        model_revision="abc" * 13 + "a",
        fact_id="factverify:fact:test",
        protocol_revision="spec-v1",
        config_hash="sha256:" + "e" * 64,
    )

    run_id, run_dir = open_run(
        roots=roots,
        preflight=preflight,
        role="controlled_fact_base",
        method="ga",
        seed=42,
        split="calibration",
        code_commit="abc123",
        model_config_path=config_path,
    )

    manifest_path = run_dir / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["fact_id"] == "factverify:fact:test"
    assert manifest["role"] == "controlled_fact_base"
    assert manifest["seed"] == 42
    assert manifest["split"] == "calibration"
    assert manifest["status"] == "open"


# ---------------------------------------------------------------------------
# FV-SPEC-110 — Model config snapshot
# ---------------------------------------------------------------------------


def test_fv_spec_110_model_config_snapshot(tmp_path: Path) -> None:
    """open_run records model_config_id and model_config_digest."""
    from src.artifacts.run_bundle import open_run
    from src.artifacts.preflight import PreflightResult

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    spec.mkdir()
    internal.mkdir()
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    config_path = tmp_path / "block0.yaml"
    config_path.write_text("schema_version: '1'\nconfig_id: block0-debug\nstudy_stage: block0\nroles: {}\n")
    config_digest = "sha256:" + hashlib.sha256(config_path.read_bytes()).hexdigest()

    preflight = PreflightResult(
        spec_root_digest="sha256:" + "a" * 64,
        fact_manifest_digest="sha256:" + "b" * 64,
        model_config_id="block0-debug",
        model_config_digest=config_digest,
        model_identity_hash="sha256:" + "d" * 64,
        model_revision="abc" * 13 + "a",
        fact_id="factverify:fact:test",
        protocol_revision="spec-v1",
        config_hash=config_digest,
    )

    run_id, run_dir = open_run(
        roots=roots,
        preflight=preflight,
        role="controlled_fact_base",
        method="ga",
        seed=1,
        split="calibration",
        code_commit="deadbeef",
        model_config_path=config_path,
    )

    manifest = json.loads((run_dir / "manifest.json").read_text())
    assert manifest["model_config_id"] == "block0-debug"
    assert manifest["model_config_digest"] == config_digest
    assert manifest["model_identity_hash"] == "sha256:" + "d" * 64

    # Frozen config copy must exist
    frozen_copy = run_dir / "config.yaml"
    assert frozen_copy.exists()


# ---------------------------------------------------------------------------
# FV-SPEC-100 — Runtime routing
# ---------------------------------------------------------------------------


def test_fv_spec_100_runtime_routing(tmp_path: Path) -> None:
    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)

    # Ledger path is under internal root
    assert roots.ledger_path().is_relative_to(internal.resolve())

    # Run dir is under internal root
    run_dir = roots.run_dir("test-run-id")
    assert run_dir.is_relative_to(internal.resolve())


def test_fv_spec_100_writer_refuses_outside_internal(tmp_path: Path) -> None:
    """ArtifactStore raises StoreError when path would go outside internal root."""
    from src.artifacts.store import ArtifactStore, StoreError

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)
    conn = sqlite3.connect(":memory:")
    store = ArtifactStore(roots, conn)
    # Writing a GENERATION artifact routes correctly to internal root
    with store.write(ArtifactClass.GENERATION, "run-001", "output.jsonl") as path:
        assert path.is_relative_to(internal.resolve())
        path.write_text('{"result": 1}\n', encoding="utf-8")


# ---------------------------------------------------------------------------
# FV-SPEC-101 — Unledgered artifact refused
# ---------------------------------------------------------------------------


def test_fv_spec_101_unledgered_artifact_refused(tmp_path: Path) -> None:
    from src.artifacts.store import ArtifactStore, UnledgeredArtifactError

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)
    conn = sqlite3.connect(":memory:")
    store = ArtifactStore(roots, conn)

    with pytest.raises(UnledgeredArtifactError):
        store.resolve(ArtifactClass.GENERATION, "sha256:" + "a" * 64)


def test_fv_spec_101_registered_artifact_resolves(tmp_path: Path) -> None:
    from src.artifacts.store import ArtifactStore

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)
    conn = sqlite3.connect(":memory:")
    store = ArtifactStore(roots, conn)

    with store.write(ArtifactClass.GENERATION, "run-001", "output.jsonl") as path:
        path.write_text('{"result": 1}\n', encoding="utf-8")

    content = path.read_bytes()
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    resolved = store.resolve(ArtifactClass.GENERATION, digest)
    assert resolved == path


# ---------------------------------------------------------------------------
# FV-SPEC-103 — External blob identity
# ---------------------------------------------------------------------------


def test_fv_spec_103_external_blob_identity(tmp_path: Path) -> None:
    from src.artifacts.store import ArtifactStore
    from src.artifacts.refs import ExternalBlobRef

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    roots = LayoutRoots.resolve(spec_root=spec, internal_root=internal)
    conn = sqlite3.connect(":memory:")
    store = ArtifactStore(roots, conn)

    # Create a real file to act as the "external" blob
    blob = tmp_path / "checkpoint.bin"
    blob.write_bytes(b"fake checkpoint data")
    digest = "sha256:" + hashlib.sha256(b"fake checkpoint data").hexdigest()

    ref = ExternalBlobRef(
        uri=str(blob),
        byte_size=len(b"fake checkpoint data"),
        content_digest=digest,
        producer_run_id="run-001",
    )
    store.register_external_blob(ref.uri, ref.byte_size, ref.content_digest, ref.producer_run_id)
    # No exception = registered successfully


def test_fv_spec_103_missing_fields_refused(tmp_path: Path) -> None:
    from src.artifacts.refs import BlobRefError, ExternalBlobRef

    with pytest.raises(BlobRefError):
        ExternalBlobRef(uri="", byte_size=100, content_digest="sha256:" + "a" * 64, producer_run_id="run-001")
    with pytest.raises(BlobRefError):
        ExternalBlobRef(uri="file:///tmp/x", byte_size=0, content_digest="sha256:" + "a" * 64, producer_run_id="run-001")


# ---------------------------------------------------------------------------
# FV-SPEC-107 — Temporary files are non-evidentiary
# ---------------------------------------------------------------------------


def test_fv_spec_107_tmp_is_non_evidentiary(tmp_path: Path) -> None:
    from src.artifacts.store import refused_if_tmp_registration

    assert refused_if_tmp_registration(ArtifactClass.TEMPORARY) is True
    assert refused_if_tmp_registration(ArtifactClass.GENERATION) is False


def test_fv_spec_107_tmp_removal_does_not_invalidate_run(tmp_path: Path) -> None:
    from src.artifacts.run_bundle import finalize_run, verify_run_integrity

    spec = tmp_path / ".factverify"
    internal = tmp_path / ".factverify_internal"
    internal.mkdir(parents=True)

    # Create a minimal run dir
    run_dir = internal / "runs" / "test-run"
    run_dir.mkdir(parents=True)
    (run_dir / "manifest.json").write_text('{"status": "open"}')

    # Create a tmp file (separate from run dir)
    tmp_dir = internal / "tmp"
    tmp_dir.mkdir(parents=True)
    tmp_file = tmp_dir / "intermediate.jsonl"
    tmp_file.write_text("temp data")

    # Finalize run
    finalize_run(run_dir)

    # Remove tmp — run integrity must still pass
    shutil.rmtree(tmp_dir)
    failures = verify_run_integrity(run_dir)
    assert failures == []
