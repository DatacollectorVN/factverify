# Implementation Plan: FV-CTRL — P2-4 Behaviour-Matching Utility

**Branch**: `20260927-144624-behaviour-matching` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)  
**Source**: `second-brain/ml-unlearning/requirements/FV-CTRL — P2-4.md` (draft)

## Summary

`match_control` tunes one already-built negative control by trying every severity in a declared list and keeping the one the closed D-54 record ranks first. The target band is computed from the direct question-answering accuracies of the retain-only references for the same fact. A control inside that tolerance is `matched`. The best try outside it is `unmatched`, and that record is kept for the integrity-pilot report. Probes come from a closed D-58 manifest and must sit outside calibration and final-test template groups. Controls tagged `hard` also have to clear the D-59 dimensions. Matching cost is stored on the match record and is not sent through the evaluator accountant.

D-54, D-58, D-59, and D-53 stay open on any study decision record. Fixture records close only the row a hook needs. Nothing under `.factverify/spec/` is edited. This feature does not build controls, train references, or write the P3-2 report. SQLite stays in P2-5.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyYAML (match config, decision records, probe manifests, closure groups), hashlib via `src.train.config.hash_mapping` (config identity). Measurements come from a `MatchBehaviorPort`. Reference rows come from a read-only `MatchLedgerPort`. Cost uses the existing `CostRecord`. No `from_pretrained`, and no import of `src.eval.gateway` or `src.eval.budget`.  
**Storage**: One `match.json` per finished match in the caller-supplied output directory. Decision records and probe manifests are caller-supplied YAML outside `.factverify/spec/`. No new SQLite database (P2-5).  
**Testing**: pytest. Named hooks `tests/test_match.py::test_fv_ctrl_011_target_from_refs` through `test_fv_ctrl_017_reproducible`. Fixture spec roots, manifests, and decision records under `tests/fixtures/controls/match/`. No GPU and no weight download.  
**Target Platform**: Linux GPU for later study matches; CPU fixtures for these hooks  
**Project Type**: Internal Python library inside the study harness. The existing control CLI keeps refusing a SQLite ledger. Matching is called as a function.  
**Performance Goals**: Wall-clock, GPU-hours, and peak memory are recorded per match with `CostRecord`. This plan sets no numeric stop. The whole declared severity list is tried.  
**Constraints**: Fail closed (I8). No magic numbers beyond the two reference counts the execution plan already states for Block 0 and Block 1. Do not edit `.factverify/spec/`. D-54, D-58, D-59, and D-53 stay open. Do not charge the evaluator query budget. PEP 8, full type annotations, ruff. `make lint` and `make test` before implementation is complete.  
**Scale/Scope**: One match per control configuration. Downstream: P3-2 reads match records; it does not own the search. Control mechanisms (P2-3), reference training (P2-1), evaluator verdicts (P2-2), and ledger storage (P2-5) are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Design notes were read from disk. The Obsidian MCP server is not available in this session.

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | `match_control` takes an explicit `spec_root` and reads `closure_templates.yaml` from it. Missing files, open decision rows, and omitted D-54 match fields raise before a verdict file is written. The package never writes `.factverify/spec/`. |
| 2 | No Result-Dependent Choices | ✅ PASS | The severity list is declared before measurement and is tried in full. The band summary, tolerance, boundary, and ranking rule come from a closed D-54 record. A target accuracy written in the config is refused. Evaluation template groups and final-test facts are refused. |
| 3 | Final Test Runs Once | ✅ PASS | This package does not run the final-test pass. A final-test fact, reference, or template group refuses the match. |
| 4 | Equal Query Budgets (I4) | ✅ PASS | `src/controls/match.py` does not import the gateway or the accountant. A config that points at an evaluator output or a budget file is refused. Matching cost stays on `match.json`. |
| 5 | Seeded and Config-Driven | ✅ PASS | Seed, block, references, and the severity list are required config fields and enter the config hash. The search does not draw random numbers. Tolerances are read from a closed decision record. |
| 6 | Ledger Everything | ✅ PASS | The match record stores config hash, seed, split, spec revision, control ledger id, and reference ledger ids. Reference role and split are read through a port. SQLite writes stay in P2-5. |
| 7 | Gates Are Stop Points | ✅ PASS | An unmatched control is written and kept. The tolerance is the D-54 record. Nothing in this feature widens it or drops the control so Gate 1 can pass. |
| 8 | Wiki Governs Design | ✅ PASS | Execution Plan (status: planned), "Phase 2", task P2-4; "Phase 3", Gate 1 criterion 1 and the two-reference pilot; "Phase 4", at least three reference seeds; "Risk register", row "Controls too easy to reject". Proposal v3 (status: draft), "6.2" and "6.3". Fake-Unlearning Controls (status: draft), "How It Works". Handbook (status: draft), I6, I8, and "5.6 Verdict vocabulary". FV-CTRL P2-4 is draft. |
| 9 | Equivalence and Inference Never Mix (I2) | ✅ PASS | Matching probes are a declared direct-QA set. This package does not score equivalence or inference templates and does not assign groups. |
| 10 | Claims Never Exceed the Channel (I3) | ✅ PASS | A match record is a behaviour comparison with retain-only references. It is not an unlearning verdict and it does not claim the fact is absent from the weights. |
| 11 | Raw Maxima Are Never Verdicts (I5) | ✅ PASS | This package does not emit evaluator verdicts. |
| 12 | Prompts Are Not Replicates (I7) | ✅ PASS | One match is one control, one fact, and one declared severity list. Probe outputs are nested measurements, not extra controls. |
| 13 | Code Quality | ✅ PASS | New modules under `src/controls/` and `tests/test_match.py` carry annotations and pass ruff. `make lint` and `make test` are the completion bar. |

