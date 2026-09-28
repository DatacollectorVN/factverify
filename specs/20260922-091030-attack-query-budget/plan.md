# Implementation Plan: P0-3 Attack Family and Per-Channel Query Budget

**Branch**: `20260922-091030-attack-query-budget` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260922-091030-attack-query-budget/spec.md`

## Summary

Deliver a validated attack-policy specification (`attacks.yaml`) defining permitted channels, three-evaluator-arm allocations, per-channel budgets, accounting rules, adaptive policies, transformation recipes, and clue audits. The validator extends `tools/validate_spec.py` with `--scope attacks` and 13 new validation rules (FV-SPEC-034 through FV-SPEC-046). All validation is offline — zero model calls, GPU jobs, or training.

## Technical Context

**Language/Version**: Python 3.11 (managed by `uv`)
**Primary Dependencies**: PyYAML (YAML parsing), jsonschema (structural validation), referencing (schema resolution), click (CLI)
**Storage**: YAML (attacks.yaml spec artifact), JSON (reports, fixtures, manifests)
**Testing**: pytest with named test hooks `test_fv_spec_034_*` through `test_fv_spec_046_*`
**Target Platform**: macOS / Linux CLI
**Project Type**: CLI extension of `tools/validate_spec.py`
**Performance Goals**: Offline-only; sub-second validation on spec-sized inputs
**Constraints**: Zero model calls; deterministic given same versioned inputs; fail closed on bad/missing input
**Scale/Scope**: ~8 channels, 3 evaluator arms, ~13 validation rules, ~13 test classes

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Spec Is Frozen (I8) | PASS | P0-3 contributes to `spec-v1`; attacks.yaml is a normative artifact under `.factverify/spec/`. Not yet frozen. |
| 2. No Result-Dependent Choices | PASS | All parameters are declared before outcomes. Adaptive policies require predeclared search/stop rules. |
| 3. Final Test Runs Once | N/A | P0-3 validates spec; does not run tests. |
| 4. Equal Query Budgets (I4) | PASS | Core deliverable: validate matched allocations, cost vectors, per-arm totals. |
| 5. Seeded and Config-Driven | PASS | All values come from attacks.yaml fields and decision IDs, never literals. |
| 6. Ledger Everything | N/A | P0-3 is offline spec validation; ledger is P2-5. |
| 7. Gates Are Stop Points | PASS | 14 blocking decisions documented; no requirement reaches `implemented` while blocked. |
| 8. Wiki Governs Design | PASS | Design from P0-3 Study Guide and handbook; code follows spec. |
| 9. Equivalence and Inference Never Mix (I2) | PASS | Clue audit (FV-SPEC-041) routes inference-bearing inputs away from equivalence recovery. |
| 10. Claims Never Exceed the Channel (I3) | PASS | Channel permissions validated against access profile (FV-SPEC-035). |
| 11. Raw Maxima Are Never Verdicts (I5) | N/A | P0-3 is budget/policy; verdicts are P0-6. |
| 12. Prompts Are Not Replicates (I7) | PASS | Accounting units distinguish trials from completions (FV-SPEC-036). |

No violations. Gate passes.

## Project Structure

### Documentation (this feature)

```text
specs/20260922-091030-attack-query-budget/
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
├── validate_spec.py             # CLI entry point — extended with --scope attacks
└── attack_validator.py          # NEW: P0-3 validation engine (mirrors closure_validator.py)

.factverify/
├── spec/
│   └── attacks.yaml             # NEW: P0-3 deliverable (frozen spec artifact)
└── attacks/
    ├── event_fixtures.json      # NEW: offline event traces for replay
    ├── audit_manifests/         # NEW: clue audit and recipe manifests
    └── review_manifest.json     # NEW: P0-3 review records

tests/
├── test_attack_spec.py          # NEW: 13 test classes (FV-SPEC-034–046)
├── conftest.py                  # Extended with P0-3 path constants
└── fixtures/
    └── attack_spec/             # NEW: follows fact_contract/, closure_templates/ pattern
        ├── valid/
        ├── invalid/
        └── baselines/

reports/
├── p0-3-validation.json         # NEW: validation report
└── p0-3-review.md               # NEW: review template
```

**Structure Decision**: Follows the P0-1/P0-2 pattern — one validator module per scope (`attack_validator.py`), thin CLI dispatch in `validate_spec.py`, fixtures organized under `tests/fixtures/attack_spec/`.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
