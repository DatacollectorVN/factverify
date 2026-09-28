# Decision Reference

Generated from `docs/decisions/catalog.yaml`.
Do not edit by hand — regenerate with `tools/generate_decision_ref.py`.

## access

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-27 | access.scores.scope | Score / logit / rank observation scope | open |
| D-28 | access.interventions.policy | Permitted interventions | open |
| D-29 | access.history.policy | Historical checkpoint / artifact access | open |
| D-31 | access.missing_measurements.policy | Missing or unavailable measurement handling | open |

## artifacts

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-53 | artifacts.determinism.digest_tolerance | Determinism policy and digest tolerance | open |

## cache

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-60 | cache.key.software_versions | Software versions in cache keys | open |

## closure

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-41 | closure.relations.coverage | Relation coverage | open |
| D-42 | _(collision/unresolved)_ | Milestone staged-rule completeness / closure-template group/split assignment | collision |
| D-43 | closure.relations.seat_of_government_ontology | Seat-of-government ontology treatment | open |

## controls

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-54 | controls.behaviour_matching.policy | Control retention gap and match band / selection policy | open |
| D-55 | controls.catalog.coverage | Required implementation count and severities per family | open |
| D-58 | controls.behaviour_matching.probes | Approved direct-QA matching probes | open |
| D-59 | controls.behaviour_matching.hard_dimensions | Extra hard-control dimensions and tolerances | open |
| D-61 | controls.catalog.untouched_model | Untouched model as negative family and mechanism layer | open |

## data

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-62 | data.tofu.extractor_configuration | Extractor model / prompt / settings specification | open |
| D-63 | data.facts.relation_vocabulary | Included relation types | closed |
| D-64 | data.facts.book_title_inverse_policy | Inverse-query policy for book_title | open |
| D-65 | data.exclusion_gate.policy | Knowledge-exclusion gate policy | open |
| D-66 | data.bundles.record_policy | Minimum records per direction and multi-fact rewrite / exclusion policy | open |
| D-67 | data.entailment_audit.policy | Entailment method, flag rule, and unflagged sample size | open |
| D-68 | data.splits.block_0_design | Block 0 split counts and balance | open |
| D-69 | data.leaveout.unit | Fact-level versus group-level leave-out unit | open |

## eval

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-17 | _(collision/unresolved)_ | Deviation categories completeness / total evaluator trial cap | collision |
| D-18 | eval.budget.candidate_score_unit | Candidate-scoring accounting unit | open |
| D-19 | eval.budget.reference_costs | Reference-model cost treatment | open |
| D-20 | eval.cache.charge_policy | Cache-hit / retry budget policy | open |
| D-21 | eval.budget.failed_request_policy | Retry, transport-failure, and failed-request charging | open |
| D-22 | _(collision/unresolved)_ | Amendment protocol fields / equal caps versus realized usage | collision |
| D-23 | eval.budget.samples_per_prompt | Samples per prompt | open |
| D-24 | eval.transforms.export_variant_treatment | Export / variant / reference treatment | open |
| D-25 | eval.relearning.exposure_policy | Relearning and target-exposure treatment | open |
| D-26 | eval.budget.confirmation_reallocation | Unused confirmation-budget reallocation | open |
| D-30 | _(collision/unresolved)_ | Not present in repository | absent |

## facts

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-38 | facts.locality.bucket_policy | Locality bucket vocabulary and minimum coverage | open |
| D-39 | facts.answers.alias_language_scope | Alias, language, and many-valued-answer scope | open |
| D-40 | facts.answers.normalization | Answer normalization policy | open |

## ledger

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-56 | ledger.checkpoints.tier_vocabulary | Allowed checkpoint tier values | open |

## model

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-46 | model.blocks_0_2.identity | Blocks 0–2 base-model identity | closed |
| D-47 | model.block_3.identity | Block 3 confirmation model | open |
| D-48 | model.runtime.precision_attention | Dtype, precision, and attention implementation | closed |
| D-49 | model.variant.base_or_instruct | Base versus instruction-tuned variant | closed |
| D-50 | model.adapters.evaluation_mode | Adapter evaluation versus merge policy | open |

## preregistration

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-44 | preregistration.archive.location | Preregistration archive location / status | pending |
| D-45 | preregistration.exposure_record.approval | Exposure-record status / sign-off | pending |

## reporting

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-16 | reporting.claim_label.policy | Claim-labelling policy | open |

## stats

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-01 | stats.error_rates.frr_cap | False-rejection-rate cap | open |
| D-02 | stats.error_rates.minimum_fcr_reduction | Minimum worthwhile absolute FCR reduction | open |
| D-03 | stats.uncertainty.confidence_error | Confidence error and bound procedure | open |
| D-04 | stats.practical_success.criterion | Practical-success rule | open |
| D-05 | stats.thresholds.selection_uncertainty | Threshold-selection uncertainty procedure | open |
| D-06 | stats.estimands.case_weights | Case-weight policy | open |
| D-07 | stats.resampling.design | Dependence structure and paired resampling design | open |
| D-08 | _(collision/unresolved)_ | Uncertainty seed types / multiplicity procedure | collision |
| D-09 | _(collision/unresolved)_ | Uncertainty family / FRR cap and spec-freeze blocker | collision |
| D-10 | stats.estimands.aggregation | Per-family and overall aggregation | open |
| D-11 | stats.relearning.tolerance | Relearning tolerance | open |
| D-12 | _(collision/unresolved)_ | Definition missing | unresolved |
| D-13 | stats.estimands.status_mapping | Missing/non-identifiable/incomplete status mapping | open |
| D-14 | stats.estimands.coverage | Coverage and outcome eligibility / denominator treatment | open |
| D-15 | stats.sample_size.power_method | Sample-size and power calculation method | open |
| D-57 | stats.bootstrap.interval_policy | Bootstrap interval type, replicate count, and coverage tolerance | open |

## training

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-51 | training.unlearning.hyperparameters | Per-method unlearning hyperparameters | open |
| D-52 | training.lora.configuration | Shared LoRA rank, alpha, dropout, and target modules | open |

## witness

| ID | Semantic key | Title | Status |
|----|--------------|-------|--------|
| D-32 | witness.raw_scores.normalization | Raw-score convention | open |
| D-33 | witness.raw_scores.candidate_policy | Candidate universe / ties / aggregation | open |
| D-34 | witness.scoring.ambiguity_policy | Ambiguous-response handling | open |
| D-35 | witness.route_a.independence | Family grouping, repetition, and Route-A independence | open |
| D-36 | witness.route_b.replication | Route-B eligible seeds and replication count | open |
| D-37 | witness.route_c.replication | Route-C confirmation / replication | open |
