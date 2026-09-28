# Implementation Plan: FV-SPEC — Artifact Namespace Refactor

**Branch**: `20261002-111741-artifact-namespace-refactor` | **Date**: 2026-10-02 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/20261002-111741-artifact-namespace-refactor/spec.md`

## Summary

Refactor FactVerify storage into two namespaces (`.factverify/` for frozen inputs; `.factverify_internal/` for runtime transactions), rename and consolidate the five frozen protocol artifacts, replace Wikidata as the canonical identity authority with FactVerify-native IDs, and retire every legacy interface without a live successor. The model-config split and ledger schema are already implemented; this plan wires the new `src/artifacts/` package, migration tool, layout validator, updated JSON schema, and legacy retirement inventory.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: PyYAML ≥ 6.0, jsonschema + referencing ≥ 4.23/0.37, click ≥ 8.0, hashlib (stdlib), sqlite3 (stdlib), pathlib (stdlib)
**Storage**: SQLite (ledger at `.factverify_internal/ledger.sqlite`), JSON/JSONL (contracts, bundles, manifests, run records), YAML (spec artifacts, model configs)
**Testing**: pytest + pytest-cov; `make test` must pass before any task is complete
**Linting**: ruff (check + format); `make lint` must pass before any task is complete
**Target Platform**: Linux/macOS developer workstation; also CI (GitHub Actions or equivalent)
**Project Type**: CLI tools + Python library package (`src/artifacts/`)
**Performance Goals**: All namespace checks (layout validation, preflight, ledger registration) must complete without any model call — no GPU resources required
**Constraints**: Fail closed on any missing or unresolved spec field; interrupted migration must leave the source tree unchanged
**Scale/Scope**: ~25 legacy artifacts to migrate; ~30 affected source files to update; 4 new test modules (~16 test functions from the verification matrix)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| 1. Spec Is Frozen | **PASS** | `spec-v1` tag does not exist (`git tag -l` empty). Pre-freeze layout changes are permitted without amendment. |
| 2. No Result-Dependent Choices | **PASS** | This is a structural refactor. No thresholds or parameters are changed. |
| 3. Final Test Runs Once | **PASS** | Final-test pass has not occurred. Not affected. |
| 4. Equal Query Budgets | **PASS** | No evaluator code is changed in this refactor. Budget accountant is unaffected. |
| 5. Seeded and Config-Driven | **PASS** | Roots are environment/CLI-configurable (FR-035). No magic paths in code after cutover. |
| 6. Ledger Everything | **PASS** | Ledger moves to `.factverify_internal/ledger.sqlite` via layout resolver. Schema already has required columns. |
| 7. Gates Are Stop Points | **PASS** | Research Finding 6 (protocol.yaml consolidation structure) is flagged as a stop point requiring Nathan's approval before the migration tool is written. |
| 8. Wiki Governs Design | **PASS** | D-71 and D-72 are owner-resolved decisions documented in the requirements spec. |
| 13. PEP 8, Type Annotations, Ruff | **MUST ENFORCE** | All new code in `src/artifacts/` and `tools/` must carry full type annotations. `ruff check` and `ruff format --check` must pass. |
| 14. Decision Identification | **ACTION REQUIRED** | D-71 (`artifacts.namespace.boundary`) and D-72 (`artifacts.identity.authority`) must be added to `config/decisions/catalog.yaml` as part of this implementation. |

**Constitution Check post-design**: Re-evaluate after Phase 1. No violations found in design phase.

## Project Structure

### Documentation (this feature)

```text
specs/20261002-111741-artifact-namespace-refactor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli-contracts.md # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
# New package
src/artifacts/
├── __init__.py
├── layout.py            # LayoutRoots resolver, ArtifactClass enum (FV-SPEC-096, 097, 100)
├── store.py             # Runtime artifact writer + ledger guard (FV-SPEC-100, 101, 107)
├── preflight.py         # Run preflight guard (FV-SPEC-104)
├── run_bundle.py        # Run bundle management (FV-SPEC-102)
├── refs.py              # External blob references (FV-SPEC-103)
└── export.py            # Portable reproduction snapshot (FV-SPEC-106)

# New data module
src/data/
└── fact_bundle.py       # FactCaseBundle loader/validator (FV-SPEC-099)

