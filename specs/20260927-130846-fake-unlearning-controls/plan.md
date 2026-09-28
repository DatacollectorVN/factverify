# Implementation Plan: FV-CTRL — P2-3 Fake-Unlearning Controls

**Branch**: `20260927-130846-fake-unlearning-controls` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)  
**Source**: `second-brain/ml-unlearning/requirements/FV-CTRL — P2-3.md` (draft)

## Summary

`build_control` turns one control configuration into a labelled negative system on the finetuned parent for that fact. The catalog has one registered implementation for each of the eight plan families, plus the untouched model as a ninth family whose build stays refused until D-61 records a mechanism layer. Severity is stored on the label and is not applied. Suppression and destruction checks accept a control only when a closed decision record and the frozen margins say so. Wrapper queries go through the existing eval `Gateway`, so they are charged as plain model calls.

D-53, D-54, D-55, and D-61 stay open. A study run pointed at an open decision record refuses the check or the certification that decision blocks. Fixture records close only the decision a hook needs. Nothing under `.factverify/spec/` is edited. `src/controls/match.py` is P2-4 and is not created here. SQLite stays in P2-5. Weight-update algorithms stay in `src/train/`.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyYAML (control config and spec artifacts), hashlib (config and artifact digests). Model calls go through the existing eval `Gateway` and `ModelPort`. Checkpoint loading stays in `load_model` (P2-0). Weight updates stay in `src/train/` behind a `TrainerPort`. No `from_pretrained` in `src/controls/`.  
**Storage**: Control labels as `control.json` next to the artifact. Rejection and unchecked records as JSON. Ledger rows through a `ControlLedgerPort`; no new SQLite database (P2-5). Decision records are caller-supplied YAML outside `.factverify/spec/`.  
**Testing**: pytest. Named hooks `tests/test_controls.py::test_fv_ctrl_001_family_coverage` through `test_fv_ctrl_010_wrapper_charged`. Fixture spec roots and decision records under `tests/fixtures/controls/`. No GPU and no weight download.  
**Target Platform**: Linux GPU for later study builds; CPU fixtures for these hooks  
**Project Type**: Internal Python library plus CLI (`python -m src.controls.run`) inside the study harness  
**Performance Goals**: Wall-clock, GPU-hours, and peak memory are recorded per control build. This plan sets no numeric stop.  
**Constraints**: Fail closed (I8). No magic numbers. Do not edit `.factverify/spec/`. D-53, D-54, D-55, and D-61 stay open. Severity is stored and not searched (P2-4). PEP 8, full type annotations, ruff. `make lint` and `make test` before implementation is complete.  
**Scale/Scope**: Nine families, one registered implementation each. Downstream: P2-4 behaviour matching, P3-2 pilot subset, P4-2 control matrix. Evaluators, ledger storage, and weight-update algorithms are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Design notes were read from disk. The Obsidian MCP server is not available in this session.

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | `build_control` takes an explicit `spec_root`. Missing files, null locality margins, and unresolved decision records raise before an accepted label is published. The package never writes `.factverify/spec/`. |
| 2 | No Result-Dependent Choices | ✅ PASS | Severity is copied onto the label and never searched. Builds refuse evaluator scores and verdicts. Implementation ids cannot sit on both calibration and final test. Tolerances come from a closed decision record, not from the outcome. |
| 3 | Final Test Runs Once | ✅ PASS | This package does not run the final-test pass and does not resume one. It only refuses a shared implementation id across calibration and final test. |
| 4 | Equal Query Budgets (I4) | ✅ PASS | Refusal and output-filter ports are served through `src.eval.gateway.Gateway`. One evaluator query is one accountant charge. The unwrapped parent is not exposed. Other families use the same serve path. |
| 5 | Seeded and Config-Driven | ✅ PASS | Seed and severity are required config fields. No study tolerance, cap, or refusal phrase is hardcoded. Digest comparison applies a tolerance only when D-53 is closed and the tolerance string is `0`. |
| 6 | Ledger Everything | ✅ PASS | An accepted build commits a row with role `control`, family, parent id, and cost. SQLite writes stay in P2-5. A missing port refuses the build. |
| 7 | Gates Are Stop Points | ✅ PASS | No Gate 1 loosening and no severity search. P2-4 owns matching. A failed retention or locality check rejects the control and records the rejection. |
| 8 | Wiki Governs Design | ✅ PASS | Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-3, and "Phase 3 — Block 0", Gate 1. Fake-Unlearning Controls (status: draft), "Definition" and "How It Works". Handbook (status: draft), "5.1 Where the boundary sits" and "5.2 The identifiability argument". FV-CTRL P2-3 and P2-4 are draft. |
| 9 | Equivalence and Inference Never Mix (I2) | ✅ PASS | This package does not score equivalence or inference probes. Template-specific suppression takes caller-supplied group ids and does not assign groups. |
| 10 | Claims Never Exceed the Channel (I3) | ✅ PASS | An output-filter control under Profile A is labelled `structurally_indistinguishable`. No other family is given an inferred identifiability flag. |
| 11 | Raw Maxima Are Never Verdicts (I5) | ✅ PASS | This package does not emit evaluator verdicts. |
| 12 | Prompts Are Not Replicates (I7) | ✅ PASS | One build is one control on one parent checkpoint and one fact. Direct-QA probes used by a caller-supplied behavior port are nested measurements, not extra controls. |
| 13 | Code Quality | ✅ PASS | New modules under `src/controls/` and `tests/test_controls.py` carry annotations and pass ruff. `make lint` and `make test` are the completion bar. |

