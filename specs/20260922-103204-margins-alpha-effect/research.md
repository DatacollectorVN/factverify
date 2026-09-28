# Research: P0-5 Alpha and Practical Effect Size

## R1 — Margins Artifact Format

**Decision**: Pure YAML file `.factverify/spec/margins.yaml` (not Markdown frontmatter).

**Rationale**: The P0-5 Study Guide §13 worksheet is already YAML. The artifact is almost entirely structured policy fields (units, domains, rules, decision refs). Unlike `access_profile.md` / `witness_rule.md`, there is little normative prose that must live beside the fields. Pure YAML matches `attacks.yaml` and keeps parsing simple.

**Alternatives considered**:
- YAML frontmatter + Markdown body: rejected — insufficient prose to justify the hybrid; study guide worksheet is pure YAML.
- JSON Schema–only with separate JSON instance: rejected — project convention for normative policy is YAML under `.factverify/spec/`; schema validation can still be applied later if needed.

## R2 — Unresolved Values vs Teaching Literals

**Decision**: Normative numeric fields may be `null` with an accompanying `decision_ref` / status of `open` or `DECISION_REQUIRED` in non-strict structural validation. Strict readiness fails until applicable decisions are resolved with approval records. Illustrative values such as `0.05` MUST NOT be treated as approved policy without an approval record.

**Rationale**: Constitution TODO(ALPHA) and FV-SPEC-058 forbid variance or teaching examples from becoming the operating point. Fail-closed (I8) requires unresolved fields to remain visible, not silently coerced to zero.

**Alternatives considered**:
- Hard-code provisional α = 0.05 in the artifact as “temporary default”: rejected — becomes a frozen teaching value.
- Require all numbers resolved before any validator lands: rejected — blocks incremental P0 work while supervisor decisions remain open.

## R3 — Typed Policy Fields and Units

**Decision**: Distinct top-level (or nested) typed fields with explicit `value`, `unit`, `domain`, and `decision_ref` where applicable:

| Field | Typical unit | Notes |
|-------|--------------|-------|
| `frr_cap` (α_FRR) | probability in [0,1] | Never substituted by a score threshold |
| `confidence_error_probability` | probability in [0,1] | Inferential error rate of the CI/UCB procedure |
| `minimum_fcr_reduction_absolute` (d_min) | percentage_points | Absolute FCR reduction |
| `channel_margins[]` | per-statistic unit | Oriented; never mix rank with correctness |
| `locality_margins` | per-bucket unit | Keys: `same_subject`, `same_relation`, `compositional`, `global` |
| `relearning_tolerance` | declared unit + ref | Reference to relearning channel policy |

Mixing probability and percentage-point units on comparable fields fails validation (C-5).

**Rationale**: Study Guide §4 (“four different numbers that must not be called alpha”) and §12 (margins are not interchangeable).

**Alternatives considered**:
- Single `alpha` field reused for everything: rejected — conflates FRR cap, CI error, and effect size.
- Store all quantities as percentages: rejected — FRR/FCR rates are probabilities; ΔFCR practical effect is percentage points.

## R4 — Approval Records Location

**Decision**: Separate JSON approval records under `.factverify/margins/approvals/` referenced from `margins.yaml` via `approval_refs`, plus `.factverify/margins/review_manifest.json` for review currency.

**Rationale**: Mirrors P0-4 provenance/review pattern; digests and stale-review checks are straightforward; FRR-cap and practical-success approvals can be updated independently of the policy skeleton.

**Alternatives considered**:
- Embed approvals only inside `margins.yaml`: rejected — harder to review independently and to digest.
- Markdown approval notes only: rejected — not machine-checkable for required fields.

## R5 — Estimands and Empty Denominators

**Decision**: Estimand block declares FRR = genuine_rejections / eligible_genuine and FCR = fake_acceptances / eligible_fake, with explicit weight, aggregation, coverage, and status mappings. Empty denominators yield status `undefined` (never rate 0.0). Synthetic fixtures assert 3/100 → 0.03 and 12/40 → 0.30.

**Rationale**: FV-SPEC-059; wrong denominators reverse conclusions; zeroing empty denominators hides coverage failure.

**Alternatives considered**:
- Impute empty denominators as 0: rejected — silently invents a rate.
- Single pooled denominator: rejected — FRR and FCR have different populations.

## R6 — Calibration Selection Rule

**Decision**: Declare `threshold_selection.data: calibration_only`, eligibility `ucb_frr <= frr_cap` using an approved `selection_uncertainty_procedure` reference, and a deterministic `tie_rule`. No feasible point → `infeasible`. Presence of final-test outcomes in selection inputs → reject. Do not implement the production UCB estimator in P0-5; validate the *contract* and fixture behaviour.

