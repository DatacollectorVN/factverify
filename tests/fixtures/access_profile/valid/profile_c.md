---
version: "1.0.0"
profile: C
measurement_point: serving_pipeline_output
score_scope:
  type: pre_mask
  vocabulary: full
systems:
  candidate:
    system_id: candidate
    profile_letter: C
    capabilities:
      text: verified
      scores: verified
      internals: verified
      candidate_scoring: verified
      controllable_decoding: verified
    manifest_ref: capability_manifests/manifest_candidate.json
    verification_state: verified
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
    permitted_actions:
      - observe_text_output
      - observe_scores
      - observe_internals
  - role_id: operator_1
    role_type: operator
    permitted_actions:
      - export_checkpoint
permitted_sources:
  - model_api
  - weight_access
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

# Access Profile: Profile C (Full Internals)

## Observation Boundary

Full internal access to candidate model weights, activations, and gradients.

## Provenance Procedure

Internal access verified via direct weight loading and inspection.

## Limitations

- Reference system remains text-only.
