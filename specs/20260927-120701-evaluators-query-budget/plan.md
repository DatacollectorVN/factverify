# Implementation Plan: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Branch**: `20260927-120701-evaluators-query-budget` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)  
**Source**: `second-brain/ml-unlearning/requirements/FV-EVAL — P2-2.md` (draft)

## Summary

One entry point, `evaluate_case`, runs the native, semantic-only, and FactVerify arms on one case. Every model call goes through `Accountant.query` in `src/eval/budget.py`. The accountant charges the channel named on the request, refuses an overspend, keeps confirmation on its own line, and writes the cost vector. The run refuses to start when arm totals differ, when a cache or failure policy is unresolved, or when a blocking decision that the operation depends on is still `open`.

The integer `BudgetAccountant` already in `src/eval/budget.py` charges one count against `budget_per_fact`. That API is removed. `tests/test_budget.py` is replaced by `tests/test_eval.py`. Cache storage stays in P2-7; this feature only applies the frozen charge rule through a `CachePort`. Threshold selection, controls, confidence intervals, and the SQLite ledger stay in their own tasks.

D-14, D-17, D-18, D-20, D-21, D-22, D-26, and D-27 stay open. A study run pointed at `.factverify/spec/` refuses while they are open. Fixture specs close only the decisions a hook needs.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyYAML (spec artifacts), hashlib (digests and prompt identity), subprocess git (read-only check that `results/thresholds.json` matches the `thresholds-v1` blob). Model calls go through a `ModelPort` whose study implementation uses `load_model` (P2-0). No `from_pretrained` in `src/eval/`. Text metrics that need another model (BERTScore) sit behind a `MetricPort` so tests do not download weights.  
**Storage**: Raw generations as JSONL in a caller-supplied directory outside `.factverify/`. Budget records and verdicts as JSON under the caller-supplied results directory. No new SQLite database. The generation cache is a port; `src/cache/store.py` remains the P2-7 stub and is not given charge logic.  
**Testing**: pytest. Named hooks `tests/test_eval.py::test_fv_eval_001_all_calls_charged` through `test_fv_eval_014_raw_generations`. Fixture spec roots under `tests/fixtures/eval/` with decisions closed. One hook loads the real `.factverify/spec/` and expects a refusal that names the open decision. No GPU and no weight download.  
**Target Platform**: Linux GPU for later study runs; CPU fixtures for these hooks  
**Project Type**: Internal Python library plus CLI (`python -m src.eval.run`) inside the study harness  
**Performance Goals**: Wall-clock, GPU-hours, and peak memory are recorded per arm. The plan risk register compares evaluation time with training time later. This plan sets no numeric stop.  
**Constraints**: Fail closed before the first model call (I8). No magic numbers: caps, units, and policies are spec fields. Accountant (FR-001–FR-006) before evaluators (FR-008–FR-013). Final-test cases load thresholds only from the file at tag `thresholds-v1`. PEP 8, full type annotations, `ruff check` and `ruff format`. Do not edit `.factverify/spec/` or `spec-unlearning/`.  
**Scale/Scope**: Three arms, the channels `attacks.yaml` assigns them, one case at a time. Downstream: P3-4 pilot scores, P4-3 calibration, P4-5 final test. Controls, cache storage, bootstrap, and the ledger writer are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Design notes were read from disk. The Obsidian MCP server is not available in this session.

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | `evaluate_case` takes an explicit `spec_root`. Missing files, null, and `DECISION_REQUIRED` raise before a model call. Open blocking decisions raise the same way. Raw generations cannot be written under `.factverify/`. The package never writes the spec namespace. |
| 2 | No Result-Dependent Choices | ✅ PASS | Caps, the scoring unit, cache and failure policies, confirmation reallocation, and logit scope stay on spec fields. D-14, D-17, D-18, D-20, D-21, D-22, D-26, and D-27 stay open. Final-test refuses a threshold passed as an argument. |
| 3 | Final Test Runs Once | ✅ PASS | A final-test case loads `results/thresholds.json` only when its bytes match the `thresholds-v1` blob. This package does not select thresholds and does not resume a partial final-test split. |
| 4 | Equal Query Budgets (I4) | ✅ PASS | One accountant. Per-channel allocations, confirmation reserve, cache, retry, and failure charges, and the cost vector. The integer `budget_per_fact` stub is removed so it cannot sit beside the real accountant. |
| 5 | Seeded and Config-Driven | ✅ PASS | Decoding seed and sample index are request fields. Replay uses stored generations. No study cap is hardcoded. |
| 6 | Ledger Everything | ✅ PASS | Verdict rows carry the checkpoint ledger identifier. SQLite writes stay in P2-5. |
| 7 | Gates Are Stop Points | ✅ PASS | No Gate 1 threshold and no control loosening. The 5× eval-time risk trigger is not implemented here. |
| 8 | Wiki Governs Design | ✅ PASS | Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-2, including the callout to build the accountant first. Handbook (status: draft): "2. The eight invariants" (I2–I5, I8), "6.4 One query needs a definition", "6.5 Budget arithmetic", "6.6 Adaptive attacks". FV-EVAL is draft. |
| 9 | Equivalence and Inference Never Mix (I2) | ✅ PASS | An inference template (`extra_premises` non-empty, or class `I`) is refused for the primary equivalence score and written to a separate inference output. |
| 10 | Claims Never Exceed the Channel (I3) | ✅ PASS | Every verdict carries the access label. A case marked structurally indistinguishable receives non-identifiable. Logit and activation channels are refused when the profile marks scores or internals unavailable. |
| 11 | Raw Maxima Are Never Verdicts (I5) | ✅ PASS | A confirmed recovery witness requires an enabled confirmation route. A lone bound crossing is stored as a diagnostic. Channel scores are not averaged. |
| 12 | Prompts Are Not Replicates (I7) | ✅ PASS | The case is one checkpoint and one fact. Prompts and samples are nested charges, not extra cases. |
| 13 | Code Quality | ✅ PASS | New modules under `src/eval/` and `tests/test_eval.py` carry annotations and pass ruff. |

