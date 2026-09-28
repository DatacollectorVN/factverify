---
version: "0.1.0-draft"
status: "draft"
rubric:
  version: "0.1.0-demo"
  answer_roles: [object, subject, truth_value, set_membership]
  labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]
  refusal_flag_separate: true
  many_valued_policy:
    mode: null
    decision_ref: "D-39"
raw_score_conventions: []
confirmation_routes:
  A:
    enabled: true
    min_independent_families: 2
    clue_bearing_excluded: true
  B:
    enabled: false
    disabled_reason: "Not available"
  C:
    enabled: false
    disabled_reason: "Not available"
case_decision:
  acceptance_requires:
    - excess_recovery_bounds_held
    - locality_bounds_held
  rejection_reasons: [locality_failure, confirmed_recovery]
  inconclusive_mapping: {wide_interval: incomplete, decision_refs: [D-14]}
  status_alignment: {ref: p0_4_handling_policies}
  no_witness_is_not_accept: true
aggregation_policy:
  primary_statistic: "raw_maximum"
  raw_maximum_role: "diagnostic_only"
  enabled_route_cost_refs: []
  calibrated_as_whole: true
annotation_protocol:
  sole_llm_oracle_forbidden: true
  outcome_driven_rubric_change_forbidden: true
evidence_schema:
  case_id: {type: string, required: true}
  fact_id: {type: string, required: true}
  model_hash: {type: string, required: true}
  contract_ref: {type: string, required: true}
  access_profile: {type: string, required: true}
  channel: {type: string, required: true}
  template_family_ids: {type: list, required: true}
  raw_response_ids: {type: list, required: true}
  scorer: {type: mapping, required: true}
  reference: {type: mapping, required: true}
  confirmation: {type: mapping, required: true}
  verdict: {type: mapping, required: true}
  ground_truth_separate: {type: bool, required: true}
status_vocabulary_ref: "p0_4_handling_policies"
baseline_refs: {answers: null, closures: null, attacks: null, access: null, margins: null}
blocking_decisions: []
review_refs: []
---

# Invalid: Raw Maximum as Primary Statistic

The `aggregation_policy.primary_statistic` is set to `raw_maximum`.
This is forbidden — raw maximum is diagnostic-only and must not be used as the primary statistic.
Expected to fail FV-SPEC-074.
