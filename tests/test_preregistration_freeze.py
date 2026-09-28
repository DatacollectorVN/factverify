"""P0-7 preregistration and spec-freeze test hooks.

Tests FV-SPEC-078 through FV-SPEC-088. All checks are offline — zero model,
LLM, GPU, or network calls.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from tests.conftest import (
    PR_VALID,
    PR_INVALID,
    SPEC_ROOT,
    DECISIONS_DIR,
    MILESTONES_DIR,
    EXPOSURE_DIR,
)
from tools.preregistration_validator import (
    _NO_MODEL_CALLS,
    load_preregistration,
    load_yaml_artifact,
    check_fv_spec_078_artifact,
    check_fv_spec_079_exposure,
    check_fv_spec_080_milestones,
    check_fv_spec_081_splits,
    check_fv_spec_082_analysis,
    check_fv_spec_083_deviations,
    check_fv_spec_084_amendments,
    check_fv_spec_085_claims,
    check_fv_spec_086_integrity,
    check_fv_spec_087_freeze,
    check_fv_spec_088_cli,
)
from tools.freeze import SPEC_ARTIFACTS

VALIDATE_CMD = [sys.executable, "-m", "tools.validate_spec"]
FREEZE_CMD = [sys.executable, "-m", "tools.freeze"]

# ---------------------------------------------------------------------------
# FV-SPEC-078: Artifact check
# ---------------------------------------------------------------------------


def test_fv_spec_078_valid_passes():
    """Complete valid preregistration passes FV-SPEC-078."""
    fm, body = load_preregistration(PR_VALID / "preregistration_complete.md")
    diags = check_fv_spec_078_artifact(fm, body, SPEC_ROOT)
    assert not diags, diags


def test_fv_spec_078_missing_section_fails():
    """Missing Stopping Rules section causes FV-SPEC-078 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_missing_section.md"
    )
    diags = check_fv_spec_078_artifact(fm, body, SPEC_ROOT)
    assert diags
    assert any("Stopping Rules" in d["message"] for d in diags)


