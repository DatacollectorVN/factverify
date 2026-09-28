# Implementation Plan: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Branch**: `20260927-161631-ledger-stats-cache` | **Date**: 2026-09-27 | **Spec**: [spec.md](spec.md)  
**Source**: `FV-LEDG — P2-5.md`, `FV-STAT — P2-6.md`, `FV-CACHE — P2-7.md` (each draft)

## Summary

Three study services share one plan. The run ledger is the only place a checkpoint or evaluation run becomes usable: a complete row is appended, a correction is a new row, a dirty final-test row is refused, and a second final-test pass on the same split is refused unless an incident row references the first pass. The generation cache replays an identical request and refuses a different body under the same key. The interval module resamples checkpoint and fact blocks, keeps both evaluators on the same cases, and refuses threshold selection when any input row is final-test.

`scripts/ledger.py` and `src/cache/store.py` are stubs. The ledger stub allows a null tier and a role list shorter than the spec. The cache stub uses `INSERT OR REPLACE` and a 16-character hash. Both are replaced. `tests/test_cache.py::test_overwrite` is removed because it requires the overwrite this spec forbids.

D-56, D-60, D-20, D-07, D-06, D-10, D-03, D-08, and D-57 stay open on the study records. Fixture records close only the row a hook needs. Nothing under `.factverify/spec/` is edited. Query-budget charge rules stay in `attacks.yaml` and `src/eval/budget.py`.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyYAML (decision records and fixture margins), hashlib via `src.train.config.hash_mapping` (row and key digests), sqlite3 (ledger and cache files). No new third-party statistics library. No `from_pretrained`. The ledger does not invoke git.  
**Storage**: Caller-supplied `ledger.sqlite` (CLI default path `ledger.sqlite`). Cache directory supplied by the caller, refused when it sits inside `.factverify/`. Decision records and fixture spec roots live under `tests/fixtures/` and are not copied into `.factverify/spec/`. Exports are CSV and JSON beside a schema version.  
**Testing**: pytest. Hooks `tests/test_ledger.py::test_fv_ledg_001_unledgered_refused` through `test_fv_ledg_011_concurrency`, `tests/test_cache.py::test_fv_cache_001_full_key` through `test_fv_cache_008_export`, and `tests/test_stats.py::test_fv_stat_001_block_resampling` through `test_fv_stat_010_ledgered_only`. No GPU and no weight download.  
**Target Platform**: Linux for study runs; CPU fixtures for these hooks  
**Project Type**: Internal Python library plus `scripts/ledger.py`. The evaluator gateway is the only production caller of the cache.  
**Performance Goals**: Ledger and cache writes are off the gradient path. Each analysis records its own wall-clock. This plan sets no numeric stop.  
**Constraints**: Fail closed (I8). No magic numbers for tier, replicate count, gamma, multiplicity, or whether software versions enter the cache key. Do not edit `.factverify/spec/`. Do not change cache, retry, or failure charge rules. PEP 8, full type annotations, ruff. `make lint` and `make test` before implementation is complete.  
**Scale/Scope**: One ledger for checkpoints, evaluation runs, and incidents. One cache store per caller-supplied root. One estimate call per verdict table. Training algorithms, control mechanisms, and verdict text stay in P2-1, P2-3, and P2-2.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Design notes were read from disk. The Obsidian MCP server is not available in this session.

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | Ledger, cache, and `estimate` take an explicit spec root or decision file. Missing files, open decision rows, and `DECISION_REQUIRED` fields raise. A rejected ledger write rolls back. The package never writes `.factverify/spec/`. |
| 2 | No Result-Dependent Choices | ✅ PASS | Tier values, software-in-key, resample design, weights, aggregation, confidence procedure, multiplicity, replicate count, and interval type are read from a closed decision row. The study rows stay open, so those paths raise. Threshold selection raises before any bound when a row is `final_test`. |
| 3 | Final Test Runs Once | ✅ PASS | A second final-test pass on the same split raises unless an incident row references pass 1. A dirty final-test checkpoint or evaluation run raises. |
| 4 | Equal Query Budgets (I4) | ✅ PASS | The cache returns one event per lookup. The gateway already charges `cache_hit` and `generation` through `Accountant`. This feature does not add a charge kind and does not edit `cache_policy`. |
| 5 | Seeded and Config-Driven | ✅ PASS | Estimate takes a seed and records it with the replicate count and the design. Cache keys include the decoding seed and the sample index. No study rate is hardcoded. |
| 6 | Ledger Everything | ✅ PASS | This feature is that ledger. A checkpoint with no row is unusable. Evaluation runs store the checkpoint id, the thresholds tag, and the budget used. |
| 7 | Gates Are Stop Points | ✅ PASS | Nothing here loosens a gate, a tolerance, or a split. An unmatched control from P2-4 is not filtered. |
| 8 | Wiki Governs Design | ✅ PASS | Execution Plan (status: planned), "Phase 2", tasks P2-5, P2-6, P2-7; "Phase 4", P4-5 and P4-6; "Start here" item 3; "Tracking conventions"; "Risk register" rows "Threshold leakage" and "Evaluation dominates wall-clock". Proposal v3 (status: draft), "6.2", "6.4", "8". Handbook (status: draft), I6, I7, I8, "6.4", "6.7", "8.4", "8.7", V23. The three requirements notes are draft. |
| 9 | Equivalence and Inference Never Mix (I2) | ✅ PASS | This package does not score probes or assign template groups. |
| 10 | Claims Never Exceed the Channel (I3) | ✅ PASS | Outputs are provenance rows, cache entries, and rate intervals. They are not unlearning verdicts. |
| 11 | Raw Maxima Are Never Verdicts (I5) | ✅ PASS | Intervals are attached to FRR, FCR, and ΔFCR. No raw maximum is promoted to a verdict. |
| 12 | Prompts Are Not Replicates (I7) | ✅ PASS | `estimate` resamples checkpoint and fact blocks. A request to resample prompt rows raises. The coverage check runs a row resample only as the sensitivity case the spec requires, and that path is not the reported estimator. |
| 13 | Code Quality | ✅ PASS | New modules under `src/ledger/`, `src/cache/`, `src/stats/`, `scripts/ledger.py`, and the three test modules carry annotations and pass ruff. `make lint` and `make test` are the completion bar. |

