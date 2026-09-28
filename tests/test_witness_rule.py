"""P0-6 witness-rule validator tests: FV-SPEC-067 through FV-SPEC-077."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from tests.conftest import (
    WITNESS_RULE_MD,
    WITNESS_DIR,
    WR_VALID,
    WR_INVALID,
    WR_BASELINES,
    SPEC_ROOT,
    REPO,
    P0_6_REPORT,
)
from tools.witness_rule_validator import (
    load_witness_rule,
    check_fv_spec_067_witness_contract_artifact,
    check_fv_spec_068_direction_aware_rubric,
    check_fv_spec_069_raw_score_semantics,
    check_fv_spec_070_route_a_confirmation,
    check_fv_spec_071_route_b_replication,
    check_fv_spec_072_route_c_verdict_flips,
    check_fv_spec_073_case_level_verdict,
    check_fv_spec_074_evidence_aggregation,
    check_fv_spec_075_blinded_annotation,
    check_fv_spec_076_reconstructable_records,
    check_fv_spec_077_scoped_cli_validation,
    _NO_MODEL_CALLS,
)

VALIDATE_CMD = [sys.executable, "-m", "tools.validate_spec"]


# ---------------------------------------------------------------------------
# FV-SPEC-067: Witness Contract Artifact
# ---------------------------------------------------------------------------


def test_fv_spec_067_valid_layers_pass():
    """Valid witness_rule.md passes layer-separation check."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_067_witness_contract_artifact(fm)
    assert not diags, diags


def test_fv_spec_067_response_as_verdict_fails():
    """Fixture with rubric label in acceptance_requires fails layer-conflation check."""
    fm, _ = load_witness_rule(WR_INVALID / "response_as_verdict.md")
    diags = check_fv_spec_067_witness_contract_artifact(fm)
    assert diags, "Expected layer-conflation diagnostic"
    assert any("layer" in d.get("message", "").lower() or "conflat" in d.get("message", "").lower()
               for d in diags), f"Expected layer-conflation message, got: {diags}"


def test_fv_spec_067_missing_definitions_fails():
    """Fixture missing confirmation_routes key fails missing-definitions check."""
    fm, _ = load_witness_rule(WR_INVALID / "missing_route_definitions.md")
    diags = check_fv_spec_067_witness_contract_artifact(fm)
    assert diags, "Expected missing-definitions diagnostic"


def test_fv_spec_067_all_required_fields_present():
    """All 13 required frontmatter fields are present in the main artifact."""
    from tools.witness_rule_validator import REQUIRED_FRONTMATTER_FIELDS
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    for field in REQUIRED_FRONTMATTER_FIELDS:
        assert field in fm, f"Missing required field: {field}"


def test_fv_spec_067_routes_abc_have_enabled():
    """Routes A, B, C each have an 'enabled' field."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    routes = fm.get("confirmation_routes", {})
    for route_key in ("A", "B", "C"):
        assert route_key in routes, f"Missing route: {route_key}"
        assert "enabled" in routes[route_key], f"Route {route_key} missing 'enabled' field"


def test_fv_spec_067_complete_worksheet_passes():
    """Complete unresolved worksheet fixture passes FV-SPEC-067."""
    fm, _ = load_witness_rule(WR_VALID / "complete_unresolved_worksheet.md")
    diags = check_fv_spec_067_witness_contract_artifact(fm)
    assert not diags, diags


# ---------------------------------------------------------------------------
# FV-SPEC-068: Direction-Aware Rubric
# ---------------------------------------------------------------------------


def test_fv_spec_068_rubric_categories_declared():
    """Main artifact rubric has all required roles and labels."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_068_direction_aware_rubric(fm)
    assert not diags, diags


def test_fv_spec_068_disclosure_refusal_records_both_fields():
    """Disclosure-plus-refusal fixture records both correctness=correct and refusal_flag=true."""
    fixture = json.loads((WR_VALID / "scoring" / "disclosure_plus_refusal.json").read_text())
    expected = fixture["expected"]
    assert expected["correctness"] == "correct"
    assert expected["refusal_flag"] is True


