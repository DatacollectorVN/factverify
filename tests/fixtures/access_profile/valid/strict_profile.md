---
version: "1.0.0"
profile: A
measurement_point: serving_pipeline_output
score_scope: null
systems:
  candidate:
    system_id: candidate
    profile_letter: A
    capabilities:
      text: verified
      scores: unavailable
      internals: unavailable
      candidate_scoring: unavailable
      controllable_decoding: unavailable
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
  synthetic_simulator_a:
    system_id: synthetic_simulator_a
    profile_letter: A
    capabilities:
      text: verified
      scores: unavailable
      internals: unavailable
      candidate_scoring: unavailable
      controllable_decoding: unavailable
    manifest_ref: capability_manifests/manifest_candidate.json
    verification_state: verified
    provider_transformations: []
  synthetic_simulator_b:
    system_id: synthetic_simulator_b
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
    permitted_actions: [observe_text_output]
  - role_id: operator_1
    role_type: operator
    person_id: bob
    permitted_actions: [export_checkpoint]
permitted_sources:
  - model_api
  - published_documentation
interventions: []
historical_access: []
handling_policies:
  non_identifiable: predeclared_reporting_rule_ni
  incomplete: predeclared_reporting_rule_inc
  confirmed_recovery: predeclared_reporting_rule_cr
  conformance: predeclared_reporting_rule_conf
evidence_mappings:
  missing_raw_score: incomplete
  known_control_label_alone: incomplete
  completed_without_witness: incomplete
budget_ref: attacks.yaml
blocking_decisions:
  - decision_id: D-13
    status: resolved
    resolution: "Accept provisional open until P0-5"
  - decision_id: D-14
    status: resolved
    resolution: "Accept provisional open until P0-5"
  - decision_id: D-27
    status: resolved
    resolution: "Accept provisional open until P0-6"
  - decision_id: D-28
    status: resolved
    resolution: "Accept provisional open until P0-6"
  - decision_id: D-29
    status: resolved
    resolution: "Accept provisional open until P0-7"
  - decision_id: D-31
    status: resolved
    resolution: "Accept provisional open until P0-7"
provenance_refs:
  - capability_manifests/manifest_candidate.json
  - capability_manifests/manifest_reference.json
claim_refs:
  - claim_templates/claim_template_a.json
identifiability_refs:
  - identifiability/justification_synthetic.json
---

# Strict Access Profile

## Observation Boundary

Text-only observation for all systems including synthetic simulators.

## Provenance Procedure

All manifests reviewed and current.

## Identifiability Argument

Constructive justification on synthetic simulator pair.

## Limitations

- Profile A output-simulation limitation applies
- Strict mode still requires P0-5/P0-6/P0-7 artifacts
