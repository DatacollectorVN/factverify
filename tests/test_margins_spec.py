"""P0-5 margins statistical-policy validation tests.

Tests FV-SPEC-057 through FV-SPEC-066 via tools.margins_validator and CLI.
"""

from __future__ import annotations

import copy
import json
import math
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.conftest import (
    MARGINS_DIR,
    MG_BASELINES,
    MG_INVALID,
    MG_VALID,
    REPO,
    SPEC_ROOT,
)
from tools.margins_validator import (
    check_baseline_comparison,
    check_calibration_selection,
    check_channel_locality_coverage,
    check_estimands_denominators,
    check_margins_contract_artifact,
    check_policy_approval,
    check_practical_effect,
    check_revision_protection,
    check_sample_size_handoff,
    check_strict_mode,
    check_uncertainty_dependence,
    compute_rate,
    load_margins,
    validate_margins,
)


def _load(name: str, *, valid: bool = True) -> dict:
    base = MG_VALID if valid else MG_INVALID
    return load_margins(base / name)


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "tools/validate_spec.py", *args],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=False,
    )


def _stage(tmp_path: Path, margins_src: Path) -> tuple[Path, Path]:
    spec_root = tmp_path / "spec"
    margins_dir = tmp_path / "margins"
    spec_root.mkdir()
    (margins_dir / "approvals").mkdir(parents=True)
    shutil.copy(margins_src, spec_root / "margins.yaml")
    # Copy attacks + schema for coverage checks
    for name in ("attacks.yaml", "fact_contract.schema.json", "access_profile.md"):
        src = SPEC_ROOT / name
        if src.exists():
            shutil.copy(src, spec_root / name)
    for appr in (MG_VALID / "approvals").glob("*.json"):
        shutil.copy(appr, margins_dir / "approvals" / appr.name)
    # Also accept approvals sitting in valid/
    for name in ("approval_frr_cap.json", "approval_practical_success.json"):
        src = MG_VALID / name
        if src.exists():
            shutil.copy(src, margins_dir / "approvals" / name)
    rev = MARGINS_DIR / "review_manifest.json"
    if rev.exists():
        shutil.copy(rev, margins_dir / "review_manifest.json")
    return spec_root, margins_dir


# ── FV-SPEC-057 ───────────────────────────────────────────────────


class TestFvSpec057Artifact:
    def test_valid_minimal_passes(self):
        assert check_margins_contract_artifact(_load("minimal_margins.yaml")) == []

    def test_malformed_exits(self):
        with pytest.raises(SystemExit):
            load_margins(MG_INVALID / "malformed.yaml")

    def test_missing_required(self):
        diags = check_margins_contract_artifact(_load("missing_required.yaml", valid=False))
        fields = {d["field"] for d in diags}
        assert "frr_cap" in fields
        assert "estimands" in fields

    def test_unknown_field(self):
        diags = check_margins_contract_artifact(_load("unknown_field.yaml", valid=False))
        assert any("Unknown top-level field" in d["message"] for d in diags)

    def test_non_finite(self):
        diags = check_margins_contract_artifact(_load("non_finite.yaml", valid=False))
        assert any("Non-finite" in d["message"] for d in diags)

    def test_mixed_units(self):
        diags = check_margins_contract_artifact(_load("mixed_units.yaml", valid=False))
        assert any("mixed" in d["message"] for d in diags)

    def test_threshold_as_alpha(self):
        diags = check_margins_contract_artifact(_load("threshold_as_alpha.yaml", valid=False))
        assert any("substituted" in d["message"].lower() or "thresholds" in d["message"].lower()
                    for d in diags)


# ── FV-SPEC-058 ───────────────────────────────────────────────────


class TestFvSpec058Approval:
    def test_complete_approvals_pass(self, tmp_path):
        spec_root, margins_dir = _stage(tmp_path, MG_VALID / "minimal_margins.yaml")
        m = load_margins(spec_root / "margins.yaml")
        assert check_policy_approval(m, margins_dir, strict=False) == []

    def test_missing_fields_fail(self, tmp_path):
        margins_dir = tmp_path / "margins"
        margins_dir.mkdir()
        shutil.copy(
            MG_INVALID / "missing_approval_fields.json",
            margins_dir / "bad.json",
        )
        m = {"version": "0.1.0-demo", "approval_refs": ["bad.json"], "frr_cap": {}}
        diags = check_policy_approval(m, margins_dir)
        assert any("Required approval field" in d["message"] for d in diags)

    def test_illustrative_unapproved_fails(self):
        m = _load("illustrative_unapproved.yaml", valid=False)
        diags = check_policy_approval(m, MARGINS_DIR, strict=True)
        assert any("Illustrative" in d["message"] or "missing current approval" in d["message"]
                    for d in diags)

    def test_strict_missing_approval(self, tmp_path):
        margins_dir = tmp_path / "margins"
        margins_dir.mkdir()
        m = _load("minimal_margins.yaml")
        m["approval_refs"] = []
        diags = check_policy_approval(m, margins_dir, strict=True)
        assert any("Strict mode" in d["message"] for d in diags)


