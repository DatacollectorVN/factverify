# Implementation Plan: Readable Decision Identifiers

**Branch**: `20260929-110152-readable-decision-identifiers` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260929-110152-readable-decision-identifiers/spec.md`

## Summary

Replace opaque `D-*` identifiers in all runtime diagnostics with a canonical
dotted semantic key and enrich every error message with the human title,
missing field, and consuming operation. Add a single authoritative catalog at
`config/decisions/catalog.yaml` that maps every legacy ID to its semantic key
and can be queried by either identifier. Write both identifiers into newly
generated ledger rows and verdict records. Enforce catalog uniqueness so future
additions cannot introduce silent collisions.

The work is delivered in four independently testable increments that mirror the
ticket's migration phases:

1. Shared `src/decisions/` module (catalog loader, resolver, diagnostic formatter)
2. Updated per-module error messages to use the shared formatter
3. Dual-ID fields in newly generated output records
4. Catalog integrity validator and deterministic reference document generator

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: PyYAML ≥ 6.0 (already declared), jsonschema ≥ 4.23 (already declared), referencing ≥ 0.37.0 (already declared), click ≥ 8.0 (already declared)
**Storage**: YAML files (`config/decisions/catalog.yaml`; existing per-module decision YAML files unchanged), SQLite (ledger rows gain a `decision_key` column)
**Testing**: pytest ≥ 8.0 (already declared)
**Target Platform**: Local development / Linux CI (same as rest of project)
**Project Type**: Internal library module within the FactVerify research pipeline
**Performance Goals**: Decision resolution happens once at config-load time; no throughput target
**Constraints**: Must not modify any file under `.factverify/spec/` or `spec-unlearning/`; existing legacy-only YAML decision files must continue to parse without error; reference document generation must be fully deterministic
**Scale/Scope**: ~67 legacy D-* references across 7 source modules; 69 catalog entries (D-01 through D-69 with gaps/collisions)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|-----------|-------|--------|
| 1 · Spec Is Frozen | catalog lives at `config/decisions/`, not under `.factverify/spec/`; no frozen artifact is touched | ✅ Pass |
| 2 · No Result-Dependent Choices | catalog is metadata; no statistical choice is made | ✅ Pass |
| 3 · Final Test Runs Once | N/A — no test-split logic | ✅ Pass |
| 4 · Equal Query Budgets | N/A — no evaluator queries | ✅ Pass |
| 5 · Seeded and Config-Driven | catalog is config-driven; no magic numbers introduced | ✅ Pass |
| 6 · Ledger Everything | FR-004 requires both IDs in ledger rows; ledger schema update included | ✅ Pass |
| 7 · Gates Are Stop Points | N/A — no study gates in this feature | ✅ Pass |
| 8 · Wiki Governs Design | ticket is sufficiently detailed; Obsidian note `02-Concepts/` contains no additional constraints on decision naming | ✅ Pass |
| 9–12 · Protocol integrity | N/A — no closure, probe, or evaluation logic | ✅ Pass |
| 13 · Code Quality | all new code must pass `ruff check` + `ruff format --check`; full type annotations required | ✅ Applies |
| 14 · Decision Identification | this feature IS the implementation of Principle 14 | ✅ Applies |

No violations. No Complexity Tracking entry required.

## Project Structure

### Documentation (this feature)

```text
specs/20260929-110152-readable-decision-identifiers/
├── plan.md              # This file
├── research.md          # Phase 0 findings
├── data-model.md        # Entity model for catalog entries and diagnostics
├── quickstart.md        # Developer usage guide
├── contracts/
│   └── decisions-api.md # Public interface for src/decisions/
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code (repository root)

```text
src/
├── decisions/                       [NEW — shared decision module]
│   ├── __init__.py
│   ├── catalog.py                   [load + uniqueness-validate catalog.yaml]
│   ├── diagnostic.py                [DecisionDiagnostic → formatted str]
│   ├── errors.py                    [DecisionError]
│   ├── resolver.py                  [lookup by semantic key or legacy ID]
│   └── types.py                     [DecisionCatalogEntry, DecisionDiagnostic]
├── data/
│   └── decisions.py                 [UPDATED — use shared diagnostic]
├── stats/
│   └── decisions.py                 [UPDATED — use shared diagnostic]
├── controls/
│   └── decisions.py                 [UPDATED — use shared diagnostic]
├── cache/
│   └── decisions.py                 [UPDATED — use shared diagnostic]
├── ledger/
│   ├── api.py                       [UPDATED — dual-ID in checkpoint rows]
│   └── decisions.py                 [UPDATED — use shared diagnostic]
└── eval/
    └── spec_load.py                 [UPDATED — require_closed uses semantic keys]

config/
└── decisions/
    └── catalog.yaml                 [NEW — 69-entry canonical catalog]

tools/
└── generate_decision_ref.py         [NEW — deterministic reference doc generator]

tests/
├── unit/
│   ├── test_decisions_catalog.py    [NEW — load, uniqueness, collision detection]
│   ├── test_decisions_diagnostic.py [NEW — formatted output verification]
│   └── test_decisions_resolver.py   [NEW — by key, by id, not-found paths]
├── integration/
│   ├── test_data_decisions.py       [NEW — updated error message format]
│   └── test_generate_decision_ref.py [NEW — determinism check]
└── fixtures/
    └── decisions/
        ├── catalog_valid.yaml       [NEW — minimal valid 3-entry catalog]
        ├── catalog_dup_key.yaml     [NEW — triggers key uniqueness violation]
        └── catalog_dup_legacy.yaml  [NEW — triggers legacy ID collision]
```

**Structure Decision**: Single-project layout extending the existing `src/` tree.
A new top-level `src/decisions/` package provides the shared layer; all
per-module `decisions.py` files remain in place and gain imports from it. The
catalog lives under a new `config/decisions/` directory that is outside the
frozen spec namespace.
