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
    internals_scope: unrestricted
    capabilities:
      text: verified
      scores: verified
      internals: verified
      candidate_scoring: verified
      controllable_decoding: verified
    manifest_ref: capability_manifests/manifest_candidate.json
    verification_state: partial
    provider_transformations: []
roles:
  - role_id: evaluator_1
    role_type: evaluator
    permitted_actions:
      - observe_text_output
permitted_sources:
  - model_api
handling_policies:
  non_identifiable: rule_ni
  incomplete: rule_inc
  confirmed_recovery: rule_cr
  conformance: rule_conf
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
provenance_refs: []
---

# Partial Internals Labelled Unrestricted
