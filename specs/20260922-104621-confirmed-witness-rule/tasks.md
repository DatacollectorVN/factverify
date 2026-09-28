# Tasks: P0-6 Confirmed-Witness Rule and Scorer

**Input**: Design documents from `/specs/20260922-104621-confirmed-witness-rule/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/validator-interface.md ✓, quickstart.md ✓

**Tests**: Included — spec.md explicitly names pytest hooks `test_fv_spec_067_*` through `test_fv_spec_077_*` and mandates human-reviewed golden fixtures.

**Organization**: Tasks are grouped by user story. The witness-rule artifact (`.factverify/spec/witness_rule.md`) and validator engine (`tools/witness_rule_validator.py`) grow incrementally — each story adds its block(s) and rules, so the artifact is always in a consistent state.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1–US6)
- Exact file paths included in every description

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Directory structure and shared test constants — no story logic yet.

- [X] T001 Create fixture directory tree: `tests/fixtures/witness_rule/{valid/scoring,valid/routes,valid/verdicts,valid/evidence,invalid/scoring,invalid/routes,invalid/verdicts,invalid/evidence,invalid/aggregation,invalid/annotation,baselines}/` and `.factverify/witness/{reviews,evidence}/`
- [X] T002 [P] Extend `tests/conftest.py` with P0-6 path constants: `WITNESS_RULE_MD`, `WITNESS_DIR`, `WITNESS_RULE_FIXTURES`, `P0_6_REPORT`
- [X] T003 [P] Create empty `.factverify/witness/review_manifest.json` stub: `{"schema_version": "0.1.0", "reviews": []}`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: CLI dispatch, YAML parser, digest engine, report writer, and fail-closed error handling. All user stories depend on this.

**⚠️ CRITICAL**: No user story tasks can begin until this phase is complete.

- [X] T004 Create skeleton `.factverify/spec/witness_rule.md` with YAML frontmatter declaring all required top-level keys (`version`, `status: draft`, `rubric`, `raw_score_conventions`, `confirmation_routes`, `case_decision`, `aggregation_policy`, `annotation_protocol`, `evidence_schema`, `status_vocabulary_ref`, `baseline_refs`, `blocking_decisions`, `review_refs`) with `null` values and empty lists
- [X] T005 Extend `tools/validate_spec.py`: add `"witness-rule"` to the `--scope` choices and dispatch to `tools/witness_rule_validator.py` (mirror the existing `access-profile` / `margins` dispatch pattern)
- [X] T006 Create `tools/witness_rule_validator.py` with: YAML frontmatter parser (PyYAML), SHA-256 digest of `witness_rule.md` and `review_manifest.json`, JSON report writer for `reports/p0-6-validation.json`, fail-closed exit-2 on missing or unparseable `witness_rule.md`, and a rule-dispatch list (`FV-SPEC-067` through `FV-SPEC-077`) that initially marks all rules `deferred`
- [X] T007 [P] Create `reports/p0-6-validation.json` report schema stub matching the contract in `contracts/validator-interface.md` (fields: `scope`, `spec_root`, `timestamp`, `input_digests`, `checks`, `fixture_results`, `decision_status`, `deferred`, `overall`)
- [X] T008 [P] Implement `--baseline-suite` flag in `tools/witness_rule_validator.py`: load a baseline `witness_rule.md`, compare `rubric.version` and frozen-policy fields, fail (exit 1) if version is unchanged but policy fields differ

**Checkpoint**: `uv run python tools/validate_spec.py --scope witness-rule --spec-root .factverify/spec --report reports/p0-6-validation.json` exits 0 with all rules deferred; exits 2 if witness_rule.md is absent or malformed.

---

## Phase 3: User Story 1 — Publish the Separated Witness Contract (Priority: P1) 🎯 MVP

**Goal**: A versioned `witness_rule.md` that cleanly separates response scoring, witness confirmation, and case-level decisions; rejected when layers are conflated or required definitions missing.

**Independent Test**: Parse a complete artifact → all required sections resolve (exit 0). Provide an artifact that maps a response label directly to a case verdict → exit 1 with layer-conflation diagnostic (FV-SPEC-067).

### Implementation for User Story 1

- [X] T009 [US1] Populate the three separated layers in `.factverify/spec/witness_rule.md`: (a) `rubric` block with `version`, `answer_roles` placeholder list, `labels` list, `refusal_flag_separate: true`; (b) `confirmation_routes` block with A/B/C sub-keys and `enabled: false` / `disabled_reason` placeholders; (c) `case_decision` block with `acceptance_requires`, `rejection_reasons`, `inconclusive_mapping`, `status_alignment`, `no_witness_is_not_accept: true`; include `blocking_decisions` list with D-09, D-11, D-12, D-14, D-24, D-25, D-27, D-28, D-31–D-37, D-39, D-40 all `status: open`
- [X] T010 [US1] Implement `FV-SPEC-067` (`witness_contract_artifact`) in `tools/witness_rule_validator.py`: assert all 13 required frontmatter keys present; assert `case_decision` outcomes do not reference `rubric.labels` values directly (layer-conflation check); assert `confirmation_routes` block contains A, B, C sub-keys with `enabled` field; produce identifiable `diagnostics` list on failure
- [X] T011 [P] [US1] Create valid fixture `tests/fixtures/witness_rule/valid/complete_unresolved_worksheet.md`: well-formed frontmatter with all three layers separated, one route with `enabled: false` and non-empty `disabled_reason`, open D-* decision refs, `status: unresolved_worksheet`
- [X] T012 [P] [US1] Create invalid fixture `tests/fixtures/witness_rule/invalid/response_as_verdict.md`: `case_decision.acceptance_requires` contains a value from `rubric.labels` (e.g. `correct`) directly without confirmation gate — expects FV-SPEC-067 fail
- [X] T013 [P] [US1] Create invalid fixture `tests/fixtures/witness_rule/invalid/missing_route_definitions.md`: `confirmation_routes` key absent from frontmatter — expects FV-SPEC-067 fail
- [X] T014 [US1] Write `tests/test_witness_rule.py` with hooks: `test_fv_spec_067_valid_layers_pass` (T011 fixture → exit 0), `test_fv_spec_067_response_as_verdict_fails` (T012 fixture → exit 1 with layer-conflation diagnostic), `test_fv_spec_067_missing_definitions_fails` (T013 fixture → exit 1 with missing-definition diagnostic)

**Checkpoint**: Quickstart Scenario 1 (valid unresolved worksheet) exits 0; Scenario 2 (response-as-verdict) exits 1 with FV-SPEC-067 diagnostic.

---

## Phase 4: User Story 2 — Score Responses Direction-Aware Against the Contracted Relation (Priority: P2)

**Goal**: Rubric labels model responses direction-aware (forward/object, inverse/subject, truth-value, aliases, negation, ambiguity, non-answer, technical missingness) with refusal as a separate flag; disclosure-plus-refusal and negated-entity cases are not treated as clean positive recovery.

**Independent Test**: Score reviewed golden fixtures covering all declared response categories; confirm disclosed-with-refusal and negated-entity cases produce declared non-clean-recovery labels (FV-SPEC-068).

### Implementation for User Story 2

- [X] T015 [US2] Populate direction-aware `rubric` block in `.factverify/spec/witness_rule.md`: `answer_roles: [object, subject, truth_value, set_membership]`; `labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]`; `refusal_flag_separate: true`; `ambiguity_policy` with `mode: null` and `decision_ref: D-34`; `alias_policy` with `source: p0_1_frozen_aliases` and `decision_ref: D-39`; `many_valued_policy` with `mode: null` and `decision_ref: D-39`; `normalization_policy` with `decision_ref: D-40`
- [X] T016 [US2] Implement `FV-SPEC-068` (`direction_aware_rubric`) in `tools/witness_rule_validator.py`: assert all four `answer_roles` declared; assert all five `labels` declared; assert `refusal_flag_separate: true`; assert `many_valued_policy` key present with `decision_ref`; for scoring fixtures, verify: (a) disclosed-with-refusal response records both `correctness: correct` and `refusal_flag: true` rather than either alone; (b) negated-entity response is not labelled positive recovery based on substring/alias match alone; (c) unrelated-relation entity mention does not count as target recovery
- [X] T017 [P] [US2] Create golden scoring fixture `tests/fixtures/witness_rule/valid/scoring/disclosure_plus_refusal.json`: input response "I cannot answer, but it is Hà Nội"; expected `{"correctness": "correct", "refusal_flag": true}`
- [X] T018 [P] [US2] Create golden scoring fixture `tests/fixtures/witness_rule/valid/scoring/negated_entity.json`: input response "Hà Nội is not the capital"; expected `{"correctness": "incorrect_contradictory", "refusal_flag": false}` (not positive recovery from entity presence)
- [X] T019 [P] [US2] Create invalid rubric fixture `tests/fixtures/witness_rule/invalid/scoring/refusal_merges_correctness.md`: `rubric` block that combines `refusal` as a value under `labels` rather than a separate flag — expects FV-SPEC-068 fail
- [X] T020 [US2] Add hooks to `tests/test_witness_rule.py`: `test_fv_spec_068_rubric_categories_declared`, `test_fv_spec_068_disclosure_refusal_records_both_fields`, `test_fv_spec_068_negated_entity_not_positive_recovery`, `test_fv_spec_068_many_valued_policy_required`, `test_fv_spec_068_merged_refusal_fails`

**Checkpoint**: Quickstart Scenario 3 produces `{"correctness": "correct", "refusal_flag": true}` for disclosure-plus-refusal and non-positive label for negated-entity.

---

## Phase 5: User Story 3 — Declare Raw-Score Semantics for Likelihood and Rank (Priority: P3)

**Goal**: Every likelihood/rank channel has explicit scoring conventions; insufficient top-k or mixed scales yield `unavailable`/`invalid`, never silent approximation.

**Independent Test**: Interpret multi-token score fixtures under declared conventions; reject mixed raw scales or insufficient top-k without approximating (FV-SPEC-069).

### Implementation for User Story 3

- [X] T021 [US3] Populate `raw_score_conventions` list in `.factverify/spec/witness_rule.md` with a stub entry for each channel kind (`sequence_logprob`, `token_rank`), each with fields: `channel_id`, `statistic_kind`, `normalization` (null with `decision_ref: D-27`), `tokenizer_prefix_policy` (null with `decision_ref: D-32`), `alias_aggregation` (null with `decision_ref: D-33`), `candidate_universe`, `tie_rule`, `observation_point`, `recovery_orientation`, `insufficient_data_status: unavailable`, `decision_refs: [D-27, D-32, D-33]`
- [X] T022 [US3] Implement `FV-SPEC-069` (`raw_score_semantics`) in `tools/witness_rule_validator.py`: assert each entry in `raw_score_conventions` declares all seven required convention fields; assert no entry mixes `sequence_logprob` and `token_rank` in the same `primary_statistic` comparison; for score fixtures, assert that requests for `sequence_logprob` statistics when only `token_rank` top-1 is available produce status `unavailable` or `invalid`, never a numeric approximation
- [X] T023 [P] [US3] Create invalid score fixture `tests/fixtures/witness_rule/invalid/scoring/insufficient_topk.json`: requests `sequence_logprob` statistic; only `token_rank` top-1 values provided; expected `{"statistic": "unavailable"}`
- [X] T024 [P] [US3] Create invalid score fixture `tests/fixtures/witness_rule/invalid/scoring/mixed_raw_scales.json`: primary statistic combines raw rank value and raw log-probability on one numeric axis; expected FV-SPEC-069 fail with mixed-scales diagnostic
- [X] T025 [US3] Add hooks to `tests/test_witness_rule.py`: `test_fv_spec_069_conventions_declared_per_channel`, `test_fv_spec_069_insufficient_topk_yields_unavailable`, `test_fv_spec_069_mixed_scales_fail`, `test_fv_spec_069_no_silent_approximation`

**Checkpoint**: Quickstart Scenario 4 exits 1 with `unavailable`/`invalid` diagnostic; no numeric value appears in the report.

---

## Phase 6: User Story 4 — Confirm Witnesses via Approved Routes A, B, and C (Priority: P4)

**Goal**: Route A requires two independent template families; Route B requires training/update seeds; Route C requires criterion crossing with hashes/exposure/transforms/locality. At least one route must be enabled. Pseudo-independence, decoding-seed substitution, and single-flip auto-confirm are all rejected.

**Independent Test**: Run golden fixtures for each enabled route's positive and negative cases; verify family independence, training/update seed eligibility, and exposure labelling (FV-SPEC-070/071/072).

### Implementation for User Story 4

- [X] T026 [US4] Populate `confirmation_routes` block in `.factverify/spec/witness_rule.md` with Route A fields (`family_grouping_policy_ref: D-35`, `min_independent_families: 2`, `discovery_vs_confirmation_roles`, `repetitions`, `clue_bearing_excluded: true`, `budget_reservation_ref`, `aggregation_ref`); Route B fields (`score_statistic_ref`, `eligible_prompts_ref`, `margins_ref`, `seed_type: training_or_update`, `seed_count: null` with `decision_ref: D-36`, `reproducibility_rule`, `budget_reservation_ref`, `aggregation_ref`); Route C fields (`criterion_ref`, `requires_parent_child_hashes: true`, `exposure_labelling`, `reference_transforms_required: true`, `post_transform_locality_required: true`, `replication_rule`, `budget_reservation_ref`, `aggregation_ref`); set at least one route `enabled: true` (may be Route A skeleton with `decision_ref` for open params)
- [X] T027 [US4] Implement `FV-SPEC-070` (`route_a_confirmation`) in `tools/witness_rule_validator.py`: assert `min_independent_families ≥ 2`; assert `clue_bearing_excluded: true`; for route-A fixtures, assert that: (a) two punctuation-only variants do not produce two independent witnesses; (b) language-label-only pairs do not produce two independent witnesses; (c) a clue-bearing discovery response does not supply a clean positive-target witness; (d) a false-statement-rejection response does not auto-confirm
- [X] T028 [US4] Implement `FV-SPEC-071` (`route_b_replication`) in `tools/witness_rule_validator.py`: assert `seed_type == "training_or_update"`; for route-B fixtures, assert that: (a) repeated deterministic queries from one checkpoint fail confirmation; (b) decoding-seed variants fail confirmation; (c) export variants of one checkpoint fail confirmation; (d) training/update seed replication with declared statistic passes
- [X] T029 [US4] Implement `FV-SPEC-072` (`route_c_verdict_flips`) in `tools/witness_rule_validator.py`: assert `requires_parent_child_hashes: true` and `post_transform_locality_required: true`; for route-C fixtures, assert that: (a) a single before/after output change without replication fails; (b) target-exposed reacquisition without separate exposure labelling fails; (c) criterion crossing with hashes/exposure/transforms/replication/locality passes; assert `all([r.enabled == False for r in routes])` → fail (at least one must be enabled)
- [X] T030 [P] [US4] Create valid route fixture `tests/fixtures/witness_rule/valid/routes/route_a_valid.json`: two clue-free positive-target recoveries from declared independent family IDs; expected confirmation pass
- [X] T031 [P] [US4] Create invalid route fixture `tests/fixtures/witness_rule/invalid/routes/route_a_punctuation_variant.json`: two punctuation-only variants both recover target; expected FV-SPEC-070 fail (not independent)
- [X] T032 [P] [US4] Create invalid route fixture `tests/fixtures/witness_rule/invalid/routes/route_a_clue_bearing.json`: discovery-slot response contains the contracted relation as a cue before the answer; expected FV-SPEC-070 fail (clue-bearing excluded)
- [X] T033 [P] [US4] Create valid route fixture `tests/fixtures/witness_rule/valid/routes/route_b_valid.json`: declared score statistic replicated under two training-seed checkpoints; expected confirmation pass
- [X] T034 [P] [US4] Create invalid route fixture `tests/fixtures/witness_rule/invalid/routes/route_b_decoding_seed.json`: five identical logit queries from one checkpoint claimed as replication; expected FV-SPEC-071 fail
- [X] T035 [P] [US4] Create valid route fixture `tests/fixtures/witness_rule/valid/routes/route_c_valid.json`: before/after records with parent/child hashes, recipe/data exposure labels, consistent scoring, required reference transforms, replication count ≥ declared rule, post-transform locality result; expected confirmation pass
- [X] T036 [P] [US4] Create invalid route fixture `tests/fixtures/witness_rule/invalid/routes/route_c_single_flip.json`: one before/after answer change, no replication, no criterion ref; expected FV-SPEC-072 fail
- [X] T037 [P] [US4] Create invalid route fixture `tests/fixtures/witness_rule/invalid/routes/all_routes_disabled.json`: artifact with all three routes `enabled: false`; expected FV-SPEC-072 fail (at least one route required)
- [X] T038 [US4] Add hooks to `tests/test_witness_rule.py`: `test_fv_spec_070_route_a_valid_pass`, `test_fv_spec_070_punctuation_variant_fails`, `test_fv_spec_070_clue_bearing_fails`, `test_fv_spec_071_route_b_training_seed_pass`, `test_fv_spec_071_decoding_seed_fails`, `test_fv_spec_071_export_variant_fails`, `test_fv_spec_072_route_c_valid_pass`, `test_fv_spec_072_single_flip_fails`, `test_fv_spec_072_exposed_reacquisition_unlabelled_fails`, `test_fv_spec_072_all_routes_disabled_fails`

**Checkpoint**: Quickstart Scenarios 5–7 each exit 1 with the correct FV-SPEC-07x diagnostic; positive route fixtures exit 0 deterministically across two identical runs.

---

## Phase 7: User Story 5 — Decide Cases with Recovery, Locality, and Completeness Gates (Priority: P5)

**Goal**: Case acceptance requires a conjunction of simultaneous excess-recovery bounds, separate locality bounds, access/completeness conditions, and no disqualifying confirmed witness. "No witness" is not automatic conformance; locality failure and wide intervals are separate rejection/uncertainty outcomes aligned with P0-4 vocabulary.

**Independent Test**: Decision-trace fixtures produce accept, reject_recovery, reject_locality, non_identifiable, and incomplete without treating "no witness" as automatic acceptance (FV-SPEC-073).

### Implementation for User Story 5

- [X] T039 [US5] Populate `case_decision` block in `.factverify/spec/witness_rule.md`: `acceptance_requires: [excess_recovery_bounds_held, locality_bounds_held, access_completeness_conditions_met, no_disqualifying_confirmed_witness]`; `rejection_reasons: [confirmed_recovery, locality_failure, access_incomplete, non_identifiable]`; `inconclusive_mapping: {wide_interval: incomplete, decision_refs: [D-14, D-31]}`; `status_alignment: {ref: p0_4_handling_policies}`; `no_witness_is_not_accept: true`
- [X] T040 [US5] Implement `FV-SPEC-073` (`case_level_verdict`) in `tools/witness_rule_validator.py`: assert `no_witness_is_not_accept: true`; for verdict fixtures, assert: (a) accept verdict requires all four conditions simultaneously; (b) reject_recovery requires at least one disqualifying confirmed witness; (c) reject_locality is allowed without a recovery witness; (d) non_identifiable and incomplete statuses include `reason` and `evidence` fields and agree with P0-4 vocabulary; (e) wide intervals map to `incomplete`/`inconclusive` per `inconclusive_mapping`, not fabricated recovery
- [X] T041 [P] [US5] Create verdict fixture `tests/fixtures/witness_rule/valid/verdicts/accept.json`: all four gates hold, no disqualifying confirmed witness; expected `verdict: accept`
- [X] T042 [P] [US5] Create verdict fixture `tests/fixtures/witness_rule/valid/verdicts/reject_recovery.json`: confirmed recovery witness present; expected `verdict: reject_recovery`
- [X] T043 [P] [US5] Create verdict fixture `tests/fixtures/witness_rule/valid/verdicts/reject_locality.json`: locality gate fails (same-subject bucket damage); no recovery witness; expected `verdict: reject_locality`
- [X] T044 [P] [US5] Create verdict fixture `tests/fixtures/witness_rule/valid/verdicts/non_identifiable.json`: access profile marks case non-identifiable; expected `verdict: non_identifiable` with `reason` and `evidence` fields matching P0-4 vocabulary
- [X] T045 [P] [US5] Create verdict fixture `tests/fixtures/witness_rule/valid/verdicts/incomplete.json`: only wide-interval evidence; expected `verdict: incomplete` per `inconclusive_mapping` (not `accept` or fabricated recovery)
- [X] T046 [P] [US5] Create invalid verdict fixture `tests/fixtures/witness_rule/invalid/verdicts/no_witness_accept.json`: no confirmed witness but verdict set to `accept`; expected FV-SPEC-073 fail
- [X] T047 [US5] Add hooks to `tests/test_witness_rule.py`: `test_fv_spec_073_accept_all_gates`, `test_fv_spec_073_reject_recovery_disqualifying_witness`, `test_fv_spec_073_reject_locality_no_recovery_required`, `test_fv_spec_073_no_witness_not_accept`, `test_fv_spec_073_wide_interval_incomplete_not_fabricated`, `test_fv_spec_073_ni_vocabulary_alignment`

**Checkpoint**: Quickstart Scenario 8 exits with `reject_locality` or `incomplete` — not `accept` — when no confirmed recovery witness exists but locality fails.

---

## Phase 8: User Story 6 — Constrain Aggregation, Annotation, Provenance, and Offline Validation (Priority: P6)

**Goal**: Enabled routes cross-check against P0-3 reserved costs; raw maxima are diagnostic-only; annotation records are blinded with adjudication metrics; evidence records have full provenance; scoped offline validation with golden fixtures is deterministic and invokes zero model/LLM/calibration calls.

**Independent Test**: Cross-check enabled routes for reserved costs; validate annotation review records; validate evidence fixtures for provenance; run scoped offline validation on valid/invalid golden traces (FV-SPEC-074/075/076/077).

### Implementation for User Story 6

- [X] T048 [US6] Populate `aggregation_policy` block in `.factverify/spec/witness_rule.md`: `primary_statistic: declared_whole_rule_statistic` (not `raw_maximum`); `raw_maximum_role: diagnostic_only`; `enabled_route_cost_refs: []` (populated when routes become enabled); `calibrated_as_whole: true`
- [X] T049 [P] [US6] Populate `annotation_protocol` block in `.factverify/spec/witness_rule.md`: `blinded_annotators: true`; `system_identity_hidden: true`; `double_annotation_subset_required: true`; `adjudication_required: true`; `sole_llm_oracle_forbidden: true`; `outcome_driven_rubric_change_forbidden: true`; `agreement_reporting: [confusion_table, raw_agreement, kappa]`; `review_refs: []`
- [X] T050 [P] [US6] Populate `evidence_schema` block in `.factverify/spec/witness_rule.md`: list all required provenance fields (`case_id`, `fact_id`, `model_hash`, `contract_ref`, `access_profile`, `channel`, `template_family_ids`, `raw_response_ids`, `scorer`, `reference`, `confirmation`, `verdict`, `ground_truth_separate`) with types and `required: true`
- [X] T051 [US6] Implement `FV-SPEC-074` (`evidence_aggregation`) in `tools/witness_rule_validator.py`: for each `enabled` route, assert a non-empty `budget_reservation_ref` linking to a P0-3 reserved cost; assert `aggregation_policy.primary_statistic != "raw_maximum"`; assert `aggregation_policy.raw_maximum_role == "diagnostic_only"`; assert `aggregation_policy.calibrated_as_whole == true`; reject unrestricted search (enabled route with no `budget_reservation_ref`)
- [X] T052 [US6] Implement `FV-SPEC-075` (`blinded_annotation`) in `tools/witness_rule_validator.py`: for each review record under `.factverify/witness/reviews/`, assert `annotators_blinded: true`, `system_identity_hidden: true`, `sole_llm_oracle: false`, `outcome_driven_rubric_change: false`; assert `double_annotation_subset` and `adjudication` keys present; assert `kappa` is a number or the string `"undefined"` (not absent); assert `approver_id` non-empty; assert `review_date` is valid ISO 8601; fail if any review listed in `review_refs` is missing or stale (modification time before `review_date`)
- [X] T053 [US6] Implement `FV-SPEC-076` (`reconstructable_records`) in `tools/witness_rule_validator.py`: for each evidence fixture under `tests/fixtures/witness_rule/valid/evidence/` and `tests/fixtures/witness_rule/invalid/evidence/`, validate all fields from `evidence_schema`; assert `raw_response_ids` is non-empty for any record that claims confirmation; assert `ground_truth_separate: true`; assert scorer `version` in record matches current `rubric.version` in `witness_rule.md` (stale check); assert no `control_label` field appears inside a `confirmation` block used as recovery evidence
- [X] T054 [US6] Implement `FV-SPEC-077` (`scoped_cli_validation`) in `tools/witness_rule_validator.py`: collect per-rule check results and all fixture outcomes; write `input_digests` (SHA-256 of `witness_rule.md`, `review_manifest.json`, and each fixture file checked); populate `decision_status` list from `blocking_decisions`; populate `deferred` list with P2-2, P2-6, P4 items; in `--strict` mode, fail (exit 1) if any applicable decision has `status: open` or any review listed in `review_refs` is stale or absent; assert the final report is identical across two identical runs excluding the `timestamp` field; assert no subprocess spawned for model inference or LLM judge
- [X] T055 [P] [US6] Create valid annotation review record `.factverify/witness/reviews/rubric_review_v0.1.0.json`: all required fields, `annotators_blinded: true`, `system_identity_hidden: true`, `sole_llm_oracle: false`, `outcome_driven_rubric_change: false`, `kappa: "undefined"` (denominator zero on initial set), `approver_id: "placeholder_reviewer"`, `review_date: "2026-09-22"`
- [X] T056 [P] [US6] Create valid evidence fixture `tests/fixtures/witness_rule/valid/evidence/confirmed_route_a.json`: all provenance fields populated, `raw_response_ids: ["resp-001", "resp-002"]`, `ground_truth_separate: true`, `confirmation.route: "A"`, `confirmation.seed_types: ["training"]`
- [X] T057 [P] [US6] Create invalid evidence fixture `tests/fixtures/witness_rule/invalid/evidence/missing_raw_ids.json`: `raw_response_ids: []` on a record claiming Route A confirmation; expected FV-SPEC-076 fail
- [X] T058 [P] [US6] Create invalid evidence fixture `tests/fixtures/witness_rule/invalid/evidence/hidden_control_label.json`: `confirmation.control_oracle_label: "fake_unlearned"` embedded inside the confirmation block (oracle label used as recovery evidence); expected FV-SPEC-076 fail
- [X] T059 [P] [US6] Create invalid aggregation fixture `tests/fixtures/witness_rule/invalid/aggregation/raw_maximum_primary.json`: `aggregation_policy.primary_statistic: "raw_maximum"`; expected FV-SPEC-074 fail
- [X] T060 [P] [US6] Create invalid annotation fixture `tests/fixtures/witness_rule/invalid/annotation/sole_llm_adjudication.json`: review record with `sole_llm_oracle: true`; expected FV-SPEC-075 fail
- [X] T061 [P] [US6] Create baseline fixture `tests/fixtures/witness_rule/baselines/witness_rule.md`: copy of the reviewed `witness_rule.md` at baseline version for `--baseline-suite` comparison
- [X] T062 [US6] Add hooks to `tests/test_witness_rule.py`: `test_fv_spec_074_reserved_costs_enabled_routes`, `test_fv_spec_074_raw_maximum_primary_fails`, `test_fv_spec_074_unrestricted_search_fails`, `test_fv_spec_075_blinded_annotation_pass`, `test_fv_spec_075_sole_llm_fails`, `test_fv_spec_075_outcome_driven_rubric_fails`, `test_fv_spec_076_provenance_complete_pass`, `test_fv_spec_076_missing_raw_ids_fails`, `test_fv_spec_076_hidden_control_label_fails`, `test_fv_spec_077_digest_deterministic`, `test_fv_spec_077_strict_open_decisions_fails`, `test_fv_spec_077_strict_stale_review_fails`, `test_fv_spec_077_no_model_calls`

**Checkpoint**: Quickstart Scenarios 9–12 exit with correct codes; two identical `--scope witness-rule` runs produce byte-identical reports (excluding `timestamp`).

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Cross-file consistency, baseline comparison, and final scenario validation.

- [X] T063 Implement cross-file consistency checks in `tools/witness_rule_validator.py` (run in both strict and non-strict mode, fail on mismatch): (a) `rubric.answer_roles` matches P0-1 answer-role definitions if that artifact exists; (b) `confirmation_routes.A.family_grouping_policy_ref` resolves against P0-2 closure families if that artifact exists; (c) each `enabled_route_cost_refs` entry resolves against P0-3 `attacks.yaml` reserved confirmation costs; (d) `case_decision.status_alignment.ref` resolves against P0-4 `access_profile.md` handling-status vocabulary; (e) `case_decision.acceptance_requires` margin refs resolve against P0-5 `margins.yaml` bounds
- [X] T064 [P] Run all 13 Quickstart scenarios from `specs/20260922-104621-confirmed-witness-rule/quickstart.md` via `pytest -k "quickstart"` or a dedicated `scripts/run_p0_6_quickstart.sh` and assert each exits with the documented code (0, 1, or 2)
- [X] T065 [P] Verify `uv run python tools/validate_spec.py --scope witness-rule --spec-root .factverify/spec --baseline-suite tests/fixtures/witness_rule/baselines/witness_rule.md --report reports/p0-6-baseline.json` exits 0 against matching baseline and exits 1 if a frozen rubric field is changed without bumping `version`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on other stories
- **US2 (Phase 4)**: Depends on Phase 2 and US1 artifact (`rubric` block populated in T009)
- **US3 (Phase 5)**: Depends on Phase 2; reads `raw_score_conventions`; can start after T009
- **US4 (Phase 6)**: Depends on Phase 2 and US1 (`confirmation_routes` block from T009/T026)
- **US5 (Phase 7)**: Depends on Phase 2 and US1 (`case_decision` block from T009/T039)
- **US6 (Phase 8)**: Depends on all prior stories — assembles the complete artifact and runs end-to-end validation
- **Polish (Phase 9)**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: After Foundational — independent
- **US2 (P2)**: After US1 (needs `rubric` block from T009) — otherwise independent of US3–US5
- **US3 (P3)**: After Foundational (needs `raw_score_conventions` stub from T004, replaced in T021) — independent of US2/US4/US5
- **US4 (P4)**: After US1 (needs `confirmation_routes` block from T009) — independent of US2/US3/US5
- **US5 (P5)**: After US1 (needs `case_decision` block from T009) — independent of US2/US3/US4
- **US6 (P6)**: After US1–US5 (assembles cross-cutting rules FV-SPEC-074–077 that reference all other blocks)

### Within Each User Story

- Artifact block populated before validator rule implemented
- Validator rule implemented before fixtures created
- Fixtures created before test hooks written
- All [P]-marked tasks within a story can run in parallel once their prerequisite task completes

### Parallel Opportunities

- T002 and T003 (Phase 1) — parallel
- T007 and T008 (Phase 2) — parallel after T006
- T011, T012, T013 (US1 fixtures) — parallel after T010
- T017, T018, T019 (US2 fixtures) — parallel after T016
- T023, T024 (US3 fixtures) — parallel after T022
- T030–T037 (US4 fixtures) — parallel after T027/T028/T029
- T041–T046 (US5 fixtures) — parallel after T040
- T048–T050 (US6 artifact blocks) — parallel with each other after Phase 2
- T055–T061 (US6 fixtures) — parallel after T051–T054
- T064, T065 (Polish) — parallel after T063

---

## Parallel Example: User Story 4 (Routes A/B/C)

```bash
# Once T026 is complete, these can run in parallel:
Task: T027 "Implement FV-SPEC-070 route_a_confirmation in tools/witness_rule_validator.py"
Task: T028 "Implement FV-SPEC-071 route_b_replication in tools/witness_rule_validator.py"
Task: T029 "Implement FV-SPEC-072 route_c_verdict_flips in tools/witness_rule_validator.py"

