# Implementation Plan: P1 Fact Bundle Preparation

**Branch**: `20260928-224019-p1-bundle-prep` | **Date**: 2026-09-28 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/20260928-224019-p1-bundle-prep/spec.md`

## Summary

Build three data-preparation scripts that complete the Stage A fact corpus before Phase 3 (Block 0 pilot) training begins: `build_bundles.py` (P1-3) enumerates source bundles and leave-out manifests from TOFU; `build_neighbourhoods.py` (P1-5) replaces all neighbourhood stubs with sourced retain probes; and `entailment_audit.py` (P1-4) verifies that no retained training record expresses or entails any target fact. All scripts are CPU-only except the P1-4 LLM entailment screen. Open decisions D-38, D-39, D-42, D-66, D-67, D-69 are resolved in research.md with provisional Block-0 values.

## Technical Context

**Language/Version**: Python 3.11 (managed by uv)
**Primary Dependencies**: PyYAML (spec parsing), jsonschema + referencing (contract validation), click (CLI), hashlib stdlib (digests), anthropic SDK (P1-4 LLM judge only)
**Storage**: JSONL files (records, index, neighbourhoods, audit), JSON files (bundles, manifests), Markdown (reports)
**Testing**: pytest (`tests/test_bundles.py`, `tests/test_neighbourhoods.py`, `tests/test_entailment_audit.py`)
**Target Platform**: macOS / Linux local machine (no GPU required)
**Project Type**: Research data pipeline — three CLI scripts
**Performance Goals**: All three scripts complete on ~35 Block-0 facts in < 5 minutes wall-clock (excluding LLM API latency for P1-4)
**Constraints**: CPU-only for P1-3 and P1-5; P1-4 LLM calls must use the existing reviewer_response_cache pattern for reproducibility; all outputs deterministic given fixed seed
**Scale/Scope**: Block 0 pilot — ~35 facts, ~200 training records, ~35 leave-out manifests

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I8 — Spec Is Frozen / Fail Closed** | ✅ PASS | Scripts read `.factverify/spec/closure_templates.yaml` for template-group disjointness; refuse on missing or unresolved spec fields |
| **No Result-Dependent Choices** | ✅ PASS | Bundles built only for facts with `pass` gate verdict; thresholds come from spec/config not code |
| **Final Test Runs Once** | ✅ N/A | Data preparation phase; no evaluation split is touched |
| **I4 — Equal Query Budgets** | ✅ PASS | P1-3 and P1-5 make zero model queries; P1-4 LLM calls are data-preparation cost, not evaluation budget — cached via reviewer_response_cache pattern |
| **Seeded and Config-Driven** | ✅ PASS | D-66 minimum, D-38 minimum, D-67 sample fraction read from spec config; no magic numbers in scripts |
| **Ledger Everything** | ✅ N/A | No model checkpoints produced; audit LLM calls logged in cache; build artifacts are data, not checkpoints |
| **Gates Are Stop Points** | ✅ PASS | P1-4 audit is itself a gate — confirmed failures block Phase 3 training |
| **Wiki Governs Design** | ✅ PASS | Design drawn from FV-DATA-P1-3, P1-4, P1-5 requirement notes; all decisions cited |
| **I2 — Equivalence/Inference Never Mix** | ✅ PASS | FR-003 (training-wording disjointness) enforced by template-group check against closure_templates.yaml |
| **I3 — Claims Never Exceed Channel** | ✅ N/A | No claims made; data preparation only |
| **I5 — Raw Maxima Not Verdicts** | ✅ N/A | No probe verdicts; entailment audit uses binary flag + human adjudication |
| **I7 — Prompts Not Replicates** | ✅ N/A | No statistical analysis in this feature |
| **Code Quality** | ✅ REQUIRED | PEP 8, full type annotations, ruff check + ruff format must pass; enforced by make lint |

**Post-design re-check**: All principles pass. No violations to justify.

## Project Structure

### Documentation (this feature)

```text
specs/20260928-224019-p1-bundle-prep/
├── plan.md              # This file
├── research.md          # Phase 0 — open decisions resolved
├── data-model.md        # Phase 1 — entities and file layout
├── quickstart.md        # Phase 1 — how to run the three scripts
└── tasks.md             # Phase 2 output (/speckit.tasks — not yet created)
```

### Source Code

```text
scripts/
├── build_bundles.py         # P1-3: source bundles + leave-out manifests (NEW)
├── build_neighbourhoods.py  # P1-5: replace neighbourhood stubs (NEW)
└── entailment_audit.py      # P1-4: duplication + entailment screen (NEW)

src/data/
└── tofu.py                  # existing — may need small extensions for index queries

data/controlled/
├── facts.jsonl              # input (existing)
├── sources/
│   ├── records.jsonl        # output: all training records
│   ├── index.jsonl          # output: record → fact IDs
│   └── bundles/             # output: one JSON per fact
└── leaveout/                # output: one JSON per fact

data/controlled/
└── neighbourhoods.jsonl     # output: neighbourhood items (all facts)

data/tofu_derived/
└── transformations.jsonl    # appended by build_bundles.py

results/
└── entailment_audit.jsonl   # output: per (unit, record) audit rows

reports/
└── entailment_audit.md      # output: human-readable audit summary

tests/
├── test_bundles.py          # NEW: FV-DATA-019–024 + 018 guard
├── test_neighbourhoods.py   # NEW: FV-DATA-030–034
└── test_entailment_audit.py # NEW: FV-DATA-025–029
```

**Structure Decision**: Single-project layout following existing repo conventions. New scripts in `scripts/`, new tests in `tests/`, output artifacts in `data/controlled/` and `results/`. No new `src/` modules unless `src/data/tofu.py` extensions are needed for index queries.
