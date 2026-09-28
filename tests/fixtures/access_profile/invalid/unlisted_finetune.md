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
roles:
  - role_id: operator_1
    role_type: operator
    permitted_actions: [fine_tune]
permitted_sources: [model_api]
interventions:
  - action: fine_tune
    actor_role: operator_1
    approved_recipes: []
    artifact_lineage: lineage/ft.json
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

# Unlisted Fine-Tune (empty approved_recipes)