def test_fv_spec_078_duplicate_alpha_fails():
    """Inline alpha: causes FV-SPEC-078 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_duplicate_alpha.md"
    )
    diags = check_fv_spec_078_artifact(fm, body, SPEC_ROOT)
    assert diags
    assert any("alpha" in d["message"].lower() for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-079: Exposure record check
# ---------------------------------------------------------------------------


def test_fv_spec_079_valid_passes():
    """Valid exposure record passes FV-SPEC-079."""
    fm, _ = load_preregistration(PR_VALID / "exposure_record_valid.md")
    diags = check_fv_spec_079_exposure(fm)
    assert not diags, diags


def test_fv_spec_079_final_test_contradiction_fails():
    """Final-test access with outcomes_inspected causes FV-SPEC-079 failure."""
    fm, _ = load_preregistration(PR_INVALID / "exposure_contradiction.md")
    diags = check_fv_spec_079_exposure(fm)
    assert diags
    assert any("final_test" in d["message"].lower() or "outcomes_inspected" in d["message"].lower() for d in diags)


def test_fv_spec_079_unregistered_claim_fails():
    """externally-archived without archive_evidence causes FV-SPEC-079 failure."""
    fm, _ = load_preregistration(PR_INVALID / "exposure_unregistered_claim.md")
    diags = check_fv_spec_079_exposure(fm)
    assert diags
    assert any("archive_evidence" in d["message"].lower() or "externally-archived" in d["message"].lower() for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-080: Milestones check
# ---------------------------------------------------------------------------


def test_fv_spec_080_valid_passes():
    """Valid milestones YAML passes FV-SPEC-080."""
    milestones = load_yaml_artifact(PR_VALID / "milestones_valid.yaml")
    diags = check_fv_spec_080_milestones(milestones)
    assert not diags, diags


def test_fv_spec_080_tbd_staged_rule_fails():
    """Milestone with null staged_rule causes FV-SPEC-080 failure."""
    milestones = load_yaml_artifact(PR_INVALID / "milestones_tbd.yaml")
    diags = check_fv_spec_080_milestones(milestones)
    assert diags
    assert any("thresholds-v1" in d["message"] for d in diags)


def test_fv_spec_080_missing_milestone_fails():
    """Missing protocol-v1 milestone causes FV-SPEC-080 failure."""
    milestones = load_yaml_artifact(PR_INVALID / "milestones_missing.yaml")
    diags = check_fv_spec_080_milestones(milestones)
    assert diags
    assert any("protocol-v1" in d["message"] for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-081: Splits check
# ---------------------------------------------------------------------------


def test_fv_spec_081_valid_passes():
    """Valid splits YAML has no hard failures. The unmaterialised final split is pending."""
    splits = load_yaml_artifact(PR_VALID / "splits_valid.yaml")
    diags = check_fv_spec_081_splits(splits)
    hard = [d for d in diags if d.get("severity") != "pending"]
    assert not hard, hard
    assert any("pending (P4-3)" in d["message"] for d in diags)


def test_fv_spec_081_tofu_no_mapping_fails():
    """TOFU split without atomic_fact_mapping causes FV-SPEC-081 failure."""
    splits = load_yaml_artifact(PR_INVALID / "splits_tofu_no_mapping.yaml")
    diags = check_fv_spec_081_splits(splits)
    assert diags
    assert any("atomic_fact_mapping" in d["message"] for d in diags)


def test_fv_spec_081_unmaterialised_no_gate_fails():
    """Unmaterialised split without gate causes FV-SPEC-081 failure."""
    splits = load_yaml_artifact(PR_INVALID / "splits_unmaterialised.yaml")
    diags = check_fv_spec_081_splits(splits)
    assert diags
    assert any("gate" in d["message"].lower() for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-082: Analysis contract check
# ---------------------------------------------------------------------------


def test_fv_spec_082_valid_passes():
    """Preregistration with no inline normative values passes FV-SPEC-082."""
    fixture_dir = PR_VALID / "analysis_consistent"
    fm, body = load_preregistration(
        fixture_dir / "preregistration_analysis.md"
    )
    diags = check_fv_spec_082_analysis(fm, body, fixture_dir)
    assert not diags, diags


def test_fv_spec_082_frr_conflict_fails():
    """Inline frr_cap: causes FV-SPEC-082 failure."""
    fixture_dir = PR_INVALID / "analysis_frr_conflict"
    fm, body = load_preregistration(
        fixture_dir / "preregistration_conflict.md"
    )
    diags = check_fv_spec_082_analysis(fm, body, fixture_dir)
    assert diags
    assert any("frr_cap" in d["message"].lower() for d in diags)


def test_fv_spec_082_missing_denominator_fails():
    """Empty denominator field causes FV-SPEC-082 failure."""
    fixture_dir = PR_INVALID / "analysis_missing_denominator"
    fm, body = load_preregistration(
        fixture_dir / "preregistration_missing_denom.md"
    )
    diags = check_fv_spec_082_analysis(fm, body, SPEC_ROOT)
    assert diags
    assert any("denominator" in d["message"].lower() for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-083: Deviations check
# ---------------------------------------------------------------------------


def test_fv_spec_083_valid_passes():
    """Preregistration with all 8 deviation categories passes FV-SPEC-083."""
    fm, body = load_preregistration(
        PR_VALID / "preregistration_deviations_valid.md"
    )
    diags = check_fv_spec_083_deviations(fm, body)
    assert not diags, diags


def test_fv_spec_083_missing_category_fails():
    """Missing budget_overrun category causes FV-SPEC-083 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_missing_category.md"
    )
    diags = check_fv_spec_083_deviations(fm, body)
    assert diags
    assert any("budget_overrun" in d["message"] for d in diags)


