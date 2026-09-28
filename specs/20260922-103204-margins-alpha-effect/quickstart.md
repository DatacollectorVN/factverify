# Quickstart: P0-5 Margins Validation

**Feature**: `20260922-103204-margins-alpha-effect`
**Created**: 2026-09-22

---

## Scenario 1 — Valid Unresolved Worksheet (non-strict)

Create a well-formed `margins.yaml` with typed fields, units, domains, and open decision refs (null values allowed), then run:

```bash
uv run python tools/validate_spec.py \
  --scope margins \
  --spec-root .factverify/spec \
  --report reports/p0-5-validation.json
```

**Expected**: Exit 0 in non-strict mode when structure is valid. Report lists checks, digests, open decision status, and deferred P0-6/P0-7/P2-6/P4 work. Null policy values remain unresolved — not coerced to zero.

---

## Scenario 2 — Mixed Units Rejected

Provide `frr_cap.unit: probability` and `minimum_fcr_reduction_absolute.unit: probability` (should be percentage points), or otherwise mix probability with percentage points on related fields.

**Expected**: Exit 1. FV-SPEC-057 fails with a units diagnostic.

---

## Scenario 3 — Illustrative Cap Without Approval (strict)

Set an illustrative `frr_cap.value: 0.05` without an approval record, then run with `--strict`.

**Expected**: Exit 1. FV-SPEC-058 fails strict readiness.

---

## Scenario 4 — Estimand Fixture Rates

Use synthetic fixtures: 3 genuine rejections / 100 eligible; 12 fake acceptances / 40 eligible. Also include an empty-denominator case.

**Expected**: Rates 0.03 and 0.30. Empty denominator is `undefined`, never `0.0` (FV-SPEC-059).

---

## Scenario 5 — Calibration Leakage

Attempt selection using final-test outcomes, or only a point estimate without the approved upper-bound eligibility rule.

**Expected**: Exit 1. FV-SPEC-060 rejects leakage or silent cap relaxation; infeasible sets report `infeasible`.

---

## Scenario 6 — Single-Baseline “Success”

FactVerify FCR 0.18 vs native 0.30 (delta −0.12) but semantic-only comparison fails the criterion.

**Expected**: Primary success is false (FV-SPEC-061). Both baselines required under common budget.

---

## Scenario 7 — Illegal Uncertainty Contract

Declare row-wise independent resampling of correlated prompts, or separate intervals labelled as joint coverage.

**Expected**: Exit 1. FV-SPEC-062 rejects the analysis contract.

---

## Scenario 8 — Missing Channel or Bucket Margin

Enable a channel in `attacks.yaml` without a matching `channel_margins` entry, or omit `locality_margins.compositional`.

**Expected**: Exit 1. FV-SPEC-063 coverage failure.

---

## Scenario 9 — Sample-Size / Revision Failures

Invent `final_n` in P0, or change frozen policy fields without bumping version / amendment authorization.

**Expected**: FV-SPEC-064 / FV-SPEC-065 fail; confirmatory claim disallowed when amendment is missing.

---

## Scenario 10 — Malformed Input

Provide unparseable YAML or a missing `margins.yaml`.

**Expected**: Exit 2 with file/parse diagnostics (FV-SPEC-066 / I8 fail-closed).

---

## Scenario 11 — Baseline Comparison

```bash
uv run python tools/validate_spec.py \
  --scope margins \
  --spec-root .factverify/spec \
  --baseline-suite tests/fixtures/margins_spec/baselines/margins.yaml \
  --report reports/p0-5-baseline.json
```

**Expected**: Exit 0 if policy matches baseline revision. Exit 1 if frozen policy changed under the same version.
