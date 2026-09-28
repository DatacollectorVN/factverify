# Data Model: P0-5 Alpha and Practical Effect Size

**Feature**: `20260922-103204-margins-alpha-effect`
**Created**: 2026-09-22
**Source**: [spec.md](spec.md), [research.md](research.md), P0-5 Study Guide §13

---

## Entity: Margins Policy Artifact

**Artifact**: `.factverify/spec/margins.yaml`
**Purpose**: Single authoritative statistical-policy contract for error tolerances, estimands, calibration selection, practical success, uncertainty, channel/locality margins, sample-size handoff, and decision references.

### Top-Level Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string (semver) | yes | Artifact revision, e.g. `"0.1.0-demo"` |
| `status` | enum | yes | `draft` \| `unresolved_worksheet` \| `approved` \| `frozen` |
| `frr_cap` | quantity | yes | α_FRR — false-rejection rate upper bound |
| `confidence_error_probability` | quantity | yes | Inferential error probability of the CI/UCB procedure |
| `minimum_fcr_reduction_absolute` | quantity | yes | d_min — minimum absolute FCR reduction (percentage points) |
| `delta_definition` | string | yes | Declared delta formula, e.g. `FCR_factverify_minus_FCR_baseline` |
| `practical_success` | mapping | yes | Success rule and comparator arms |
| `threshold_selection` | mapping | yes | Calibration-only selection contract |
| `estimands` | mapping | yes | FRR/FCR definitions, weights, aggregation, status maps |
| `uncertainty` | mapping | yes | Dependence, multiplicity, resampling contract |
| `channel_margins` | list or mapping | yes | Oriented margin per enabled channel |
| `locality_margins` | mapping | yes | Per retained bucket |
| `relearning_tolerance` | quantity or mapping | yes | Relearning tolerance reference |
| `sample_size_handoff` | mapping | yes | Pilot power-planning contract (no final N invented) |
| `approval_refs` | list of string | yes | Paths to approval JSON records |
| `blocking_decisions` | list of mapping | yes | Decision IDs with status (`open`/`resolved`/`not_applicable`) |
| `baseline_refs` | mapping | no | Cross-file refs (attacks, access, fact schema) |
| `amendment_policy_ref` | string | no | Path/ref to P0-7 amendment interface (deferred non-strict) |

### Quantity Shape

```yaml
frr_cap:
  value: null          # null = unresolved, not zero
  unit: probability    # probability | percentage_points | other declared
  domain: [0, 1]
  decision_ref: D-01
  approval_ref: approvals/frr_cap.json   # optional per-field
```

### Validation Rules

- Unknown top-level fields fail (or are listed as unknown and fail in strict mode).
- `null` values are unresolved — never coerced to 0.
- Non-finite numbers fail.
- Mixing `probability` and `percentage_points` on fields that must share a unit family fails.
- Threshold fields MUST NOT be used as a substitute for `frr_cap`.

---

## Entity: Policy Approval Record

**Location**: `.factverify/margins/approvals/<id>.json`
**Purpose**: Reviewed justification that a policy value is acceptable (not merely statistically convenient).

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `approval_id` | string | yes | Unique ID |
| `policy_field` | string | yes | e.g. `frr_cap`, `practical_success` |
| `population` | string | yes | Population to which the policy applies |
| `false_rejection_consequences` | string | yes | Why the FRR cap (or related) is acceptable |
| `minimum_worthwhile_benefit` | string | yes | Stated worthwhile improvement |
| `approver_id` | string | yes | Non-empty approver |
| `approval_date` | string (ISO 8601) | yes | When approved |
| `artifact_revision` | string | yes | Bound to `margins.yaml` version |
| `decision_refs` | list of string | yes | e.g. `["D-01","D-02"]` |
| `notes` | string | no | Free text |

### Validation Rules

- Strict readiness fails if `frr_cap` or `practical_success` lack current approvals.
- Illustrative teaching values without approval fail strict readiness.
- Stale review entries in `review_manifest.json` fail strict mode.

---

## Entity: Estimand Definition

**Location**: `estimands` block in `margins.yaml`
**Purpose**: Explicit FRR/FCR formulas and denominator policies.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `frr` | mapping | yes | `numerator`, `denominator`, `eligible_population` |
| `fcr` | mapping | yes | Same shape for fake acceptances |
| `case_weights` | mapping or string | yes | Weighting policy or `uniform` |
| `aggregation` | mapping | yes | `per_family`, `overall` rules |
| `coverage` | mapping | yes | How coverage is reported |
| `status_mappings` | mapping | yes | `missing`, `non_identifiable`, `incomplete` → denominator treatment |

### Validation Rules

- Empty denominators → `undefined` (never 0.0).
- Synthetic fixtures: 3/100 → 0.03 FRR; 12/40 → 0.30 FCR.
- Non-identifiable and incomplete must not silently enter the wrong denominator.

---

## Entity: Calibration Selection Rule

**Location**: `threshold_selection` in `margins.yaml`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `data` | enum | yes | Must be `calibration_only` |
| `eligibility_rule` | string | yes | e.g. `ucb_frr_le_frr_cap` |
| `selection_uncertainty_procedure` | string | yes | Reviewed procedure ref / decision |
| `tie_rule` | string | yes | Deterministic tie-break |
| `no_feasible_threshold` | enum | yes | `report_infeasible` |
| `forbid_final_test_inputs` | bool | yes | Must be `true` |