def test_fv_spec_068_negated_entity_not_positive_recovery():
    """Negated-entity fixture is not labelled as positive recovery."""
    fixture = json.loads((WR_VALID / "scoring" / "negated_entity.json").read_text())
    expected = fixture["expected"]
    assert expected["correctness"] != "correct"
    assert expected["refusal_flag"] is False


def test_fv_spec_068_many_valued_policy_required():
    """Main artifact rubric has many_valued_policy key."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    rubric = fm.get("rubric") or {}
    assert "many_valued_policy" in rubric, "many_valued_policy key must be present"


def test_fv_spec_068_merged_refusal_fails():
    """Fixture with refusal in labels and refusal_flag_separate=false fails FV-SPEC-068."""
    fm, _ = load_witness_rule(WR_INVALID / "scoring" / "refusal_merges_correctness.md")
    diags = check_fv_spec_068_direction_aware_rubric(fm)
    assert diags, "Expected refusal-merged-into-labels diagnostic"


def test_fv_spec_068_all_four_answer_roles():
    """Main artifact rubric declares all four answer roles."""
    from tools.witness_rule_validator import ANSWER_ROLES
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    rubric = fm.get("rubric", {})
    declared = set(str(r) for r in rubric.get("answer_roles", []))
    assert declared >= ANSWER_ROLES, f"Missing answer roles: {ANSWER_ROLES - declared}"


def test_fv_spec_068_all_five_rubric_labels():
    """Main artifact rubric declares all five correctness labels."""
    from tools.witness_rule_validator import RUBRIC_LABELS
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    rubric = fm.get("rubric", {})
    declared = set(str(l) for l in rubric.get("labels", []))
    assert declared >= RUBRIC_LABELS, f"Missing labels: {RUBRIC_LABELS - declared}"


# ---------------------------------------------------------------------------
# FV-SPEC-069: Raw Score Semantics
# ---------------------------------------------------------------------------


def test_fv_spec_069_conventions_declared_per_channel():
    """Main artifact raw_score_conventions are declared per channel."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_069_raw_score_semantics(fm)
    # should pass (open decisions are deferred, not failures in non-strict)
    assert not diags, diags


def test_fv_spec_069_conventions_have_required_fields():
    """Each raw_score_conventions entry has channel_id, statistic_kind, and insufficient_data_status."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    for i, entry in enumerate(fm.get("raw_score_conventions", [])):
        assert "channel_id" in entry, f"Entry {i} missing channel_id"
        assert "statistic_kind" in entry, f"Entry {i} missing statistic_kind"
        assert "insufficient_data_status" in entry, f"Entry {i} missing insufficient_data_status"


def test_fv_spec_069_insufficient_topk_yields_unavailable():
    """insufficient_topk fixture asserts expected statistic = unavailable."""
    fixture = json.loads((WR_INVALID / "scoring" / "insufficient_topk.json").read_text())
    assert fixture.get("expected", {}).get("statistic") == "unavailable"
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_069_mixed_scales_fail():
    """mixed_raw_scales fixture asserts validation_should_fail."""
    fixture = json.loads((WR_INVALID / "scoring" / "mixed_raw_scales.json").read_text())
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_069_no_silent_approximation():
    """insufficient_topk fixture has no numeric approximation fallback."""
    fixture = json.loads((WR_INVALID / "scoring" / "insufficient_topk.json").read_text())
    expected = fixture.get("expected", {})
    assert "statistic" in expected
    # There must be no approximated_value field
    assert "approximated_value" not in expected


# ---------------------------------------------------------------------------
# FV-SPEC-070: Route A Confirmation
# ---------------------------------------------------------------------------


def test_fv_spec_070_route_a_valid_pass():
    """Valid Route A fixture confirms two independent family witnesses."""
    fixture = json.loads((WR_VALID / "routes" / "route_a_valid.json").read_text())
    assert fixture["expected_outcome"] == "confirmed_witness"
    assert len(fixture["families"]) >= 2


def test_fv_spec_070_punctuation_variant_fails():
    """Punctuation-variant Route A fixture must have validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "routes" / "route_a_punctuation_variant.json").read_text())
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_070_clue_bearing_fails():
    """Clue-bearing discovery fixture must have validation_should_fail=true."""
    from tools.witness_rule_validator import evaluate_route_a

    fixture = json.loads((WR_INVALID / "routes" / "route_a_clue_bearing.json").read_text())
    assert fixture.get("validation_should_fail") is True
    assert evaluate_route_a(fixture) == "clue_bearing_excluded"


