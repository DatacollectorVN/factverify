# Data Model: P0-2 Closure Template Suite

**Feature**: `20260921-235511-closure-template-suite`
**Date**: 2026-09-21

## Core Entities

### ClosureTemplateSuite (YAML document)

The root entity. Single file at `.factverify/spec/closure_templates.yaml`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_version` | string | yes | Version of the closure artifact format |
| `fact_contract_ref` | string | yes | Path to the P0-1 schema |
| `boundary_policy` | string | yes | Policy identifier (e.g., "equivalence-inference-v1") |
| `sets` | SetsSpec | yes | Equivalence and inference template collections |
| `controls` | ControlsSpec | yes | R and X template collections |
| `groups` | GroupSpec[] | yes | Near-duplicate groupings |
| `splits` | SplitAssignment | yes | Group-to-split mapping |
| `relation_manifest` | string[] | yes | Approved relation types |
| `revision` | string | yes | Suite revision identifier |
| `content_digest` | string | no | SHA-256 of canonical content |

### SetsSpec

| Field | Type | Required |
|-------|------|----------|
| `equivalence` | EquivalenceTemplate[] | yes |
| `inference` | InferenceTemplate[] | yes |

### EquivalenceTemplate

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (unique) | yes | Stable template identity |
| `class` | const "E" | yes | Must be E for equivalence |
| `group` | string | yes | Group ID reference |
| `language` | BCP 47 tag | yes | Template language |
| `format` | enum: free_answer, completion, true_false | yes | Response format |
| `text` | string (non-empty) | yes | Template with {placeholders} |
| `context_refs` | string[] | no | Multi-turn context template IDs |
| `relation_applicability` | string[] | yes | Which relation types this applies to |
| `answer_role` | enum: subject, object, truth_value | yes | Which triple component is the expected answer |
| `primary_family` | enum: direct, inverse, cloze, paraphrase, multilingual, verification | yes | Primary classification |
| `overlapping_attributes` | string[] | no | Additional family attributes |
| `extra_premises` | const [] | yes | MUST be empty for E |

### InferenceTemplate

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (unique) | yes | Stable template identity |
| `class` | const "I" | yes | Must be I for inference |
| `group` | string | yes | Group ID reference |
| `language` | BCP 47 tag | yes | Template language |
| `format` | enum: free_answer, completion, true_false | yes | Response format |
| `text` | string (non-empty) | yes | Template with {placeholders} |
| `context_refs` | string[] | no | Multi-turn context template IDs |
| `relation_applicability` | string[] | yes | Which relation types this applies to |
| `answer_role` | enum: subject, object, truth_value | yes | Which triple component is expected |
| `subtype` | enum: prompt_supplied, contextual, compositional | yes | Inference subtype |
| `extra_premises` | PremiseEntry[] (min 1) | yes | MUST be nonempty for I |
| `premise_origins` | string[] (min 1) | yes | Source of each premise |
| `reasoning_status` | enum: bridge, chain, multi_hop | yes | Type of reasoning required |
| `support_status` | enum: supporting, sufficient, necessary | yes | How premises relate to conclusion |
| `separate_reporting` | const true | yes | Always reported separately from E |

### PremiseEntry

| Field | Type | Required |
|-------|------|----------|
| `text` | string (non-empty) | yes |
| `source` | enum: prompt, context, world_knowledge | yes |

### RetainedControlTemplate

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (unique) | yes | Stable template identity |
| `class` | const "R" | yes | Must be R for retained |
| `group` | string | yes | Group ID reference |
| `language` | BCP 47 tag | yes | Template language |
| `format` | enum: free_answer, completion, true_false | yes | Response format |
| `text` | string (non-empty) | yes | Template with {placeholders} |
| `relation_applicability` | string[] | yes | Which relation types this applies to |
| `answer_role` | enum: subject, object, truth_value | yes | Expected answer role |
| `retained_entry_ref` | string | yes | References a P0-1 retained_neighbourhood entry ID |
| `bucket` | enum: same_subject, same_relation, compositional, global | yes | Locality bucket |

### ExcludedTemplate

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string (unique) | yes | Stable template identity |
| `class` | const "X" | yes | Must be X for excluded |
| `group` | string | no | Group ID if applicable |
| `language` | BCP 47 tag | yes | Template language |
| `text` | string (non-empty) | yes | Template text |
| `exclusion_reason` | string (non-empty) | yes | Why excluded (e.g., "supplied_answer", "out_of_temporal_scope") |
| `diagnostic_role` | string | no | How this can be used diagnostically |

### VerificationInstance (extends EquivalenceTemplate where primary_family = "verification")

Additional fields for verification templates:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `candidate` | string | yes | The proposition being verified |
| `oracle_label` | enum: true, false | yes | Correct answer (stored in evaluator_metadata only) |
| `recognition_role` | enum: positive_recognition, negative_recognition | yes | Role in verification block |
| `balance_block` | string | yes | Block key for balance checking (contract_id:relation:language:split) |

### GroupSpec

| Field | Type | Required |
|-------|------|----------|
| `group_id` | string (unique) | yes |
| `members` | string[] (min 1) | yes |
| `split` | enum: construction, calibration, final_test | yes |

**Constraints**:
- Every template ID appears in exactly one group
- Near-duplicate templates MUST be in the same group
- Calibration and final_test groups are disjoint sets

### SplitAssignment

| Field | Type | Required |
|-------|------|----------|
| `construction` | string[] | yes |
| `calibration` | string[] | yes |
| `final_test` | string[] | yes |

Each entry is a group_id. No group_id appears in more than one split.

### InstanceBinding (JSON document)

Stored at `.factverify/closure/instance_bindings.json`. Maps templates to contract-specific values.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `suite_revision` | string | yes | Must match closure_templates.yaml revision |
| `bindings` | BindingEntry[] | yes | Per-template bindings |

### BindingEntry

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template_id` | string | yes | References a template ID |
| `contract_id` | string | yes | References a P0-1 contract_id |
| `contract_version` | string | yes | Exact contract version |
| `subject_value` | string | yes | Resolved subject text |
| `object_value` | string | yes | Resolved object text |
| `relation_value` | string | yes | Resolved relation text |
| `answer_key` | string | yes | Expected answer text |
| `truth_label` | enum: true, false | no | For verification instances |
| `target_aliases` | string[] | no | Approved target aliases |
| `distractor_source` | string | no | Source for false verification candidates |
| `retained_entry_id` | string | no | For R controls: P0-1 retained_neighbourhood ID |

