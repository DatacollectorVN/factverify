---
version: "0.1.0-draft"
status: "draft"
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
  - channel_id: "token_rank_output"
    statistic_kind: "token_rank"
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
    family_grouping_policy_ref: "closure_templates.primary_family"
    allowed_family_ids: [direct, inverse, cloze, paraphrase, multilingual, verification]
    min_independent_families: 2
    discovery_vs_confirmation_roles:
      discovery: "first_family"
      confirmation: "second_family"
    repetitions:
      per_family: null
      decision_ref: "D-35"
    clue_bearing_excluded: true
    budget_reservation_ref: "confirm_equiv"
    aggregation_ref: "confirmation_reservations.confirm_equiv"
  B:
    enabled: false
    disabled_reason: "Route B requires Profile B/C score access; Profile A only currently. Decision D-36 open."
    score_statistic_ref: null
    eligible_prompts_ref: null
    margins_ref: null
    seed_type: "training_or_update"
    seed_count: null
    reproducibility_rule: null
    budget_reservation_ref: null
    aggregation_ref: null
  C:
    enabled: false
    disabled_reason: "Route C requires checkpoint pair access and training recipe; not yet available. D-24/D-25/D-28 open."
    criterion_ref: null
    requires_parent_child_hashes: true
    exposure_labelling:
      target_free: null
      target_exposed: null
    reference_transforms_required: true
    post_transform_locality_required: true
    replication_rule: null
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
    mapping:
      non_identifiable: non_identifiable
      incomplete: incomplete
      confirmed_recovery: confirmed_recovery
      accept: conformance
  no_witness_is_not_accept: true
aggregation_policy:
  primary_statistic: "whole_rule_calibrated_statistic"
  raw_maximum_role: "diagnostic_only"
  enabled_route_cost_refs: ["confirm_equiv"]
  calibrated_as_whole: true
annotation_protocol:
  blinded_annotators: true
  system_identity_hidden: true
  double_annotation_subset_required: true
  adjudication_required: true
  sole_llm_oracle_forbidden: true
  outcome_driven_rubric_change_forbidden: true
  agreement_reporting: [confusion_table, raw_agreement, kappa]
  illustrative_targets_not_adopted: true
  review_refs: ["reviews/rubric_review_v0.1.0.json"]
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
  answers: "fact_contract.schema.json"
  closures: "closure_templates.yaml"
  attacks: "attacks.yaml"
  access: "access_profile.md"
  margins: "margins.yaml"
blocking_decisions:
  - {decision_id: "D-09", status: "open"}
  - {decision_id: "D-11", status: "open"}
  - {decision_id: "D-12", status: "open"}
  - {decision_id: "D-14", status: "open"}
  - {decision_id: "D-24", status: "open"}
  - {decision_id: "D-25", status: "open"}
  - {decision_id: "D-27", status: "open"}
  - {decision_id: "D-28", status: "open"}
  - {decision_id: "D-31", status: "open"}
  - {decision_id: "D-32", status: "open"}
  - {decision_id: "D-33", status: "open"}
  - {decision_id: "D-34", status: "open"}
  - {decision_id: "D-35", status: "open"}
  - {decision_id: "D-36", status: "open"}
  - {decision_id: "D-37", status: "open"}
  - {decision_id: "D-39", status: "open"}
  - {decision_id: "D-40", status: "open"}
review_refs:
  - "reviews/rubric_review_v0.1.0.json"
---

# Witness Rule: P0-6 Confirmed-Witness Rule and Scorer

This artifact separates response scoring, witness confirmation, and case-level decisions.
It is built against named fields and decision IDs. Teaching examples are illustrative only.

## Layers

- **Layer 1 — Response Scoring**: Does this response recover the contracted relation in context?
- **Layer 2 — Witness Confirmation**: Is the evidence reproducible under an approved route?
- **Layer 3 — Case Decision**: Do recovery, locality, access, and completeness gates hold?