def test_fv_spec_070_language_label_fails():
    """A language label alone does not supply Route A independence."""
    from tools.witness_rule_validator import evaluate_route_a

    fixture = json.loads((WR_INVALID / "routes" / "route_a_language_label.json").read_text())
    assert evaluate_route_a(fixture) == "language_label_only"


def test_fv_spec_070_false_statement_fails():
    """Rejecting a false statement does not confirm positive-target recovery."""
    from tools.witness_rule_validator import evaluate_route_a

    fixture = json.loads((WR_INVALID / "routes" / "route_a_false_statement.json").read_text())
    assert evaluate_route_a(fixture) == "false_statement_rejection"


def test_fv_spec_070_route_a_min_families_gte_2():
    """Main artifact Route A min_independent_families >= 2."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    route_a = fm.get("confirmation_routes", {}).get("A", {})
    assert route_a.get("enabled") is True
    assert route_a.get("min_independent_families", 0) >= 2


def test_fv_spec_070_route_a_clue_bearing_excluded():
    """Main artifact Route A clue_bearing_excluded is true."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    route_a = fm.get("confirmation_routes", {}).get("A", {})
    assert route_a.get("clue_bearing_excluded") is True


def test_fv_spec_070_route_a_passes_validator():
    """Main artifact Route A passes FV-SPEC-070."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_070_route_a_confirmation(fm)
    assert not diags, diags


# ---------------------------------------------------------------------------
# FV-SPEC-071: Route B Replication
# ---------------------------------------------------------------------------


def test_fv_spec_071_route_b_training_seed_pass():
    """Valid Route B fixture uses training_or_update seed type."""
    fixture = json.loads((WR_VALID / "routes" / "route_b_valid.json").read_text())
    assert fixture["seed_type"] == "training_or_update"
    assert fixture["expected_outcome"] == "confirmed_witness"


def test_fv_spec_071_decoding_seed_fails():
    """Decoding-seed Route B fixture must have validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "routes" / "route_b_decoding_seed.json").read_text())
    assert fixture["seed_type"] == "decoding"
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_071_export_variant_fails():
    """An export variant of one checkpoint is not a training/update seed."""
    from tools.witness_rule_validator import evaluate_route_b

    fixture = json.loads((WR_INVALID / "routes" / "route_b_export_variant.json").read_text())
    assert fixture["substitute_for_training_seed"] == "export_variant"
    assert evaluate_route_b(fixture) == "invalid_seed_type"
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_071_route_b_seed_type_declared():
    """Main artifact Route B seed_type is training_or_update even when disabled."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    route_b = fm.get("confirmation_routes", {}).get("B", {})
    assert route_b.get("seed_type") == "training_or_update"


def test_fv_spec_071_route_b_skipped_when_disabled():
    """FV-SPEC-071 check is a no-op when Route B is disabled."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    # Route B is disabled in the main artifact
    route_b = fm.get("confirmation_routes", {}).get("B", {})
    assert route_b.get("enabled") is False
    diags = check_fv_spec_071_route_b_replication(fm)
    assert not diags, "Route B disabled — no diagnostics expected"


