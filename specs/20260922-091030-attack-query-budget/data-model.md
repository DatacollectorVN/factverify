# Data Model: P0-3 Attack Family and Per-Channel Query Budget

**Feature**: `20260922-091030-attack-query-budget`
**Date**: 2026-09-22

## Core Entities

### AttackSpecification (YAML document)

The root entity. Single file at `.factverify/spec/attacks.yaml`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_version` | string | yes | Version of the attack specification format |
| `revision` | string | yes | Spec revision identifier |
| `content_digest` | string | no | SHA-256 of canonical content |
| `upstream_refs` | UpstreamRefs | yes | References to consumed P0-1/P0-2/P0-4/P0-5/P0-6 artifacts |
| `common_cap` | integer (positive) | yes | Per-case generation trial cap shared by all arms |
| `accounting` | AccountingRules | yes | Charging policies and unit definitions |
| `arms` | ArmAllocation[3] | yes | Exactly three evaluator arm allocations |
| `channels` | ChannelSpec[] | yes | Permitted attack channels |
| `adaptive_policies` | AdaptivePolicy[] | no | Finite execution policies for adaptive channels |
| `confirmation_reservations` | ConfirmationReservation[] | no | Budget reservations for witness-rule routes |
| `transformations` | TransformationRecipe[] | no | Recipes for enabled export/activation interventions |
| `relearning` | RelearningSpec | no | Relearning condition specifications |
| `blocking_decisions` | DecisionRef[] | yes | D-17 through D-29, D-31 resolution status |

### UpstreamRefs

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `fact_contract_schema` | string | yes | Path to P0-1 schema |
| `closure_templates` | string | yes | Path to P0-2 closure suite |
| `access_profile` | string | yes | Path to P0-4 access profile |
| `witness_rule` | string | no | Path to P0-6 witness rule (deferred if not yet available) |
| `margins` | string | no | Path to P0-5 margins (deferred if not yet available) |

### AccountingRules

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generation_trial_unit` | UnitDefinition | yes | What constitutes one generation trial |
| `candidate_scoring_unit` | UnitDefinition | yes | What constitutes one candidate-score operation |
| `cost_vector_fields` | string[] | yes | Required cost dimensions: tokens, scored_candidates, training_steps, exports, wall_clock |
| `cache_policy` | EventPolicy | yes | How cache hits are charged |
| `retry_policy` | EventPolicy | yes | How retries are charged |
| `failure_policy` | EventPolicy | yes | How transport failures are charged |
| `discard_policy` | EventPolicy | yes | How discarded responses are charged |
| `reference_cost_policy` | EventPolicy | yes | How reference-model evaluations are charged |

### UnitDefinition

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | string | yes | Unit name (e.g., "generation_trial", "candidate_score") |
| `definition` | string | yes | Precise definition of what constitutes one unit |
| `multiplicity_rule` | string | yes | How batched/multi-completion requests map to units |
| `identity_fields` | string[] | yes | Fields that distinguish one unit from another (prompt, checkpoint, sample, decoding) |

### EventPolicy

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `policy_id` | string | yes | Stable policy identifier |
| `charge_rule` | enum: charged, zero_new_compute, separately_reported, not_charged | yes | How this event type is accounted |
| `observation_charged` | boolean | yes | Whether the observation itself counts toward budget |
| `distinction` | string | yes | How this is distinguished from other event types |
| `decision_ref` | string | no | Blocking decision ID if unresolved (e.g., "D-19") |

### ArmAllocation

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `arm_id` | enum: native, semantic_only, factverify | yes | Evaluator identity |
| `total` | integer (nonneg) | yes | Total generation trials for this arm; must equal common_cap |
| `channel_allocations` | ChannelAllocation[] | yes | Per-channel breakdown |
| `cost_vector` | CostVector | no | Realized or estimated cost breakdown |

**Constraint**: For each arm, `sum(channel_allocations[*].trials) == total == common_cap`.

### ChannelAllocation

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `channel_id` | string | yes | References a ChannelSpec.id |
| `trials` | integer (nonneg) | yes | Generation trials allocated to this channel for this arm |
| `purpose` | string | yes | Scientific purpose of this allocation |