# ── FV-SPEC-059 ───────────────────────────────────────────────────


class TestFvSpec059Estimands:
    def test_rates(self):
        syn = json.loads((MG_VALID / "synthetic_rates.json").read_text())
        assert compute_rate(3, 100) == pytest.approx(0.03)
        assert compute_rate(12, 40) == pytest.approx(0.30)
        assert compute_rate(0, 0) == "undefined"
        m = _load("minimal_margins.yaml")
        assert check_estimands_denominators(m, syn) == []

    def test_empty_denom_as_zero_fails(self):
        diags = check_estimands_denominators(
            _load("empty_denom_as_zero.yaml", valid=False)
        )
        assert any("undefined" in d["message"] for d in diags)

    def test_status_mappings_required(self):
        m = _load("minimal_margins.yaml")
        del m["estimands"]["status_mappings"]["incomplete"]
        diags = check_estimands_denominators(m)
        assert any("incomplete" in d["message"] for d in diags)


# ── FV-SPEC-060 ───────────────────────────────────────────────────


class TestFvSpec060Calibration:
    def test_feasible_passes(self):
        m = _load("minimal_margins.yaml")
        cand = json.loads((MG_VALID / "calibration_candidates.json").read_text())
        assert check_calibration_selection(m, cand) == []

    def test_final_test_rejected(self):
        diags = check_calibration_selection(
            _load("final_test_in_selection.yaml", valid=False)
        )
        assert any("final-test" in d["message"] for d in diags)

    def test_point_estimate_only_fails(self):
        diags = check_calibration_selection(
            _load("point_estimate_only_selection.yaml", valid=False)
        )
        assert any("Point-estimate" in d["message"] for d in diags)

    def test_infeasible_reported(self):
        m = _load("minimal_margins.yaml")
        fix = json.loads((MG_INVALID / "infeasible_selection.json").read_text())
        assert check_calibration_selection(m, fix) == []

    def test_silent_relax_fails(self):
        m = _load("minimal_margins.yaml")
        fix = {"status": "infeasible", "relaxed_alpha": True}
        diags = check_calibration_selection(m, fix)
        assert any("relaxation" in d["message"] for d in diags)


# ── FV-SPEC-061 ───────────────────────────────────────────────────


class TestFvSpec061Effect:
    def test_delta(self):
        m = _load("minimal_margins.yaml")
        fx = json.loads((MG_VALID / "effect_both_baselines.json").read_text())
        assert check_practical_effect(m, fx) == []
        assert (0.18 - 0.30) == pytest.approx(-0.12)

    def test_both_baselines_required(self):
        m = _load("single_baseline_success.yaml", valid=False)
        fx = {
            "fcr_factverify": 0.18,
            "fcr_baseline": 0.30,
            "expected_delta": -0.12,
            "native_meets": True,
            "semantic_only_meets": False,
            "claimed_primary_success": True,
        }
        diags = check_practical_effect(m, fx)
        assert any("both" in d["message"] for d in diags)


# ── FV-SPEC-062 ───────────────────────────────────────────────────


class TestFvSpec062Uncertainty:
    def test_valid_passes(self):
        assert check_uncertainty_dependence(_load("minimal_margins.yaml")) == []

    def test_illegal_resampling(self):
        diags = check_uncertainty_dependence(
            _load("illegal_resampling.yaml", valid=False)
        )
        assert any("independent" in d["message"] for d in diags)

    def test_zero_errors_policy_required(self):
        m = _load("minimal_margins.yaml")
        m["uncertainty"]["zero_errors_policy"] = ""
        diags = check_uncertainty_dependence(m)
        assert any("uncertainty" in d["message"].lower() for d in diags)


# ── FV-SPEC-063 ───────────────────────────────────────────────────


class TestFvSpec063Coverage:
    def test_enabled_channels_covered(self):
        m = _load("minimal_margins.yaml")
        assert check_channel_locality_coverage(m, SPEC_ROOT) == []

    def test_missing_channel(self):
        diags = check_channel_locality_coverage(
            _load("missing_channel_margin.yaml", valid=False), SPEC_ROOT
        )
        assert any("prompt_variation" in d["message"] for d in diags)

    def test_missing_bucket(self):
        diags = check_channel_locality_coverage(
            _load("missing_bucket_margin.yaml", valid=False), SPEC_ROOT
        )
        assert any("compositional" in d["message"] for d in diags)

    def test_rank_correctness_mix(self):
        diags = check_channel_locality_coverage(
            _load("rank_correctness_mix.yaml", valid=False), SPEC_ROOT
        )
        assert any("rank" in d["message"].lower() for d in diags)