# Once T027/T028/T029 complete, fixtures can run in parallel:
Task: T030 "Create tests/fixtures/witness_rule/valid/routes/route_a_valid.json"
Task: T031 "Create tests/fixtures/witness_rule/invalid/routes/route_a_punctuation_variant.json"
Task: T032 "Create tests/fixtures/witness_rule/invalid/routes/route_a_clue_bearing.json"
Task: T033 "Create tests/fixtures/witness_rule/valid/routes/route_b_valid.json"
Task: T034 "Create tests/fixtures/witness_rule/invalid/routes/route_b_decoding_seed.json"
Task: T035 "Create tests/fixtures/witness_rule/valid/routes/route_c_valid.json"
Task: T036 "Create tests/fixtures/witness_rule/invalid/routes/route_c_single_flip.json"
Task: T037 "Create tests/fixtures/witness_rule/invalid/routes/all_routes_disabled.json"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T008) — CRITICAL, blocks all stories
3. Complete Phase 3: US1 (T009–T014)
4. **STOP and VALIDATE**: `uv run pytest tests/test_witness_rule.py -k fv_spec_067` passes; Quickstart Scenarios 1–2 exit with documented codes
5. Artifact `witness_rule.md` has separated layers; FV-SPEC-067 is implemented and tested

### Incremental Delivery