### ReviewManifest (JSON document)

Stored at `.factverify/closure/review_manifest.json`.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `suite_revision` | string | yes | Closure suite revision being reviewed |
| `suite_digest` | string | yes | SHA-256 of closure_templates.yaml |
| `bindings_digest` | string | yes | SHA-256 of instance_bindings.json |
| `reviews` | ReviewEntry[] | yes | Per-instance review records |
| `bilingual_approvals` | BilingualApproval[] | no | For multilingual E instances |
| `classification_review` | ClassificationReview | no | Independent classification review |
| `decision_refs` | DecisionRef[] | yes | D-38 through D-43 resolution status |

### ReviewEntry

| Field | Type | Required |
|-------|------|----------|
| `template_id` | string | yes |
| `reviewer_id` | string | yes |
| `date` | ISO date | yes |
| `label` | enum: E, I, R, X | yes |
| `rationale` | string (non-empty) | yes |
| `approved` | boolean | yes |

### BilingualApproval

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template_id` | string | yes | Multilingual E template |
| `reviewer_id` | string | yes | Bilingual reviewer |
| `date` | ISO date | yes | Approval date |
| `checks` | BilingualCheck | yes | What was verified |
| `normalization_policy_ref` | string | yes | Contract's normalization policy |
| `approved` | boolean | yes | Pass/fail |

### BilingualCheck

| Field | Type | Required |
|-------|------|----------|
| `relation_preserved` | boolean | yes |
| `direction_preserved` | boolean | yes |
| `qualifiers_preserved` | boolean | yes |
| `negation_preserved` | boolean | yes |
| `answer_identity_preserved` | boolean | yes |
| `clue_free` | boolean | yes |

### ClassificationReview

| Field | Type | Required |
|-------|------|----------|
| `reader_1` | ReviewerRecord | yes |
| `reader_2` | ReviewerRecord | yes |
| `adjudicator` | ReviewerRecord | no |
| `disagreements` | DisagreementEntry[] | no |
| `revision` | string | yes |

### PreviewRecord (JSONL output)

One record per line in the preview output file.

| Field | Type | Description |
|-------|------|-------------|
| `instance_id` | string | Stable instance identity |
| `model_input` | Message[] | Ordered model-visible messages |
| `evaluator_metadata` | Metadata | Answer keys, class, truth_label, premises, review refs |

### Message

| Field | Type | Required |
|-------|------|----------|
| `role` | enum: system, user, assistant | yes |
| `content` | string | yes |

### Metadata (evaluator-only, never in model_input)

| Field | Type |
|-------|------|
| `contract_id` | string |
| `contract_version` | string |
| `template_id` | string |
| `group_id` | string |
| `split` | string |
| `relation` | string |
| `class` | enum: E, I, R, X |
| `primary_family` | string |
| `overlapping_attributes` | string[] |
| `answer_role` | string |
| `answer_key` | string |
| `truth_label` | boolean or null |
| `reporting_population` | string |
| `premises` | PremiseEntry[] |
| `review_ref` | string |

## Relationships

```
ClosureTemplateSuite
├── sets
│   ├── equivalence: EquivalenceTemplate[]
│   └── inference: InferenceTemplate[]
├── controls
│   ├── retained: RetainedControlTemplate[]
│   └── excluded: ExcludedTemplate[]
├── groups: GroupSpec[]
│   └── members → template IDs
└── splits: SplitAssignment
    └── group_ids → GroupSpec

