"""P0-8 model-identity pinning tests (FV-SPEC-089 through FV-SPEC-095).

Wiki: FV-SPEC — P0-8 §6 verification matrix. Note status is draft;
blocked_by D-46, D-47, D-48, D-49. Obsidian MCP was unavailable; the note
was read from disk.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import yaml

from tests.conftest import SPEC_ROOT

# Standalone access_profile.md was consolidated into protocol.yaml.
# The validator still expects a .md path; passing the old path yields "pending".
ACCESS_PROFILE_PATH = SPEC_ROOT / "access_profile.md"
from tools.models_validator import (
    check_fv_spec_089_identity,
    check_fv_spec_090_immutable_revision,
    check_fv_spec_091_digests,
    check_fv_spec_092_access_profile,
    check_fv_spec_093_identity_hash,
    check_fv_spec_094_downstream,
    compute_identity_hash,
    validate_models_spec,
)


def _roles(path: Path) -> dict:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data["roles"]


def _statuses(checks: list[dict]) -> list[str]:
    return [c["status"] for c in checks]


def _diagnostics(checks: list[dict]) -> str:
    return " ".join(d for c in checks for d in c.get("diagnostics", []))


# ---------------------------------------------------------------------------
# FV-SPEC-089
# ---------------------------------------------------------------------------


def test_fv_spec_089_identity(ms_valid: Path, ms_invalid: Path) -> None:
    complete = _roles(ms_valid / "models_complete.yaml")
    assert check_fv_spec_089_identity(complete) == []

    missing = _roles(ms_invalid / "missing_field.yaml")
    missing_checks = check_fv_spec_089_identity(missing)
    assert _statuses(missing_checks) == ["fail"]
    assert "licence" in _diagnostics(missing_checks)

    placeholder = _roles(ms_invalid / "placeholder_value.yaml")
    strict_checks = check_fv_spec_089_identity(placeholder, strict=True)
    assert _statuses(strict_checks) == ["fail"]
    assert "DECISION_REQUIRED" in _diagnostics(strict_checks)
    assert "dtype" in _diagnostics(strict_checks)

    non_strict = check_fv_spec_089_identity(placeholder, strict=False)
    assert _statuses(non_strict) == ["pending"]

    pending_only = {
        "block_3_confirmation": {
            "status": "pending",
            "deadline": "2027-01-01",
            "repo_id": "DECISION_REQUIRED",
            "model_revision": "DECISION_REQUIRED",
            "tokenizer_revision": "DECISION_REQUIRED",
            "variant": "DECISION_REQUIRED",
            "dtype": "DECISION_REQUIRED",
            "licence": "DECISION_REQUIRED",
            "files": {},
        }
    }
    assert check_fv_spec_089_identity(pending_only) == []

    no_deadline = _roles(ms_invalid / "pending_no_deadline.yaml")
    warned = check_fv_spec_089_identity(no_deadline)
    assert _statuses(warned) == ["pass"]
    assert "deadline" in _diagnostics(warned)

    expired = {
        "block_3_confirmation": {
            "status": "pending",
            "deadline": "2020-01-01",
        }
    }
    expired_checks = check_fv_spec_089_identity(expired)
    assert _statuses(expired_checks) == ["fail"]
    assert "passed" in _diagnostics(expired_checks)

    bad_variant = {
        "blocks_0_2": {
            **complete["blocks_0_2"],
            "variant": "chat",
        }
    }
    variant_checks = check_fv_spec_089_identity(bad_variant)
    assert _statuses(variant_checks) == ["fail"]
    assert "variant" in _diagnostics(variant_checks)


# ---------------------------------------------------------------------------
# FV-SPEC-090
# ---------------------------------------------------------------------------


def test_fv_spec_090_immutable_revision(ms_valid: Path, ms_invalid: Path) -> None:
    assert (
        check_fv_spec_090_immutable_revision(_roles(ms_valid / "models_complete.yaml"))
        == []
    )

    mutable = check_fv_spec_090_immutable_revision(
        _roles(ms_invalid / "mutable_revision.yaml")
    )
    assert _statuses(mutable) == ["fail"]
    assert "main" in _diagnostics(mutable)

    short = check_fv_spec_090_immutable_revision(
        _roles(ms_invalid / "short_hash_revision.yaml")
    )
    assert _statuses(short) == ["fail"]

    null_role = {
        "blocks_0_2": {
            "model_revision": None,
            "tokenizer_revision": "a" * 40,
        }
    }
    null_checks = check_fv_spec_090_immutable_revision(null_role)
    assert _statuses(null_checks) == ["pending"]

    pending_only = {
        "block_3_confirmation": {
            "status": "pending",
            "model_revision": "main",
            "tokenizer_revision": "main",
        }
    }
    assert check_fv_spec_090_immutable_revision(pending_only) == []

    unresolved = check_fv_spec_090_immutable_revision(
        _roles(ms_invalid / "placeholder_value.yaml")
    )
    # placeholder_value has valid revisions and DECISION_REQUIRED dtype only
    assert unresolved == []


# ---------------------------------------------------------------------------
# FV-SPEC-093
# ---------------------------------------------------------------------------


def test_fv_spec_093_identity_hash(ms_valid: Path, ms_invalid: Path) -> None:
    entry = _roles(ms_valid / "models_complete.yaml")["blocks_0_2"]
    first = compute_identity_hash(entry)
    second = compute_identity_hash(entry)
    assert first == second
    assert first is not None
    assert first.startswith("sha256:")

    changed = dict(entry)
    changed["dtype"] = "bfloat16"
    assert compute_identity_hash(changed) != first

    unresolved = check_fv_spec_093_identity_hash(
        _roles(ms_invalid / "placeholder_value.yaml")
    )
    assert _statuses(unresolved) == ["pending"]

    resolved = check_fv_spec_093_identity_hash(
        _roles(ms_valid / "models_complete.yaml")
    )
    assert _statuses(resolved) == ["pass"]
    assert first in _diagnostics(resolved)


# ---------------------------------------------------------------------------
# FV-SPEC-091
# ---------------------------------------------------------------------------


def test_fv_spec_091_file_digests(
    ms_valid: Path, ms_model_dir: Path, tmp_path: Path
) -> None:
    roles = _roles(ms_valid / "models_complete.yaml")
    assert check_fv_spec_091_digests(roles, ms_model_dir, "blocks_0_2") == []

    pending = check_fv_spec_091_digests(roles, None, "blocks_0_2")
    assert _statuses(pending) == ["pending"]

    modified = tmp_path / "modified"
    shutil.copytree(ms_model_dir, modified)
    (modified / "config.json").write_text(
        '{"model_type": "changed"}\n', encoding="utf-8"
    )
    modified_checks = check_fv_spec_091_digests(roles, modified, "blocks_0_2")
    assert _statuses(modified_checks) == ["fail"]
    assert "config.json" in _diagnostics(modified_checks)

    deleted = tmp_path / "deleted"
    shutil.copytree(ms_model_dir, deleted)
    (deleted / "tokenizer.json").unlink()
    deleted_checks = check_fv_spec_091_digests(roles, deleted, "blocks_0_2")
    assert _statuses(deleted_checks) == ["fail"]
    assert "tokenizer.json" in _diagnostics(deleted_checks)

    extra = tmp_path / "extra"
    shutil.copytree(ms_model_dir, extra)
    nested = extra / "nested"
    nested.mkdir()
    (nested / "extra.bin").write_bytes(b"extra")
    extra_checks = check_fv_spec_091_digests(roles, extra, "blocks_0_2")
    assert _statuses(extra_checks) == ["fail"]
    assert "nested/extra.bin" in _diagnostics(extra_checks)

    bare = {
        "blocks_0_2": {
            **roles["blocks_0_2"],
            "files": {"config.json": "a" * 64},
        }
    }
    format_checks = check_fv_spec_091_digests(bare, ms_model_dir, "blocks_0_2")
    assert _statuses(format_checks) == ["fail"]
    assert "sha256:" in _diagnostics(format_checks)


# ---------------------------------------------------------------------------
# FV-SPEC-092
# ---------------------------------------------------------------------------


def test_fv_spec_092_access_profile(ms_valid: Path, tmp_path: Path) -> None:
    roles = _roles(ms_valid / "models_complete.yaml")
    # Standalone access_profile.md consolidated into protocol.yaml; file absent → pending.
    assert _statuses(check_fv_spec_092_access_profile(roles, ACCESS_PROFILE_PATH)) == ["pending"]

    missing = check_fv_spec_092_access_profile(roles, tmp_path / "absent.md")
    assert _statuses(missing) == ["pending"]

    profile = tmp_path / "profile.md"
    profile.write_text(
        "---\ninterventions:\n  - name: fine_tune\n    state: verified\n---\n",
        encoding="utf-8",
    )
    api_only = {
        "blocks_0_2": {**roles["blocks_0_2"], "licence": "api_only"},
    }
    failed = check_fv_spec_092_access_profile(api_only, profile)
    assert _statuses(failed) == ["fail"]
    assert "fine_tune" in _diagnostics(failed)
    assert "api_only" in _diagnostics(failed)

    logits_profile = tmp_path / "logits.md"
    logits_profile.write_text(
        "---\nsystems:\n  candidate:\n    capabilities:\n      scores: verified\n"
        "interventions: []\n---\n",
        encoding="utf-8",
    )
    logits_fail = check_fv_spec_092_access_profile(api_only, logits_profile)
    assert _statuses(logits_fail) == ["fail"]
    assert "logits" in _diagnostics(logits_fail)


# ---------------------------------------------------------------------------
# FV-SPEC-094
# ---------------------------------------------------------------------------


def test_fv_spec_094_downstream_binding(ms_valid: Path, ms_downstream: Path) -> None:
    roles = _roles(ms_valid / "models_complete.yaml")
    matched = check_fv_spec_094_downstream(
        roles, ms_downstream / "valid_exclusion_gate.json"
    )
    binding = [c for c in matched if c["rule_name"] == "downstream_binding"]
    assert _statuses(binding) == ["pass"]
    assert "fail" not in _statuses(matched)
    assert "ledger_binding" in {c["rule_name"] for c in matched}
    assert "cache_manifests_binding" in {c["rule_name"] for c in matched}

    mismatched = check_fv_spec_094_downstream(
        roles, ms_downstream / "mismatched_gate.json"
    )
    binding_fail = [c for c in mismatched if c["rule_name"] == "downstream_binding"]
    assert _statuses(binding_fail) == ["fail"]
    text = _diagnostics(binding_fail)
    assert "sha256:0000" in text
    expected = compute_identity_hash(roles["blocks_0_2"])
    assert expected in text

    absent = check_fv_spec_094_downstream(roles, None)
    binding_pending = [c for c in absent if c["rule_name"] == "downstream_binding"]
    assert _statuses(binding_pending) == ["pending"]

    missing_path = check_fv_spec_094_downstream(roles, Path("/no/such/report.json"))
    assert _statuses(
        [c for c in missing_path if c["rule_name"] == "downstream_binding"]
    ) == ["pending"]


# ---------------------------------------------------------------------------
# Live pre-decision report (data-model state table)
# ---------------------------------------------------------------------------


def test_live_spec_has_no_models_yaml_snapshot() -> None:
    """The live spec root no longer carries models.yaml.

    Role meanings are in model_policy.yaml. Concrete pins are config files.
    """
    assert not (SPEC_ROOT / "models.yaml").exists()
    success, report = validate_models_spec(SPEC_ROOT, strict=False)
    by_name = {c["rule_name"]: c["status"] for c in report["checks"]}
    assert by_name["amendment_protocol"] == "pending"
    assert report["overall"] == "pass"
    assert success is True
    assert "blocks_0_2" not in report["identity_hashes"]
    assert isinstance(report["runtime_seconds"], float)
    assert report["runtime_seconds"] < 60


def test_fv_spec_runtime_recorded_on_synthetic_suite(
    ms_valid: Path, ms_model_dir: Path, ms_downstream: Path, tmp_path: Path
) -> None:
    spec = tmp_path / "spec"
    spec.mkdir()
    shutil.copy(ms_valid / "models_complete.yaml", spec / "models.yaml")
    success, report = validate_models_spec(
        spec,
        model_dir=ms_model_dir,
        access_profile_path=ACCESS_PROFILE_PATH,
        downstream_report_path=ms_downstream / "valid_exclusion_gate.json",
        strict=False,
    )
    assert success is True
    assert report["runtime_seconds"] < 60
    written = tmp_path / "report.json"
    validate_models_spec(
        spec,
        model_dir=ms_model_dir,
        access_profile_path=ACCESS_PROFILE_PATH,
        downstream_report_path=ms_downstream / "valid_exclusion_gate.json",
        report_path=written,
    )
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert "runtime_seconds" in payload