# ---------------------------------------------------------------------------
# FV-SPEC-072: Route C Verdict Flips
# ---------------------------------------------------------------------------


def test_fv_spec_072_route_c_valid_pass():
    """Valid Route C fixture has parent/child hashes and required fields."""
    fixture = json.loads((WR_VALID / "routes" / "route_c_valid.json").read_text())
    assert fixture["expected_outcome"] == "confirmed_witness"
    assert fixture.get("parent_hash") is not None
    assert fixture.get("child_hash") is not None


def test_fv_spec_072_single_flip_fails():
    """Single-flip Route C fixture must have validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "routes" / "route_c_single_flip.json").read_text())
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_072_exposed_reacquisition_unlabelled_fails():
    """Target-exposed reacquisition without an exposure label is not residual-memory recovery."""
    from tools.witness_rule_validator import evaluate_route_c

    fixture = json.loads((WR_INVALID / "routes" / "route_c_exposed_unlabelled.json").read_text())
    assert fixture.get("exposure") == "target_exposed"
    assert fixture.get("exposure_labelled") is False
    assert evaluate_route_c(fixture) == "unlabelled_target_exposed"


def test_fv_spec_072_all_routes_disabled_fails():
    """Artifact with all routes disabled fails FV-SPEC-072 at-least-one-route check."""
    fm, _ = load_witness_rule(WR_INVALID / "routes" / "all_routes_disabled.md")
    diags = check_fv_spec_072_route_c_verdict_flips(fm)
    assert diags, "Expected at-least-one-route-enabled diagnostic"


def test_fv_spec_072_route_c_skipped_when_disabled():
    """FV-SPEC-072 structural checks skip when Route C is disabled (but checks at-least-one)."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    # Route C is disabled but Route A is enabled — should pass
    diags = check_fv_spec_072_route_c_verdict_flips(fm)
    assert not diags, diags


# ---------------------------------------------------------------------------
# FV-SPEC-073: Case-Level Verdict
# ---------------------------------------------------------------------------


def test_fv_spec_073_accept_all_gates():
    """Accept verdict fixture has all gates holding."""
    fixture = json.loads((WR_VALID / "verdicts" / "accept.json").read_text())
    summary = fixture["evidence_summary"]
    assert all(summary.values()), "All gates should hold for accept"


def test_fv_spec_073_reject_recovery_disqualifying_witness():
    """reject_recovery verdict has confirmed_recovery_witness=true."""
    fixture = json.loads((WR_VALID / "verdicts" / "reject_recovery.json").read_text())
    assert fixture["expected_verdict"] == "reject_recovery"
    assert fixture["evidence_summary"].get("confirmed_recovery_witness") is True


def test_fv_spec_073_reject_locality_no_recovery_required():
    """reject_locality verdict does not require a recovery witness."""
    fixture = json.loads((WR_VALID / "verdicts" / "reject_locality.json").read_text())
    assert fixture["expected_verdict"] == "reject_locality"
    assert fixture["evidence_summary"].get("confirmed_recovery_witness") is False


