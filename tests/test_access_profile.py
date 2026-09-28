"""P0-4 access profile validation tests.

Tests FV-SPEC-047 through FV-SPEC-056, exercising access_profile_validator
via fixture-driven structural, capability, provenance, intervention, source,
identifiability, status, reporting, claim-template, and scoped-CLI checks.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.conftest import (
    ACCESS_DIR,
    AP_BASELINES,
    AP_INVALID,
    AP_VALID,
    REPO,
    SPEC_ROOT,
)
from tools.access_profile_validator import (
    check_access_contract_artifact,
    check_baseline_comparison,
    check_claim_templates,
    check_cross_file_references,
    check_eligibility_reporting,
    check_historical_external_access,
    check_identifiability_justification,
    check_observation_capabilities,
    check_observation_intervention_separation,
    check_provenance_verification,
    check_status_contracts,
    check_strict_mode,
    load_access_profile,
    validate_access_profile,
)


# ── helpers ────────────────────────────────────────────────────────


def _load_profile(name: str, *, valid: bool = True) -> tuple[dict, str]:
    base = AP_VALID if valid else AP_INVALID
    return load_access_profile(base / name)


def _load_json(name: str, *, valid: bool = True) -> dict:
    base = AP_VALID if valid else AP_INVALID
    return json.loads((base / name).read_text(encoding="utf-8"))


def _stage_profile(
    tmp_path: Path,
    profile_src: Path,
    *,
    extra_files: dict[str, Path] | None = None,
) -> tuple[Path, Path]:
    """Copy a profile + manifests into a temp spec/access tree."""
    spec_root = tmp_path / "spec"
    access_dir = tmp_path / "access"
    spec_root.mkdir()
    (access_dir / "capability_manifests").mkdir(parents=True)
    (access_dir / "identifiability").mkdir(parents=True)
    (access_dir / "claim_templates").mkdir(parents=True)

    shutil.copy(profile_src, spec_root / "access_profile.md")

    # Copy standard manifests
    for name in ("manifest_candidate.json", "manifest_reference.json"):
        src = AP_VALID / name
        if src.exists():
            shutil.copy(src, access_dir / "capability_manifests" / name)

    # Copy attacks.yaml so budget_ref resolves
    attacks = SPEC_ROOT / "attacks.yaml"
    if attacks.exists():
        shutil.copy(attacks, spec_root / "attacks.yaml")

    if extra_files:
        for rel, src in extra_files.items():
            dest = access_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dest)

    return spec_root, access_dir


def _run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, "tools/validate_spec.py", *args]
    return subprocess.run(
        cmd, cwd=REPO, capture_output=True, text=True, check=False,
    )


# ── FV-SPEC-047: access contract artifact ─────────────────────────


class TestFvSpec047Artifact:
    """Structural validation of access_profile.md."""

    def test_valid_profile_has_no_diagnostics(self):
        fm, body = _load_profile("minimal_profile.md")
        diags = check_access_contract_artifact(fm, body)
        assert diags == []

    def test_malformed_frontmatter_exits(self):
        with pytest.raises(SystemExit):
            load_access_profile(AP_INVALID / "malformed.md")

    def test_missing_required_fields(self):
        fm, body = _load_profile("missing_required.md", valid=False)
        diags = check_access_contract_artifact(fm, body)
        fields = {d["field"] for d in diags}
        assert "profile" in fields
        assert "systems" in fields

    def test_unknown_profile_rejected(self):
        fm, body = _load_profile("unknown_profile.md", valid=False)
        diags = check_access_contract_artifact(fm, body)
        assert any("Unknown profile" in d["message"] for d in diags)

    def test_bad_version_rejected(self):
        fm, body = _load_profile("bad_version.md", valid=False)
        diags = check_access_contract_artifact(fm, body)
        assert any("semver" in d["message"] for d in diags)

    def test_blocking_decisions_checked(self):
        fm, body = _load_profile("minimal_profile.md")
        fm["blocking_decisions"] = [{"decision_id": "D-13", "status": "open"}]
        diags = check_access_contract_artifact(fm, body)
        assert any("Missing required blocking decisions" in d["message"]
                    for d in diags)

    def test_duplicate_system_ids(self):
        fm, body = _load_profile("duplicate_keys.md", valid=False)
        diags = check_access_contract_artifact(fm, body)
        assert any("Duplicate system_id" in d["message"] for d in diags)

    def test_cross_file_refs_resolve(self, tmp_path):
        spec_root, access_dir = _stage_profile(
            tmp_path, AP_VALID / "minimal_profile.md",
        )
        fm, _ = load_access_profile(spec_root / "access_profile.md")
        diags = check_cross_file_references(fm, spec_root, access_dir)
        assert diags == []

    def test_broken_budget_ref_fails(self, tmp_path):
        spec_root, access_dir = _stage_profile(
            tmp_path, AP_VALID / "minimal_profile.md",
        )
        (spec_root / "attacks.yaml").unlink(missing_ok=True)
        fm, _ = load_access_profile(spec_root / "access_profile.md")
        diags = check_cross_file_references(fm, spec_root, access_dir)
        assert any("Budget reference not found" in d["message"] for d in diags)


# ── FV-SPEC-048: observation capabilities ─────────────────────────


class TestFvSpec048Capabilities:
    """Per-system A/B/C capability consistency."""

    def test_profile_a_consistent(self):
        fm, _ = _load_profile("minimal_profile.md")
        assert check_observation_capabilities(fm) == []

    def test_profile_b_consistent(self):
        fm, _ = _load_profile("profile_b.md")
        assert check_observation_capabilities(fm) == []

    def test_profile_c_consistent(self):
        fm, _ = _load_profile("profile_c.md")
        assert check_observation_capabilities(fm) == []

    def test_postmask_premask_mismatch(self):
        fm, _ = _load_profile("postmask_premask.md", valid=False)
        diags = check_observation_capabilities(fm)
        assert any("pre_mask" in d["message"] for d in diags)

    def test_partial_unrestricted_mismatch(self):
        fm, _ = _load_profile("partial_unrestricted.md", valid=False)
        diags = check_observation_capabilities(fm)
        assert any("unrestricted" in d["message"].lower() for d in diags)

    def test_invalid_capability_state(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["systems"]["candidate"]["capabilities"]["text"] = "magic"
        diags = check_observation_capabilities(fm)
        assert any("Invalid capability state" in d["message"] for d in diags)

    def test_score_scope_required_for_b(self):
        fm, _ = _load_profile("profile_b.md")
        fm["score_scope"] = None
        diags = check_observation_capabilities(fm)
        assert any("score_scope required" in d["message"] for d in diags)


# ── FV-SPEC-049: provenance verification ──────────────────────────


class TestFvSpec049Provenance:
    """Capability/provenance manifest validation."""

    def test_valid_manifests_pass(self, tmp_path):
        spec_root, access_dir = _stage_profile(
            tmp_path, AP_VALID / "minimal_profile.md",
        )
        fm, _ = load_access_profile(spec_root / "access_profile.md")
        assert check_provenance_verification(fm, access_dir) == []

    def test_missing_manifest_fields(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "capability_manifests").mkdir(parents=True)
        shutil.copy(
            AP_INVALID / "bad_manifest.json",
            access_dir / "capability_manifests" / "bad.json",
        )
        fm = {
            "systems": {"candidate": {}},
            "provenance_refs": ["capability_manifests/bad.json"],
        }
        diags = check_provenance_verification(fm, access_dir)
        fields = {d["field"] for d in diags}
        assert "system_id" in fields
        assert "reviewer_id" in fields

    def test_wrong_system_id(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "capability_manifests").mkdir(parents=True)
        shutil.copy(
            AP_INVALID / "wrong_system_manifest.json",
            access_dir / "capability_manifests" / "wrong.json",
        )
        fm = {
            "systems": {"candidate": {}},
            "provenance_refs": ["capability_manifests/wrong.json"],
        }
        diags = check_provenance_verification(fm, access_dir)
        assert any("not found in access profile systems" in d["message"]
                    for d in diags)

    def test_bad_hash_format(self, tmp_path):
        access_dir = tmp_path / "access"
        man_dir = access_dir / "capability_manifests"
        man_dir.mkdir(parents=True)
        man = _load_json("manifest_candidate.json")
        man["model_identity"]["hash"] = "not-a-hash"
        (man_dir / "m.json").write_text(json.dumps(man), encoding="utf-8")
        fm = {
            "systems": {"candidate": {}},
            "provenance_refs": ["capability_manifests/m.json"],
        }
        diags = check_provenance_verification(fm, access_dir)
        assert any("SHA-256" in d["message"] for d in diags)

    def test_empty_reviewer_fails(self, tmp_path):
        access_dir = tmp_path / "access"
        man_dir = access_dir / "capability_manifests"
        man_dir.mkdir(parents=True)
        man = _load_json("manifest_candidate.json")
        man["reviewer_id"] = "  "
        (man_dir / "m.json").write_text(json.dumps(man), encoding="utf-8")
        fm = {
            "systems": {"candidate": {}},
            "provenance_refs": ["capability_manifests/m.json"],
        }
        diags = check_provenance_verification(fm, access_dir)
        assert any("reviewer_id must be non-empty" in d["message"]
                    for d in diags)


# ── FV-SPEC-050: observation/intervention separation ──────────────


class TestFvSpec050Separation:
    """Intervention permissions independent of observation."""

    def test_valid_intervention_passes(self):
        fm, _ = _load_profile("profile_with_interventions.md")
        assert check_observation_intervention_separation(fm) == []

    def test_unlisted_finetune_rejected(self):
        fm, _ = _load_profile("unlisted_finetune.md", valid=False)
        diags = check_observation_intervention_separation(fm)
        assert any("approved_recipes" in d["message"] for d in diags)

    def test_missing_role_fails(self):
        fm, _ = _load_profile("missing_role.md", valid=False)
        diags = check_observation_intervention_separation(fm)
        assert any("not found in declared roles" in d["message"] for d in diags)

    def test_exceeds_capabilities_fails(self):
        fm, _ = _load_profile("exceeds_capabilities.md", valid=False)
        diags = check_observation_intervention_separation(fm)
        assert any("unavailable" in d["message"] for d in diags)

    def test_role_separation_enforced(self):
        fm, _ = _load_profile("profile_with_interventions.md")
        fm["roles"].append({
            "role_id": "dual_role",
            "role_type": "operator",
            "person_id": "alice",
            "permitted_actions": ["export_checkpoint"],
        })
        diags = check_observation_intervention_separation(fm)
        assert any("Role separation violated" in d["message"] for d in diags)

    def test_evaluator_cannot_intervene(self):
        fm, _ = _load_profile("profile_with_interventions.md")
        fm["interventions"][0]["actor_role"] = "evaluator_1"
        diags = check_observation_intervention_separation(fm)
        assert any("Evaluator role" in d["message"] for d in diags)


# ── FV-SPEC-051: historical and external access ───────────────────


class TestFvSpec051Sources:
    """Permitted sources and historical access attribution."""

    def test_declared_sources_pass(self):
        fm, _ = _load_profile("minimal_profile.md")
        assert check_historical_external_access(fm) == []

    def test_undeclared_source_fails(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["permitted_sources"] = ["secret_backdoor"]
        diags = check_historical_external_access(fm)
        assert any("Unrecognized source" in d["message"] for d in diags)

    def test_historical_with_attribution_passes(self):
        fm, _ = _load_profile("profile_with_interventions.md")
        assert check_historical_external_access(fm) == []

    def test_missing_attribution_fails(self):
        fm, _ = _load_profile("undeclared_history.md", valid=False)
        diags = check_historical_external_access(fm)
        assert any("missing attribution" in d["message"] for d in diags)

    def test_pre_unlearning_must_be_attributed(self):
        fm, _ = _load_profile("profile_with_interventions.md")
        fm["historical_access"][0]["attribution"] = "generic_dump"
        diags = check_historical_external_access(fm)
        assert any("pre-unlearning" in d["message"] for d in diags)


# ── FV-SPEC-052: identifiability justification ────────────────────


class TestFvSpec052Identifiability:
    """Scoped identifiability justifications."""

    def test_constructive_passes(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "identifiability").mkdir(parents=True)
        shutil.copy(
            AP_VALID / "justification_synthetic.json",
            access_dir / "identifiability" / "just.json",
        )
        fm = {
            "systems": {
                "synthetic_simulator_a": {},
                "synthetic_simulator_b": {},
            },
            "identifiability_refs": ["identifiability/just.json"],
        }
        assert check_identifiability_justification(fm, access_dir) == []

    def test_empirical_with_limitation_passes(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "identifiability").mkdir(parents=True)
        shutil.copy(
            AP_VALID / "justification_empirical.json",
            access_dir / "identifiability" / "just.json",
        )
        fm = {
            "systems": {"candidate": {}, "reference": {}},
            "identifiability_refs": ["identifiability/just.json"],
        }
        assert check_identifiability_justification(fm, access_dir) == []

    def test_finite_matching_without_limitation_fails(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "identifiability").mkdir(parents=True)
        shutil.copy(
            AP_INVALID / "finite_matching.json",
            access_dir / "identifiability" / "just.json",
        )
        fm = {
            "systems": {"candidate": {}, "reference": {}},
            "identifiability_refs": ["identifiability/just.json"],
        }
        diags = check_identifiability_justification(fm, access_dir)
        assert any("finite" in d["message"].lower() for d in diags)

    def test_wrong_system_pair_fails(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "identifiability").mkdir(parents=True)
        shutil.copy(
            AP_INVALID / "wrong_system_pair.json",
            access_dir / "identifiability" / "just.json",
        )
        fm = {
            "systems": {"candidate": {}, "reference": {}},
            "identifiability_refs": ["identifiability/just.json"],
        }
        diags = check_identifiability_justification(fm, access_dir)
        assert any("not found" in d["message"] for d in diags)

    def test_missing_fields_fail(self, tmp_path):
        access_dir = tmp_path / "access"
        (access_dir / "identifiability").mkdir(parents=True)
        shutil.copy(
            AP_INVALID / "missing_justification_fields.json",
            access_dir / "identifiability" / "just.json",
        )
        fm = {
            "systems": {"candidate": {}, "reference": {}},
            "identifiability_refs": ["identifiability/just.json"],
        }
        diags = check_identifiability_justification(fm, access_dir)
        fields = {d["field"] for d in diags}
        assert "revision" in fields
        assert "reviewer_id" in fields

    def test_no_justification_deferred_non_strict(self):
        fm = {"systems": {}, "identifiability_refs": []}
        diags = check_identifiability_justification(
            fm, Path("."), strict=False,
        )
        assert diags == []

    def test_no_justification_fails_strict(self):
        fm = {"systems": {}, "identifiability_refs": []}
        diags = check_identifiability_justification(
            fm, Path("."), strict=True,
        )
        assert any("strict mode" in d["message"].lower() for d in diags)


# ── FV-SPEC-053: status contracts ─────────────────────────────────


class TestFvSpec053StatusContracts:
    """Four statuses with no silent promotion."""

    def test_four_statuses_enforced(self):
        fm, _ = _load_profile("minimal_profile.md")
        assert check_status_contracts(fm) == []

    def test_missing_status_fails(self):
        fm, _ = _load_profile("minimal_profile.md")
        del fm["handling_policies"]["incomplete"]
        diags = check_status_contracts(fm)
        assert any("incomplete" in d["message"] for d in diags)

    def test_missing_raw_score_maps_to_incomplete(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["evidence_mappings"] = {
            "missing_raw_score": "non_identifiable",
            "known_control_label_alone": "incomplete",
            "completed_without_witness": "incomplete",
        }
        diags = check_status_contracts(fm)
        assert any("missing_raw_score" in d["message"] for d in diags)

    def test_control_label_not_witness(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["evidence_mappings"] = {
            "missing_raw_score": "incomplete",
            "known_control_label_alone": "confirmed_recovery",
            "completed_without_witness": "incomplete",
        }
        diags = check_status_contracts(fm)
        assert any(
            "control label" in d["message"].lower()
            or "known_control_label_alone" in d["message"]
            for d in diags
        )

    def test_completed_without_witness_incomplete(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["evidence_mappings"] = {
            "missing_raw_score": "incomplete",
            "known_control_label_alone": "incomplete",
            "completed_without_witness": "conformance",
        }
        diags = check_status_contracts(fm)
        assert any("completed_without_witness" in d["message"] for d in diags)

    def test_valid_evidence_mappings_pass(self):
        fm, _ = _load_profile("strict_profile.md")
        assert check_status_contracts(fm) == []


# ── FV-SPEC-054: eligibility and reporting ────────────────────────


class TestFvSpec054Reporting:
    """Eligibility / denominator reporting rules."""

    def test_resolved_policies_pass(self):
        fm, _ = _load_profile("minimal_profile.md")
        assert check_eligibility_reporting(fm, SPEC_ROOT) == []

    def test_same_counting_rule_fails(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["handling_policies"]["non_identifiable"] = "same_rule"
        fm["handling_policies"]["incomplete"] = "same_rule"
        diags = check_eligibility_reporting(fm, SPEC_ROOT)
        assert any("separate" in d["message"] for d in diags)

    def test_outcome_dependent_exclusion_fails(self):
        fm, _ = _load_profile("minimal_profile.md")
        fm["eligibility_rules"] = {
            "r1": {"outcome_dependent": True},
        }
        diags = check_eligibility_reporting(fm, SPEC_ROOT, strict=True)
        assert any("Outcome-dependent" in d["message"] for d in diags)

    def test_strict_missing_margins(self, tmp_path):
        fm, _ = _load_profile("minimal_profile.md")
        diags = check_eligibility_reporting(fm, tmp_path, strict=True)
        assert any("margins.yaml" in d["message"] for d in diags)


# ── FV-SPEC-055: claim templates ──────────────────────────────────


class TestFvSpec055ClaimTemplates:
    """Claim templates scoped to declared evidence."""

    def _check_template(self, tmp_path, template_name, profile, *, valid=True):
        access_dir = tmp_path / "access"
        (access_dir / "claim_templates").mkdir(parents=True)
        src = (AP_VALID if valid else AP_INVALID) / template_name
        shutil.copy(src, access_dir / "claim_templates" / "t.json")
        fm = {
            "profile": profile,
            "claim_refs": ["claim_templates/t.json"],
        }
        return check_claim_templates(fm, access_dir)

    def test_valid_a_template(self, tmp_path):
        assert self._check_template(
            tmp_path, "claim_template_a.json", "A",
        ) == []

    def test_valid_b_template(self, tmp_path):
        assert self._check_template(
            tmp_path, "claim_template_b.json", "B",
        ) == []

    def test_valid_c_template(self, tmp_path):
        assert self._check_template(
            tmp_path, "claim_template_c.json", "C",
        ) == []

    def test_universal_erasure_rejected(self, tmp_path):
        diags = self._check_template(
            tmp_path, "universal_erasure.json", "A", valid=False,
        )
        assert any("Universal erasure" in d["message"] for d in diags)

    def test_mismatched_profile_rejected(self, tmp_path):
        diags = self._check_template(
            tmp_path, "mismatched_profile.json", "A", valid=False,
        )
        assert any("does not match" in d["message"] for d in diags)

    def test_stage_b_causal_rejected(self, tmp_path):
        diags = self._check_template(
            tmp_path, "stage_b_causal.json", "A", valid=False,
        )
        assert any("Stage B" in d["message"] for d in diags)

    def test_profile_a_missing_limitation(self, tmp_path):
        diags = self._check_template(
            tmp_path, "missing_a_limitation.json", "A", valid=False,
        )
        assert any("output-simulation" in d["message"] for d in diags)


# ── FV-SPEC-056: scoped CLI validation ────────────────────────────


class TestFvSpec056ScopedCli:
    """End-to-end CLI, strict mode, baseline, determinism."""

    def test_demo_validation_passes(self):
        result = _run_cli(
            "--scope", "access-profile",
            "--spec-root", str(SPEC_ROOT),
            "--access-dir", str(ACCESS_DIR),
            "--report", str(REPO / "reports" / "p0-4-test-run.json"),
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(
            (REPO / "reports" / "p0-4-test-run.json").read_text(encoding="utf-8")
        )
        assert report["overall"] == "pass"
        assert report["scope"] == "access-profile"
        assert "checks" in report
        assert "capabilities" in report
        assert "deferred_checks" in report
        assert len(report["deferred_checks"]) >= 1

    def test_strict_mode_unresolved_exits_1(self):
        result = _run_cli(
            "--scope", "access-profile",
            "--spec-root", str(SPEC_ROOT),
            "--access-dir", str(ACCESS_DIR),
            "--strict",
            "--report", str(REPO / "reports" / "p0-4-strict-fail.json"),
        )
        assert result.returncode == 1

    def test_baseline_detects_policy_change(self, tmp_path):
        spec_root, access_dir = _stage_profile(
            tmp_path, AP_VALID / "minimal_profile.md",
        )
        # Mutate frozen policy without bumping version
        fm, body = load_access_profile(spec_root / "access_profile.md")
        fm["handling_policies"]["incomplete"] = "changed_rule"
        # Rewrite profile
        import yaml
        text = (
            "---\n"
            + yaml.dump(fm, default_flow_style=False, sort_keys=False)
            + "---\n"
            + body
        )
        (spec_root / "access_profile.md").write_text(text, encoding="utf-8")

        passed, report = validate_access_profile(
            spec_root=spec_root,
            access_dir=access_dir,
            baseline_suite_path=AP_BASELINES / "access_profile.md",
        )
        assert not passed
        bl = report.get("baseline_comparison")
        assert bl is not None
        assert "handling_policies" in bl.get("changed_fields", [])

    def test_report_required_fields(self):
        passed, report = validate_access_profile(
            spec_root=SPEC_ROOT,
            access_dir=ACCESS_DIR,
        )
        assert passed
        for key in (
            "report_id", "timestamp", "scope", "checks", "capabilities",
            "permission_conflicts", "review_state", "cross_file_checks",
            "input_digests", "deferred_checks", "overall",
        ):
            assert key in report

    def test_deterministic_output(self):
        _, r1 = validate_access_profile(
            spec_root=SPEC_ROOT, access_dir=ACCESS_DIR,
        )
        _, r2 = validate_access_profile(
            spec_root=SPEC_ROOT, access_dir=ACCESS_DIR,
        )
        for key in ("report_id", "timestamp"):
            r1.pop(key, None)
            r2.pop(key, None)
        assert r1 == r2

    def test_malformed_exits_2(self, tmp_path):
        spec_root = tmp_path / "spec"
        access_dir = tmp_path / "access"
        spec_root.mkdir()
        access_dir.mkdir()
        shutil.copy(AP_INVALID / "malformed.md", spec_root / "access_profile.md")
        result = _run_cli(
            "--scope", "access-profile",
            "--spec-root", str(spec_root),
            "--access-dir", str(access_dir),
        )
        assert result.returncode == 2

    def test_baseline_comparison_function(self):
        fm, _ = _load_profile("minimal_profile.md")
        diags, comparison = check_baseline_comparison(
            fm, AP_BASELINES / "access_profile.md",
        )
        assert diags == []
        assert comparison["revision_match"] is True
        assert comparison["status"] == "pass"

    def test_strict_mode_check(self, tmp_path):
        access_dir = tmp_path / "access"
        access_dir.mkdir()
        fm, _ = _load_profile("minimal_profile.md")
        diags = check_strict_mode(fm, access_dir, tmp_path)
        assert any("not resolved" in d["message"] for d in diags)
        assert any("review_manifest" in d["message"] for d in diags)