# New tools
tools/
├── validate_layout.py   # Layout validator CLI (FV-SPEC-097, 098, 100, 111)
└── migrate_artifacts.py # Migration command (FV-SPEC-105)

# Updated namespace artifacts
.factverify/
├── protocol.yaml        # NEW — consolidated normative spec (replaces attacks, margins, access_profile, witness_rule, preregistration body)
├── templates.yaml       # RENAME from spec/closure_templates.yaml
├── model_policy.yaml    # MOVE from spec/model_policy.yaml
├── fact.schema.json     # RENAME+UPDATE from spec/fact_contract.schema.json
├── FREEZE.json          # NEW — replaces CHECKSUMS.sha256 + reports/spec-v1-freeze-receipt.json
└── facts/               # NEW directory — fact case bundles
    └── <fact_id>/
        ├── contract.json
        ├── sources.jsonl
        ├── neighbourhood.jsonl
        ├── prompts.jsonl
        └── manifest.json

# Updated tools
tools/
├── freeze.py            # REFACTOR — update SPEC_ARTIFACTS, FREEZE.json target, paths
├── models_validator.py  # REFACTOR — remove models.yaml references
└── preregistration_validator.py  # REFACTOR — update spec path references

# Updated configuration
config/decisions/
└── catalog.yaml         # ADD D-71 (artifacts.namespace.boundary) and D-72 (artifacts.identity.authority)

# Updated tests
tests/
├── test_artifact_layout.py     # NEW — FV-SPEC-096, 097, 098, 100, 101, 102, 103, 104, 107, 110
├── test_fact_bundle.py         # NEW — FV-SPEC-099
├── test_artifact_migration.py  # NEW — FV-SPEC-105, 111
├── test_artifact_export.py     # NEW — FV-SPEC-106
├── test_contract_schema.py     # UPDATE — FV-SPEC-108, 109
└── test_models_spec.py         # UPDATE — remove legacy load_model_spec test
```

**Source files requiring path-reference updates** (FV-SPEC-111 legacy retirement):
- `src/models/spec.py` — delete legacy `load_model_spec()` function (reads `models.yaml`)
- `src/models/loader.py` — update spec_root references
- `src/data/spec_readers.py` — update spec_root references
- `src/eval/spec_load.py`, `src/eval/store.py`, `src/eval/run.py`
- `src/controls/spec_load.py`, `src/controls/run.py`
- `src/stats/io.py`, `src/stats/thresholds.py`, `src/stats/bootstrap.py`, `src/stats/report.py`
- `src/cache/store.py`
- `src/train/run.py`
- `tools/witness_rule_validator.py`
- `tests/test_contract_schema.py`, `tests/test_model_config.py`, `tests/test_models_spec.py`, `tests/conftest.py`

## Complexity Tracking

> No constitution violations requiring justification.

## Open Decision Required Before Implementation

**Finding 6 from research.md**: The consolidation structure for `protocol.yaml` is not fully specified. The following mapping is proposed — Nathan must confirm before `tools/migrate_artifacts.py` is written:

| Current file | Proposed target |
|---|---|
| `spec/fact_contract.schema.json` | `.factverify/fact.schema.json` (rename + schema update) |
| `spec/closure_templates.yaml` | `.factverify/templates.yaml` (rename only) |
| `spec/model_policy.yaml` | `.factverify/model_policy.yaml` (path-only move) |
| `spec/attacks.yaml` | Absorbed into `.factverify/protocol.yaml` |
| `spec/margins.yaml` | Absorbed into `.factverify/protocol.yaml` |
| `spec/access_profile.md` | Absorbed into `.factverify/protocol.yaml` |
| `spec/witness_rule.md` | Absorbed into `.factverify/protocol.yaml` |
| `spec/preregistration.md` | Registration metadata → `FREEZE.json`; scientific rationale text → `protocol.yaml` body |
| `.factverify/contracts/` | Migrated to `.factverify/facts/<fact_id>/contract.json` per bundle |
| `.factverify/closure/`, `access/`, `attacks/`, `margins/`, `witness/`, `exposure/`, `milestones/`, `decisions/` | Each entry either absorbed into target artifacts, archived in `FREEZE.json.decisions`, or deleted |

**Action**: Confirm this mapping (or provide corrections) before `/speckit.tasks` is run.