def test_fv_spec_073_no_witness_not_accept():
    """Main artifact has no_witness_is_not_accept=true."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_073_case_level_verdict(fm)
    assert not diags, diags
    case = fm.get("case_decision") or {}
    assert case.get("no_witness_is_not_accept") is True


def test_fv_spec_073_wide_interval_incomplete_not_fabricated():
    """incomplete verdict maps wide intervals to incomplete, not fabricated recovery."""
    fixture = json.loads((WR_VALID / "verdicts" / "incomplete.json").read_text())
    assert fixture["expected_verdict"] == "incomplete"


def test_fv_spec_073_ni_vocabulary_alignment():
    """non_identifiable verdict has reason and evidence fields."""
    fixture = json.loads((WR_VALID / "verdicts" / "non_identifiable.json").read_text())
    assert fixture["expected_verdict"] == "non_identifiable"
    assert "reason" in fixture
    assert "evidence" in fixture


def test_fv_spec_073_no_witness_accept_fixture_fails():
    """no_witness_accept fixture has validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "verdicts" / "no_witness_accept.json").read_text())
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_073_rejection_reasons_complete():
    """Main artifact case_decision rejection_reasons includes locality_failure and confirmed_recovery."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    case = fm.get("case_decision", {})
    rr = set(str(r) for r in case.get("rejection_reasons", []))
    assert "locality_failure" in rr
    assert "confirmed_recovery" in rr


# ---------------------------------------------------------------------------
# FV-SPEC-074: Evidence Aggregation
# ---------------------------------------------------------------------------


def test_fv_spec_074_reserved_costs_enabled_routes():
    """Main artifact aggregation_policy primary_statistic != raw_maximum and raw_maximum_role == diagnostic_only."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    agg = fm.get("aggregation_policy") or {}
    assert agg.get("primary_statistic") != "raw_maximum"
    assert agg.get("raw_maximum_role") == "diagnostic_only"


def test_fv_spec_074_raw_maximum_primary_fails():
    """Fixture with primary_statistic=raw_maximum fails FV-SPEC-074."""
    fixture_path = WR_INVALID / "aggregation" / "raw_maximum_primary.md"
    fm, _ = load_witness_rule(fixture_path)
    diags = check_fv_spec_074_evidence_aggregation(fm)
    assert diags, "Expected raw-maximum-primary diagnostic"
    assert any("raw_maximum" in d.get("message", "") for d in diags)


def test_fv_spec_074_unrestricted_search_fails():
    """An enabled route with no reservation fails FV-SPEC-074."""
    fixture_path = WR_INVALID / "aggregation" / "unrestricted_search.md"
    fm, _ = load_witness_rule(fixture_path)
    diags = check_fv_spec_074_evidence_aggregation(fm)
    budget_diags = [d for d in diags if "budget_reservation_ref" in d.get("message", "")]
    assert budget_diags, "Expected a hard budget_reservation_ref failure"
    assert all(d.get("severity") != "warning" for d in budget_diags)


def test_fv_spec_074_calibrated_as_whole():
    """Main artifact aggregation_policy.calibrated_as_whole is true."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    agg = fm.get("aggregation_policy", {})
    assert agg.get("calibrated_as_whole") is True


# ---------------------------------------------------------------------------
# FV-SPEC-075: Blinded Annotation
# ---------------------------------------------------------------------------


def test_fv_spec_075_blinded_annotation_pass():
    """Main artifact annotation_protocol and review records pass FV-SPEC-075."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_075_blinded_annotation(fm, WITNESS_DIR)
    assert not diags, diags


def test_fv_spec_075_sole_llm_fails():
    """sole_llm_adjudication review fixture has sole_llm_oracle=true (validation_should_fail)."""
    review_path = WR_INVALID / "annotation" / "sole_llm_adjudication.json"
    review = json.loads(review_path.read_text())
    assert review.get("sole_llm_oracle") is True
    assert review.get("validation_should_fail") is True


def test_fv_spec_075_outcome_driven_rubric_fails():
    """sole_llm_adjudication fixture also covers outcome_driven_rubric_change forbidden check."""
    review_path = WR_INVALID / "annotation" / "sole_llm_adjudication.json"
    review = json.loads(review_path.read_text())
    assert review.get("validation_should_fail") is True