### Validation Rules

- Point-estimate-only eligibility without UCB (or approved equivalent) fails.
- Final-test inputs in selection fixtures → reject.
- No silent cap relaxation.

---

## Entity: Practical-Success Rule

**Location**: `practical_success` in `margins.yaml`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `comparators` | list | yes | Must include `native` and `semantic_only` |
| `common_budget_ref` | string | yes | Path/ref to attacks common cap |
| `delta_unit` | enum | yes | `percentage_points` |
| `criterion` | string | yes | Declared success criterion |
| `require_both_baselines` | bool | yes | Must be `true` for primary success |
| `delta_uncertainty_rule` | string or null | no | e.g. `ucb_delta_le_neg_d_min` only if explicitly adopted |

### Validation Rules

- Primary success false unless both baselines meet criterion.
- Fixture: FCR 0.18 vs 0.30 → delta −0.12 (12 percentage points).

---

## Entity: Uncertainty Contract

**Location**: `uncertainty` in `margins.yaml`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dependence_structure` | string | yes | e.g. paired checkpoint × fact |
| `seed_types` | list | yes | Intervention vs observation seeds |
| `weighting` | string | yes | Unit and weighting policy |
| `simultaneous_family` | string | yes | Multiplicity family |
| `confidence_target` | quantity | yes | Linked to confidence_error_probability |
| `resampling_contract` | string | yes | Paired resampling declaration |
| `zero_errors_policy` | string | yes | Non-zero uncertainty even if zero events |

### Validation Rules

- Reject independent row-wise resampling of correlated prompts.
- Reject separate intervals labelled as joint coverage.

---

## Entity: Channel / Locality Margin

**Location**: `channel_margins`, `locality_margins` in `margins.yaml`

### Channel Margin Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `channel_id` | string | yes | Must match enabled attack channel `id` |
| `statistic` | string | yes | Oriented statistic name |
| `unit` | string | yes | Declared unit |
| `reference` | string | yes | Reference definition |
| `margin` | quantity | yes | Value may be null if decision open |
| `orientation` | enum | yes | `upper` \| `lower` \| `two_sided` |

### Locality Margin Keys

Must cover: `same_subject`, `same_relation`, `compositional`, `global` (fact-contract bucket enum).

### Validation Rules

- Every `attacks.yaml` channel with `enabled: true` needs a margin entry.
- Every locality bucket needs a margin entry.
- Reject raw rank averaged with correctness.
- Do not auto-import mandatory privacy margins from superseded notes.

---

## Entity: Sample-Size Handoff

**Location**: `sample_size_handoff` in `margins.yaml`

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `allowed_inputs` | list | yes | What pilot inputs may be used |
| `target_power` | quantity or null | yes | With unit/decision_ref |
| `effect_scenario` | string | yes | Tied to d_min / practical hypothesis |
| `dependence_model` | string | yes | Must agree with uncertainty block |
| `feasibility_limits` | mapping | yes | Cost/time/N bounds |
| `algorithm_version` | string | yes | Declared algorithm identity |
| `pre_final_deadline` | string | yes | Deadline before final test |
| `final_n` | null | yes | MUST be null in P0-5 |

### Validation Rules

- Power against zero used to justify exceeding d_min → fail/flag.
- Inventing `final_n` in P0 → fail.

---

## Entity: Revision / Amendment Record

**Purpose**: Protect staged statistical commitments between `spec-v1` policy and later `thresholds-v1` values.

### Validation Rules

- Baseline comparison detects changed frozen fields under unchanged version → fail.
- Missing amendment authorization → confirmatory claim disallowed.
- Distinguish specification policy revision from threshold-tag values.

---

## Entity: Validation Report

**Location**: `reports/p0-5-validation.json` (or `--report` path)

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | string | UUID |
| `timestamp` | string | ISO 8601 |
| `spec_root` | string | Spec root path |
| `scope` | string | `"margins"` |
| `strict` | boolean | Strict mode flag |
| `margins_version` | string | From artifact |
| `checks` | list | FV-SPEC-057–066 results |
| `decision_status` | mapping | Per decision ID |
| `input_digests` | mapping | SHA-256 of inputs |
| `deferred_checks` | list | P0-6/P0-7/P2-6/P4 deferred work |
| `baseline_comparison` | mapping or null | If baseline requested |
| `overall` | enum | `pass` \| `fail` |

---

## Entity: Review Manifest

**Location**: `.factverify/margins/review_manifest.json`

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `reviews` | list | Each: `artifact_id`, `artifact_type`, `reviewer_id`, `review_date`, `status` (`current`\|`expired`\|`pending`) |

### Validation Rules

- Pending/expired reviews block strict mode for applicable approvals.

---

## Cross-Entity Relationships

```
margins.yaml
├── frr_cap / practical_success ──► approvals/*.json
├── estimands.status_mappings ───► access_profile handling_policies (P0-4)
├── channel_margins[] ───────────► attacks.yaml channels (enabled)
├── locality_margins ────────────► fact_contract.schema.json bucket enum
├── practical_success.common_budget_ref ► attacks.yaml common_cap
├── sample_size_handoff ─────────► P4 / P2-6 (deferred execution)
├── amendment_policy_ref ────────► P0-7 preregistration (deferred non-strict)
└── blocking_decisions[] ────────► D-01…D-16, D-38

review_manifest.json
└── reviews[].artifact_id ───────► approvals, procedure refs
```