**Constraint**: A disabled channel cannot have `trials > 0`.

### CostVector

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input_tokens` | integer | no | Total input tokens |
| `output_tokens` | integer | no | Total output tokens |
| `scored_candidates` | integer | no | Total candidate-score operations |
| `training_steps` | integer | no | Total training steps (relearning) |
| `training_examples` | integer | no | Total training examples (relearning) |
| `exports` | integer | no | Total export/quantization operations |
| `wall_clock_seconds` | number | no | Estimated or actual wall-clock time |

### ChannelSpec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (unique) | yes | Stable channel identifier |
| `name` | string | yes | Human-readable channel name |
| `enabled` | boolean | yes | Whether this channel is active |
| `purpose` | string | yes | Scientific purpose of this channel |
| `capability_requirements` | CapabilityReq | yes | Access profile requirements |
| `policy_source` | string | yes | Reference to the governing policy |
| `budget_source` | string | yes | Which arm allocation funds this channel |
| `reporting_condition` | string | yes | When/how results are reported |

### CapabilityReq

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `observation` | boolean | yes | Requires text-output observation |
| `controllable_decoding` | boolean | no | Requires controllable decoding (sampling) |
| `raw_scores` | boolean | no | Requires raw logit/probability access |
| `historical_checkpoints` | boolean | no | Requires access to prior checkpoints |
| `export` | boolean | no | Requires model export (quantization) |
| `weight_update` | boolean | no | Requires training/fine-tuning capability |
| `internal_access` | boolean | no | Requires activation/gradient access (Profile B) |

### AdaptivePolicy

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `policy_id` | string (unique) | yes | Stable policy identifier |
| `channel_id` | string | yes | References a ChannelSpec.id |
| `policy_type` | enum: fixed, adaptive | yes | Fixed or adaptive execution |
| `search_space` | SearchSpace | yes | Bounded search definition |
| `update_rule` | string | yes | How the policy updates between trials |
| `stop_rule` | string | yes | When the policy stops searching |
| `discovery_limit` | integer (positive) | yes | Max discovery trials before stopping |
| `confirmation_limit` | integer (nonneg) | yes | Max confirmation trials (inside total) |
| `budget_ceiling` | integer (positive) | yes | Absolute trial ceiling for this policy |

### SearchSpace

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dimensions` | string[] | yes | What dimensions are searched (e.g., temperature, prompt_variant) |
| `cardinality` | integer (positive) | yes | Total configurations in the space |
| `enumerable` | boolean | yes | Whether the space can be fully enumerated |