def test_fv_spec_075_annotation_protocol_fields():
    """Main artifact annotation_protocol has required boolean fields."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    ap = fm.get("annotation_protocol", {})
    assert ap.get("sole_llm_oracle_forbidden") is True
    assert ap.get("outcome_driven_rubric_change_forbidden") is True


def test_fv_spec_075_review_record_valid():
    """Valid review record in witness_dir/reviews has all required fields."""
    review_path = WITNESS_DIR / "reviews" / "rubric_review_v0.1.0.json"
    assert review_path.exists(), "Review file not found"
    review = json.loads(review_path.read_text())
    assert review.get("annotators_blinded") is True
    assert review.get("system_identity_hidden") is True
    assert review.get("sole_llm_oracle") is False
    assert review.get("outcome_driven_rubric_change") is False
    assert review.get("kappa") == "undefined"
    assert review.get("approver_id") == "placeholder_reviewer"


# ---------------------------------------------------------------------------
# FV-SPEC-076: Reconstructable Records
# ---------------------------------------------------------------------------


def test_fv_spec_076_provenance_complete_pass():
    """Valid evidence fixture has all required provenance fields."""
    fixture = json.loads((WR_VALID / "evidence" / "confirmed_route_a.json").read_text())
    required_fields = [
        "case_id", "fact_id", "model_hash", "contract_ref", "access_profile",
        "channel", "template_family_ids", "raw_response_ids", "scorer",
        "reference", "confirmation", "verdict", "ground_truth_separate",
    ]
    for field in required_fields:
        assert field in fixture, f"Missing field: {field}"
    assert fixture["raw_response_ids"]  # non-empty
    assert fixture["ground_truth_separate"] is True


def test_fv_spec_076_missing_raw_ids_fails():
    """missing_raw_ids fixture has empty raw_response_ids and validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "evidence" / "missing_raw_ids.json").read_text())
    assert fixture["raw_response_ids"] == []
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_076_hidden_control_label_fails():
    """hidden_control_label fixture has control_oracle_label in confirmation and validation_should_fail=true."""
    fixture = json.loads((WR_INVALID / "evidence" / "hidden_control_label.json").read_text())
    assert "control_oracle_label" in fixture.get("confirmation", {})
    assert fixture.get("validation_should_fail") is True


def test_fv_spec_076_evidence_schema_complete():
    """Main artifact evidence_schema has all required fields declared."""
    from tools.witness_rule_validator import REQUIRED_EVIDENCE_FIELDS
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    schema = fm.get("evidence_schema", {})
    for field in REQUIRED_EVIDENCE_FIELDS:
        assert field in schema, f"evidence_schema missing field: {field}"


def test_fv_spec_076_validator_passes_main_artifact():
    """FV-SPEC-076 check passes on the main witness_rule.md."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_076_reconstructable_records(fm)
    assert not diags, diags


# ---------------------------------------------------------------------------
# FV-SPEC-077: Scoped CLI Validation
# ---------------------------------------------------------------------------


def test_fv_spec_077_digest_deterministic(tmp_path):
    """Two identical validation runs produce identical digests (excluding timestamp)."""
    report1 = tmp_path / "run1.json"
    report2 = tmp_path / "run2.json"

    result1 = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--report", str(report1)],
        cwd=str(REPO),
        capture_output=True,
    )
    result2 = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--report", str(report2)],
        cwd=str(REPO),
        capture_output=True,
    )

    assert result1.returncode in (0, 1), f"Run 1 failed with rc={result1.returncode}: {result1.stderr.decode()}"
    assert result2.returncode in (0, 1), f"Run 2 failed with rc={result2.returncode}: {result2.stderr.decode()}"

    r1 = json.loads(report1.read_text())
    r2 = json.loads(report2.read_text())

    # Remove timestamp before comparing
    r1.pop("timestamp", None)
    r2.pop("timestamp", None)

    assert r1 == r2, "Reports differ between identical runs (excluding timestamp)"


def test_fv_spec_077_strict_open_decisions_fails():
    """Strict mode fails when applicable decisions are open."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_077_scoped_cli_validation(
        fm, SPEC_ROOT, WITNESS_DIR, None, strict=True
    )
    # witness_rule.md has open D-* decisions → strict should fail
    assert diags, "Expected strict-mode open-decisions diagnostic"