# ── FV-SPEC-064 ───────────────────────────────────────────────────


class TestFvSpec064Power:
    def test_valid_handoff(self):
        assert check_sample_size_handoff(_load("minimal_margins.yaml")) == []

    def test_invented_final_n(self):
        diags = check_sample_size_handoff(_load("invented_final_n.yaml", valid=False))
        assert any("final_n" in d["message"] for d in diags)

    def test_power_against_zero(self):
        diags = check_sample_size_handoff(
            _load("power_against_zero.yaml", valid=False)
        )
        assert any("d_min" in d["message"] for d in diags)


# ── FV-SPEC-065 ───────────────────────────────────────────────────


class TestFvSpec065Revision:
    def test_baseline_match(self):
        m = _load("minimal_margins.yaml")
        diags, comp = check_baseline_comparison(m, MG_BASELINES / "margins.yaml")
        assert diags == []
        assert comp["revision_match"] is True

    def test_policy_change_same_version(self, tmp_path):
        m = _load("minimal_margins.yaml")
        m = copy.deepcopy(m)
        m["practical_success"]["criterion"] = "changed"
        diags, comp = check_baseline_comparison(m, MG_BASELINES / "margins.yaml")
        assert diags
        assert "practical_success" in comp["changed_fields"]

    def test_missing_amendment(self):
        m = _load("minimal_margins.yaml")
        m["confirmatory_claim_authorized"] = True
        diags = check_revision_protection(m)
        assert any("amendment" in d["message"] for d in diags)


# ── FV-SPEC-066 ───────────────────────────────────────────────────


class TestFvSpec066ScopedCli:
    def test_demo_validation_passes(self):
        result = _run_cli(
            "--scope", "margins",
            "--spec-root", str(SPEC_ROOT),
            "--margins-dir", str(MARGINS_DIR),
            "--report", str(REPO / "reports" / "p0-5-test-run.json"),
        )
        assert result.returncode == 0, result.stderr + result.stdout
        report = json.loads(
            (REPO / "reports" / "p0-5-test-run.json").read_text(encoding="utf-8")
        )
        assert report["overall"] == "pass"
        assert report["scope"] == "margins"
        assert report["deferred_checks"]
        for key in (
            "report_id", "timestamp", "checks", "decision_status",
            "input_digests", "deferred_checks", "overall",
        ):
            assert key in report

    def test_strict_unresolved_exits_1(self):
        result = _run_cli(
            "--scope", "margins",
            "--spec-root", str(SPEC_ROOT),
            "--margins-dir", str(MARGINS_DIR),
            "--strict",
        )
        assert result.returncode == 1

    def test_malformed_exits_2(self, tmp_path):
        spec_root = tmp_path / "spec"
        margins_dir = tmp_path / "margins"
        spec_root.mkdir()
        margins_dir.mkdir()
        shutil.copy(MG_INVALID / "malformed.yaml", spec_root / "margins.yaml")
        result = _run_cli(
            "--scope", "margins",
            "--spec-root", str(spec_root),
            "--margins-dir", str(margins_dir),
        )
        assert result.returncode == 2

    def test_deterministic(self):
        _, r1 = validate_margins(SPEC_ROOT, MARGINS_DIR)
        _, r2 = validate_margins(SPEC_ROOT, MARGINS_DIR)
        for k in ("report_id", "timestamp"):
            r1.pop(k, None)
            r2.pop(k, None)
        assert r1 == r2

    def test_strict_mode_check(self):
        m = _load("minimal_margins.yaml")
        diags = check_strict_mode(m, MARGINS_DIR, SPEC_ROOT)
        assert any("not resolved" in d["message"] for d in diags)

    def test_baseline_cli(self, tmp_path):
        spec_root, margins_dir = _stage(tmp_path, MG_VALID / "minimal_margins.yaml")
        m = load_margins(spec_root / "margins.yaml")
        m["practical_success"]["criterion"] = "mutated"
        (spec_root / "margins.yaml").write_text(
            yaml.dump(m, sort_keys=False), encoding="utf-8"
        )
        passed, report = validate_margins(
            spec_root,
            margins_dir,
            baseline_suite_path=MG_BASELINES / "margins.yaml",
        )
        assert not passed
        assert report["baseline_comparison"]["changed_fields"]