def test_fv_spec_083_patch_and_resume_fails():
    """'patch and resume' phrasing causes FV-SPEC-083 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_patch_and_resume.md"
    )
    diags = check_fv_spec_083_deviations(fm, body)
    assert diags
    assert any("patch and resume" in d["message"].lower() for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-084: Amendments check
# ---------------------------------------------------------------------------


def test_fv_spec_084_valid_passes():
    """Valid amendment_log passes FV-SPEC-084."""
    fm, _ = load_preregistration(
        PR_VALID / "preregistration_amendment_valid.md"
    )
    diags = check_fv_spec_084_amendments(fm)
    assert not diags, diags


def test_fv_spec_084_missing_approver_fails():
    """Missing approver field causes FV-SPEC-084 failure."""
    fm, _ = load_preregistration(
        PR_INVALID / "preregistration_amendment_missing_approver.md"
    )
    diags = check_fv_spec_084_amendments(fm)
    assert diags
    assert any("approver" in d["message"] for d in diags)


def test_fv_spec_084_post_hoc_fails():
    """post_hoc: true causes FV-SPEC-084 failure."""
    fm, _ = load_preregistration(
        PR_INVALID / "preregistration_amendment_post_hoc.md"
    )
    diags = check_fv_spec_084_amendments(fm)
    assert diags
    assert any("post_hoc" in d["message"] for d in diags)


# ---------------------------------------------------------------------------
# FV-SPEC-085: Claims check
# ---------------------------------------------------------------------------


def test_fv_spec_085_valid_passes():
    """Properly labelled claims pass FV-SPEC-085."""
    fm, body = load_preregistration(
        PR_VALID / "preregistration_claims_valid.md"
    )
    diags = check_fv_spec_085_claims(fm, body)
    assert not diags, diags


def test_fv_spec_085_unlabelled_exploratory_fails():
    """Unlabelled Stage B analysis causes FV-SPEC-085 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_unlabelled_exploratory.md"
    )
    diags = check_fv_spec_085_claims(fm, body)
    assert diags


def test_fv_spec_085_postfreeze_confirmatory_fails():
    """Post-freeze paraphrase without exploratory label causes FV-SPEC-085 failure."""
    fm, body = load_preregistration(
        PR_INVALID / "preregistration_postfreeze_paraphrase_confirmatory.md"
    )
    diags = check_fv_spec_085_claims(fm, body)
    assert diags


# ---------------------------------------------------------------------------
# FV-SPEC-086: Integrity check
# ---------------------------------------------------------------------------


def test_fv_spec_086_valid_snapshot_passes(tmp_path):
    """Correctly hashed snapshot passes integrity check."""
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        (spec / name).write_bytes(b"content")
    from tools.freeze import write_checksums, verify_checksums

    checksums_path = tmp_path / ".factverify" / "CHECKSUMS.sha256"
    write_checksums(spec, checksums_path)
    mismatched = verify_checksums(spec, checksums_path)
    assert not mismatched


def test_fv_spec_086_tampered_artifact_fails(tmp_path):
    """Tampered artifact byte causes verify_checksums to report it."""
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        (spec / name).write_bytes(b"content")
    from tools.freeze import write_checksums, verify_checksums

    checksums_path = tmp_path / ".factverify" / "CHECKSUMS.sha256"
    write_checksums(spec, checksums_path)
    # Tamper with one artifact
    (spec / "margins.yaml").write_bytes(b"tampered")
    mismatched = verify_checksums(spec, checksums_path)
    assert any("margins.yaml" in m for m in mismatched)


def test_fv_spec_086_missing_checksums_passes(tmp_path):
    """No CHECKSUMS file returns empty diagnostics (not error in dry-run)."""
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    (spec / "preregistration.md").write_bytes(b"content")
    diags = check_fv_spec_086_integrity(
        spec, tmp_path / ".factverify" / "CHECKSUMS.sha256"
    )
    assert diags == []


# ---------------------------------------------------------------------------
# FV-SPEC-087: Freeze gate check
# ---------------------------------------------------------------------------


