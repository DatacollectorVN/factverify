---
version: "0.1.0-draft"
status: "unresolved_worksheet"
rubric:
  version: "0.1.0-draft"
  answer_roles: [object, subject, truth_value, set_membership]
  labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]
  refusal_flag_separate: true
  ambiguity_policy:
    mode: null
    decision_ref: "D-34"
  alias_policy:
    source: "p0_1_frozen_aliases"
    decision_ref: "D-39"
  normalization_policy:
    decision_ref: "D-40"
  many_valued_policy:
    mode: null
    decision_ref: "D-39"
raw_score_conventions:
  - channel_id: "text_output"
    statistic_kind: "sequence_logprob"
    normalization: null
    tokenizer_prefix_policy: null
    alias_aggregation: null
    candidate_universe: null
    tie_rule: null
    observation_point: null
    recovery_orientation: null
    insufficient_data_status: "unavailable"
    decision_refs: ["D-27", "D-32", "D-33"]
confirmation_routes:
  A:
    enabled: true
    family_grouping_policy_ref: "D-35"
    min_independent_families: 2
    discovery_vs_confirmation_roles:
      discovery: "first_family"
      confirmation: "second_family"
    repetitions:
      per_family: null
      decision_ref: "D-35"
    clue_bearing_excluded: true
    budget_reservation_ref: null
    aggregation_ref: null
  B:
    enabled: false
    disabled_reason: "Route B requires Profile B/C score access; D-36 open."
    seed_type: "training_or_update"
    budget_reservation_ref: null
    aggregation_ref: null
  C:
    enabled: false
    disabled_reason: "Route C requires checkpoint pairs; D-24/D-25/D-28 open."
    requires_parent_child_hashes: true
    post_transform_locality_required: true
    budget_reservation_ref: null
    aggregation_ref: null
case_decision:
  acceptance_requires:
    - excess_recovery_bounds_held
    - locality_bounds_held
    - access_completeness_conditions_met
    - no_disqualifying_confirmed_witness
  rejection_reasons:
    - confirmed_recovery
    - locality_failure
    - access_incomplete
    - non_identifiable
  inconclusive_mapping:
    wide_interval: incomplete
    decision_refs: ["D-14", "D-31"]
  status_alignment:
    ref: "p0_4_handling_policies"
  no_witness_is_not_accept: true
aggregation_policy:
  primary_statistic: "whole_rule_calibrated_statistic"
  raw_maximum_role: "diagnostic_only"
  enabled_route_cost_refs: []
  calibrated_as_whole: true
annotation_protocol:
  blinded_annotators: true
  system_identity_hidden: true
  double_annotation_subset_required: true
  adjudication_required: true
  sole_llm_oracle_forbidden: true
  outcome_driven_rubric_change_forbidden: true
  agreement_reporting: [confusion_table, raw_agreement, kappa]
  review_refs: []
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
baseline_refs:
  answers: null
  closures: null
  attacks: null
  access: null
  margins: null
blocking_decisions:
  - {decision_id: "D-09", status: "open"}
  - {decision_id: "D-14", status: "open"}
  - {decision_id: "D-24", status: "open"}
  - {decision_id: "D-35", status: "open"}
  - {decision_id: "D-39", status: "open"}
  - {decision_id: "D-40", status: "open"}
review_refs: []
---

# Valid Complete Unresolved Worksheet

This fixture is a well-formed witness_rule.md with all three layers separated,
Route A enabled as a skeleton with open D-* decision refs, and status: unresolved_worksheet.
It should pass FV-SPEC-067 layer-separation checks.
