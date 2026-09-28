# Implementation Plan: P0-2 Closure Template Suite

**Feature**: `20260921-235511-closure-template-suite` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260921-235511-closure-template-suite/spec.md`

## Summary

Deliver a finite, versioned prompt suite (closure_templates.yaml) that separates equivalence, inference, retained controls, and excluded cases before evaluation. Extend the existing validator CLI with `--scope closure-templates` to structurally validate the suite, its contract bindings, template group/split isolation, verification balance, and review records. Ship demonstration fixtures and regression tests for 18 requirements (FV-SPEC-016 through FV-SPEC-033).

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: PyYAML (YAML parsing), jsonschema (structural validation), referencing (schema resolution), click (CLI)
**Storage**: YAML (closure artifact), JSON (bindings, review manifest, reports), JSONL (previews)
**Testing**: pytest
**Target Platform**: Local development / CI
**Project Type**: CLI validation tool (extension of existing `tools/validate_spec.py`)
**Performance Goals**: Offline validation — zero model calls or GPU jobs
**Constraints**: Deterministic rendering (C-1), fail closed (C-4), split isolation (C-5), upstream compatibility (C-6)
**Scale/Scope**: ~50–100 templates per demonstration suite, 2 contracts, 6 families, 3 splits

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8) | PASS | Suite lives at `.factverify/spec/closure_templates.yaml` — the resolved spec root. Fail-closed validation enforced (FV-SPEC-032). |
| 2 | No Result-Dependent Choices | PASS | Group/split assignments frozen before outcomes. Template groups (not just strings) disjoint from calibration (FV-SPEC-023). |
| 3 | Final Test Runs Once | PASS | `--split final_test` requires explicit flag. Preview only renders selected split. |
| 4 | Equal Query Budgets (I4) | PASS (deferred) | Budget accounting is P0-3 scope. P0-2 lists it as deferred in reports. |
| 5 | Seeded and Config-Driven | PASS | Template IDs stable. Rendering deterministic. No randomness in validation. |
| 6 | Ledger Everything | PASS (deferred) | Ledger is P2-5 scope. P0-2 does not produce checkpoints. |
| 7 | Gates Are Stop Points | PASS | Strict mode blocks handoff on unresolved decisions. |
| 8 | Wiki Governs Design | PASS | Design drawn from P0-2 Study Guide §§3–11 and handbook §4/V05–V13. |
| 9 | E and I Never Mix (I2) | PASS | FV-SPEC-017 enforces routing. FV-SPEC-018/019 enforce premise rules. Core design constraint. |
| 10 | Claims Never Exceed Channel (I3) | PASS (deferred) | Access profiles are P0-4 scope. |
| 11 | Raw Maxima Never Verdicts (I5) | PASS (deferred) | Witness rule is P0-6 scope. |
| 12 | Prompts Not Replicates (I7) | PASS | FV-SPEC-022 enforces unique identities. Overlapping attributes recorded, not counted as separate templates. |

All 12 principles pass (4 deferred to downstream components as designed).

## Project Structure

### Documentation (this feature)

```text
specs/20260921-235511-closure-template-suite/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── validator-interface.md
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
.factverify/
├── spec/
│   ├── fact_contract.schema.json    # P0-1 (existing)
│   └── closure_templates.yaml       # P0-2 (new)
├── contracts/                        # P0-1 contracts (existing)
├── closure/
│   ├── instance_bindings.json       # P0-2 (new)
│   └── review_manifest.json         # P0-2 (new)

tools/
└── validate_spec.py                 # Extended with --scope closure-templates

tests/
├── test_contract_schema.py          # P0-1 (existing, unchanged)
├── test_closure_templates.py        # P0-2 (new)
├── conftest.py                      # Extended with P0-2 constants
└── fixtures/
    ├── valid/                        # P0-1 fixtures (existing)
    ├── invalid/                      # P0-1 fixtures (existing)
    ├── baselines/                    # P0-1 baselines (existing)
    └── p0_2/
        ├── valid/                    # P0-2 valid fixtures
        ├── invalid/                  # P0-2 invalid fixtures
        └── baselines/               # P0-2 baseline fixtures

reports/
├── p0-1-validation.json             # Existing
├── p0-2-validation.json             # New
├── p0-2-construction-preview.jsonl  # New
├── p0-2-semantic-review.md          # New
└── p0-1-semantic-review.md          # Existing
```

**Structure Decision**: Extends the existing P0-1 layout. New closure artifacts go under `.factverify/closure/` (separate from the frozen spec namespace at `.factverify/spec/`). The validator is extended, not duplicated. P0-2 test fixtures are namespaced under `tests/fixtures/p0_2/`.

## Complexity Tracking

No constitution violations. No complexity justifications needed.