**All applicable gates pass. No violations.** Post-design re-check: the model gateway, the cache port, the metric port, and the git blob check for thresholds do not add a gate violation. The eight decisions above remain open on purpose. The integer accountant is specified as deleted, not retained beside the new one.

## Project Structure

### Documentation (this feature)

```text
specs/20260927-120701-evaluators-query-budget/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── evaluate_case.md
│   ├── accountant.md
│   ├── verdict_row.md
│   └── thresholds.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/eval/
├── __init__.py          # exports: evaluate_case, CaseResult, FactVerifyEvalError
├── errors.py            # FactVerifyEvalError, BudgetExhaustedError
├── spec_load.py         # fail-closed load of the five spec artifacts
├── budget.py            # FV-EVAL-001–006 — Accountant
├── gateway.py           # sole model-call site; charges, then ModelPort
├── channels.py          # FV-EVAL-007 — access gate
├── probes.py            # native vs closure vs inference; split membership
├── native.py            # FV-EVAL-008
├── semantic.py          # FV-EVAL-009
├── verdict.py           # FV-EVAL-010
├── factverify.py        # FV-EVAL-011, FV-EVAL-013
├── thresholds.py        # FV-EVAL-012
├── store.py             # FV-EVAL-014 — raw JSONL
├── cost.py              # cost-vector assembly
└── run.py               # CLI

tests/
├── test_eval.py         # test_fv_eval_001 … test_fv_eval_014
└── fixtures/eval/       # spec roots, cases, scripted model and cache
```

**Structure Decision**: Single project. `src/eval/` is the package the execution plan assigns to P2-2. File names match the FV-EVAL trace targets. `gateway.py`, `spec_load.py`, `probes.py`, `cost.py`, and `errors.py` exist so the trace files stay one requirement each and so model calls have a single site the AST check can name. `from_pretrained` stays in `src/models/`.

## Complexity Tracking

No constitution violations — table not required.

## Open decisions (do not close in implementation)

| ID | What stays unset | Blocks study values for |
|----|------------------|-------------------------|
| D-14 | How incomplete and non-identifiable enter denominators | FR-010 |
| D-17 | Total trial cap per case | FR-002 |
| D-18 | Candidate-scoring accounting unit | FR-001 |
| D-20 | Cache and retry policy | FR-006 |
| D-21 | Failed-request policy | FR-006 |
| D-22 | Equal caps versus equal realized usage | FR-003 |
| D-26 | Unused-confirmation reallocation | FR-005 |
| D-27 | Logit scope under the access profile | FR-007 |

`tests/fixtures/eval/` may mark a decision `closed` and supply a field value so a hook can run. Those fixtures are not copied into `.factverify/spec/`. A study invocation whose `spec_root` is the frozen spec refuses and names each open decision it needs. No requirement is marked implemented while its decision is open.

## Ordering

Implement and pass FR-001 through FR-006 before FR-008 through FR-013 are treated as ready. FR-007, FR-012, and FR-014 can be built beside the accountant because they gate or record calls. They still call `Accountant.query` for any model work.
