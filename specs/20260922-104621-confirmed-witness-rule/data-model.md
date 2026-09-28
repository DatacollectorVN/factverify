# Data Model: P0-6 Confirmed-Witness Rule and Scorer

**Feature**: `20260922-104621-confirmed-witness-rule`
**Created**: 2026-09-22
**Source**: [spec.md](spec.md), [research.md](research.md), P0-6 Study Guide §§2–12

---

## Entity: Witness-Rule Artifact

**Artifact**: `.factverify/spec/witness_rule.md`
**Purpose**: Single authoritative contract separating response scoring, confirmation routes, and case-level decisions, with cross-refs to answers, closure, attacks/budgets, access, and margins.

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string (semver) | yes | Artifact revision |
| `status` | enum | yes | `draft` \| `unresolved_worksheet` \| `approved` \| `frozen` |
| `rubric` | mapping | yes | Versioned response-scoring contract |
| `raw_score_conventions` | list of mapping | yes | Per likelihood/rank channel conventions |
| `confirmation_routes` | mapping | yes | Routes A/B/C with enablement and parameters |
| `case_decision` | mapping | yes | Acceptance / rejection / NI / incomplete gates |
| `aggregation_policy` | mapping | yes | Whole-rule search+confirm aggregation |
| `annotation_protocol` | mapping | yes | Blinded review requirements and refs |
| `evidence_schema` | mapping | yes | Required provenance fields for witness records |
| `status_vocabulary_ref` | string | yes | Alignment with P0-4 handling statuses |
| `baseline_refs` | mapping | yes | Paths/ids for answers, closures, attacks, access, margins |
| `blocking_decisions` | list of mapping | yes | Decision IDs with `open` / `resolved` / `not_applicable` + reason |
| `review_refs` | list of string | yes | Paths to annotation/rubric review records |

### Rubric Shape

```yaml
rubric:
  version: "0.1.0-demo"
  answer_roles: [object, subject, truth_value, set_membership]
  labels: [correct, incorrect_contradictory, ambiguous, non_answer, technical_missingness]
  refusal_flag_separate: true
  ambiguity_policy:
    mode: null                 # adjudicate | conservative_flag | analyze_separately
    decision_ref: D-34
  alias_policy:
    source: p0_1_frozen_aliases
    decision_ref: D-39
  normalization_policy:
    decision_ref: D-40
  many_valued_policy:
    mode: null                 # set | membership_criterion
    decision_ref: D-39
```

### Validation Rules

- Unknown required structural fields fail.
- Response label used as `case_decision` outcome fails (layer conflation).
- `null` operational parameters with open `decision_ref` are unresolved — never invent defaults.
- At least one confirmation route must be `enabled: true`.

---

## Entity: Raw Score Convention

**Location**: `raw_score_conventions[]` in frontmatter
**Purpose**: Make likelihood/rank quantities comparable and refuse silent approximation.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `channel_id` | string | yes | Matches attacks/margins channel id where applicable |
| `statistic_kind` | enum | yes | `sequence_logprob` \| `token_rank` \| `other_declared` |
| `normalization` | enum | conditional | `total_logprob` \| `length_normalized` (for logprob) |
| `tokenizer_prefix_policy` | string | yes | Declared tokenizer/prefix handling |
| `alias_aggregation` | string | yes | How aliases combine |
| `candidate_universe` | string | yes | Declared universe for rank |
| `tie_rule` | string | yes | Deterministic ties |
| `observation_point` | string | yes | Must agree with access profile measurement point |
| `recovery_orientation` | enum | yes | `higher_is_more_recovery` \| `lower_is_more_recovery` |
| `insufficient_data_status` | enum | yes | `unavailable` \| `invalid` |
| `decision_refs` | list | yes | e.g. D-27, D-32, D-33 |

### Validation Rules

- Mixed raw scales in one primary statistic fail.
- Processed/top-k insufficient for requested statistic → `unavailable`/`invalid`, not approximated.

---

## Entity: Confirmation Route

**Location**: `confirmation_routes.{A,B,C}`
**Purpose**: Approved path from scored observations to candidate/confirmed witness.

### Shared Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `enabled` | bool | yes | Whether the route may produce confirmations |
| `disabled_reason` | string | if disabled | Non-empty reason when `enabled: false` |
| `budget_reservation_ref` | string | if enabled | P0-3 reserved confirmation cost |
| `aggregation_ref` | string | if enabled | Link to whole-rule aggregation policy |

### Route A Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `family_grouping_policy_ref` | string | if enabled | D-35 grouping policy |
| `min_independent_families` | int | if enabled | Must be ≥ 2 |
| `discovery_vs_confirmation_roles` | mapping | if enabled | Role assignment rules |
| `repetitions` | mapping | if enabled | Required repeats |
| `clue_bearing_excluded` | bool | if enabled | Must be true for clean E recovery |

### Route B Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `score_statistic_ref` | string | if enabled | Declared statistic |
| `eligible_prompts_ref` | string | if enabled | Prompt eligibility |
| `margins_ref` | string | if enabled | P0-5 margin reference |
| `seed_type` | enum | if enabled | Must be `training_or_update` |
| `seed_count` | int or null | if enabled | Count or open (D-36) |
| `reproducibility_rule` | string | if enabled | Declared rule |

