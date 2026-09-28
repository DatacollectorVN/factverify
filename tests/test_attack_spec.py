"""P0-3 attack specification validation tests.

Tests FV-SPEC-034 through FV-SPEC-046, exercising the attack_validator
module via fixture-driven structural, allocation, accounting, permission,
confirmation, adaptive-policy, clue-audit, transformation, relearning,
cost-report, revision-protection, and strict-mode checks.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from tests.conftest import AT_FIXTURES

# Import validator functions directly for unit testing
from tools.attack_validator import (
    check_accounting_units,
    check_adaptive_policies,
    check_artifact_structure,
    check_channel_permissions,
    check_clue_audit,
    check_confirmation_reservations,
    check_cost_records,
    check_event_policies,
    check_matched_allocations,
    check_relearning,
    check_revision_protection,
    check_strict_mode,
    check_transformations,
    generate_cost_records,
    load_attack_spec,
    load_event_fixtures,
    replay_event_traces,
    validate_attack_spec,
)


# ── helpers ────────────────────────────────────────────────────────

def _load_fixture(name: str) -> dict:
    """Load a YAML fixture from the valid/ directory."""
    path = AT_FIXTURES / "valid" / name
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_invalid(name: str) -> dict | None:
    """Load a YAML fixture from the invalid/ directory, return None on parse error."""
    path = AT_FIXTURES / "invalid" / name
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return None


# ── FV-SPEC-034: artifact structure ──────────────────────────────


class TestFvSpec034Artifact:
    """Structural validation of attacks.yaml."""

    def test_valid_spec_has_no_diagnostics(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_artifact_structure(spec, "attacks.yaml")
        assert diags == []

    def test_malformed_yaml_raises(self):
        path = AT_FIXTURES / "invalid" / "malformed.yaml"
        with pytest.raises(yaml.YAMLError):
            yaml.safe_load(path.read_text(encoding="utf-8"))

    def test_missing_required_fields(self):
        spec = _load_invalid("missing_required.yaml")
        assert spec is not None
        diags = check_artifact_structure(spec, "attacks.yaml")
        missing_fields = {d["json_pointer"].split("/")[-1] for d in diags}
        assert "common_cap" in missing_fields
        assert "accounting" in missing_fields
        assert "arms" in missing_fields
        assert "channels" in missing_fields

    def test_duplicate_channel_ids(self):
        spec = _load_invalid("duplicate_channels.yaml")
        assert spec is not None
        diags = check_artifact_structure(spec, "attacks.yaml")
        dup_diags = [d for d in diags if "Duplicate channel" in d["message"]]
        assert len(dup_diags) >= 1

    def test_three_arms_required(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # Remove one arm
        spec["arms"] = spec["arms"][:2]
        diags = check_artifact_structure(spec, "attacks.yaml")
        arm_diags = [d for d in diags if "3 arms required" in d["message"]]
        assert len(arm_diags) == 1

    def test_unknown_arm_id_rejected(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["arms"][0]["arm_id"] = "unknown_arm"
        diags = check_artifact_structure(spec, "attacks.yaml")
        unknown_diags = [d for d in diags if "Unknown arm_id" in d["message"]]
        assert len(unknown_diags) >= 1

    def test_blocking_decisions_validated(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # Remove required field from a decision
        spec["blocking_decisions"][0] = {"decision_id": "D-17"}
        diags = check_artifact_structure(spec, "attacks.yaml")
        dec_diags = [d for d in diags
                     if "blocking_decisions" in d["json_pointer"]]
        assert len(dec_diags) >= 1

    def test_common_cap_must_be_positive(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["common_cap"] = -1
        diags = check_artifact_structure(spec, "attacks.yaml")
        cap_diags = [d for d in diags if "common_cap" in d["json_pointer"]]
        assert len(cap_diags) >= 1


# ── FV-SPEC-035: channel permissions ─────────────────────────────


class TestFvSpec035Permissions:
    """Channel permission cross-check against access profile."""

    def test_no_profile_skips_check(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_channel_permissions(spec, "attacks.yaml", None)
        assert diags == []

    def test_all_capabilities_met(self):
        spec = _load_fixture("minimal_attacks.yaml")
        profile = {
            "capabilities": {
                "observation": True,
                "controllable_decoding": True,
            }
        }
        diags = check_channel_permissions(spec, "attacks.yaml", profile)
        assert diags == []

    def test_missing_capability_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # repeated_sampling requires controllable_decoding
        profile = {
            "capabilities": {
                "observation": True,
                "controllable_decoding": False,
            }
        }
        diags = check_channel_permissions(spec, "attacks.yaml", profile)
        assert len(diags) >= 1
        assert any("controllable_decoding" in d["message"] for d in diags)

    def test_disabled_channel_not_checked(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # raw_likelihood is disabled — should not fail even without raw_scores
        profile = {
            "capabilities": {
                "observation": True,
                "controllable_decoding": True,
            }
        }
        diags = check_channel_permissions(spec, "attacks.yaml", profile)
        raw_diags = [d for d in diags if "raw_likelihood" in str(d)]
        assert raw_diags == []

    def test_permission_violation_fixture(self):
        spec = _load_invalid("permission_violation.yaml")
        assert spec is not None
        profile = {
            "capabilities": {
                "observation": True,
                "raw_scores": False,
            }
        }
        diags = check_channel_permissions(spec, "attacks.yaml", profile)
        assert len(diags) >= 1
        assert any("raw_scores" in d["message"] for d in diags)


# ── FV-SPEC-036: accounting units ────────────────────────────────


class TestFvSpec036Units:
    """Accounting unit declaration validation."""

    def test_valid_units_pass(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_accounting_units(spec, "attacks.yaml")
        assert diags == []

    def test_missing_unit_fields(self):
        spec = _load_invalid("missing_unit.yaml")
        assert spec is not None
        diags = check_accounting_units(spec, "attacks.yaml")
        # generation_trial_unit is missing definition, multiplicity_rule, identity_fields
        assert len(diags) >= 1

    def test_empty_identity_fields_fails(self):
        spec = _load_invalid("missing_unit.yaml")
        assert spec is not None
        diags = check_accounting_units(spec, "attacks.yaml")
        empty_diags = [d for d in diags if "identity_fields" in d["json_pointer"]
                       and "nonempty" in d["message"]]
        assert len(empty_diags) >= 1

    def test_empty_cost_vector_fails(self):
        spec = _load_invalid("missing_unit.yaml")
        assert spec is not None
        diags = check_accounting_units(spec, "attacks.yaml")
        cvf_diags = [d for d in diags if "cost_vector_fields" in d["json_pointer"]]
        assert len(cvf_diags) >= 1


# ── FV-SPEC-037: event policies ──────────────────────────────────


class TestFvSpec037EventPolicies:
    """Event charge policy validation."""

    def test_valid_policies_pass(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_event_policies(spec, "attacks.yaml")
        assert diags == []

    def test_missing_policies_detected(self):
        spec = _load_invalid("missing_cache_policy.yaml")
        assert spec is not None
        # check_artifact_structure detects missing accounting fields
        diags = check_artifact_structure(spec, "attacks.yaml")
        acct_diags = [d for d in diags if "/accounting/" in d["json_pointer"]]
        assert len(acct_diags) >= 1

    def test_invalid_charge_rule_rejected(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["accounting"]["cache_policy"]["charge_rule"] = "free_lunch"
        diags = check_event_policies(spec, "attacks.yaml")
        assert len(diags) >= 1
        assert any("Invalid charge_rule" in d["message"] for d in diags)

    def test_event_replay_valid_traces(self):
        spec = _load_fixture("minimal_attacks.yaml")
        events_path = AT_FIXTURES / "valid" / "minimal_events.json"
        events = json.loads(events_path.read_text(encoding="utf-8"))
        diags = replay_event_traces(spec, events, "attacks.yaml")
        assert diags == []

    def test_cache_hit_with_new_compute_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        events = [{
            "trace_id": "test",
            "arm_id": "native",
            "events": [{
                "event_id": "bad_cache",
                "arm_id": "native",
                "case_id": "fact_001",
                "phase": "discovery",
                "channel_id": "prompt_variation",
                "probe_id": "direct_001",
                "sample_index": 0,
                "decoding_config": {"temperature": 0.0, "max_tokens": 64},
                "artifact_id": "ckpt_001",
                "operation": "cache_hit",
                "outcome": "cached",
                "charge": {
                    "generation_trials": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "new_compute": True,
                    "policy_applied": "cache_hit",
                },
            }],
        }]
        diags = replay_event_traces(spec, events, "attacks.yaml")
        assert len(diags) >= 1
        assert any("zero_new_compute" in d["message"] for d in diags)


# ── FV-SPEC-038: matched allocations ─────────────────────────────


class TestFvSpec038Allocations:
    """Matched allocation validation."""

    def test_valid_allocations_pass(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_matched_allocations(spec, "attacks.yaml")
        assert diags == []

    def test_unequal_totals_fail(self):
        spec = _load_invalid("unequal_allocations.yaml")
        assert spec is not None
        diags = check_matched_allocations(spec, "attacks.yaml")
        assert len(diags) >= 1
        assert any("common_cap" in d["message"] for d in diags)

    def test_negative_allowance_fails(self):
        spec = _load_invalid("negative_allowance.yaml")
        assert spec is not None
        diags = check_matched_allocations(spec, "attacks.yaml")
        neg_diags = [d for d in diags if "Negative" in d["message"]]
        assert len(neg_diags) >= 1

    def test_allocation_sum_mismatch_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # Change a channel allocation to make sum != total
        spec["arms"][0]["channel_allocations"][0]["trials"] = 1
        diags = check_matched_allocations(spec, "attacks.yaml")
        sum_diags = [d for d in diags if "Allocation sum" in d["message"]]
        assert len(sum_diags) >= 1

    def test_disabled_channel_with_allocation_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        # Give the disabled adversarial_wrapper channel an allocation
        spec["arms"][0]["channel_allocations"].append({
            "channel_id": "adversarial_wrapper",
            "trials": 2,
            "purpose": "Should not have budget",
        })
        # Adjust total to match
        spec["arms"][0]["total"] = 14
        diags = check_matched_allocations(spec, "attacks.yaml")
        disabled_diags = [d for d in diags if "Disabled channel" in d["message"]]
        assert len(disabled_diags) >= 1


# ── FV-SPEC-039: confirmation reservations ───────────────────────


class TestFvSpec039Confirmation:
    """Confirmation route budget reservation validation."""

    def test_valid_reservation_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_confirmation_reservations(spec, "attacks.yaml")
        assert diags == []

    def test_missing_reservation_fields(self):
        spec = _load_invalid("missing_reservation.yaml")
        assert spec is not None
        diags = check_confirmation_reservations(spec, "attacks.yaml")
        assert len(diags) >= 1

    def test_duplicate_reservation_id_fails(self):
        spec = _load_invalid("double_funded.yaml")
        assert spec is not None
        diags = check_confirmation_reservations(spec, "attacks.yaml")
        dup_diags = [d for d in diags if "Duplicate" in d["message"]]
        assert len(dup_diags) >= 1

    def test_self_shared_reservation_fails(self):
        spec = _load_invalid("double_funded.yaml")
        assert spec is not None
        diags = check_confirmation_reservations(spec, "attacks.yaml")
        self_diags = [d for d in diags if "share with itself" in d["message"]]
        assert len(self_diags) >= 1

    def test_zero_reserved_trials_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["confirmation_reservations"][0]["reserved_trials"] = 0
        diags = check_confirmation_reservations(spec, "attacks.yaml")
        assert len(diags) >= 1
        assert any("positive" in d["message"] for d in diags)


# ── FV-SPEC-040: adaptive policies ───────────────────────────────


class TestFvSpec040Adaptive:
    """Adaptive policy validation."""

    def test_valid_policy_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_adaptive_policies(spec, "attacks.yaml")
        assert diags == []

    def test_unbounded_policy_fails(self):
        spec = _load_invalid("unbounded_policy.yaml")
        assert spec is not None
        diags = check_adaptive_policies(spec, "attacks.yaml")
        # Should catch: invalid policy_type, negative cardinality,
        # empty stop_rule, negative budget_ceiling
        assert len(diags) >= 2

    def test_invalid_policy_type_rejected(self):
        spec = _load_invalid("unbounded_policy.yaml")
        assert spec is not None
        diags = check_adaptive_policies(spec, "attacks.yaml")
        type_diags = [d for d in diags if "Invalid policy_type" in d["message"]]
        assert len(type_diags) >= 1

    def test_negative_budget_ceiling_fails(self):
        spec = _load_invalid("unbounded_policy.yaml")
        assert spec is not None
        diags = check_adaptive_policies(spec, "attacks.yaml")
        ceil_diags = [d for d in diags if "budget_ceiling" in d["message"]]
        assert len(ceil_diags) >= 1

    def test_empty_stop_rule_fails(self):
        spec = _load_invalid("unbounded_policy.yaml")
        assert spec is not None
        diags = check_adaptive_policies(spec, "attacks.yaml")
        stop_diags = [d for d in diags if "stop_rule" in d["message"]]
        assert len(stop_diags) >= 1


# ── FV-SPEC-041: clue audit ─────────────────────────────────────


class TestFvSpec041ClueAudit:
    """Clue audit manifest validation."""

    def test_valid_audit_passes(self):
        manifest_path = Path(__file__).resolve().parent.parent / ".factverify" / "attacks" / "audit_manifests" / "demo_audit.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_clue_audit(spec, "attacks.yaml", [manifest])
        assert diags == []

    def test_unversioned_audit_fails(self):
        manifest_path = AT_FIXTURES / "invalid" / "unversioned_audit.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_clue_audit(spec, "attacks.yaml", [manifest])
        rev_diags = [d for d in diags if "version-bound" in d["message"]]
        assert len(rev_diags) >= 1

    def test_direct_disclosure_in_equivalence_fails(self):
        manifest_path = AT_FIXTURES / "invalid" / "unflagged_disclosure.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_clue_audit(spec, "attacks.yaml", [manifest])
        eq_diags = [d for d in diags
                    if "equivalence" in d["message"].lower()
                    and "direct disclosure" in d["message"].lower()]
        assert len(eq_diags) >= 1

    def test_invalid_exposure_class_rejected(self):
        manifest = {
            "manifest_id": "test",
            "revision": "0.1.0",
            "content_digest": "sha256:test",
            "channel_id": "prompt_variation",
            "reviewer_id": "test",
            "review_date": "2026-09-22",
            "entries": [{
                "input_id": "bad_class",
                "input_type": "template",
                "exposure_class": "totally_made_up",
                "routing": "equivalence",
                "rationale": "test",
            }],
        }
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_clue_audit(spec, "attacks.yaml", [manifest])
        class_diags = [d for d in diags if "Invalid exposure_class" in d["message"]]
        assert len(class_diags) >= 1


# ── FV-SPEC-042: transformation recipes ─────────────────────────


class TestFvSpec042Transformations:
    """Transformation recipe validation."""

    def test_no_transformations_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_transformations(spec, "attacks.yaml")
        assert diags == []

    def test_complete_recipe_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["transformations"] = [{
            "recipe_id": "quant_4bit",
            "channel_id": "deployment_transformation",
            "algorithm": "GPTQ",
            "software_version": "auto-gptq==0.7.1",
            "parent_checkpoint": "ckpt_candidate_001",
            "tokenizer": "same_as_parent",
            "decoding_config": {"temperature": 0.0, "max_tokens": 64},
            "fitting_data_exposure": "target_free",
            "reference_treatment": "same_quantization",
            "output_provenance": "local_gpu",
        }]
        diags = check_transformations(spec, "attacks.yaml")
        assert diags == []

    def test_missing_recipe_fields_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["transformations"] = [{
            "recipe_id": "incomplete",
            "channel_id": "deployment_transformation",
            # Missing: algorithm, software_version, parent_checkpoint, etc.
        }]
        diags = check_transformations(spec, "attacks.yaml")
        assert len(diags) >= 1

    def test_invalid_exposure_type_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["transformations"] = [{
            "recipe_id": "bad_exposure",
            "channel_id": "deployment_transformation",
            "algorithm": "GPTQ",
            "software_version": "0.7.1",
            "parent_checkpoint": "ckpt_001",
            "tokenizer": "same",
            "decoding_config": {},
            "fitting_data_exposure": "contaminated",
            "reference_treatment": "same",
            "output_provenance": "local",
        }]
        diags = check_transformations(spec, "attacks.yaml")
        assert len(diags) >= 1
        assert any("Invalid fitting_data_exposure" in d["message"] for d in diags)


# ── FV-SPEC-043: relearning conditions ───────────────────────────


class TestFvSpec043Relearning:
    """Relearning condition separation validation."""

    def test_no_relearning_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_relearning(spec, "attacks.yaml")
        assert diags == []

    def test_unseparated_relearning_fails(self):
        spec = _load_invalid("unseparated_relearning.yaml")
        assert spec is not None
        diags = check_relearning(spec, "attacks.yaml")
        missing_diags = [d for d in diags if "target_exposed" in d["message"]]
        assert len(missing_diags) >= 1

    def test_complete_relearning_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["relearning"] = {
            "enabled": True,
            "conditions": [
                {
                    "condition_id": "relearn_tf",
                    "exposure_type": "target_free",
                    "data_source": "retain_corpus",
                    "schedule": "5 epochs",
                    "optimizer": "AdamW",
                    "trainable_parameters": "LoRA rank-8",
                    "held_out_evaluation": "20% val",
                    "reporting_contract": {
                        "reached_format": "epochs_to_recovery",
                        "unreached_format": "censored",
                        "substitution_prohibited": True,
                    },
                },
                {
                    "condition_id": "relearn_te",
                    "exposure_type": "target_exposed",
                    "data_source": "target_corpus",
                    "schedule": "5 epochs",
                    "optimizer": "AdamW",
                    "trainable_parameters": "LoRA rank-8",
                    "held_out_evaluation": "20% val",
                    "reporting_contract": {
                        "reached_format": "epochs_to_recovery",
                        "unreached_format": "censored",
                        "substitution_prohibited": True,
                    },
                },
            ],
        }
        diags = check_relearning(spec, "attacks.yaml")
        assert diags == []

    def test_substitution_prohibited_false_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        spec["relearning"] = {
            "enabled": True,
            "conditions": [
                {
                    "condition_id": "relearn_tf",
                    "exposure_type": "target_free",
                    "data_source": "retain_corpus",
                    "schedule": "5 epochs",
                    "optimizer": "AdamW",
                    "trainable_parameters": "LoRA rank-8",
                    "held_out_evaluation": "20% val",
                    "reporting_contract": {
                        "reached_format": "epochs",
                        "unreached_format": "censored",
                        "substitution_prohibited": False,
                    },
                },
                {
                    "condition_id": "relearn_te",
                    "exposure_type": "target_exposed",
                    "data_source": "target_corpus",
                    "schedule": "5 epochs",
                    "optimizer": "AdamW",
                    "trainable_parameters": "LoRA rank-8",
                    "held_out_evaluation": "20% val",
                    "reporting_contract": {
                        "reached_format": "epochs",
                        "unreached_format": "censored",
                        "substitution_prohibited": True,
                    },
                },
            ],
        }
        diags = check_relearning(spec, "attacks.yaml")
        sub_diags = [d for d in diags if "substitution_prohibited" in d["message"]]
        assert len(sub_diags) >= 1


# ── FV-SPEC-044: cost records ────────────────────────────────────


class TestFvSpec044CostRecords:
    """Cost record generation and validation."""

    def test_cost_records_per_arm(self):
        spec = _load_fixture("minimal_attacks.yaml")
        records = generate_cost_records(spec, None)
        assert len(records) == 3
        arm_ids = {r["arm_id"] for r in records}
        assert arm_ids == {"native", "semantic_only", "factverify"}

    def test_cost_records_preserve_cap(self):
        spec = _load_fixture("minimal_attacks.yaml")
        records = generate_cost_records(spec, None)
        for r in records:
            assert r["cap"] == 12

    def test_cost_records_from_events(self):
        spec = _load_fixture("minimal_attacks.yaml")
        events_path = AT_FIXTURES / "valid" / "minimal_events.json"
        events = json.loads(events_path.read_text(encoding="utf-8"))
        records = generate_cost_records(spec, events)
        native = next(r for r in records if r["arm_id"] == "native")
        # Events have generation_trials: 1+0+1+1+1 = 4
        assert native["generation_trials"] == 4
        assert native["actual_trials"] == 4
        assert native["unused_trials"] == 8  # 12 - 4

    def test_missing_charge_detected(self):
        spec = _load_fixture("minimal_attacks.yaml")
        events = [{
            "trace_id": "test",
            "arm_id": "native",
            "events": [{
                "event_id": "no_charge",
                "arm_id": "native",
                "case_id": "fact_001",
                "phase": "discovery",
                "channel_id": "prompt_variation",
                "operation": "generation",
                "outcome": "completed",
                # Missing: charge
            }],
        }]
        diags = check_cost_records(spec, events, "attacks.yaml")
        assert len(diags) >= 1


# ── FV-SPEC-045: revision protection ─────────────────────────────


class TestFvSpec045Revision:
    """Revision protection validation."""

    def test_identical_baseline_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        baseline = _load_fixture("minimal_attacks.yaml")
        result = check_revision_protection(spec, baseline, "attacks.yaml")
        assert result["status"] == "pass"

    def test_no_baseline_not_requested(self):
        spec = _load_fixture("minimal_attacks.yaml")
        result = check_revision_protection(spec, None, "attacks.yaml")
        assert result["status"] == "not_requested"

    def test_changed_content_same_revision_fails(self):
        spec = _load_fixture("minimal_attacks.yaml")
        baseline = _load_fixture("minimal_attacks.yaml")
        # Change channel allocation without bumping revision
        spec["arms"][0]["channel_allocations"][0]["trials"] = 999
        spec["arms"][0]["total"] = 999
        result = check_revision_protection(spec, baseline, "attacks.yaml")
        assert result["status"] == "fail"

    def test_changed_content_new_revision_passes(self):
        spec = _load_fixture("minimal_attacks.yaml")
        baseline = _load_fixture("minimal_attacks.yaml")
        spec["revision"] = "0.2.0-demo"
        spec["arms"][0]["channel_allocations"][0]["trials"] = 999
        result = check_revision_protection(spec, baseline, "attacks.yaml")
        assert result["status"] == "pass"


# ── FV-SPEC-046: scoped CLI and strict mode ──────────────────────


class TestFvSpec046ScopedCli:
    """Strict mode and CLI integration."""

    def test_strict_mode_catches_open_decisions(self):
        spec = _load_fixture("minimal_attacks.yaml")
        diags = check_strict_mode(spec, "attacks.yaml", [])
        # All 14 decisions are open — should flag them all
        assert len(diags) >= 14

    def test_strict_mode_clean_when_resolved(self):
        spec = _load_fixture("minimal_attacks.yaml")
        for d in spec["blocking_decisions"]:
            d["status"] = "resolved"
        diags = check_strict_mode(spec, "attacks.yaml", [])
        decision_diags = [d for d in diags if "Unresolved" in d["message"]]
        assert decision_diags == []

    def test_strict_mode_flags_missing_audit(self):
        spec = _load_fixture("minimal_attacks.yaml")
        for d in spec["blocking_decisions"]:
            d["status"] = "resolved"
        # No audit manifests for prompt_variation (enabled prompt channel)
        diags = check_strict_mode(spec, "attacks.yaml", [])
        audit_diags = [d for d in diags if "clue audit" in d["message"].lower()]
        assert len(audit_diags) >= 1

    def test_end_to_end_valid_spec(self, tmp_path):
        """Integration: validate_attack_spec on valid fixture."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        shutil.copy(
            AT_FIXTURES / "valid" / "minimal_attacks.yaml",
            spec_dir / "attacks.yaml",
        )
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        report_path = tmp_path / "report.json"

        success, rpt = validate_attack_spec(
            spec_root=spec_dir,
            contracts_dir=contracts_dir,
            report_path=report_path,
        )
        assert success is True
        assert report_path.exists()
        report = json.loads(report_path.read_text(encoding="utf-8"))
        assert report["scope"] == "attacks"
        assert report["summary"]["failed"] == 0

    def test_end_to_end_with_events(self, tmp_path):
        """Integration: validate with event fixtures."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        shutil.copy(
            AT_FIXTURES / "valid" / "minimal_attacks.yaml",
            spec_dir / "attacks.yaml",
        )
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        report_path = tmp_path / "report.json"
        events_path = AT_FIXTURES / "valid" / "minimal_events.json"

        success, rpt = validate_attack_spec(
            spec_root=spec_dir,
            contracts_dir=contracts_dir,
            report_path=report_path,
            event_fixtures_path=events_path,
        )
        assert success is True
        assert rpt["event_replay"]["status"] == "pass"

    def test_end_to_end_strict_fails_open_decisions(self, tmp_path):
        """Integration: strict mode rejects open decisions."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        shutil.copy(
            AT_FIXTURES / "valid" / "minimal_attacks.yaml",
            spec_dir / "attacks.yaml",
        )
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        report_path = tmp_path / "report.json"

        success, rpt = validate_attack_spec(
            spec_root=spec_dir,
            contracts_dir=contracts_dir,
            report_path=report_path,
            strict=True,
        )
        assert success is False

    def test_deferred_checks_listed(self, tmp_path):
        """Deferred checks appear in report."""
        spec_dir = tmp_path / "spec"
        spec_dir.mkdir()
        shutil.copy(
            AT_FIXTURES / "valid" / "minimal_attacks.yaml",
            spec_dir / "attacks.yaml",
        )
        contracts_dir = tmp_path / "contracts"
        contracts_dir.mkdir()
        report_path = tmp_path / "report.json"

        _, rpt = validate_attack_spec(
            spec_root=spec_dir,
            contracts_dir=contracts_dir,
            report_path=report_path,
        )
        assert len(rpt["deferred_checks"]) >= 2
        assert any("P0-5" in d for d in rpt["deferred_checks"])