### ConfirmationReservation

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reservation_id` | string (unique) | yes | Stable reservation identifier |
| `route_ref` | string | yes | References a P0-6 witness-rule confirmation route |
| `channel_id` | string | yes | Which channel this reservation covers |
| `reserved_trials` | integer (positive) | yes | Trials reserved for confirmation |
| `includes_transformed` | boolean | yes | Whether transformed-checkpoint calls are covered |
| `includes_reference` | boolean | yes | Whether reference-model calls are covered |
| `shared_with` | string[] | no | Other reservations that share this budget; competition must be declared |

**Constraint**: No trial can be charged to two reservations (`shared_with` declares competition, not double-spending).

### TransformationRecipe

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `recipe_id` | string (unique) | yes | Stable recipe identifier |
| `channel_id` | string | yes | References the transformation channel |
| `algorithm` | string | yes | Export/quantization algorithm name |
| `software_version` | string | yes | Exact software version used |
| `parent_checkpoint` | string | yes | Identity of the source checkpoint |
| `group_size` | integer | no | Quantization group size |
| `calibration_corpus` | string | no | Calibration data source |
| `precision_exceptions` | string[] | no | Layers/modules with different precision |
| `tokenizer` | string | yes | Tokenizer identity |
| `decoding_config` | object | yes | Decoding parameters |
| `fitting_data_exposure` | enum: target_free, target_exposed, unknown | yes | Whether fitting data contains target info |
| `reference_treatment` | string | yes | How reference checkpoint is transformed comparably |
| `output_provenance` | string | yes | How output checkpoint is identified and stored |
| `lineage` | string[] | no | Explicit cumulative branch lineage if applicable |

### RelearningSpec

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | boolean | yes | Whether relearning channel is active |
| `conditions` | RelearningCondition[] | yes | Target-free and target-exposed conditions |
| `tolerance_ref` | string | yes | Reference to P0-5 margins for relearning threshold |

### RelearningCondition

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `condition_id` | string (unique) | yes | Stable condition identifier |
| `exposure_type` | enum: target_free, target_exposed | yes | Whether training data contains the target fact |
| `data_source` | string | yes | Training data identity |
| `schedule` | string | yes | Training schedule (steps, epochs, LR) |
| `optimizer` | string | yes | Optimizer identity |
| `trainable_parameters` | string | yes | Which parameters are updated |
| `held_out_evaluation` | string | yes | How convergence is evaluated |
| `reporting_contract` | ReportingContract | yes | How results are reported |

### ReportingContract

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `reached_format` | string | yes | How a reached threshold is reported |
| `unreached_format` | string | yes | How an unreached threshold is reported (must be censored/not-reached) |
| `substitution_prohibited` | boolean | yes | Whether substituting a comparator is prohibited (must be true) |

### ClueAuditManifest (JSON document)

Stored under `.factverify/attacks/audit_manifests/`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `manifest_id` | string (unique) | yes | Stable manifest identifier |
| `revision` | string | yes | Revision of the audited content |
| `content_digest` | string | yes | SHA-256 of the audited content |
| `channel_id` | string | yes | Which channel's inputs are audited |
| `entries` | ClueAuditEntry[] | yes | Per-input exposure classifications |
| `reviewer_id` | string | yes | Who performed the audit |
| `review_date` | ISO date | yes | When the audit was performed |

### ClueAuditEntry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `input_id` | string | yes | Identity of the audited input |
| `input_type` | enum: wrapper, few_shot_demo, conversation_context, training_data | yes | Type of input |
| `exposure_class` | enum: clue_free, alias_present, inverse_present, indirect_clue, direct_disclosure | yes | Exposure classification |
| `aliases_found` | string[] | no | Any target aliases detected |
| `inverse_forms_found` | string[] | no | Any inverse answer forms detected |
| `routing` | enum: equivalence, inference, supplied_answer, excluded | yes | Where this input is routed |
| `rationale` | string | yes | Reviewer rationale for classification |

### EventTrace (JSON document — fixture)

Stored under `tests/fixtures/attack_spec/valid/` for testing.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `trace_id` | string | yes | Stable trace identifier |
| `arm_id` | enum: native, semantic_only, factverify | yes | Which evaluator arm |
| `events` | EventRecord[] | yes | Ordered event sequence |

### EventRecord

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_id` | string (unique) | yes | Stable event identifier |
| `arm_id` | string | yes | Evaluator arm |
| `case_id` | string | yes | Fact/case identity |
| `phase` | enum: discovery, confirmation | yes | Discovery or confirmation phase |
| `channel_id` | string | yes | Attack channel |
| `probe_id` | string | no | Template/probe identity |
| `sample_index` | integer | no | Sample index within a multi-completion request |
| `decoding_config` | object | no | Decoding parameters (temperature, top_k, etc.) |
| `artifact_id` | string | no | Checkpoint/transformation identity |
| `parent_id` | string | no | Parent checkpoint/artifact for transformations |
| `operation` | enum: generation, candidate_score, training_step, export, cache_hit, retry, failure, discard, reference | yes | Operation type |
| `outcome` | enum: completed, cached, retried, failed, discarded | yes | Event outcome |
| `charge` | ChargeRecord | yes | How this event is charged |

### ChargeRecord

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `generation_trials` | integer (nonneg) | yes | Trials charged |
| `candidate_scores` | integer (nonneg) | no | Score operations charged |
| `input_tokens` | integer (nonneg) | no | Input tokens consumed |
| `output_tokens` | integer (nonneg) | no | Output tokens consumed |
| `training_steps` | integer (nonneg) | no | Training steps charged |
| `new_compute` | boolean | yes | Whether this event required new computation |
| `policy_applied` | string | yes | Which EventPolicy was applied |