**All applicable gates pass. No violations.** Post-design re-check: replacing the stubs, extending the harness and control rows with git and cost fields, and pointing the gateway at `get_or_compute` do not add a gate violation. The nine decisions below remain open on purpose. A numeric bound, a cache key, or a checkpoint row is not produced from the study decision files while those rows are open.

## Project Structure

### Documentation (this feature)

```text
specs/20260927-161631-ledger-stats-cache/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── ledger.md
│   ├── cache.md
│   └── estimate.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/ledger/
├── api.py               # add, get, lineage, disjointness, final-pass guard
├── schema.py            # tables and append-only triggers
├── export.py            # CSV and JSON round-trip
└── errors.py

src/cache/
├── key.py               # full key; raises while D-60 is open
├── store.py             # replaces GenerationCache
├── export.py
└── errors.py

src/stats/
├── io.py                # ledgered verdicts
├── bootstrap.py         # block draws; row draws only for the coverage check
├── delta.py
├── bounds.py
├── multiplicity.py
├── thresholds.py
├── report.py
└── errors.py

scripts/ledger.py        # init, add, show, lineage, check-disjoint, final-pass, export, import

src/train/ledger.py      # extend CheckpointRow
src/train/run.py         # fill the new fields when committing
src/controls/ledger.py   # extend LedgerRow
src/controls/build.py    # fill the new fields when committing
src/eval/gateway.py      # CachePort becomes get_or_compute
src/eval/types.py        # sample_index on the completion call

tests/
├── test_ledger.py
├── test_cache.py        # replace the overwrite test
├── test_stats.py
└── fixtures/{ledger,cache,stats}/
```

**Structure Decision**: Single project. The execution plan already assigns `ledger.sqlite` and `scripts/ledger.py` to P2-5, `src/stats/` to P2-6, and `src/cache/` to P2-7. The gateway remains the only module that calls a model. The accountant remains the only module that applies a charge rule.

## Complexity Tracking

No constitution violations — table not required.

## Open decisions (do not close in implementation)

| ID | What stays unset | Blocks |
|----|------------------|--------|
| D-56 | The allowed `tier` strings | FR-002, FR-003. A checkpoint add raises `D-56` |
| D-60 | Whether software versions are part of the cache key | FR-012. Key derivation raises `D-60` |
| D-20 | Whether a cache hit costs budget | FR-014 is not marked implemented. Charge rules are untouched |
| D-07 | Dependence structure and resampling design | FR-019. `estimate` raises `D-07` |
| D-06 | Case weights | A weighted estimate raises `D-06`. Same-case pairing still runs |
| D-10 | Per-family and overall aggregation | FR-021. The family estimate raises `D-10` |
| D-03 | Confidence procedure | FR-022 and the numeric threshold bound. Those calls raise `D-03` |
| D-08 | Multiplicity family and procedure | FR-023. Adjustment raises `D-08` |
| D-57 | Replicate count, interval type, coverage tolerance | FR-024, FR-025. Those calls raise `D-57` |

`tests/fixtures/` may mark a decision `closed` and supply the field that hook needs. Those fixtures are not copied into `.factverify/spec/`. No requirement is marked implemented while its decision is open on the study record. See `research.md`.

## Ordering

Ledger schema, append-only triggers, and the checkpoint add path first (FR-001 through FR-005), including the D-56 refusal. Then lineage, git state, disjointness, the single final-test pass, and evaluation-run rows (FR-004, FR-007 through FR-010). Then export and concurrent commits (FR-006, FR-011) and the CLI. Then extend the harness and control rows so a real commit can carry git state and the cost fields. Then the cache key, store, integrity, conflict, and location (FR-012, FR-013, FR-015 through FR-017), with D-60 refusing derivation. Then events, export, and the gateway call site (FR-014, FR-018). Then verdict loading and the final-test threshold refusal (FR-026, FR-027). Block resampling, pairing, family rows, zero-error bounds, multiplicity, determinism, and the coverage check land last, each raising while its decision is open (FR-019 through FR-025).