**Rationale**: FV-SPEC-060; Constitution principles 2 and 11. Empirical procedure execution belongs to P4 / P2-6.

**Alternatives considered**:
- Select on point estimate FRR ≤ α: rejected — does not establish the cap under uncertainty.
- Ship a full bootstrap selector in P0-5: rejected — out of scope; invents analysis engine early.

## R7 — Practical Success Against Both Baselines

**Decision**: `practical_success` requires both `native` and `semantic_only` comparisons under the declared common cap/budget. Delta definition: `FCR_factverify - FCR_baseline` in percentage points (example fixture: 0.18 − 0.30 = −0.12). Primary success is conjunction of both comparisons. Optional `ucb_delta <= -d_min` only if `delta_uncertainty_rule` is explicitly adopted.

**Rationale**: FV-SPEC-061; Study Guide §7; I4 equal budgets.

**Alternatives considered**:
- Success if either baseline improves: rejected — primary success requires both.
- Relative reduction only: rejected — absolute percentage-point reduction is the declared practical quantity (relative may be reported but not substitute).

## R8 — Uncertainty / Dependence / Multiplicity

**Decision**: Explicit `uncertainty` block: dependence structure (paired checkpoint × fact), seed types, weighting, simultaneous family, confidence target, paired resampling contract. Reject contracts that (a) treat correlated prompts as independent row replicates, or (b) label separate intervals as joint coverage. Zero observed errors still require a positive uncertainty statement field/policy.

**Rationale**: FV-SPEC-062; Constitution I7; Study Guide §§6, 10–11.

**Alternatives considered**:
- Prompt-level independent bootstrap as default: rejected — prompts are not replicates.
- Skip uncertainty declaration until P2-6: rejected — P0-5 must freeze the *contract* before the engine exists.

## R9 — Channel and Locality Coverage

**Decision**: Cross-check enabled channels from `attacks.yaml` (`channels[].enabled == true`, id field) and locality buckets from fact-contract enum (`same_subject`, `same_relation`, `compositional`, `global`). Each must have an oriented margin entry. Reject raw-rank averaged with correctness. Do not import mandatory privacy/membership-inference margins from superseded notes unless an explicit scoped substudy field is present.

**Rationale**: FV-SPEC-063; handbook V17; Study Guide §12.

**Alternatives considered**:
- Single aggregate locality margin: rejected — conceals bucket-specific damage.
- Auto-enable privacy margin from older decision-rule notes: rejected — v3 removed it from the mandatory path.

## R10 — Sample-Size Handoff and Revision Protection

**Decision**: `sample_size_handoff` declares allowed inputs, target power, effect scenario, dependence model, feasibility limits, algorithm/version, pre-final deadline — but not a final N invented in P0. Flag power-against-zero used to justify exceeding d_min. Revision checks compare baseline suite vs current: policy changes require version bump + permitted amendment metadata (P0-7 interface deferred in non-strict).

**Rationale**: FV-SPEC-064–065.

**Alternatives considered**:
- Compute and freeze N in P0-5: rejected — no pilot data yet; invents the study size.
- Allow silent policy edits under same version: rejected — invalidates confirmatory claims.

## R11 — CLI Scope and Fixture Layout

**Decision**: `--scope margins`; engine in `tools/margins_validator.py`; fixtures under `tests/fixtures/margins_spec/{valid,invalid,baselines}/` (aligned with `attack_spec` / `access_profile`). Requirements’ `tests/fixtures/p0_5/` is treated as the same conceptual set.

**Rationale**: Consistency with P0-3/P0-4 reduces cognitive load and reuses conftest patterns.

**Alternatives considered**:
- Literal `tests/fixtures/p0_5/` only: acceptable but inconsistent with sibling features; rejected for layout consistency.
- Fold checks into `access_profile_validator.py`: rejected — different artifact and rule IDs.

## R12 — Deferred Cross-File Checks

**Decision**: Non-strict mode may list P0-6 witness and P0-7 preregistration/amendment references as deferred. P0-1 buckets, P0-3 channels/budgets, and P0-4 status mappings are required for coverage/estimand cross-checks when those artifacts exist. Strict mode requires resolved applicable decisions, current approval reviews, and consistent cross-file policies.

**Rationale**: Same incremental pattern as P0-4 deferred P0-5/P0-6/P0-7 checks; now P0-5 is the producer that later consumers depend on.