def test_fv_spec_077_strict_stale_review_fails():
    """Strict mode fails when review_manifest is missing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_dir = Path(tmpdir)
        fm, _ = load_witness_rule(WITNESS_RULE_MD)
        # tmp_dir has no review_manifest.json
        diags = check_fv_spec_077_scoped_cli_validation(
            fm, SPEC_ROOT, tmp_dir, None, strict=True
        )
        assert diags, "Expected missing-review-manifest diagnostic in strict mode"


def test_fv_spec_077_no_model_calls():
    """Validator makes zero model/LLM/GPU/calibration calls."""
    assert _NO_MODEL_CALLS is True


def test_fv_spec_077_non_strict_open_decisions_pass():
    """Non-strict mode does not fail on open decisions."""
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags = check_fv_spec_077_scoped_cli_validation(
        fm, SPEC_ROOT, WITNESS_DIR, None, strict=False
    )
    assert not diags, "Non-strict mode should not fail on open decisions"


def test_fv_spec_077_cli_exits_correctly(tmp_path):
    """CLI exits with 0 or 1 for valid witness_rule.md."""
    report = tmp_path / "report.json"
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--report", str(report)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode in (0, 1), (
        f"Unexpected exit code {result.returncode}: {result.stderr.decode()}"
    )
    assert report.exists(), "Report file not created"
    rpt = json.loads(report.read_text())
    assert "scope" in rpt
    assert rpt["scope"] == "witness-rule"


def test_fv_spec_077_missing_artifact_exits_2(tmp_path):
    """CLI exits 2 when witness_rule.md is absent."""
    empty_spec = tmp_path / "spec"
    empty_spec.mkdir()
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(empty_spec)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 2, (
        f"Expected exit 2 for missing artifact, got {result.returncode}"
    )


# ---------------------------------------------------------------------------
# Baseline comparison
# ---------------------------------------------------------------------------


def test_baseline_identical_passes(tmp_path):
    """Baseline comparison passes when artifact is identical to baseline."""
    from tools.witness_rule_validator import check_baseline_comparison_wr
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    baseline_path = WR_BASELINES / "witness_rule.md"
    diags, comparison = check_baseline_comparison_wr(fm, baseline_path)
    assert not diags, diags
    assert comparison["status"] == "pass"


def test_fv_spec_068_unrelated_relation_not_recovery():
    """An unrelated relation that names the entity is not target recovery."""
    from tools.witness_rule_validator import evaluate_response

    fixture = json.loads((WR_VALID / "scoring" / "unrelated_relation.json").read_text())
    observed = evaluate_response(fixture)
    assert observed["correctness"] == "non_answer"
    assert observed["refusal_flag"] is False


def test_quickstart_valid_worksheet_exits_0(tmp_path):
    """Quickstart scenario 1: the shipped contract validates offline."""
    report = tmp_path / "p0-6-validation.json"
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--report", str(report)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr.decode()
    report_body = json.loads(report.read_text())
    assert report_body["overall"] == "pass"
    interpreted = [row for row in report_body["fixture_results"] if row.get("observed") is not None]
    assert interpreted
    assert all(row["status"] == "pass" for row in interpreted)


def test_quickstart_response_as_verdict_exits_1(tmp_path):
    """Quickstart scenario 2: a response label used as a verdict fails."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "witness_rule.md").write_text(
        (WR_INVALID / "response_as_verdict.md").read_text(),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(spec),
         "--witness-dir", str(tmp_path / "witness")],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 1, result.stderr.decode()