**All applicable gates pass. No violations.** Post-design re-check: the match ledger port, the match behavior port, the probe manifest, and the extra decision fields do not add a gate violation. The four decisions below remain open on purpose. P2-3 retention still uses only `max_abs_gap`. A closed D-54 row that has `max_abs_gap` and lacks the match fields still refuses a match.

## Project Structure

### Documentation (this feature)

```text
specs/20260927-144624-behaviour-matching/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── match_control.md
│   ├── match_record.md
│   └── probes.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/controls/
├── decisions.py         # extend: D-58, D-59, optional D-54 match fields
├── match.py             # FV-CTRL-011 … FV-CTRL-017
└── __init__.py          # export match_control, compare_matches

tests/
├── test_match.py        # test_fv_ctrl_011 … test_fv_ctrl_017
└── fixtures/controls/match/
    ├── spec/closure_templates.yaml
    ├── probes/
    ├── decisions/
    └── configs/
```

**Structure Decision**: Single project. `src/controls/match.py` is the module the execution plan assigns to P2-4. P2-3's `load_config` stays unchanged, so a match document is a separate YAML file and a severity search cannot leak into control builds. `from_pretrained` stays in `src/models/`. The accountant stays in `src/eval/budget.py` and is not called.

## Complexity Tracking

No constitution violations — table not required.

## Open decisions (do not close in implementation)

| ID | What stays unset | Blocks |
|----|------------------|--------|
| D-54 | Band summary, tolerance, boundary, and the ranking rule. Retention's `max_abs_gap` is a separate field on the same row | FR-001 and FR-002 |
| D-58 | Which direct-QA probes are the matching set | FR-003 |
| D-59 | Extra dimensions, metrics, and tolerances for controls tagged `hard` | FR-005, unless a recorded waiver is present |
| D-53 | Determinism policy. Only decimal string `0` is interpreted, and only by `compare_matches` | FR-007 comparison |

`tests/fixtures/controls/match/` may mark a decision `closed` and supply the field that hook needs. Those fixtures are not copied into `.factverify/spec/`. No requirement is marked implemented while its decision is open. See `research.md`.

## Ordering

Extend decision loading first, without changing retention. Then the match-config loader and the probe-isolation check (FR-003, FR-008). Then the reference-band target and the tolerance judgement (FR-001, FR-002). Then the search list, cost, and the ban on evaluator budgets (FR-006). Then unmatched retention for the pilot inputs (FR-004). Then hard dimensions (FR-005). Seed identity and `compare_matches` land last (FR-007).
