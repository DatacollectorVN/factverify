---
version: "0.1.0-draft"
status: "draft"
rubric:
  version: "0.1.0-draft"
  answer_roles: [object, subject, truth_value, set_membership]
  labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]
  refusal_flag_separate: true
raw_score_conventions: []
confirmation_routes:
  A:
    enabled: true
    budget_reservation_ref: null
    min_independent_families: 2
    clue_bearing_excluded: true
  B:
    enabled: false
    disabled_reason: "disabled for this fixture"
  C:
    enabled: false
    disabled_reason: "disabled for this fixture"
case_decision:
  no_witness_is_not_accept: true
aggregation_policy:
  primary_statistic: "whole_rule_calibrated_statistic"
  raw_maximum_role: "diagnostic_only"
  enabled_route_cost_refs: []
  calibrated_as_whole: true
annotation_protocol: {}
evidence_schema: {}
status_vocabulary_ref: "p0_4_handling_policies"
baseline_refs: {}
blocking_decisions: []
review_refs: []
---

# Invalid: enabled route without a reserved confirmation cost