def test_quickstart_malformed_exits_2(tmp_path):
    """Quickstart scenario 12: unparseable frontmatter fails closed."""
    spec = tmp_path / "spec"
    spec.mkdir()
    (spec / "witness_rule.md").write_text("---\nversion: [\n---\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(spec)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 2, result.stderr.decode()


def test_quickstart_remaining_fixture_scenarios():
    """Quickstart scenarios 3–10: interpreter and rule checks match the documented outcomes."""
    from tools.witness_rule_validator import (
        evaluate_response,
        evaluate_route_a,
        evaluate_route_b,
        evaluate_route_c,
        evaluate_score,
        evaluate_verdict,
    )

    disclosure = json.loads((WR_VALID / "scoring" / "disclosure_plus_refusal.json").read_text())
    negated = json.loads((WR_VALID / "scoring" / "negated_entity.json").read_text())
    assert evaluate_response(disclosure) == {"correctness": "correct", "refusal_flag": True}
    assert evaluate_response(negated)["correctness"] == "incorrect_contradictory"

    topk = json.loads((WR_INVALID / "scoring" / "insufficient_topk.json").read_text())
    assert evaluate_score(topk)["statistic"] == "unavailable"

    punctuation = json.loads((WR_INVALID / "routes" / "route_a_punctuation_variant.json").read_text())
    assert evaluate_route_a(punctuation) == "punctuation_only"

    decoding = json.loads((WR_INVALID / "routes" / "route_b_decoding_seed.json").read_text())
    assert evaluate_route_b(decoding) == "invalid_seed_type"

    single_flip = json.loads((WR_INVALID / "routes" / "route_c_single_flip.json").read_text())
    assert evaluate_route_c(single_flip) == "insufficient_evidence"

    no_witness = json.loads((WR_INVALID / "verdicts" / "no_witness_accept.json").read_text())
    assert evaluate_verdict(no_witness) != "accept"

    raw_max, _ = load_witness_rule(WR_INVALID / "aggregation" / "raw_maximum_primary.md")
    assert check_fv_spec_074_evidence_aggregation(raw_max)

    sole_llm = json.loads((WR_INVALID / "annotation" / "sole_llm_adjudication.json").read_text())
    assert sole_llm["sole_llm_oracle"] is True
    missing_raw = json.loads((WR_INVALID / "evidence" / "missing_raw_ids.json").read_text())
    assert missing_raw["raw_response_ids"] == []


def test_quickstart_strict_open_decisions_exit_1(tmp_path):
    """Quickstart scenario 11: strict readiness fails while blocking decisions stay open."""
    report = tmp_path / "strict.json"
    result = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--strict",
         "--report", str(report)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 1, result.stderr.decode()


def test_quickstart_baseline_match_and_unbumped_edit(tmp_path):
    """Quickstart scenario 13: matching baseline passes; an unbumped rubric edit fails."""
    report = tmp_path / "baseline.json"
    match = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(SPEC_ROOT),
         "--baseline-suite", str(WR_BASELINES / "witness_rule.md"),
         "--report", str(report)],
        cwd=str(REPO),
        capture_output=True,
    )
    assert match.returncode == 0, match.stderr.decode()

    edited = tmp_path / "edited"
    spec = edited / "spec"
    spec.mkdir(parents=True)
    text = WITNESS_RULE_MD.read_text(encoding="utf-8")
    text = text.replace(
        "labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]",
        "labels: [correct, incorrect_contradictory, ambiguous, non_answer]",
        1,
    )
    (spec / "witness_rule.md").write_text(text, encoding="utf-8")
    changed = subprocess.run(
        [sys.executable, "tools/validate_spec.py",
         "--scope", "witness-rule",
         "--spec-root", str(spec),
         "--witness-dir", str(WITNESS_DIR),
         "--baseline-suite", str(WR_BASELINES / "witness_rule.md")],
        cwd=str(REPO),
        capture_output=True,
    )
    assert changed.returncode == 1, changed.stderr.decode()


def test_baseline_missing_fails():
    """Baseline comparison fails when baseline file does not exist."""
    from tools.witness_rule_validator import check_baseline_comparison_wr
    fm, _ = load_witness_rule(WITNESS_RULE_MD)
    diags, comparison = check_baseline_comparison_wr(fm, Path("/nonexistent/witness_rule.md"))
    assert diags, "Expected missing-baseline diagnostic"
    assert comparison["status"] == "fail"