InstanceBinding
├── bindings: BindingEntry[]
│   ├── template_id → EquivalenceTemplate | InferenceTemplate | ...
│   └── contract_id → P0-1 AtomicFactContract

ReviewManifest
├── reviews: ReviewEntry[]
│   └── template_id → template
├── bilingual_approvals: BilingualApproval[]
│   └── template_id → multilingual E template
└── classification_review: ClassificationReview

PreviewRecord
├── model_input: Message[] (no answer keys)
└── evaluator_metadata: Metadata (answer keys, class, etc.)
```

## Validation Report (output entity)

Extends the P0-1 report schema with P0-2 fields.

| Field | Type | Description |
|-------|------|-------------|
| `scope` | const "closure-templates" | P0-2 scope identifier |
| `suite_path` | string | Resolved path to closure_templates.yaml |
| `suite_digest` | string | SHA-256 of suite file |
| `bindings_path` | string | Resolved path to instance_bindings.json |
| `schema_path` | string | Resolved P0-1 schema path |
| `checked_templates` | object[] | Per-template validity and diagnostics |
| `coverage` | CoverageReport | Family × relation coverage matrix |
| `balance` | BalanceReport | Verification block balance status |
| `split_isolation` | SplitReport | Group/split disjointness status |
| `review_status` | ReviewStatus | Bilingual/classification review completeness |
| `revision_check` | object/string | Baseline comparison or "not_requested" |
| `deferred_checks` | string[] | Out-of-scope checks listed for transparency |
| `diagnostics` | Diagnostic[] | All diagnostics across all checks |
| `summary` | SummaryStats | Counts of valid/invalid/deferred |