### Route C Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `criterion_ref` | string | if enabled | Predeclared crossing criterion |
| `requires_parent_child_hashes` | bool | if enabled | Must be true |
| `exposure_labelling` | mapping | if enabled | Target-free vs target-exposed |
| `reference_transforms_required` | bool | if enabled | Per D-24/D-25/D-28 |
| `post_transform_locality_required` | bool | if enabled | Must be true |
| `replication_rule` | string | if enabled | Declared replication |

### Validation Rules

- Punctuation-only / language-label-only / clue-bearing dual hits fail Route A fixtures.
- Decoding-seed / export-variant substitution fails Route B fixtures.
- Single output change or unlabeled target-exposed reacquisition fails Route C fixtures.
- All three disabled → fail (at least one enabled).

---

## Entity: Case Decision Rule

**Location**: `case_decision` block
**Purpose**: Map scoped evidence to accept / reject / non_identifiable / incomplete.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `acceptance_requires` | list | yes | Simultaneous recovery bounds, locality bounds, access/completeness, no disqualifying witness |
| `rejection_reasons` | list | yes | Includes `locality_failure`, `confirmed_recovery`, etc. as distinct codes |
| `inconclusive_mapping` | mapping | yes | Wide intervals → incomplete/inconclusive per D-14/D-31 |
| `status_alignment` | mapping | yes | Must agree with P0-4 handling_policies vocabulary |
| `no_witness_is_not_accept` | bool | yes | Must be true |

### State Transitions (conceptual)

```text
observations → scored responses
            → candidate witnesses (per route eligibility)
            → confirmed witnesses (route pass)
            → case verdict:
                 accept | reject_recovery | reject_locality
                 | non_identifiable | incomplete
```

---

## Entity: Aggregation Policy

**Location**: `aggregation_policy`
**Purpose**: Calibrate search+confirm as one rule; forbid uncalibrated raw maxima as primary.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `primary_statistic` | string | yes | Must not be `raw_maximum` |
| `raw_maximum_role` | enum | yes | `diagnostic_only` (required) |
| `enabled_route_cost_refs` | list | yes | Each enabled route’s P0-3 reservation |
| `calibrated_as_whole` | bool | yes | Must be true |

---

## Entity: Annotation Review Record

**Location**: `.factverify/witness/reviews/<id>.json`
**Purpose**: Human-supported blinded rubric development evidence.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `review_id` | string | yes | Unique ID |
| `rubric_version` | string | yes | Bound to `rubric.version` |
| `annotators_blinded` | bool | yes | Must be true |
| `system_identity_hidden` | bool | yes | Must be true |
| `double_annotation_subset` | mapping | yes | Preselected subset definition |
| `adjudication` | mapping | yes | Procedure and outcomes |
| `confusion_table` | mapping | yes | Reported |
| `raw_agreement` | number | yes | Reported |
| `kappa` | number or string | yes | Number or `"undefined"` |
| `sole_llm_oracle` | bool | yes | Must be false |
| `outcome_driven_rubric_change` | bool | yes | Must be false for approval |
| `approver_id` | string | yes | Non-empty |
| `review_date` | string (ISO 8601) | yes | When reviewed |

---

## Entity: Witness Evidence Record

**Location**: Fixture or `.factverify/witness/evidence/<id>.json`
**Purpose**: Reconstructable provenance for a witness/case decision.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `case_id` | string | yes | Case identifier |
| `fact_id` | string | yes | Fact identifier |
| `model_hash` | string | yes | Model/checkpoint hash |
| `contract_ref` | string | yes | Fact contract |
| `access_profile` | string | yes | Profile letter / ref |
| `channel` | string | yes | Channel id |
| `template_family_ids` | list | yes | Families used |
| `raw_response_ids` | list | yes | Non-empty for confirmation claims |
| `scorer` | mapping | yes | Version, labels, refusal, annotation ids |
| `reference` | mapping | yes | Checkpoint ids + calibrated statistic |
| `confirmation` | mapping | yes | Route, seeds, transforms, budget |
| `verdict` | mapping | yes | Status, claim_scope, limitations |
| `ground_truth_separate` | bool | yes | Must be true (oracle not embedded as recovery) |

### Validation Rules

- Missing raw IDs, stale scorer revision vs artifact, or control label used as recovery → invalid.

---

## Entity: Validation Report

**Location**: `reports/p0-6-validation.json`
**Purpose**: Offline check results for CI/reviewers.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `scope` | string | yes | `witness-rule` |
| `spec_root` | string | yes | Spec root path |
| `input_digests` | mapping | yes | SHA-256 of checked artifacts |
| `checks` | list | yes | Per-rule status + diagnostics |
| `fixture_results` | list | yes | Golden label/route/verdict outcomes |
| `decision_status` | list | yes | Open / resolved / N/A decisions |
| `deferred` | list | yes | P2-2 / P2-6 / P4 work listed |
| `overall` | enum | yes | `pass` \| `fail` |

---

## Relationships

```text
witness_rule.md
  ├── rubric ──────────────► Annotation Review Record(s)
  ├── raw_score_conventions ► access_profile (observation_point), attacks channels
  ├── confirmation_routes ─► attacks.yaml (budget reserves), margins.yaml (bounds)
  ├── case_decision ───────► access_profile (status vocabulary), margins (ε)
  ├── aggregation_policy ──► attacks.yaml confirmation reserves
  └── evidence_schema ─────► Witness Evidence Record fixtures
```
