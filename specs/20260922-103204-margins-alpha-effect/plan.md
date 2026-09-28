# Implementation Plan: P0-5 Alpha and Practical Effect Size

**Branch**: `20260922-103204-margins-alpha-effect` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260922-103204-margins-alpha-effect/spec.md`

## Summary

Deliver a validated statistical-policy contract (`.factverify/spec/margins.yaml`) for error tolerances, practical improvement, calibration selection, uncertainty, channel/locality margins, and sample-size handoff. The validator extends `tools/validate_spec.py` with `--scope margins` and 10 new validation rules (FV-SPEC-057 through FV-SPEC-066). All validation is offline — zero model inference, GPU jobs, threshold fitting, or empirical bootstrap. Numeric policy values remain open behind blocking decisions; the artifact and validator are built against named fields and decision IDs, never against illustrative literals as frozen truth.

## Technical Context

**Language/Version**: Python 3.11 (managed by `uv`)
**Primary Dependencies**: PyYAML (YAML parsing), click (CLI), hashlib (digests), math (finite checks)
**Storage**: YAML (`margins.yaml`), JSON (approval records, reports, fixtures)
**Testing**: pytest with named hooks `test_fv_spec_057_*` through `test_fv_spec_066_*`
**Target Platform**: macOS / Linux CLI
**Project Type**: CLI extension of `tools/validate_spec.py`
**Performance Goals**: Offline-only; sub-second validation on spec-sized inputs
**Constraints**: Zero endpoint/model/GPU calls; deterministic given same versioned inputs; fail closed on bad/missing/unresolved normative input; no teaching value becomes a default
**Scale/Scope**: ~10 validation rules, ~10 test classes, synthetic rate/bound fixtures, ~17 open blocking decisions (D-01–D-16, D-38)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Spec Is Frozen (I8) | PASS | P0-5 contributes `margins.yaml` to `spec-v1`. Not yet frozen. Fail-closed: null/unknown/non-finite/mixed units → nonzero exit. Unresolved normative fields remain explicit, never silently zeroed. |
| 2. No Result-Dependent Choices | PASS | Calibration selection is declared calibration-only; final-test inputs rejected for selection. Practical-success and FRR-cap policies require predeclared approval, not variance-derived invention. |
| 3. Final Test Runs Once | N/A | P0-5 validates policy artifacts; does not run experiments. |
| 4. Equal Query Budgets (I4) | PASS | Practical-success comparisons require declared common cap/budget from P0-3 `attacks.yaml` for both baseline arms. |
| 5. Seeded and Config-Driven | PASS | All quantities live in `margins.yaml` fields and decision IDs; illustrative 0.05 is never hard-coded as approved policy. |
| 6. Ledger Everything | N/A | Offline spec validation; ledger is P2-5. |
| 7. Gates Are Stop Points | PASS | Blocking decisions D-01–D-16, D-38 documented; no requirement reaches `implemented` while blocked. Strict readiness fails on unresolved applicable decisions. |
| 8. Wiki Governs Design | PASS | Design from P0-5 Study Guide §§2–15, handbook V17/V20, FV-SPEC-P0-5; code follows fields, not teaching examples. |
| 9. Equivalence and Inference Never Mix (I2) | PASS | Estimand definitions keep genuine-rejection (FRR) and fake-acceptance (FCR) denominators separate; status mappings for non-identifiable/incomplete are explicit. |
| 10. Claims Never Exceed the Channel (I3) | PASS | Channel/locality margins required per enabled channel and retained bucket; aggregate cannot conceal local damage. |
| 11. Raw Maxima Are Never Verdicts (I5) | PASS | Zero observed errors ≠ zero uncertainty; UCB(FRR) ≤ α for selection; empty denominators undefined. |
| 12. Prompts Are Not Replicates (I7) | PASS | Uncertainty contract rejects row-wise independent resampling of correlated prompts; paired checkpoint-by-fact structure required. |

No violations. Gate passes.

### Post-design re-check

Same table still PASS after Phase 1. Design keeps empirical bootstrap (P2-6) and calibration/power runs (P4) out of scope; P0-5 only declares the analysis/power *contract* and validates it offline.

## Project Structure

### Documentation (this feature)

```text
specs/20260922-103204-margins-alpha-effect/
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
├── validate_spec.py          # CLI entry — extended with --scope margins
└── margins_validator.py      # NEW: P0-5 validation engine (mirrors access_profile_validator.py)

.factverify/
├── spec/
│   └── margins.yaml          # NEW: P0-5 deliverable (normative statistical policy)
└── margins/
    ├── approvals/            # NEW: FRR-cap and practical-success approval records
    └── review_manifest.json  # NEW: review currency for approvals/procedures

tests/
├── test_margins_spec.py      # NEW: FV-SPEC-057–066 hooks
├── conftest.py               # Extended with P0-5 path constants
└── fixtures/
    └── margins_spec/         # NEW: follows attack_spec / access_profile pattern
        ├── valid/
        ├── invalid/
        └── baselines/
```

**Structure Decision**: Follows P0-1–P0-4 pattern — thin CLI dispatch in `validate_spec.py`, full engine in `tools/margins_validator.py`, fixtures under `tests/fixtures/margins_spec/` (repo convention; maps to requirements’ `tests/fixtures/p0_5/`), normative artifact at `.factverify/spec/margins.yaml`, supporting approvals under `.factverify/margins/`.

## Complexity Tracking

> No constitution violations requiring justification.