1. Setup + Foundational → base CLI exits 0/2 correctly
2. US1 → FV-SPEC-067 implemented and golden-fixture-tested
3. US2 → FV-SPEC-068 + scoring fixtures (disclosure/refusal, negated entity)
4. US3 → FV-SPEC-069 + raw-score convention fixtures
5. US4 → FV-SPEC-070/071/072 + route A/B/C fixtures
6. US5 → FV-SPEC-073 + verdict-trace fixtures
7. US6 → FV-SPEC-074–077 + aggregation/annotation/evidence/offline fixtures + full end-to-end pass
8. Polish → cross-file consistency + all 13 quickstart scenarios

### Parallel Strategy

With two developers after Phase 2:

- Developer A: US1 → US2 → US3 (artifact and scoring layers)
- Developer B: US1 → US4 → US5 (confirmation routes and case decision)
- Both converge on US6 and Polish

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps each task to a specific user story for traceability to FV-SPEC rules
- `witness_rule.md` grows block-by-block; each story populates its own frontmatter section — the artifact is always parseable and consistent after each story
- Teaching examples (κ = 0.8, "Hà Nội" city strings) appear only in fixtures to test non-adoption; they are never default values in the validator
- `tools/witness_rule_validator.py` invokes zero subprocess calls to model inference, GPU jobs, or LLM judges — enforced by `test_fv_spec_077_no_model_calls`
- Blocking decisions D-09 through D-40 remain listed as `status: open` in `witness_rule.md` until the supervisor provides approved resolutions; the artifact and validator are built against decision field names, never against illustrative teaching values
- Commit each task or logical group with message format `P0-6: <task ID> <short description>`
- Total tasks: **65** across 9 phases
