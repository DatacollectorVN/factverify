---
version: "1.0.0"
profile: A
measurement_point: serving_pipeline_output
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
roles:
  - role_id: operator_1
    role_type: operator
    permitted_actions: [fine_tune]
permitted_sources: [model_api]
interventions:
  - action: fine_tune
    actor_role: operator_1
    approved_recipes: [recipes/ft.md]
    artifact_lineage: lineage/ft.json
    target_system: candidate
    requires_capabilities: [internals]
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

# Intervention Exceeds System Capabilities
