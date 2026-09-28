# Implementation Plan: P0-6 Confirmed-Witness Rule and Scorer

**Branch**: `20260922-104621-confirmed-witness-rule` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260922-104621-confirmed-witness-rule/spec.md`

## Summary

Deliver a validated scoring and confirmation contract (`.factverify/spec/witness_rule.md`) that keeps response scoring, witness confirmation (Routes A/B/C), and case-level verdicts distinct. The validator extends `tools/validate_spec.py` with `--scope witness-rule` and eleven rules (FV-SPEC-067 through FV-SPEC-077). Validation is offline with human-reviewed golden fixtures — zero model/LLM calls, GPU jobs, or empirical calibration. Operational route parameters and rubric policies may remain open behind blocking decisions; the artifact and validator are built against named fields and decision IDs, never against illustrative teaching examples as frozen truth.

## Technical Context

**Language/Version**: Python 3.11 (managed by `uv`)
**Primary Dependencies**: PyYAML (YAML frontmatter parsing), click (CLI), hashlib (digests)
**Storage**: Markdown with YAML frontmatter (`witness_rule.md`), JSON (review/annotation manifests, evidence fixtures, reports)
**Testing**: pytest with named hooks `test_fv_spec_067_*` through `test_fv_spec_077_*`
**Target Platform**: macOS / Linux CLI
**Project Type**: CLI extension of `tools/validate_spec.py`
**Performance Goals**: Offline-only; sub-second validation on spec-sized inputs and golden fixture suites
**Constraints**: Zero model/GPU/LLM calls; deterministic given same versioned inputs; fail closed on bad/missing/unresolved normative input; no teaching value becomes a default; at least one confirmation route enabled
**Scale/Scope**: 11 validation rules (FV-SPEC-067–077), golden positive/negative fixtures per layer/route, ~14 open blocking decisions (D-09, D-11, D-12, D-14, D-24, D-25, D-27, D-28, D-31–D-37, D-39, D-40)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Spec Is Frozen (I8) | PASS | P0-6 contributes `witness_rule.md` to `spec-v1`. Not yet frozen. Fail-closed: missing defs, malformed evidence, unresolved strict policy → nonzero exit. |
| 2. No Result-Dependent Choices | PASS | Rubric and route criteria are predeclared; outcome-driven rubric edits fail annotation approval (FV-SPEC-075). |
| 3. Final Test Runs Once | N/A | P0-6 validates decision-rule artifacts; does not run experiments. |
| 4. Equal Query Budgets (I4) | PASS | Enabled confirmation routes must have P0-3 reserved costs; unrestricted search / absent reservation fails (FV-SPEC-074). |
| 5. Seeded and Config-Driven | PASS | Labels, routes, margins refs, and seed-type rules live in `witness_rule.md` fields and decision IDs; teaching kappa/city examples never hard-coded as policy. |
| 6. Ledger Everything | N/A | Offline spec validation; ledger is P2-5. |
| 7. Gates Are Stop Points | PASS | Blocking decisions documented; no requirement reaches `implemented` while blocked. Strict readiness fails on unresolved applicable decisions. |
| 8. Wiki Governs Design | PASS | Design from P0-6 Study Guide §§2–14, handbook V16/V18/V19/I8, FV-SPEC-P0-6; code follows fields, not teaching examples. Notes are `needs-review`. |
| 9. Equivalence and Inference Never Mix (I2) | PASS | Clue-bearing / inference responses cannot silently supply clean Route A equivalence witnesses (C-5 / FR-008). |
| 10. Claims Never Exceed the Channel (I3) | PASS | Case verdicts retain claim_scope / access alignment; non-identifiable and incomplete stay distinct from pass/reject (FR-015). |
| 11. Raw Maxima Are Never Verdicts (I5) | PASS | Uncalibrated raw maxima rejected as primary rules; confirmation routes + simultaneous bounds required (FR-016). |
| 12. Prompts Are Not Replicates (I7) | PASS | Route B requires training/update seeds; decoding seeds / export variants of one checkpoint fail confirmation (FR-010). |

No violations. Gate passes.

### Post-design re-check

Same table still PASS after Phase 1. Design keeps production semantic scorer / live confirmation (P2-2), statistical engine (P2-6), and empirical calibration (P4) out of scope; P0-6 only declares the scoring/confirmation/case *contract*, golden fixtures, and offline validation.

## Project Structure

### Documentation (this feature)

```text
specs/20260922-104621-confirmed-witness-rule/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── validator-interface.md
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
tools/
├── validate_spec.py             # CLI entry — extended with --scope witness-rule
└── witness_rule_validator.py    # NEW: P0-6 validation engine (mirrors access_profile_validator.py)

.factverify/
├── spec/
│   └── witness_rule.md          # NEW: P0-6 deliverable (normative scoring/confirmation/case contract)
└── witness/
    ├── reviews/                 # NEW: annotation / adjudication review records
    ├── evidence/                # NEW: reconstructable witness evidence fixtures (optional runtime path)
    └── review_manifest.json     # NEW: review currency for annotation + rubric reviews

tests/
├── test_witness_rule.py         # NEW: FV-SPEC-067–077 hooks
├── conftest.py                  # Extended with P0-6 path constants
└── fixtures/
    └── witness_rule/            # NEW: follows access_profile fixture layout
        ├── valid/
        ├── invalid/
        └── baselines/
```

**Structure Decision**: Follows P0-4 access-profile pattern — Markdown + YAML frontmatter normative artifact, thin CLI dispatch in `validate_spec.py`, full engine in `tools/witness_rule_validator.py`, fixtures under `tests/fixtures/witness_rule/` (repo convention; maps to requirements’ `tests/fixtures/p0_6/`), supporting reviews under `.factverify/witness/`.

## Complexity Tracking

> No constitution violations requiring justification.
