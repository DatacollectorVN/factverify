---
version: "1.0.0"
profile: B
measurement_point: serving_pipeline_output
score_scope:
  type: pre_mask
  vocabulary: full
systems:
  candidate:
    system_id: candidate
    profile_letter: B
    capabilities:
      text: verified
      scores: declared
      internals: unavailable
      candidate_scoring: declared
      controllable_decoding: unavailable
    manifest_ref: capability_manifests/manifest_candidate.json
    verification_state: partial
    provider_transformations: []
  reference:
    system_id: reference
    profile_letter: A
    capabilities:
      text: verified
      scores: unavailable
      internals: unavailable
      candidate_scoring: unavailable
      controllable_decoding: unavailable
    manifest_ref: capability_manifests/manifest_reference.json
    verification_state: verified
    provider_transformations: []
roles:
  - role_id: evaluator_1
    role_type: evaluator
    person_id: alice
    permitted_actions:
      - observe_text_output
      - observe_scores
  - role_id: operator_1
    role_type: operator
    person_id: bob
    permitted_actions:
      - export_checkpoint
permitted_sources:
  - model_api
  - score_endpoint
  - checkpoint_export
interventions:
  - action: export_checkpoint
    actor_role: operator_1
    approved_recipes:
      - recipes/checkpoint_export_v1.md
    artifact_lineage: lineage/export_candidate_ckpt.json
    target_system: candidate
    requires_capabilities: []
historical_access:
  - artifact_id: pre_ckpt_001
    artifact_type: pre_unlearning_checkpoint
    source: pre_unlearning_model
    attribution: pre_unlearning_checkpoint_ckpt001
handling_policies:
  non_identifiable: predeclared_reporting_rule_ni
  incomplete: predeclared_reporting_rule_inc
  confirmed_recovery: predeclared_reporting_rule_cr
  conformance: predeclared_reporting_rule_conf
budget_ref: attacks.yaml
blocking_decisions:
  - decision_id: D-13
    status: open
  - decision_id: D-14
    status: open
  - decision_id: D-27
    status: open
  - decision_id: D-28
    status: open
  - decision_id: D-29
    status: open
  - decision_id: D-31
    status: open
provenance_refs:
  - capability_manifests/manifest_candidate.json
  - capability_manifests/manifest_reference.json
claim_refs: []
identifiability_refs: []
---

# Access Profile With Interventions

## Observation Boundary

Evaluator observes text and scores; operator exports checkpoints separately.

## Provenance Procedure

Measurement at serving pipeline; interventions tracked via artifact lineage.

## Limitations

Intervention permissions are independent of observation profile.