def test_fv_spec_087_dry_run_allpass(tmp_path):
    """Dry-run on a fully valid fixture repo passes with no writes."""
    import subprocess as sp

    sp.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True, capture_output=True,
    )
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        if name == "preregistration.md":
            (spec / name).write_text(
                (PR_VALID / "preregistration_complete.md").read_text(encoding="utf-8"),
                encoding="utf-8",
            )
        else:
            (spec / name).write_bytes(b"content")

    # All decisions resolved
    decisions_dir = tmp_path / ".factverify" / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "register.yaml").write_text(
        "D-01:\n  status: resolved\n  resolution: agreed\n  reason: ''\n"
        "  blocked_specs: []\n  owner: ''\n",
        encoding="utf-8",
    )

    # Exposure reviewed
    exposure_dir = tmp_path / ".factverify" / "exposure"
    exposure_dir.mkdir()
    (exposure_dir / "exposure_record.md").write_text(
        "---\nstatus: reviewed\nregistration_status: local-only\n"
        "access_events: []\n---\n",
        encoding="utf-8",
    )

    # Milestones with staged_rule
    milestones_dir = tmp_path / ".factverify" / "milestones"
    milestones_dir.mkdir()
    (milestones_dir / "milestones.yaml").write_text(
        "spec-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P0-7\n    inputs: [all]\n    method: all pass\n"
        "thresholds-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P4-3\n    inputs: [calibration]\n"
        "    method: select threshold\n"
        "protocol-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: Gate-3\n    inputs: [ablation]\n"
        "    method: retain components\n",
        encoding="utf-8",
    )

    from tools.freeze import run_gate_checks

    all_passed, results = run_gate_checks(
        spec,
        "spec-v1",
        decisions_dir / "register.yaml",
        exposure_dir / "exposure_record.md",
        milestones_dir / "milestones.yaml",
    )
    # Verify no writes happened
    assert not (tmp_path / ".factverify" / "CHECKSUMS.sha256").exists()
    assert all_passed, results


def test_fv_spec_087_open_decision_fails(tmp_path):
    """Open decision in register causes gate check to fail."""
    import subprocess as sp

    sp.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True, capture_output=True,
    )
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        (spec / name).write_bytes(b"content")

    decisions_dir = tmp_path / ".factverify" / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "register.yaml").write_text(
        "D-01:\n  status: open\n  resolution: ''\n  reason: ''\n"
        "  blocked_specs: []\n  owner: ''\n",
        encoding="utf-8",
    )

    exposure_dir = tmp_path / ".factverify" / "exposure"
    exposure_dir.mkdir()
    (exposure_dir / "exposure_record.md").write_text(
        "---\nstatus: reviewed\nregistration_status: local-only\n"
        "access_events: []\n---\n",
        encoding="utf-8",
    )

    milestones_dir = tmp_path / ".factverify" / "milestones"
    milestones_dir.mkdir()
    (milestones_dir / "milestones.yaml").write_text(
        "spec-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P0-7\n    inputs: [all]\n    method: all pass\n"
        "thresholds-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P4-3\n    inputs: [calibration]\n"
        "    method: select threshold\n"
        "protocol-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: Gate-3\n    inputs: [ablation]\n"
        "    method: retain components\n",
        encoding="utf-8",
    )

    from tools.freeze import run_gate_checks

    all_passed, results = run_gate_checks(
        spec,
        "spec-v1",
        decisions_dir / "register.yaml",
        exposure_dir / "exposure_record.md",
        milestones_dir / "milestones.yaml",
    )
    assert not all_passed
    assert any(
        r["name"] == "decisions_resolved" and not r["passed"] for r in results
    )
    assert any(
        "D-01" in str(r.get("diagnostics", "")) for r in results
    )


def test_fv_spec_087_existing_tag_fails(tmp_path):
    """Existing spec-v1 tag causes gate check to fail."""
    import subprocess as sp

    sp.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True, capture_output=True,
    )
    # Create initial commit so we can tag
    (tmp_path / "README").write_text("init", encoding="utf-8")
    sp.run(
        ["git", "-C", str(tmp_path), "add", "README"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "commit", "-m", "init"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "tag", "-a", "spec-v1", "-m", "test"],
        check=True, capture_output=True,
    )

    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        (spec / name).write_bytes(b"content")

    decisions_dir = tmp_path / ".factverify" / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "register.yaml").write_text(
        "D-01:\n  status: resolved\n  resolution: ok\n  reason: ''\n"
        "  blocked_specs: []\n  owner: ''\n",
        encoding="utf-8",
    )

    exposure_dir = tmp_path / ".factverify" / "exposure"
    exposure_dir.mkdir()
    (exposure_dir / "exposure_record.md").write_text(
        "---\nstatus: reviewed\nregistration_status: local-only\n"
        "access_events: []\n---\n",
        encoding="utf-8",
    )

    milestones_dir = tmp_path / ".factverify" / "milestones"
    milestones_dir.mkdir()
    (milestones_dir / "milestones.yaml").write_text(
        "spec-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P0-7\n    inputs: [all]\n    method: all pass\n"
        "thresholds-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P4-3\n    inputs: [calibration]\n"
        "    method: select threshold\n"
        "protocol-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: Gate-3\n    inputs: [ablation]\n"
        "    method: retain components\n",
        encoding="utf-8",
    )

    from tools.freeze import run_gate_checks

    all_passed, results = run_gate_checks(
        spec,
        "spec-v1",
        decisions_dir / "register.yaml",
        exposure_dir / "exposure_record.md",
        milestones_dir / "milestones.yaml",
    )
    assert not all_passed
    assert any(
        r["name"] == "no_existing_tag" and not r["passed"] for r in results
    )