**All applicable gates pass. No violations.** Post-design re-check: the ledger port, the trainer port, the behavior port, and the decision-record file do not add a gate violation. The four decisions below remain open on purpose. `src/controls/match.py` is specified as not created.

## Project Structure

### Documentation (this feature)

```text
specs/20260927-130846-fake-unlearning-controls/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── build_control.md
│   ├── control_label.md
│   └── serve.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/controls/
├── __init__.py          # exports: build_control, load_control, compare_builds, ControlError
├── errors.py
├── config.py            # fail-closed config load
├── decisions.py         # D-53, D-54, D-55, D-61 records
├── spec_load.py         # margins.yaml locality block and access_profile.md
├── registry.py          # FV-CTRL-001, FV-CTRL-006
├── base.py              # FV-CTRL-002, FV-CTRL-003 — label and mechanism layer
├── ledger.py            # ControlLedgerPort; no SQLite
├── build.py             # FV-CTRL-007, FV-CTRL-008, FV-CTRL-009
├── checks.py            # retention and locality rules
├── suppression.py       # FV-CTRL-004 — six suppression mechanisms
├── destruction.py       # FV-CTRL-005 — trainer-port jobs
├── wrappers.py          # FV-CTRL-010 — Gateway serve path
└── run.py               # CLI

tests/
├── test_controls.py     # test_fv_ctrl_001 … test_fv_ctrl_010
└── fixtures/controls/   # spec roots, contracts, decision records, configs
```

**Structure Decision**: Single project. `src/controls/` is the package the execution plan assigns to P2-3. `registry.py`, `base.py`, `build.py`, `suppression.py`, `destruction.py`, and `wrappers.py` match the FV-CTRL trace targets. `match.py` is reserved for P2-4. `from_pretrained` stays in `src/models/`. The accountant stays in `src/eval/budget.py`.

## Complexity Tracking

No constitution violations — table not required.

## Open decisions (do not close in implementation)

| ID | What stays unset | Blocks |
|----|------------------|--------|
| D-55 | How many implementations, and which severities, each family has | FR-001 certification |
| D-61 | Whether the untouched model is a primary negative family, and its mechanism layer | FR-001 build of `untouched` |
| D-54 | Numeric retention tolerance against the parent | FR-004 acceptance |
| D-53 | Determinism metric for a non-zero digest tolerance | FR-008 comparison |

`tests/fixtures/controls/` may mark a decision `closed` and supply the field that hook needs. Those fixtures are not copied into `.factverify/spec/`. A study decision record keeps each row `open`. No requirement is marked implemented while its decision is open. See `research.md`.

## Ordering

Land config, decision, spec, and ledger refusal first. Then the catalog, labels, parent check, and split rule (FR-001, FR-002, FR-003, FR-006, FR-009). Then provenance, the evaluator-output ban, and digest comparison (FR-007, FR-008). Then suppression acceptance (FR-004) and destruction acceptance (FR-005). Wrapper charging (FR-010) uses the Gateway that P2-2 already provides.
