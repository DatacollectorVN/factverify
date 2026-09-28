# Quickstart: P0-4 Access Profile Validation

**Feature**: `20260922-095456-access-profile-identifiability`
**Created**: 2026-09-22

---

## Scenario 1 — Valid Profile A (text-only)

Create a minimal valid `access_profile.md` with Profile A declarations and run:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec \
  --report reports/p0-4-validation.json
```

**Expected**: Exit 0. Report shows all 10 checks passing. Capabilities show `text: verified`, `scores: unavailable`, `internals: unavailable` for all systems.

---

## Scenario 2 — Capability Mismatch Detection

Create a profile declaring `profile_letter: B` for a system but with `score_scope.type: pre_mask` when the provider applies post-masking:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec
```

**Expected**: Exit 1. FV-SPEC-048 fails with diagnostic: `post-mask scores labelled as pre_mask`.

---

## Scenario 3 — Intervention Without Role Separation

Create a profile where an intervention's `actor_role` references a nonexistent role:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec
```

**Expected**: Exit 1. FV-SPEC-050 fails with diagnostic about missing role reference.

---

## Scenario 4 — Identifiability From Finite Matching

Create an identifiability justification with `argument_type: empirical` but no finite-observation limitation in `limitations`:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec
```

**Expected**: Exit 1. FV-SPEC-052 fails — finite matching outputs do not establish universal observational equivalence.

---

## Scenario 5 — Status Promotion Detection

Create status fixtures where a missing raw score is mapped to `non_identifiable` instead of `incomplete`:

**Expected**: FV-SPEC-053 rejects — missing evidence cannot be silently promoted to a pass status.

---

## Scenario 6 — Claim Template With Universal Erasure

Create a claim template with `claim_text: "The fact was completely removed from the model"`:

**Expected**: FV-SPEC-055 rejects — universal erasure language is not permitted in claim templates.

---

## Scenario 7 — Strict Mode With Deferred References

Run with `--strict` when P0-5 margins.yaml does not exist:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec \
  --strict
```

**Expected**: Exit 1. FV-SPEC-054 and FV-SPEC-056 fail because cross-file references cannot be resolved.

---

## Scenario 8 — Baseline Comparison

Run with a baseline suite to check for frozen-policy changes:

```bash
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec \
  --baseline-suite tests/fixtures/access_profile/baselines/access_profile.md \
  --report reports/p0-4-baseline.json
```

**Expected**: Exit 0 if profile matches baseline. Exit 1 if frozen policy changed under same revision number.

---

## Scenario 9 — Malformed Frontmatter

Provide an `access_profile.md` with invalid YAML (unclosed bracket, duplicate keys):

**Expected**: Exit 2. Error message identifies the parse failure location.

---

## Scenario 10 — Cross-File Integration

With valid P0-1 fact contract, P0-2 closure templates, and P0-3 attacks.yaml all in place, run access-profile validation:

**Expected**: Exit 0. Cross-file checks show `attacks.yaml` resolved with matching digest. P0-5/P0-6/P0-7 listed as deferred.