# ---------------------------------------------------------------------------
# FV-SPEC-088: Offline CLI check
# ---------------------------------------------------------------------------


def test_fv_spec_088_all_hooks_pass_offline():
    """All 11 test hooks must be importable and have _NO_MODEL_CALLS = True."""
    import tools.preregistration_validator as mod

    assert mod._NO_MODEL_CALLS is True


def test_fv_spec_088_publication_without_receipt_fails(tmp_path):
    """Calling --verify with no checksums file exits non-zero."""
    import subprocess as sp

    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    for name in SPEC_ARTIFACTS:
        (spec / name).write_bytes(b"content")

    result = sp.run(
        [sys.executable, "-m", "tools.freeze",
         "--spec-root", str(spec), "--verify"],
        capture_output=True,
        cwd=str(tmp_path),
    )
    # No CHECKSUMS.sha256 → verify_checksums returns the missing path → non-zero
    assert result.returncode != 0


def test_fv_spec_088_partial_prep_dry_run_reports_pending(tmp_path):
    """Dry-run on incomplete fixture reports gate failures without writing snapshot."""
    import subprocess as sp

    sp.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "t@t"],
        check=True, capture_output=True,
    )
    sp.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "T"],
        check=True, capture_output=True,
    )
    spec = tmp_path / ".factverify" / "spec"
    spec.mkdir(parents=True)
    # Only put some artifacts — others missing
    (spec / "preregistration.md").write_bytes(b"content")

    decisions_dir = tmp_path / ".factverify" / "decisions"
    decisions_dir.mkdir()
    (decisions_dir / "register.yaml").write_text(
        "D-01:\n  status: open\n  resolution: ''\n  reason: ''\n"
        "  blocked_specs: []\n  owner: ''\n",
        encoding="utf-8",
    )

    exposure_dir = tmp_path / ".factverify" / "exposure"
    exposure_dir.mkdir()
    (exposure_dir / "exposure_record.md").write_text(
        "---\nstatus: draft\nregistration_status: local-only\n"
        "access_events: []\n---\n",
        encoding="utf-8",
    )

    milestones_dir = tmp_path / ".factverify" / "milestones"
    milestones_dir.mkdir()
    (milestones_dir / "milestones.yaml").write_text(
        "spec-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P0-7\n    inputs: [all]\n    method: all pass\n"
        "thresholds-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: P4-3\n    inputs: [calibration]\n"
        "    method: select threshold\n"
        "protocol-v1:\n  git_tag: null\n  staged_rule:\n"
        "    determined_at_gate: Gate-3\n    inputs: [ablation]\n"
        "    method: retain components\n",
        encoding="utf-8",
    )

    report_path = tmp_path / "reports" / "freeze_report.json"
    result = sp.run(
        [
            sys.executable, "-m", "tools.freeze",
            "--spec-root", str(spec),
            "--dry-run",
            "--report", str(report_path),
            "--decisions-register", str(decisions_dir / "register.yaml"),
            "--exposure-record", str(exposure_dir / "exposure_record.md"),
            "--milestones", str(milestones_dir / "milestones.yaml"),
        ],
        capture_output=True,
        cwd=str(tmp_path),
    )
    assert result.returncode != 0  # some gates failed
    # No snapshot was created
    assert not (tmp_path / ".factverify" / "CHECKSUMS.sha256").exists()
    # Report was still written
    assert report_path.exists()
    rpt = json.loads(report_path.read_text())
    assert rpt["overall"] == "fail"
