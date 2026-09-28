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
roles:
  - role_id: evaluator_1
    role_type: evaluator
    permitted_actions:
      - observe_text_output
  - role_id: operator_1
    role_type: operator
    permitted_actions:
      - export_checkpoint
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

# Access Profile: FactVerify Minimal Profile A

## Observation Boundary

Both the candidate and reference systems are observed at the serving pipeline
output only. Text responses are collected; no scores, logits, or internal
representations are accessible. Observations are post-decoding text strings.

## Provenance Procedure

Each system's measurement tap is at the API text output endpoint. No
intervening processors modify the text between model generation and
observation. Model and tokenizer identities are recorded in the capability
manifests referenced above. Evidence source is direct API testing.

## Limitations

- Profile A provides text-only observation; no score-based or internal
  analyses are possible.
- Runtime provenance verification (confirming live endpoint matches declared
  boundary) is out of scope for this offline validation.
- P0-5 margin thresholds, P0-6 witness rules, and P0-7 preregistration
  references are deferred.