### CostRecord (report output)

Per-arm summary in the validation report.

| Field | Type | Description |
|-------|------|-------------|
| `arm_id` | string | Evaluator arm |
| `cap` | integer | Declared trial cap |
| `actual_trials` | integer | Trials actually used |
| `unused_trials` | integer | Trials not used |
| `generation_trials` | integer | Generation trials charged |
| `candidate_scores` | integer | Score operations charged |
| `input_tokens` | integer | Total input tokens |
| `output_tokens` | integer | Total output tokens |
| `training_steps` | integer | Total training steps |
| `training_examples` | integer | Total training examples |
| `exports` | integer | Export operations |
| `wall_clock_seconds` | number | Wall-clock time |

### DecisionRef

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `decision_id` | string | yes | Decision identifier (e.g., "D-17") |
| `description` | string | yes | What the decision is about |
| `status` | enum: open, resolved, not_applicable | yes | Current resolution status |
| `resolved_value` | string | no | Value if resolved |
| `rationale` | string | no | Why resolved this way or why not applicable |

## Relationships

```
AttackSpecification
├── upstream_refs → P0-1, P0-2, P0-4, P0-5, P0-6
├── accounting: AccountingRules
│   ├── generation_trial_unit: UnitDefinition
│   ├── candidate_scoring_unit: UnitDefinition
│   └── *_policy: EventPolicy (cache, retry, failure, discard, reference)
├── arms: ArmAllocation[3]
│   └── channel_allocations: ChannelAllocation[]
│       └── channel_id → ChannelSpec
├── channels: ChannelSpec[]
│   └── capability_requirements: CapabilityReq → P0-4 access profile
├── adaptive_policies: AdaptivePolicy[]
│   ├── channel_id → ChannelSpec
│   └── search_space: SearchSpace
├── confirmation_reservations: ConfirmationReservation[]
│   ├── route_ref → P0-6 witness rule
│   └── channel_id → ChannelSpec
├── transformations: TransformationRecipe[]
│   └── channel_id → ChannelSpec
├── relearning: RelearningSpec
│   └── conditions: RelearningCondition[]
└── blocking_decisions: DecisionRef[]

ClueAuditManifest
└── entries: ClueAuditEntry[]
    └── routing → equivalence | inference | supplied_answer | excluded

EventTrace (fixture)
└── events: EventRecord[]
    ├── channel_id → ChannelSpec
    └── charge: ChargeRecord
        └── policy_applied → EventPolicy

ValidationReport (output)
├── cost_records: CostRecord[] (per arm)
├── diagnostics: Diagnostic[]
└── deferred_checks: string[]
```

## Validation Report (output entity)

Extends the validator report schema with P0-3 fields.

| Field | Type | Description |
|-------|------|-------------|
| `scope` | const "attacks" | P0-3 scope identifier |
| `spec_path` | string | Resolved path to attacks.yaml |
| `spec_digest` | string | SHA-256 of attacks.yaml |
| `upstream_digests` | object | Digests of consumed P0-1/P0-2/P0-4 inputs |
| `timestamp` | ISO datetime | Validation timestamp |
| `allocation_check` | AllocationReport | Per-arm totals and cap validation |
| `channel_permissions` | PermissionReport | Access-profile cross-check |
| `accounting_check` | AccountingReport | Unit definitions and policy validation |
| `event_replay` | EventReplayReport | Fixture replay results (if traces provided) |
| `confirmation_check` | ConfirmationReport | Reservation sufficiency |
| `policy_check` | PolicyReport | Adaptive policy boundedness |
| `audit_check` | AuditReport | Clue audit completeness |
| `transformation_check` | TransformationReport | Recipe completeness |
| `relearning_check` | RelearningReport | Condition specification |
| `cost_records` | CostRecord[] | Per-arm cost summaries |
| `revision_check` | string or object | Baseline comparison or "not_requested" |
| `deferred_checks` | string[] | Out-of-scope checks listed for transparency |
| `diagnostics` | Diagnostic[] | All diagnostics across all checks |
| `summary` | SummaryStats | Counts of checked/passed/failed/deferred |
