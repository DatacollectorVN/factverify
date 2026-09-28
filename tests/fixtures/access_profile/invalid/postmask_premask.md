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
    provider_transformations:
      - log_prob_masking
      - top_k_filtering
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

# Post-mask scores labelled pre-mask

Provider applies log_prob_masking but score_scope.type says pre_mask.
