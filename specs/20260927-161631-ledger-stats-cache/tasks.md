# Tasks: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Feature**: `20260927-161631-ledger-stats-cache`  
**Input**: Design documents from `specs/20260927-161631-ledger-stats-cache/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included. The three requirements notes (draft) name the pytest hooks in `quickstart.md`: `test_fv_ledg_001_unledgered_refused` through `test_fv_ledg_011_concurrency`, `test_fv_cache_001_full_key` through `test_fv_cache_008_export`, and `test_fv_stat_001_block_resampling` through `test_fv_stat_010_ledgered_only`. Write each story's tests before that story's implementation, and confirm they fail first.

**Organization**: Tasks are grouped by user story. Do not close D-56, D-60, D-20, D-07, D-06, D-10, D-03, D-08, or D-57 in `.factverify/spec/`. Fixture decision rows live only under `tests/fixtures/`. Do not edit `attacks.yaml` charge rules. Do not add SciPy or NumPy.

**Design notes** (read from disk; Obsidian MCP was unavailable when the plan was written): Execution Plan (status: planned), "Phase 2", tasks P2-5, P2-6, P2-7; "Phase 4", P4-5 and P4-6; "Start here" item 3. Proposal v3 (status: draft), "6.2", "6.4", "8". Handbook (status: draft), I6, I7, I8, "6.4", "6.7", "8.4", "8.7", V23. The three requirements notes are draft.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: User story this task belongs to (US1, US2, US3, US4, US5, US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Error types and fixture files. Do not download weights. Do not edit `.factverify/spec/`.

- [X] T001 [P] Add `LedgerError` in `src/ledger/errors.py`, `CacheError` in `src/cache/errors.py`, and `StatsError` in `src/stats/errors.py`. Each subclasses `Exception` and takes one string message, the field or decision id. Add an empty `src/ledger/__init__.py`, `src/cache/__init__.py`, and `src/stats/__init__.py`. Do not import `src.eval` from these packages.
- [X] T002 [P] Create `tests/fixtures/ledger/decisions/open.yaml` with `decisions:` a one-item list, D-56 `status: open`. Create `d56_pilot.yaml` with D-56 `status: closed` and `tiers: [pilot]`. Create `d56_empty.yaml` with D-56 `status: closed` and `tiers: []`. Do not copy these files into `.factverify/spec/`.
- [X] T003 [P] Create `tests/fixtures/cache/decisions/open.yaml` with D-60 `status: open`. Create `d60_omit.yaml` with D-60 `status: closed` and `include_software_versions: false`. Create `d60_include.yaml` with that flag `true`. Create `d60_bad.yaml` with the flag `maybe`.
- [X] T004 [P] Create `tests/fixtures/stats/spec/margins.yaml` with `version: "fixture-stats"`, `confidence_error_probability.value: "0.05"`, `threshold_selection.selection_uncertainty_procedure: DECISION_REQUIRED`, `threshold_selection.forbid_final_test_inputs: true`, `estimands.case_weights: uniform`, `estimands.aggregation.per_family: mean`, `estimands.aggregation.overall: mean`, `uncertainty.resampling_contract: paired_block_bootstrap`, and `blocking_decisions` listing D-03, D-05, D-06, D-07, D-08, D-10, and D-57 each `status: open`. Create `tests/fixtures/stats/decisions/open.yaml` with those same ids `open`. Create `closed.yaml` that closes D-03 `procedure: one_sided_exact`, D-05 `procedure: one_sided_exact`, D-06 `case_weights: uniform`, D-07 `resampling_contract: paired_block_bootstrap` and `design: nested`, D-08 `procedure: holm`, D-10 `per_family: mean` and `overall: mean`, D-57 `interval_type: percentile`, `replicate_count: 19`, `coverage_tolerance: "0.10"`. Create `crossed.yaml` as `closed.yaml` with D-07 `design: crossed`. Create `bad_procedure.yaml` with D-08 `procedure: bonferroni` and the other ids closed as in `closed.yaml`. Create `tests/fixtures/stats/sim.yaml` with `n_checkpoints: 30`, `n_facts: 5`, `n_prompts: 20`, `true_fcr: "0.25"`, `checkpoint_shift: "0.20"`, `n_simulations: 100`, `seed: 7`. These numbers stay in the fixture. Do not copy them into library defaults or into `.factverify/spec/`.
- [X] T005 [P] Create `tests/stats_ports.py` with `MemoryStatsLedger`. `get_checkpoint` and `get_evaluation_run` return a small frozen view (`ledger_id` or `run_id`, `split`, `checkpoint_ledger_id` on the run) or `None` for an unknown id. No SQLite and no import of `src.eval`.

**Checkpoint**: Fixture files and error types exist. `src/ledger/api.py` does not exist yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema, decision loading, and record types every story calls. No story starts until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 [P] Implement `load_decision` in `src/ledger/decisions.py`, `src/cache/decisions.py`, and `src/stats/decisions.py`. Each reads a YAML `decisions:` list. A missing id returns `status: open`. `status` other than `open` or `closed` raises that package's error naming the id. Ledger accepts only `D-56` and, when closed, requires a non-empty list of strings `tiers`; an empty list or a non-string entry raises `D-56`. Cache accepts only `D-60` and, when closed, requires `include_software_versions` to be boolean; `maybe` raises `D-60`. Stats accepts `D-03`, `D-05`, `D-06`, `D-07`, `D-08`, `D-10`, and `D-57` and keeps the closed fields from `data-model.md` without filling missing ones. Do not read `.factverify/spec/margins.yaml` in this task.
- [X] T007 [P] Implement `open_ledger` in `src/ledger/schema.py` per `research.md` Decision 2 and `contracts/ledger.md`. Create `meta` (`schema_version` text, one row `"1"`), `checkpoints`, `evaluation_runs`, and `incidents` with the columns in `data-model.md`. `parent_ledger_id`, `supersedes`, and `checkpoint_ledger_id` are foreign keys. Before insert, triggers on `checkpoints`, `evaluation_runs`, and `incidents` abort `UPDATE` and `DELETE` with `append-only`. Set `foreign_keys=ON` and `journal_mode=WAL`. Do not set a busy timeout. Do not insert a checkpoint in this task. `open_ledger` takes `path` and `decisions` and raises if the meta row is missing after creation.
- [X] T008 Add the frozen dataclasses `CheckpointRecord`, `EvaluationRun`, `Incident`, `DisjointnessReport`, and `Ledger` in `src/ledger/api.py` per `data-model.md`. `Ledger` holds the sqlite connection and the decisions path. No `add_checkpoint` yet. Do not add `src/ledger/git.py`. `git_commit` and `dirty` are fields on the record, supplied by the caller.

**Checkpoint**: `open_ledger` creates an empty file whose triggers reject `UPDATE`. User stories can begin.

---

## Phase 3: User Story 1 — Refuse an unledgered checkpoint (Priority: P1) 🎯 MVP

**Goal**: A complete checkpoint row is stored and can be read back with its role and split. An unknown identity, an empty field, an open D-56 row, a bad role or tier, or a missing parent is refused and leaves the file unchanged. A finished evaluation run stores its required fields. An empty thresholds tag is refused.

**Independent Test**: Add one complete row against `d56_pilot.yaml` and read its role and split. Repeat with D-56 open, with one required field emptied, with a child of a present parent, with a missing parent, with one finished evaluation run, and with a final-test evaluation run whose thresholds tag is empty.

### Tests for User Story 1

- [X] T009 [US1] Write failing tests in `tests/test_ledger.py`: `test_fv_ledg_001_unledgered_refused`, `test_fv_ledg_002_required_fields`, `test_fv_ledg_004_vocabularies`, `test_fv_ledg_005_lineage`, and `test_fv_ledg_009_eval_runs`. Use `tmp_path` and the fixtures from T002. A complete root uses `identity_hash` `id-root`, `parent_ledger_id` null, `parent_identity_hash` `""`, `role` `base`, `tier` `pilot`, `split` `calibration`, `family` `base`, `method` `base`, `implementation_id` `""`, `spec_tag` `fixture`, `git_commit` `abc`, `dirty` false, and every cost field `0`. Assert the returned id and a non-empty `created_at`, and that `get_checkpoint` returns `role` and `split`. An unknown id raises. Each emptied required field raises `LedgerError` whose message is that field, and a fresh open of the file shows no extra row. Open D-56 raises `D-56`. Role `ref` raises `role`. Tier `block` with `tiers: [pilot]` raises `tier`. A child whose parent exists returns a lineage that ends with the root id. A child naming a missing parent raises and writes nothing. `add_evaluation_run` on that checkpoint stores `arm`, `split`, `spec_tag`, `thresholds_tag`, `budget_used`, `pass_number` 1, and `git_commit` and `dirty`. A final-test run with `thresholds_tag` `""` raises `thresholds_tag`. Confirm the tests fail before T010.

### Implementation for User Story 1

- [X] T010 [US1] Implement `add_checkpoint`, `get_checkpoint`, and `lineage` in `src/ledger/api.py` per `contracts/ledger.md` steps for `add_checkpoint` and `research.md` Decision 3. Raise `LedgerError("D-56")` while D-56 is open. Reject an empty required field by name. A root may use a null parent and `parent_identity_hash` `""`. A non-root parent must exist and the identity hash must match. Role must be one of `base`, `finetuned`, `reference`, `control`, `candidate`. `implementation_id` must be non-empty when role is `control`. `tier` must be a member of the closed `tiers` list. Insert in one transaction and roll back on any raise. In this task a second row with the same `identity_hash` raises `identity_hash` even if `supersedes` is set; T015 adds corrections. `lineage` walks `parent_ledger_id` and returns the requested id first and the root last. `get_checkpoint` returns `None` for an unknown id.
- [X] T011 [US1] Implement `add_evaluation_run` in `src/ledger/api.py` per `data-model.md`. Require an existing `checkpoint_ledger_id`, a non-empty `thresholds_tag` on every split, a non-empty `git_commit`, `pass_number` ≥ 1, and a `budget_used` object whose keys are `tokens`, `scored_candidates`, `training_steps`, `exports`, `wall_clock_seconds`, `gpu_hours`, and `peak_memory_bytes`. A missing key raises that key. Do not yet enforce the single-pass rule or the dirty final-test rule; T019 adds those. A missing checkpoint raises `checkpoint_ledger_id` and writes nothing.
- [X] T012 [US1] Extend `CheckpointRow` in `src/train/ledger.py` and control `LedgerRow` in `src/controls/ledger.py` with required fields `family`, `implementation_id`, `git_commit`, `dirty`, `tokens`, `scored_candidates`, and `exports` per `research.md` Decision 9. Update every constructor in `src/train/run.py`, `src/controls/build.py`, and `tests/test_harness.py`. `run_job` and `build_control` take required keywords `git_commit: str` and `dirty: bool`. Do not default them and do not call git. Update every `run_job` and `build_control` call in `tests/test_harness.py` and `tests/test_controls.py` to pass `git_commit="fixture"` and `dirty=False`. Training and control commits pass `tokens=0`, `scored_candidates=0`, and `exports=0`. The harness test helper uses `git_commit="fixture"`, `dirty=False`, `family="finetune"`, `implementation_id=""`. `SqliteLedger` in `src/ledger/api.py` implements `commit_checkpoint` and the control `commit` by building a `CheckpointRecord` and calling `add_checkpoint`. Do not change training algorithms. Run `uv run pytest tests/test_harness.py tests/test_controls.py -q` and keep those hooks green.
- [X] T013 [US1] Replace the body of `scripts/ledger.py` per `contracts/ledger.md`. Subcommands `init`, `add checkpoint`, and `show` call `open_ledger`, `add_checkpoint`, and `get_checkpoint`. `init` requires `--path` and `--decisions`. `add checkpoint` reads a JSON record from `--record`, including `git_commit` and `dirty`. Do not run git. A missing `git_commit` or `dirty` raises that field name. Drop the old `runs` table and the 16-character hash. A rejected add exits 1 and prints the error message. Do not implement `export` or `check-disjoint` here.

**Checkpoint**: US1 hooks pass. An open D-56 file still refuses every checkpoint add. Existing harness and control tests still pass.

---

## Phase 4: User Story 2 — Keep the ledger append-only (Priority: P1)

**Goal**: A correction is a new row pointing at an unchanged original. `UPDATE` and `DELETE` abort. Concurrent adds and a rolled-back transaction leave no partial row. Export and re-import reproduce row digests. Any `schema_version` other than `"1"` is refused.

**Independent Test**: Record a correction and read both rows. Issue `UPDATE` and `DELETE`. Add several rows at once and roll one transaction back. Export, import into an empty file, and offer a manifest whose `schema_version` is `2`.

### Tests for User Story 2

- [X] T014 [US2] Add failing tests in `tests/test_ledger.py`: `test_fv_ledg_003_append_only`, `test_fv_ledg_010_export_roundtrip`, and `test_fv_ledg_011_concurrency`. A second row for `id-root` whose `supersedes` is the first row's id is stored, and the first row's fields are unchanged. A second row that does not set `supersedes`, or that points at a missing id, raises `supersedes` or `identity_hash`. Execute `UPDATE` and `DELETE` on `checkpoints` through the connection and assert both abort. Export to a directory, import into a new file, and assert row counts and per-row sha256 values match. Rewrite the manifest `schema_version` to `"2"` and assert import raises `schema_version`. Start four threads that each add one distinct root; assert exactly four new rows. Open a transaction, insert, and roll it back; assert that row is absent. Confirm these tests fail before T015.

### Implementation for User Story 2

- [X] T015 [US2] Extend `add_checkpoint` in `src/ledger/api.py` per `research.md` Decision 3. A repeated `identity_hash` is accepted only when `supersedes` is the id of the current row for that hash (the row no other row supersedes) and the new identity hash equals that row's. Do not modify the superseded row. Keep the append-only triggers from T007 as the only way `UPDATE` and `DELETE` fail.
- [X] T016 [US2] Implement `export_ledger` and `import_ledger` in `src/ledger/export.py` per `research.md` Decision 2. Write `manifest.json` with `schema_version`, table names, row counts, and a sha256 for each row's canonical JSON, plus one CSV and one JSON file per table (`checkpoints`, `evaluation_runs`, `incidents`, `meta`). Import accepts only `schema_version` `"1"` into an empty destination and checks the digests. A mismatch raises and leaves the destination empty.
- [X] T017 [US2] Add `export` and `import` subcommands to `scripts/ledger.py`. They call `export_ledger` and `import_ledger`. A refused import exits 1.

**Checkpoint**: US2 hooks pass. A direct `UPDATE` still aborts. US1 lookups still return the original row after a correction.

---

## Phase 5: User Story 3 — Guard the single final-test pass (Priority: P1)

**Goal**: A dirty final-test row is refused. A clean one stores the commit. The disjointness check covers fact, reference seed, and control implementation. Pass 1 on a final-test split is stored once. A later pass is refused unless an incident references pass 1.

**Independent Test**: Add a clean final-test row and a dirty one, plus a non-final dirty row. Run the disjointness check on a disjoint ledger and on ledgers that share one fact, one reference seed, or one control implementation. Open pass 1, open a second pass with no incident, then again after an incident that references pass 1.

### Tests for User Story 3

- [X] T018 [US3] Add failing tests in `tests/test_ledger.py`: `test_fv_ledg_006_code_state`, `test_fv_ledg_007_disjoint`, and `test_fv_ledg_008_single_pass`. Final-test (`final_test` and `final-test`) with `dirty` true raises `dirty` and writes nothing. The same split with `dirty` false stores `git_commit` and `dirty` false. A calibration row with `dirty` true is stored. Disjoint calibration and final-test rows make `check_disjoint` succeed with a count for `fact`, `reference_seed`, and `control_implementation` on each split. One shared `fact_id`, one shared reference `seed`, or one shared control `implementation_id` makes the report not ok and lists those row ids. A ledger with only calibration rows succeeds and reports zero on the final-test side. The CLI `check-disjoint` exits 0 on the disjoint file and exits 1 on a shared fact, printing the row ids. The first final-test evaluation run with `pass_number` 1 is stored. A second run with `pass_number` 2 raises `pass`. After `add_incident` with `references_pass_number` 1 on that split, `pass_number` 2 is stored. An incident that references pass 2 does not allow pass 3 when pass 1 was never referenced. Confirm these tests fail before T019.

### Implementation for User Story 3

- [X] T019 [US3] Enforce the final-test guards in `src/ledger/api.py` per `research.md` Decision 4 and `contracts/ledger.md`. Treat `final_test` and `final-test` as the same split. Reject `dirty` true on a final-test checkpoint and on a final-test evaluation run. Implement `check_disjoint` on checkpoint rows only, with the three dimensions in Decision 4. Do not add a template-group dimension. Implement `add_incident` and the pass rule: on a final-test split, `pass_number` 1 is accepted only when no evaluation run exists yet on that split; a greater `pass_number` is accepted only when an incident on that split has `references_pass_number` 1. `final_pass_status` returns the highest accepted pass number, or `None` when no run exists.
- [X] T020 [US3] Add `lineage`, `check-disjoint`, and `final-pass` subcommands to `scripts/ledger.py`. `check-disjoint` exits 0 when the report is ok and prints the counts; it exits 1 and prints the offending row ids otherwise. `add incident` inserts through `add_incident`.

**Checkpoint**: US3 hooks pass. A second final-test pass without an incident is still refused. Template groups are not part of the report.

---

## Phase 6: User Story 4 — Replay an identical generation once (Priority: P1)

**Goal**: The cache key covers identity, the exact model input, every decoding field, seed, sample index, and request kind. An open D-60 row refuses key derivation. A corrupt body is not returned. A different body under an existing key raises and leaves the stored digest. The cache root cannot sit inside `.factverify/`. The gateway is the only caller and records one event without changing a charge rule.

**Independent Test**: Look up two requests that differ by one field, two inputs that differ by one space, and sample indices 1..k plus a missing index. Read an intact entry and a corrupted one. Write an identical recompute and a different body. Open a root outside `.factverify/` and one inside it. Export and re-import. Repeat key derivation while D-60 is open.

### Tests for User Story 4

- [X] T021 [US4] Replace `tests/test_cache.py`. Delete `test_put_and_get`, `test_miss_returns_none`, `test_different_params_different_entries`, and `test_overwrite`. Add failing tests `test_fv_cache_001_full_key` through `test_fv_cache_008_export` per `quickstart.md`. Use `d60_omit.yaml` unless the case says otherwise. Two requests that differ in `identity_hash`, one whitespace character of `model_input`, one decoding field, `seed`, `sample_index`, or `request_kind` produce different keys. A missing field raises that field. Open D-60 raises `D-60` and does not call `compute`. `d60_include.yaml` requires a non-empty string map `software_versions` and puts it in the key; omitting it raises `software_versions`. The same `model_input` hashed twice matches. Sample indices 1, 2, and 3 yield three entries; index 4 is a miss. A hit appends one `hit` event and does not call `compute`. A miss appends `miss` and calls `compute` once. An altered stored body returns `corrupt`, does not return the old text, and calls `compute`. An identical recompute leaves the stored digest and returns `hit`. A different body raises `CacheError("conflict")`, the event carries both digests, and the stored digest is unchanged. A root inside a directory named `.factverify` raises `location`. Export then import returns the same digests; a manifest whose digest was edited raises. A source scan of `src/cache` and `src/eval` fails if a file other than `gateway.py` calls `get_or_compute`. Confirm these tests fail before T022.

### Implementation for User Story 4

- [X] T022 [P] [US4] Implement `cache_key` in `src/cache/key.py` per `research.md` Decision 5. Full sha256 of UTF-8 bytes. No trim and no case fold. `hash_mapping` from `src.train.config` hashes the decoding object. `sample_index` must be an int ≥ 1. `request_kind` is `generate` or `score`. `producer_run_id` is required on the request and is not part of the lookup key. Raise `CacheError("D-60")` while D-60 is open.
- [X] T023 [US4] Replace `GenerationCache` in `src/cache/store.py` with `open_cache` and `get_or_compute` per `contracts/cache.md` and `research.md` Decision 6. Delete the default path `.cache/generations.db`, the 16-character hash, and `INSERT OR REPLACE`. Refuse a resolved root inside `.factverify`. On a digest mismatch emit `corrupt`, do not return the stored body, and call `compute`. On a different digest for an existing key emit `conflict` with both digests, leave the row, and raise. An identical digest is a no-op. Each call returns exactly one event.
- [X] T024 [US4] Implement `export_cache` and `import_cache` in `src/cache/export.py`. The manifest lists keys and content digests and has its own digest over the entry bytes. Import refuses a mismatch.
- [X] T025 [US4] Change `CachePort` in `src/eval/gateway.py` to `get_or_compute` per `contracts/cache.md`. Add required `identity_hash: str` on `Gateway`. `complete` and `score` build a `CacheRequest` from that hash, the probe prompt as `model_input`, the decoding mapping already sent, `sample_index`, and `request_kind` `generate` or `score`. Replay still skips the cache. Add `note_cache_event` on `Accountant` in `src/eval/budget.py` that appends the event and does not change a balance or a charge rule. `hit` queries kind `cache_hit`. `miss` and `corrupt` query kind `generation`. `conflict` queries kind `generation`, notes the event, then raises. Pass `sample_index=1` at the existing single-completion calls in `src/eval/native.py` and `src/eval/__init__.py`. Update `DictCache` in `tests/eval_ports.py`, `_MemoryCache` in `src/eval/run.py`, and the `Gateway(` calls in `tests/test_eval.py` and `tests/test_controls.py` so they pass `identity_hash` and implement `get_or_compute`. Do not edit `.factverify/spec/attacks.yaml`. Run `uv run pytest tests/test_eval.py tests/test_controls.py -q` and keep those hooks green.

**Checkpoint**: US4 hooks pass. `test_overwrite` is gone. Eval tests still pass. D-20 is unread, and FV-CACHE-004 is not marked implemented.

---

## Phase 7: User Story 6 — Keep final-test rows out of threshold selection (Priority: P1)

**Goal**: Threshold selection returns one false-rejection upper bound per threshold on calibration rows, and raises as soon as any row is final-test. A verdict without a known checkpoint id or evaluation-run id fails the load and names the row.

**Independent Test**: Call `select_thresholds` on calibration rows. Call it again with one final-test row, including while D-03 is still open. Load verdicts whose ledger ids resolve, and one whose id is unknown.

### Tests for User Story 6

- [X] T026 [US6] Write failing tests in `tests/test_stats.py`: `test_fv_stat_008_no_final_test_tuning` and `test_fv_stat_010_ledgered_only`. Use `MemoryStatsLedger` and `tests/fixtures/stats/spec/margins.yaml`. Two calibration rows with `threshold_id` `t0` and `t1`, `oracle_label` `genuine_reference`, and `rejected` true and false, against a closed D-03 and D-05 in a copy of `closed.yaml`, return two bounds. Each bound's point is the rejection rate and the zero-error bound is positive. The same rows plus one `split: final_test` raise `StatsError("final_test")` even when the decision file is `open.yaml`. A verdict whose `checkpoint_ledger_id` or `evaluation_run_id` is unknown raises and the message contains that `row_id`. A matching pair loads. Confirm the tests fail before T027.

### Implementation for User Story 6

- [X] T027 [P] [US6] Implement verdict loading in `src/stats/io.py` per `contracts/estimate.md`. `load_verdicts` takes the rows, `spec_root`, and `StatsLedgerPort`. A missing margins file raises. A missing or unknown checkpoint id or evaluation-run id raises `StatsError` naming `row_id`. The run's checkpoint id must equal the verdict's checkpoint id. Do not resample in this task.
- [X] T028 [US6] Implement `select_thresholds` in `src/stats/thresholds.py` per `contracts/estimate.md`. Raise `final_test` when any loaded row has split `final_test` or `final-test` before reading D-03. Then raise `D-03` or `selection_uncertainty_procedure` while that decision is open or the margins field is null or `DECISION_REQUIRED`. When both are closed as `one_sided_exact`, return one upper bound per `threshold_id` for `oracle_label` `genuine_reference`. Zero errors use `1 - gamma ** (1/n)` in `Decimal` with gamma from the fixture margins value. Positive counts use the bisection in `research.md` Decision 7 with `SOLVER_WIDTH = Decimal("1e-12")` written once in `src/stats/bounds.py`. `estimate(..., purpose="threshold_selection")` may call this function; any other `purpose` string raises `purpose`. A final-test table must not return a partial calibration bound.

**Checkpoint**: US6 hooks pass. A mixed calibration and final-test table raises `final_test` while D-03 is open.

---

## Phase 8: User Story 5 — Estimate intervals on checkpoint and fact blocks (Priority: P2)

**Goal**: Resampling keeps every prompt row of a selected checkpoint-fact block together. A crossed table analysed as nested is refused. Paired arms share case ids. Family rows follow a closed D-10 record, and an empty family has `n` 0 and no rate. Zero errors produce a positive upper bound. Multiplicity matches the fixture. The same seed repeats. The coverage check shows the row resample falling short of nominal.

**Independent Test**: Draw one nested resample and request a row resample. Run crossed and nested on a fact that sits on two checkpoints. Estimate a paired difference on matched cases and on a missing case. Estimate two families plus an empty one. Estimate a zero-error sample. Adjust the fixture p-values. Run the same table and seed twice. Run the coverage simulation.

### Tests for User Story 5

- [X] T029 [US5] Add failing tests in `tests/test_stats.py`: `test_fv_stat_001_block_resampling`, `test_fv_stat_002_crossed`, `test_fv_stat_003_paired`, `test_fv_stat_004_per_family`, `test_fv_stat_005_zero_count`, `test_fv_stat_006_multiplicity`, `test_fv_stat_007_deterministic`, and `test_fv_stat_009_coverage_sim`. Use `closed.yaml` unless noted. A drawn nested block includes every `prompt_id` of that `(checkpoint_ledger_id, fact_id)`. `estimate(..., unit="row")` raises `rows`. A fact on two checkpoints with `crossed.yaml` resamples. The same table with `design: nested` raises `design`. Two arms that share case ids use the same ids in each replicate. An arm missing one case raises and the message lists that case. While D-06 is open, an unweighted paired difference still runs when D-07 and D-57 are closed; a verdict file that adds per-case weights raises `D-06`. Closed D-10 `mean` writes one row per family plus an overall row. A family with no rows has `n` 0 and no `point`. Open D-10 raises `D-10`. Zero errors, `n` 20, gamma `0.05`, yield point `0` and upper bound `1 - Decimal("0.95") ** (Decimal(1) / Decimal(20))` within `1e-12`. A helper that would return a zero-width interval at 0 is not what `estimate` returns. `adjust([0.01, 0.04, 0.03])` with D-08 `holm` returns `(0.03, 0.06, 0.06)`. With `bh` it returns `(0.03, 0.04, 0.04)`. With `by` it returns values within `1e-9` of `(0.055, 0.0733333333, 0.0733333333)`. `bad_procedure.yaml` raises `D-08`. Two `estimate` calls with the same verdicts, `closed.yaml`, and seed `7` match on every estimate and bound, and the table records that seed, `replicate_count` 19, and `design`. `coverage_simulation` on `sim.yaml` reports `block_coverage` within `0.10` of `0.95` and `row_coverage` below `0.95`. Open D-57 raises `D-57`. Confirm these tests fail before T030.

### Implementation for User Story 5

- [X] T030 [P] [US5] Implement `draw_blocks` and `draw_rows` in `src/stats/bootstrap.py` per `research.md` Decision 7. `draw_blocks` uses `random.Random(seed)` and only `paired_block_bootstrap`. Nested resampling draws `(checkpoint_ledger_id, fact_id)` blocks with replacement and copies every prompt row of a drawn block, repeated when the block is drawn again. Crossed resampling draws checkpoint ids and fact ids independently; a case is kept when both ids were drawn, with multiplicity the product of the two counts. Raise `design` when `nested` sees one `fact_id` on two checkpoints. `draw_rows` resamples prompt rows. `estimate` must not call `draw_rows`.
- [X] T031 [P] [US5] Finish `one_sided_exact` in `src/stats/bounds.py` per `research.md` Decision 7. T028 already places `SOLVER_WIDTH` and the zero-error power there for threshold selection. Add the positive-count bisection in that same function if it is not there yet. Do not add a second solver. Any procedure token other than `one_sided_exact` raises `D-03`. Do not call the function when D-03 is open.
- [X] T032 [P] [US5] Implement `adjust` in `src/stats/multiplicity.py` for `holm`, `bh`, and `by` only. Open D-08 or any other token raises `D-08`. The result length equals the input length. Holm adjusted values are `max` of the step-down `(m-j+1)*p_(j)` terms. BH and BY use the step-up minimum from the right. BY multiplies by the harmonic sum `1 + 1/2 + ... + 1/m`.
- [X] T033 [US5] Implement paired differences in `src/stats/delta.py` and family rows in `src/stats/report.py`. Case id is `(checkpoint_ledger_id, fact_id)`. Both arms must contain the same ids; the error lists the missing ones. The same draw is applied to both arms. While D-06 is open, each matched case has weight 1 and a caller-supplied weight raises `D-06`. A closed weight token other than `uniform` raises `D-06`. While D-10 is open, `family_rows` raises `D-10`. When closed with `mean`, emit one row per `control_family` and one overall row. `n` 0 omits `point`.
- [X] T034 [US5] Implement `estimate` in `src/stats/report.py` per `contracts/estimate.md` steps for `final_report`. Raise `D-07` or `D-57` while that row is open. Refuse `unit="row"`. Percentile bounds are the empirical quantiles at `gamma/2` and `1 - gamma/2`. Record `seed`, `replicate_count`, `design`, margins `version`, and the sha256 of the canonical verdict JSON. Call `adjust` only when D-08 is closed, using the two-sided percentile bootstrap probability against zero, clipped to 1. A zero error count goes through `one_sided_exact` only when D-03 is closed.
- [X] T035 [US5] Implement `coverage_simulation` in `src/stats/bootstrap.py` per `research.md` Decision 8. Read every field from the simulation document; a missing field raises that name. Each checkpoint rate is `true_fcr` plus that checkpoint's shift, clipped to `(0, 1)`, then independent Bernoulli prompt rows. Compare `block_coverage` with `1 - gamma` using `coverage_tolerance`. Score the same draws with `draw_rows` for `row_coverage`. Raise `D-57` while that row is open.

**Checkpoint**: US5 hooks pass. The study `margins.yaml` is untouched, and an open D-07 file still raises `D-07`.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Lint, the full suite, and a check that the frozen spec was not edited.

- [X] T036 [P] Confirm `git status -- .factverify/spec` shows no edits from this feature. Do not stage a change under that directory or under `spec-unlearning/`.
- [X] T037 Run `make lint` and fix annotations or ruff findings in `src/ledger/`, `src/cache/`, `src/stats/`, `scripts/ledger.py`, and the tests touched above. Do not silence a new finding with a blanket ignore.
- [X] T038 Run `make test` for `tests/`. The new hooks and the existing harness, control, match, and eval hooks must pass. A failure in an older hook means T012 or T025 changed a contract those tests still use.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. Blocks every user story.
- **User stories**: Depend on Foundational. US2 and US3 also depend on US1's `add_checkpoint` and `add_evaluation_run`. US4 does not depend on the ledger stories. US6 depends on Foundational plus the stats fixtures, not on the bootstrap. T028 creates `src/stats/bounds.py`. T031 extends that file and must not start before T028. US5's `estimate` depends on US6's `load_verdicts`.
- **Polish**: Depends on the stories being implemented.

### User Story Dependencies

- **US1 (P1)**: After Foundational. No other story required. MVP.
- **US2 (P1)**: After US1, because corrections call `add_checkpoint`.
- **US3 (P1)**: After US1, because the pass guard extends `add_evaluation_run`. Can follow US2 or run after US1 if it does not edit the supersession branch.
- **US4 (P1)**: After Foundational. Independent of the ledger stories. Do not start T025 until T023 exists.
- **US6 (P1)**: After Foundational and T005. Independent of US4. Does not need `estimate`.
- **US5 (P2)**: After US6's `load_verdicts`. T030, T031, and T032 touch different files and can run together after T029. T033 and T034 wait on those three. T035 waits on T030.

### Within Each User Story

- The story's test task fails before its implementation tasks.
- Schema and decision loaders stay in Foundational. Stories do not recreate them.
- A story's CLI task follows that story's library task.

### Parallel Opportunities

- T001–T005 are different files.
- T006 and T007 are different files. T008 adds dataclasses in `src/ledger/api.py` and can follow T007 because it does not call `open_ledger`. Do not create `src/ledger/git.py`.
- T022 (`key.py`) can run beside the failing cache tests once T021 exists, and beside T024 only after the store API is known. T024 waits on T023.
- T027 (`io.py`) and the US6 tests' ledger double are different files. T028 waits on T027.
- T030, T031, and T032 are different files and can run together after T029.
- US4 and US6 can proceed in parallel after Foundational, on different packages.

---

## Parallel Example: Setup

```bash
# Different files, no shared types yet:
Task: "Add LedgerError, CacheError, and StatsError"
Task: "Create tests/fixtures/ledger/decisions/*.yaml"
Task: "Create tests/fixtures/cache/decisions/*.yaml"
Task: "Create tests/fixtures/stats/spec/margins.yaml and decision files"
Task: "Create tests/stats_ports.py"
```

## Parallel Example: User Story 4 and User Story 6

```bash
# After Foundational, different packages:
Task: "Replace tests/test_cache.py and implement src/cache/key.py"
Task: "Write tests/test_stats.py threshold and ledger-id hooks and src/stats/io.py"
```

## Parallel Example: User Story 5

```bash
# After the failing stats tests exist, different modules:
Task: "Implement draw_blocks in src/stats/bootstrap.py"
Task: "Implement one_sided_exact in src/stats/bounds.py"
Task: "Implement adjust in src/stats/multiplicity.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3.
3. Stop and run the US1 hooks. A closed D-56 row stores a checkpoint and returns its role and split. An open D-56 row writes nothing. That is the MVP.

### Incremental Delivery

1. Setup + foundational → an empty ledger file whose triggers reject `UPDATE`.
2. US1 → complete rows, lineage, evaluation runs, harness fields.
3. US2 → corrections, export, concurrency.
4. US3 → dirty final-test refusal, disjointness, one pass.
5. US4 → cache key, integrity, gateway events. Charge rules stay as they are.
6. US6 → final-test rows cannot select a threshold. Unknown ledger ids fail the load.
7. US5 → block intervals, pairing, families, coverage.
8. Polish → `make lint` and `make test`.

### Notes

- Passing a fixture does not mark FV-LEDG-002, FV-LEDG-004, FV-CACHE-001, FV-CACHE-004, FV-STAT-001, FV-STAT-002, FV-STAT-004, FV-STAT-005, FV-STAT-006, FV-STAT-007, or FV-STAT-009 implemented while D-56, D-60, D-20, D-07, D-10, D-03, D-08, or D-57 is open on the study record. A weighted estimate is not implemented while D-06 is open. Fixture files may close only the row that hook asserts.
- Do not edit `.factverify/spec/` or `spec-unlearning/`.
- Do not read `cache_policy.charge_rule` from the cache package. `note_cache_event` does not change a balance.
- `draw_rows` exists for `test_fv_stat_009_coverage_sim` only. `estimate` raises `rows` if asked to use it.
- In-memory harness doubles are not required to enforce D-56. The spec hooks run against `open_ledger`.

---

## Task counts

| Phase | Tasks | IDs |
|-------|-------|-----|
| Setup | 5 | T001–T005 |
| Foundational | 3 | T006–T008 |
| US1 | 5 | T009–T013 |
| US2 | 4 | T014–T017 |
| US3 | 3 | T018–T020 |
| US4 | 5 | T021–T025 |
| US6 | 3 | T026–T028 |
| US5 | 7 | T029–T035 |
| Polish | 3 | T036–T038 |
| **Total** | **38** | |
