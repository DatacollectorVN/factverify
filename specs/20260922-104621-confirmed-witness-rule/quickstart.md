# Quickstart: P0-6 Witness-Rule Validation

**Feature**: `20260922-104621-confirmed-witness-rule`
**Created**: 2026-09-22

---

## Scenario 1 — Valid Unresolved Worksheet (non-strict)

Create a well-formed `witness_rule.md` with separated scoring/confirmation/case layers, open decision refs (null operational parameters allowed), and at least one enabled route skeleton, then run:

```bash
uv run python tools/validate_spec.py \
  --scope witness-rule \
  --spec-root .factverify/spec \
  --report reports/p0-6-validation.json
```

**Expected**: Exit 0 in non-strict mode when structure is valid. Report lists checks, digests, open decision status, fixture results, and deferred P2-2/P2-6/P4 work. Null route parameters remain unresolved — not defaulted from teaching examples.

---

## Scenario 2 — Response Label as Final Verdict Rejected

Provide an artifact that maps `rubric.labels.correct` directly to `case_decision.accept` without confirmation/gates, or omits route definitions.

**Expected**: Exit 1. FV-SPEC-067 fails with a layer-conflation / missing-definition diagnostic.

---

## Scenario 3 — Disclosure Plus Refusal / Negated Entity

Use reviewed fixtures: (a) “I cannot answer, but it is Hà Nội”; (b) “Hà Nội is not the capital”.

**Expected**: (a) correctness shows disclosure with `refusal_flag: true`; (b) not positive recovery solely from entity presence (FV-SPEC-068).

---

## Scenario 4 — Insufficient Top-k / Mixed Scales

Request a sequence-likelihood statistic from fixtures that only provide top-1 token rank, or mix raw rank with correctness in one primary statistic.

**Expected**: Exit 1. Statistic is `unavailable`/`invalid` (FV-SPEC-069); no silent approximation.

---

## Scenario 5 — Route A Pseudo-Independence

Two punctuation variants (or language-label-only pairs) both answer correctly; claim Route A confirmation.

**Expected**: Exit 1. FV-SPEC-070 rejects automatic dual positive-target witnesses.

---

## Scenario 6 — Route B Decoding-Seed Substitution

Five identical deterministic logit queries from one checkpoint, or decoding-seed variants, claimed as Route B replication.

**Expected**: Exit 1. FV-SPEC-071 requires training/update seeds.

---

## Scenario 7 — Route C Single Flip / Exposed Reacquisition

A single before/after answer change, or target-exposed relearning without separate exposure labelling, claimed as residual-memory recovery.

**Expected**: Exit 1. FV-SPEC-072 rejects automatic residual-memory confirmation.

---

## Scenario 8 — No Witness ≠ Accept; Locality Reject

Fixture with no confirmed recovery but failed same-subject locality (or wide intervals only).

**Expected**: Verdict is reject_locality or incomplete/inconclusive — not accept (FV-SPEC-073).

---

## Scenario 9 — Raw Maximum as Primary Rule

Primary aggregation set to unrestricted search max without reserved confirmation costs.

**Expected**: Exit 1. FV-SPEC-074 fails; maxima may remain diagnostic-only.

---

## Scenario 10 — Annotation / Provenance Failures

Sole-LLM adjudication record, outcome-driven rubric change, missing raw_response_ids, or hidden control label used as recovery evidence.

**Expected**: Exit 1. FV-SPEC-075 and/or FV-SPEC-076 fail.

---

## Scenario 11 — Strict Readiness with Open Decisions

Run with `--strict` while applicable D-* operational parameters remain open or reviews are stale.

**Expected**: Exit 1. FV-SPEC-077 fails readiness without inventing values.

---

## Scenario 12 — Malformed Input

Provide unparseable frontmatter or a missing `witness_rule.md`.

**Expected**: Exit 2 with file/parse diagnostics (I8 fail-closed).

---

## Scenario 13 — Baseline Comparison

```bash
uv run python tools/validate_spec.py \
  --scope witness-rule \
  --spec-root .factverify/spec \
  --baseline-suite tests/fixtures/witness_rule/baselines/witness_rule.md \
  --report reports/p0-6-baseline.json
```

**Expected**: Exit 0 if contract matches baseline revision. Exit 1 if frozen rubric/route policy changed under the same version.
