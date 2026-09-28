# Implementation Plan: P0-1 Atomic-Fact Contract Schema

**Branch**: `20260921-211249-fact-contract-schema` | **Date**: 2026-09-21 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260921-211249-fact-contract-schema/spec.md`

## Summary

Implement the P0-1 atomic-fact contract schema — a Draft 2020-12 JSON Schema plus a scoped validation tool and two demonstration contract instances. This is the first Phase 0 artifact: it defines the semantic boundary that every downstream component (P0-2 closure templates, Phase 1 datasets, evaluators) depends on. The implementation produces `fact_contract.schema.json`, a CLI validator (`tools/validate_spec.py --scope fact-contract`), demonstration contracts, and a pytest suite with named hooks tracing to FV-SPEC-001 through FV-SPEC-015.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: `jsonschema` (Draft 2020-12 support), `referencing` (schema resolution), `click` (CLI)
**Storage**: JSON files (schema, contracts, reports)
**Testing**: pytest
**Target Platform**: macOS / Linux (developer workstation, CI)
**Project Type**: CLI tool + data schema
**Performance Goals**: N/A (offline validation of small JSON files)
**Constraints**: Offline only — no network calls, no GPU, no model execution during validation
**Scale/Scope**: 2 demonstration contracts initially; ~100 contracts at dataset scale in Phase 1

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | This ticket *creates* the schema for the freeze; it does not edit a frozen artifact. Validator implements fail-closed semantics (FR-011). |
| 2 | No Result-Dependent Choices | ✅ PASS | Schema structure is fixed before any experimental data exists. |
| 3 | Final Test Runs Once | ✅ N/A | No experimental runs in this component. |
| 4 | Equal Query Budgets (I4) | ✅ N/A | No evaluator queries in this component. |
| 5 | Seeded and Config-Driven | ✅ PASS | Validation is deterministic; no randomness involved. |
| 6 | Ledger Everything | ✅ N/A | No checkpoints produced. |
| 7 | Gates Are Stop Points | ✅ N/A | No gates in this component. |
| 8 | Wiki Governs Design | ✅ PASS | Schema derived from P0-1 study guide §2.5.4; changes require recorded rationale. |
| 9 | Equivalence and Inference Never Mix (I2) | ✅ PASS | Clue boundary (FR-009) enforces the separation at the contract level. |
| 10 | Claims Never Exceed the Channel (I3) | ✅ N/A | No experimental claims in this component. |
| 11 | Raw Maxima Are Never Verdicts (I5) | ✅ N/A | No evaluation decisions in this component. |
| 12 | Prompts Are Not Replicates (I7) | ✅ N/A | No prompts or experiments in this component. |

**Gate result**: PASS — no violations.

## Project Structure

### Documentation (this feature)

```text
specs/20260921-211249-fact-contract-schema/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
.factverify/
├── spec/
│   └── fact_contract.schema.json    # The schema (FR-001)
└── contracts/                       # Demonstration instances (FR-012)
    ├── factverify-contract-wd-Q1858-P1376-Q881-v1.json   # Hà Nội
    └── factverify-contract-invented_scientist_alma_mater-v1.json  # Fictional

tools/
└── validate_spec.py                 # Scoped validator CLI (FR-011)

tests/
├── conftest.py                      # Shared fixtures
├── test_contract_schema.py          # 15 named test hooks (FV-SPEC-001–015)
└── fixtures/
    ├── valid/                       # Positive test contracts
    ├── invalid/                     # Negative test contracts (missing fields, bad IDs, etc.)
    └── baselines/                   # Frozen baseline snapshots for revision tests

reports/
├── p0-1-validation.json             # Validator output report
└── p0-1-semantic-review.md          # Two-reader review (FR-014, manual)
```

**Structure Decision**: Single-project layout. The schema lives under `.factverify/spec/` per the constitution's spec namespace. The validator lives under `tools/` per the architecture table. Tests use pytest with fixtures organized by validity.

## Complexity Tracking

> No constitution violations to justify.
