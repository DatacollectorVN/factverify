# Tasks: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Feature**: `20260927-120701-evaluators-query-budget`  
**Input**: Design documents from `specs/20260927-120701-evaluators-query-budget/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included. `FV-EVAL — P2-2.md` (draft) requires fourteen named pytest hooks, `test_fv_eval_001_all_calls_charged` through `test_fv_eval_014_raw_generations`. Write each story's tests before that story's implementation, and confirm they fail first.

**Organization**: Tasks are grouped by user story. Do not close D-14, D-17, D-18, D-20, D-21, D-22, D-26, or D-27 in `.factverify/spec/`. Numbers below belong only in `tests/fixtures/eval/`.

**Design notes** (read from disk; Obsidian MCP was unavailable when the plan was written): Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-2. Handbook (status: draft): "2. The eight invariants" (I2–I5, I8), "6.4 One query needs a definition", "6.5 Budget arithmetic", "6.6 Adaptive attacks".

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: User story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and offline fixtures. Do not download weights. Do not edit `.factverify/spec/`.

- [X] T001 Create stub modules under `src/eval/` with a module docstring and no behaviour yet: `__init__.py`, `errors.py`, `types.py`, `spec_load.py`, `budget.py`, `gateway.py`, `channels.py`, `probes.py`, `native.py`, `semantic.py`, `verdict.py`, `factverify.py`, `thresholds.py`, `store.py`, `cost.py`, `run.py`. Leave the existing integer `BudgetAccountant` in `src/eval/budget.py` until T012 replaces that file.
- [X] T002 [P] Create `tests/fixtures/eval/spec_closed/` with `attacks.yaml`, `access_profile.md`, `witness_rule.md`, `closure_templates.yaml`, and `margins.yaml`. These values are fixture inputs, not study caps. `attacks.yaml`: `revision: fixture-eval`, `common_cap: 4`, each arm `total: 4`. Channel trials: `native` and `semantic_only` get `prompt_variation: 2`, `confirmation: 1`, `locality: 1`; `factverify` gets `prompt_variation: 1`, `repeated_sampling: 1`, `confirmation: 1`, `locality: 1`. Copy the charge-rule objects from `.factverify/spec/attacks.yaml` (`generation_trial_unit`, `candidate_scoring_unit`, `cache_policy`, `retry_policy`, `failure_policy`, `discard_policy`, `reference_cost_policy`) and set `accounting.unused_confirmation_reallocation: false`. `cost_vector_fields`: `tokens`, `scored_candidates`, `training_steps`, `exports`, `wall_clock`. `blocking_decisions` for D-14, D-17, D-18, D-20, D-21, D-22, D-26, D-27 all `status: closed`. Access profile: `profile: A`, `capabilities.scores: verified`, `candidate_scoring: verified`, `internals: unavailable`, `text: verified`. Witness rule: route A `enabled: true`, routes B and C `enabled: false`, `aggregation_policy.raw_maximum_role: diagnostic_only`, `no_witness_is_not_accept: true`, `status_alignment.mapping` as in the frozen witness rule (`accept` → `conformance`). Closure file: one class `E` template `tmpl_cal` in group `grp_cal` with `split: calibration` and `extra_premises: []`; one class `E` template `tmpl_final` in group `grp_final` with `split: final_test`; one class `I` template `tmpl_infer` with `extra_premises: ["hint"]` and group `grp_infer` split `calibration`. `margins.yaml`: `status: unresolved_worksheet` and null margin values.
- [X] T003 [P] Create three more spec roots under `tests/fixtures/eval/`, each a copy of `spec_closed` with one change. `spec_unequal/`: `factverify.total` is `5` and its `prompt_variation` trials are `2` (arm sums differ; `common_cap` stays `4`). `spec_realloc/`: `unused_confirmation_reallocation: true`. `spec_unresolved/`: `accounting.cache_policy.charge_rule: DECISION_REQUIRED` and D-20 `status: open`.
- [X] T004 [P] Create `tests/fixtures/eval/cases/calibration.json` for case `case-1`, ledger id `led-1`, fact `fact-1`, split `calibration`, `spec_revision: fixture-eval`, `access_label: A`, `identifiability: identifiable`, `answers: ["Zephyr"]`, and two probes: `probe_native` with `probe_class: native` and prompt `Where is Zephyr?`, and `probe_cal` with `probe_class: template`, `template_id: tmpl_cal`, `group_id: grp_cal`. Create `tests/eval_ports.py` with a scripted `ModelPort` that returns a fixed completion `Zephyr` and fixed score fields, a dict `CachePort`, and a `MetricPort` whose BERTScore is `0.5`. No network and no `from_pretrained`.

**Checkpoint**: Stub modules and fixture files exist. The old accountant still imports.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Types, fail-closed spec load, and ports every story calls. No story starts until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Implement `FactVerifyEvalError(ValueError)` and `BudgetExhaustedError(FactVerifyEvalError)` in `src/eval/errors.py`. Every eval failure raises one of these and names the field, decision id, channel, arm, path, or call site. `BudgetExhaustedError` carries `channel_id`, `charge`, and `remaining`.
- [X] T006 [P] Implement the dataclasses from `data-model.md` in `src/eval/types.py`: `Case`, `Probe`, `QueryRequest`, `ChargeResult`, `ChannelBudget`, `BudgetRecord`, `ChannelScore`, `VerdictRow`, `Bounds`, `FrozenThresholds`. `Case.split` normalizes `final-test` to `final_test` and refuses any other unknown token. No study numbers as field defaults.
- [X] T007 [P] Implement `load_spec(spec_root: Path) -> SpecBundle` and `require_closed(bundle, decision_ids: list[str]) -> None` in `src/eval/spec_load.py`. Load the five artifact names from T002. A missing or unreadable file raises `FactVerifyEvalError` naming the path. A value that is null or the string `DECISION_REQUIRED` on an attacks accounting field the caller passes to `require_field` raises naming that field. `require_closed` raises naming each requested id whose `blocking_decisions` status is not `closed`. Nulls inside `margins.yaml` do not abort load. Do not write anything under `spec_root`.
- [X] T008 [P] Implement `empty_cost_record(arm_id, permitted_total) -> BudgetRecord` in `src/eval/cost.py`. The record includes every `data-model.md` budget field: generated trials, scored candidates, input tokens, output tokens, tokens, exports, training steps, wall-clock seconds, GPU-hours, peak memory bytes, and per-channel permitted / charged / refused / remaining. `tokens` is `input_tokens + output_tokens`. Remaining starts equal to permitted.
- [X] T009 [P] Declare `ModelPort`, `CachePort`, and `MetricPort` in `src/eval/gateway.py` as protocols matching `contracts/evaluate_case.md` and `contracts/accountant.md`. Methods are `complete`, `score_candidate`, `get`, `put`, and `bertscore`. No method body calls a model.

**Checkpoint**: A fixture spec root loads, an open decision id is refused by name, and the cost record has every field. User stories can begin.

---

## Phase 3: User Story 1 — Charge every call under one equal budget (Priority: P1) 🎯 MVP

**Goal**: `Accountant.query` charges `n * k` generation trials to a named channel, refuses an overspend and records it, refuses unequal arm totals, keeps confirmation on its own line, applies the frozen cache / retry / failure charge rules, and writes a cost vector whose unused remainder stays visible.

**Independent Test**: `uv run pytest tests/test_eval.py -k "001 or 002 or 003 or 004 or 005 or 006" -v`

### Tests for User Story 1

- [X] T010 [US1] Replace `tests/test_budget.py` by writing these tests in `tests/test_eval.py` so they fail before T011–T013 (import error or failed assertion). Use `spec_closed` unless a case says otherwise. Delete `tests/test_budget.py` in this task so `BudgetAccountant(budget_per_fact=...)` is no longer the supported API.
  - `test_fv_eval_001_all_calls_charged` — a request with `prompt_count=2` and `sample_count=3` charges 6 generation trials to `prompt_variation`. `illegal_model_calls` on a source string that calls `.generate(` outside `gateway.py` returns that line. The tree under `src/eval/` has no `from_pretrained`.
  - `test_fv_eval_002_refuses_overspend` — a charge within the remainder decreases that channel's remainder by the charge. A charge above the remainder raises `BudgetExhaustedError` and the refused request is on the budget record. The remainder is unchanged.
  - `test_fv_eval_003_equal_totals` — `spec_closed` start records total `4`. `spec_unequal` raises naming each arm id and its total. `load_spec` of `.factverify/spec` plus `require_closed` for D-22 raises naming `D-22`.
  - `test_fv_eval_004_cost_vector` — after a partial spend, every cost field from `data-model.md` is present and not null. The unspent channel `remaining` equals permitted minus charged observations.
  - `test_fv_eval_005_confirmation_reserve` — confirmation charges stop at the confirmation cap of 1. A discovery request with `spend_confirmation=true` against `spec_closed` is refused and the confirmation remainder stays 1. The same request against `spec_realloc` is allowed to draw the confirmation remainder.
  - `test_fv_eval_006_cache_retry_policy` — a cache hit follows `cache_policy` (`observation_charged` true, `charge_rule` `zero_new_compute`: observation count increases, new-compute count does not). A retry charges the new attempt and the original failure. A transport failure charges the failure policy and adds no raw completion. `spec_unresolved` start raises naming `cache_policy.charge_rule`.

### Implementation for User Story 1

- [X] T011 [US1] Replace `src/eval/budget.py` with `Accountant` per `contracts/accountant.md` and `research.md` Decisions 1–4. Construct it from a `SpecBundle`, a `Case`, and an arm id. `ensure_capacity(channel_id, trials)` raises `BudgetExhaustedError` and stores the refused request without charging when `trials` exceeds the channel remainder. `query` applies the charge table in `contracts/accountant.md`. Confirmation spends only the `confirmation` channel. Discovery with `spend_confirmation=true` is refused unless `unused_confirmation_reallocation` is `true`. Unknown `charge_rule` tokens raise. `budget_record()` returns the `cost.py` record, including a positive `remaining` when the arm stops early. `check_arm_totals(bundle)` raises listing each arm total when the three totals differ or a total disagrees with the sum of its channel trials or with `common_cap`. Do not read `budget_per_fact`.
- [X] T012 [US1] Implement `complete` and `score` on a `Gateway` class in `src/eval/gateway.py` per the gateway order in `contracts/accountant.md`: cache get, cache-hit charge with no model call, `ensure_capacity` before `model.complete`, generation charge only after a completion, transport failure charged once as `transport_failure` with no extra generation trial, then `cache.put`. Score calls use `candidate_score` and do not use the cache. Implement `illegal_model_calls(root: Path) -> list[tuple[str, int]]` that flags `from_pretrained`, `.generate(`, and `ModelPort` calls under `src/eval/` outside `gateway.py`. Fill wall-clock, GPU-hours, and peak memory on the budget record from measured values passed in by the gateway (tests may pass zeros). GPU-hours are elapsed seconds times CUDA device count over 3600 when CUDA is available, else `0`.
- [X] T013 [US1] Run `uv run pytest tests/test_eval.py -k "001 or 002 or 003 or 004 or 005 or 006" -v` and make those six hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Story 1 stands alone. Scripted charges obey the fixture spec. The frozen spec root still refuses D-22. No evaluator scores a probe yet.

---

## Phase 4: User Story 2 — Keep each arm inside its probes and its access profile (Priority: P2)

**Goal**: The access profile allows or refuses a channel. The native arm scores only native probes. Semantic-only and FactVerify draw equivalence probes only from the case split. Inference templates are reported separately.

**Independent Test**: `uv run pytest tests/test_eval.py -k "007 or 008 or 009" -v` while the US1 hooks still pass.

### Tests for User Story 2

- [X] T014 [P] [US2] Add `tests/fixtures/eval/spec_profile_a/` as a copy of `spec_closed` whose access profile sets `scores: unavailable`, `candidate_scoring: unavailable`, and `internals: unavailable`. Add `tests/fixtures/eval/cases/final_test_probe.json` with split `final_test` and template `tmpl_final`. Add `tests/fixtures/eval/cases/inference.json` with split `calibration` and template `tmpl_infer`.
- [X] T015 [US2] Append these failing tests to `tests/test_eval.py`:
  - `test_fv_eval_007_access_gate` — `prompt_variation` (observation only) is allowed on `spec_profile_a`. A request whose channel `capability_requirements` include `raw_scores`, or a score call while `scores` is `unavailable`, raises naming the channel and the capability.
  - `test_fv_eval_008_native_probes` — on `spec_closed` (scores verified, D-27 closed) the native arm returns ROUGE-L, BERTScore, Truth Ratio, answer probability, and answer rank for `probe_native`. Routing `tmpl_cal` to the native arm raises naming `tmpl_cal`. On `spec_profile_a` the three score metrics are refused and are not filled with zeros.
  - `test_fv_eval_009_split_templates` — a `final_test` case accepts `tmpl_final` and rejects `tmpl_cal`, naming `grp_cal` and both splits. Drawing `tmpl_infer` for the primary equivalence score raises naming `tmpl_infer` and places that id on `inference_output` only.

### Implementation for User Story 2

- [X] T016 [P] [US2] Implement `permit(bundle, channel_id, kind) -> None` in `src/eval/channels.py` per `research.md` Decision 7. Refuse when the channel is disabled, when `raw_scores` or `weight_update` is required and the profile does not grant scores or internals, and when `kind` is `candidate_score` while `candidate_scoring` is `unavailable`. A permitted channel returns without charging; charging stays in `Accountant`.
- [X] T017 [P] [US2] Implement `resolve_probe(bundle, case, probe) -> ProbeClass` in `src/eval/probes.py` per `research.md` Decision 6. Lookup by template id in `closure_templates.yaml` overrides `probe_class`. Class `I` or non-empty `extra_premises` is inference. Class `X` is refused for the primary score. Class `E` or `R` is legal only when `groups[].split` equals `case.split`. An id that resolves in the closure file is never `native`.
- [X] T018 [P] [US2] Implement `score_native(case, probe, gateway) -> list[ChannelScore]` in `src/eval/native.py`. Refuse a probe `resolve_probe` does not classify as native. ROUGE-L is the in-process LCS F-measure of the completion against `case.answers`. BERTScore comes from `MetricPort`. Truth Ratio, answer probability, and answer rank are `gateway.score` calls after `permit`. Do not average the five numbers. Do not substitute a number when `permit` raises.
- [X] T019 [P] [US2] Implement `select_equivalence(bundle, case, probes) -> tuple[list[Probe], list[Probe]]` in `src/eval/semantic.py`. Return `(primary, inference)`. Primary probes are class `E` on the case split. Inference probes are returned in the second list and are not included in the first. A group from another split raises naming the group id and both splits.
- [X] T020 [US2] Run `uv run pytest tests/test_eval.py -k "001 or 002 or 003 or 004 or 005 or 006 or 007 or 008 or 009" -v` and make the US1 and US2 hooks pass together.

**Checkpoint**: User Stories 1 and 2 both work. Channels and probe classes follow the fixture spec. Verdict phrases are not chosen yet.

---

## Phase 5: User Story 3 — Return one frozen verdict, with channel scores kept apart (Priority: P2)

**Goal**: Each case and arm returns exactly one of the four statuses, with the access label and provenance. A confirmed recovery witness requires an enabled confirmation route. A lone bound crossing is a diagnostic. Channel scores stay separate.

**Independent Test**: `uv run pytest tests/test_eval.py -k "010 or 011 or 013" -v` while the US1 and US2 hooks still pass.

### Tests for User Story 3

- [X] T021 [US3] Append these failing tests to `tests/test_eval.py`. Use `spec_closed`, `Bounds` labeled `calibration`, and the scripted ports in `tests/eval_ports.py`.
  - `test_fv_eval_010_verdict_vocabulary` — `identifiability: identifiable` yields one of the four phrases in `contracts/verdict_row.md`, with `status_code` from `research.md` Decision 8, plus `access_label`, `checkpoint_ledger_id`, `fact_id`, `split`, `arm_id`, and `spec_revision`. The same case with `identifiability: structurally_indistinguishable` yields `non-identifiable under this profile` and does not use the phrases for conformance or a confirmed witness. A missing `identifiability` raises.
  - `test_fv_eval_011_decision_rule` — one probe score above its bound, with route A not run, does not yield `confirmed recovery witness`; `diagnostics.raw_maximum` is that score. A scripted confirmation success on route A yields `confirmed recovery witness` and `confirmation_route` `A`. `raw_maximum_role` other than `diagnostic_only` raises.
  - `test_fv_eval_013_no_channel_average` — the verdict `scores` list has one `{channel_id, score, bound}` per channel and no `average`, `combined_score`, or `mean_score` key. Building a payload that adds `average` raises.

### Implementation for User Story 3

- [X] T022 [P] [US3] Implement `build_verdict(...) -> VerdictRow` in `src/eval/verdict.py` per `contracts/verdict_row.md`. `status` is only one of the four phrases. Map them to `status_code` exactly as `research.md` Decision 8. Raise if `average`, `combined_score`, or `mean_score` is present. Copy provenance from the case and the loaded `revision`.
- [X] T023 [US3] Implement `decide(bundle, case, scores, confirmation) -> VerdictRow` in `src/eval/factverify.py` using the order in `contracts/verdict_row.md`. Honor `no_witness_is_not_accept`. A successful enabled route with its confirmation charges inside the reservation is the only path to `confirmed recovery witness`. Store a bound crossing on `diagnostics.raw_maximum` and do not copy it into `status`. Refuse when `aggregation_policy.raw_maximum_role` is not `diagnostic_only`. Call `require_closed` for D-14 before emitting a verdict.
- [X] T024 [US3] Implement `evaluate_case` in `src/eval/__init__.py` for splits other than `final_test`, per `contracts/evaluate_case.md` steps 1–4 and 6–7, skipping the thresholds loader. Load all three arm totals even when `arm` names one arm. Run native through `native.score_native` and semantic-only / FactVerify equivalence probes through `semantic.select_equivalence` and the gateway. FactVerify's status comes from `decide`. Export `evaluate_case`, `CaseResult`, and `FactVerifyEvalError`. A final-test case raises naming `thresholds` until T028.
- [X] T025 [US3] Run `uv run pytest tests/test_eval.py -k "010 or 011 or 013" -v` and the US1 and US2 hooks. All of those hooks pass together.

**Checkpoint**: Calibration cases return one of the four statuses. Final-test cases still refuse. Raw files are not required yet.

---

## Phase 6: User Story 4 — Run final-test cases only under frozen thresholds (Priority: P2)

**Goal**: A final-test case proceeds only when `results/thresholds.json` matches the `thresholds-v1` blob. A missing tag, a changed file, or a bounds argument refuses the case. The verdict records the tag.

**Independent Test**: `uv run pytest tests/test_eval.py -k "012" -v` while the earlier hooks still pass.

### Tests for User Story 4

- [X] T026 [US4] Append `test_fv_eval_012_frozen_thresholds` to `tests/test_eval.py` so it fails before T027. Use a fake `ThresholdsSource` and a temp `results/thresholds.json` whose bytes hash to a known digest. The matching tag and digest let a `final_test` case finish and set `thresholds_tag` to `thresholds-v1`. A missing tag, a digest mismatch, and an `evaluate_case(..., bounds=...)` call on that split each raise. A `calibration` case that is given `bounds.split=final_test` raises. The test must not invoke `git`.

### Implementation for User Story 4

- [X] T027 [US4] Implement `ThresholdsSource` and `load_frozen_thresholds` in `src/eval/thresholds.py` per `contracts/thresholds.md`. The default source uses `git rev-parse` and `git show` for `thresholds-v1:results/thresholds.json`. Compare SHA-256 of the working-tree file to the blob. Refuse a path that does not resolve to `results/thresholds.json`. Do not read threshold numbers from `margins.yaml`. A null margin is not a threshold.
- [X] T028 [US4] Extend `evaluate_case` in `src/eval/__init__.py` so `split=final_test` calls `load_frozen_thresholds` and copies `tag` onto the verdict. Passing `bounds` on that split raises naming `bounds`. Construction and calibration keep using `bounds` and do not read `results/thresholds.json`.
- [X] T029 [US4] Run `uv run pytest tests/test_eval.py -k "012" -v` and the US1–US3 hooks. All of those hooks pass together.

**Checkpoint**: Final-test loading is gated by the tag. Calibration behaviour from US3 is unchanged.

---

## Phase 7: User Story 5 — Keep every raw generation for audit (Priority: P3)

**Goal**: Each charged completion is a JSONL line outside `.factverify/`. The line count equals the charged completion count. Replay from those lines repeats the verdict and scores. The CLI is the operator entry point.

**Independent Test**: `uv run pytest tests/test_eval.py -k "014" -v` while all earlier hooks still pass.

### Tests for User Story 5

- [X] T030 [US5] Append `test_fv_eval_014_raw_generations` to `tests/test_eval.py` so it fails before T031. A finished calibration case writes one JSONL object per charged completion, containing the fields in `data-model.md` (Raw generation), and `store.count` equals that charge count. A `raw_dir` resolved inside `.factverify/` raises naming the path. Replay with the same case, seed, and lines, and a `ModelPort` that would raise if called, returns the same `status` and the same scores.

### Implementation for User Story 5

- [X] T031 [P] [US5] Implement `RawStore` in `src/eval/store.py` per `contracts/verdict_row.md`. `append` refuses a resolved path equal to `.factverify` or nested inside it. Each line is one charged completion. `count(case_id, arm_id)` reads the file. Transport failures with `observation_charged: false` are not lines. A short count is a `FactVerifyEvalError` naming both counts.
- [X] T032 [US5] Teach `Gateway.complete` in `src/eval/gateway.py` to `append` after a successful generation charge. Add `evaluate_case(..., replay=True)` in `src/eval/__init__.py` that reads the JSONL and does not call `ModelPort`. Add the CLI in `src/eval/run.py`: `python -m src.eval.run --case PATH --spec-root PATH --raw-dir PATH [--arm ARM]`, default spec root `.factverify/spec`. Exit 0 only when `CaseResult.status` is `finished`. A refusal prints `error` and exits non-zero. Against the real spec root the error names the open decision ids; do not catch that and exit 0.
- [X] T033 [US5] Run `uv run pytest tests/test_eval.py -v` and make all fourteen hooks pass.

**Checkpoint**: All five stories work. A finished case can be replayed from its raw lines. The frozen spec root still refuses open decisions.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Style gate, the loader and cache boundaries, and the quickstart.

- [X] T034 [P] Run `uv run ruff check src/eval tests/test_eval.py tests/eval_ports.py` and `uv run ruff format --check` on those paths. Fix annotations and style in the files ruff names. Do not add `# noqa` to hide a missing annotation.
- [X] T035 [P] Run `uv run pytest tests/test_cache.py tests/test_models_loader.py -k "009 or test_cache" -v`. Confirm `src/eval/` adds no `from_pretrained`, and `src/cache/store.py` is unchanged.
- [X] T036 Search `src/eval/` for integer caps used as budgets (`budget_per_fact`, a bare `12`, or a default confirmation cap). Remove any that are not the `3600` seconds-per-hour conversion in `gateway.py`. Fixture totals stay in `tests/fixtures/eval/`.
- [X] T037 Run `uv run pytest tests/test_eval.py tests/test_cache.py -v` and confirm the fourteen eval hooks and the existing cache tests pass.
- [X] T038 Read `specs/20260927-120701-evaluators-query-budget/quickstart.md` against `src/eval/run.py`. Update the quickstart only if a flag name drifted. Do not write study cap values into it.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Phase 1. Blocks every story.
- **User Story 1 (Phase 3)**: Depends on Phase 2. No dependency on US2–US5.
- **User Story 2 (Phase 4)**: Depends on Phase 3, because probe scoring charges through `Accountant` and `Gateway`.
- **User Story 3 (Phase 5)**: Depends on Phases 3 and 4. It composes native and semantic scores into a verdict.
- **User Story 4 (Phase 6)**: Depends on Phase 5, because it extends `evaluate_case`. The thresholds module itself does not need probe scoring, but the hook calls `evaluate_case`.
- **User Story 5 (Phase 7)**: Depends on Phases 3 and 5. It appends from `Gateway` and replays a verdict. Start it after Phase 6 so `evaluate_case` is not edited by two stories at once.
- **Polish (Phase 8)**: Depends on Phases 3–7.

### User Story Dependencies

- **US1 (P1)**: First story. Delivers the MVP accountant.
- **US2 (P2)**: Uses US1 charging. Its tests do not need a verdict phrase.
- **US3 (P2)**: Uses US1 charging and US2 probe selection.
- **US4 (P2)**: Uses the US3 entry point. Calibration cases do not load the thresholds file.
- **US5 (P3)**: Uses US1 charges and US3 verdicts. Replay must not call the model port.

### Within Each User Story

- Tests fail before implementation tasks in that phase.
- Foundational modules are not re-stubbed inside a story.
- A story's pytest task is the last task in that phase.
- FR-001 through FR-006 (Phase 3) are green before FR-008 through FR-013 (Phases 4 and 5) are treated as ready.

### Parallel Opportunities

- T002, T003, and T004 can run together. Their paths and field values are fixed in the task text.
- T006, T007, T008, and T009 can run together after T005.
- T016, T017, T018, and T019 touch different files. T018 depends on T016 and T017. T019 depends on T017. Start T018 and T019 together only after T016 and T017 exist.
- T022 can run beside test writing only after T021's expected verdict shape is the contract text, which it is. Prefer T022 after T021 so the test is already failing.
- T031 can run beside other US5 work only before T032 edits the gateway. Do not parallelize tasks that both edit `src/eval/__init__.py`, `src/eval/gateway.py`, or `tests/test_eval.py`.
- T034 and T035 can run together.

---

## Parallel Example: Foundational phase

```bash
# After T005, different files:
Task: "Implement dataclasses in src/eval/types.py"
Task: "Implement load_spec in src/eval/spec_load.py"
Task: "Implement empty_cost_record in src/eval/cost.py"
Task: "Declare ModelPort, CachePort, and MetricPort in src/eval/gateway.py"
```

## Parallel Example: User Story 2

```bash
# After T015, different files:
Task: "Implement permit in src/eval/channels.py"
Task: "Implement resolve_probe in src/eval/probes.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3.
3. Stop and run the US1 independent test. Equal fixture totals charge, unequal totals refuse, and the frozen spec root still names D-22. That is the MVP.

### Incremental Delivery

1. Setup + foundational → spec load and cost records exist.
2. US1 → the accountant is the only charging path.
3. US2 → arms see only the probes and channels the fixture profile allows.
4. US3 → calibration cases return one of the four statuses.
5. US4 → final-test cases require the thresholds tag.
6. US5 → raw lines match charged completions and replay without the model.
7. Polish → ruff, the loader boundary, and the full eval file.

### Notes

- `src/cache/store.py` is P2-7. This task list uses `CachePort` and the dict in `tests/eval_ports.py`.
- `ledger.sqlite` is P2-5. Verdict rows copy `checkpoint_ledger_id` and do not open SQLite.
- Passing fixture tests does not mark a requirement implemented while its decision is open on `.factverify/spec/`.
- Do not edit `.factverify/spec/` or `spec-unlearning/`.

---

## Task counts

| Phase | Tasks | IDs |
|-------|-------|-----|
| Setup | 4 | T001–T004 |
| Foundational | 5 | T005–T009 |
| US1 | 4 | T010–T013 |
| US2 | 7 | T014–T020 |
| US3 | 5 | T021–T025 |
| US4 | 4 | T026–T029 |
| US5 | 4 | T030–T033 |
| Polish | 5 | T034–T038 |
| **Total** | **38** | |

---

## Post-implementation drift fixes (2026-09-27)

Three issues found by `/speckit.analyze` and resolved after all tasks were marked complete:

- **C1** `src/eval/factverify.py` — Replaced `**common` dict spread in all four `build_verdict()` calls with explicit keyword arguments. Pyrefly strict `open-unpacking` error was caused by pyrefly being unable to verify that a bare `dict` satisfied the keyword-only signature.
- **C2** `src/eval/run.py` — Changed `_ports()` return type from `tuple[object, …]` to `tuple[ModelPort, …]` and annotated the local variable as `model: ModelPort`. Both `_FixtureModel` and `_MissingModel` implement the protocol structurally; the annotation was the only thing missing.
- **C3** `tests/fixtures/fact_contract/` — Fixture files `fact_minimal.json` and `fact_example.json` were in the old schema format (pre-v1.0.0: flat string triple, dict aliases, `directions` array, dict `retained_neighbourhood`, `clue_free`/`clue_bearing` arrays). The `.factverify/spec/fact_contract.schema.json` was redesigned in a prior feature. Both fixtures were rewritten to the current v1.0.0 format and `tests/test_fact_contract_schema.py` was updated to test the current schema's required fields and constraint rules.

After fixes: `make lint` → 0 errors · `make test` → 487 passed.
