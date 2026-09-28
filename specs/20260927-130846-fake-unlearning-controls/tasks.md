# Tasks: FV-CTRL — P2-3 Fake-Unlearning Controls

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Input**: Design documents from `specs/20260927-130846-fake-unlearning-controls/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included. `FV-CTRL — P2-3.md` (draft) requires ten named pytest hooks, `test_fv_ctrl_001_family_coverage` through `test_fv_ctrl_010_wrapper_charged`. Write each story's tests before that story's implementation, and confirm they fail first.

**Organization**: Tasks are grouped by user story. Do not close D-53, D-54, D-55, or D-61 in `.factverify/spec/`. Numbers below belong only in `tests/fixtures/controls/`. Do not create `src/controls/match.py`. Do not open SQLite.

**Design notes** (read from disk; Obsidian MCP was unavailable when the plan was written): Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-3, and "Phase 3 — Block 0", Gate 1. Fake-Unlearning Controls (status: draft), "Definition" and "How It Works". Handbook (status: draft), "5.1 Where the boundary sits" and "5.2 The identifiability argument".

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: User story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and CPU fixtures. Do not download weights. Do not edit `.factverify/spec/`.

- [X] T001 Create stub modules under `src/controls/` with a module docstring and no behaviour yet: `__init__.py`, `errors.py`, `config.py`, `decisions.py`, `spec_load.py`, `registry.py`, `base.py`, `ledger.py`, `build.py`, `checks.py`, `suppression.py`, `destruction.py`, `wrappers.py`, `run.py`. Do not create `src/controls/match.py`.
- [X] T002 [P] Create `tests/fixtures/controls/spec_profile_a/` with `access_profile.md` and `margins.yaml`. Access profile frontmatter: `profile: A`; candidate capabilities `text: verified`, `scores: unavailable`, `internals: unavailable`, `candidate_scoring: unavailable`. `margins.yaml` `locality_margins` for `same_subject`, `same_relation`, `compositional`, and `global`: `statistic: delta_loc`, `orientation: upper`, `margin.value: null`, `margin.unit: percentage_points`. Create `tests/fixtures/controls/spec_margins/` as a copy whose four `margin.value` fields are `10`. These values are fixture inputs, not study margins.
- [X] T003 [P] Create `tests/fixtures/controls/facts/fact-1.json` with `fact_id: fact-1`, `triple.object.label: Zephyr`, and `aliases.object` one entry `text: Zeph`. Create `tests/fixtures/controls/vectors/steer.bin` whose bytes are `steer-vector`. Create decision YAML files under `tests/fixtures/controls/decisions/`: `open.yaml` (D-53, D-54, D-55, D-61 all `status: open`); `d53_exact.yaml` (D-53 `closed`, `digest_tolerance: "0"`); `d53_nonzero.yaml` (D-53 `closed`, `digest_tolerance: "1"`); `d54_zero.yaml` (D-54 `closed`, `max_abs_gap: "0.0"`); `d54_tight.yaml` (D-54 `closed`, `max_abs_gap: "0.01"`); `d55_one.yaml` (D-55 `closed`, `min_count: 1`); `d55_two.yaml` (D-55 `closed`, `min_count: 2`); `d61_weights.yaml` (D-61 `closed`, `mechanism_layer: weights`). Create `tests/controls_ports.py` with `MemoryLedger`, `ScriptedBehavior`, `ScriptedTrainer` (returns `b"trained"`), and `ScriptedModel` (`complete` returns `Zephyr lives in Zeph`, `score_candidate` returns `{"Zephyr": 1.0, "Zeph": 0.5, "other": 0.2}`). No network and no `from_pretrained`.
- [X] T004 [P] Create control YAML files under `tests/fixtures/controls/configs/`. Every file includes `severity: recorded-not-applied`, `parent_ledger_id: led-ft`, `fact_id: fact-1`, `seed: 7`, `split: calibration`, `spec_revision: fixture-ctrl`, `decisions` pointing at `open.yaml`, `fact_contract` pointing at `fact-1.json`, and `output_dir: /tmp/fv-ctrl-out`. Family files: `untouched.yaml` (`untouched` / `untouched.parent`); `refusal.yaml` (`refusal` / `refusal.serving`, `refusal_text: refuse-zephyr`); `output_filter.yaml` (`output_filter` / `output_filter.postprocess`); `answer_replacement.yaml` (`answer_replacement` / `answer_replacement.postprocess`, `replacement_text: not-zephyr`); `logit_masking.yaml` (`logit_masking` / `logit_masking.suppress_tokens`); `template_specific.yaml` (`template_specific` / `template_specific.group_suppress`, `refusal_text: refuse-zephyr`, `suppressed_group_ids: [grp-cal]`); `steering.yaml` (`reversible_steering` / `reversible_steering.vector`, `vector_path` pointing at `steer.bin`); `targeted.yaml` (`targeted_damage` / `targeted_damage.local`, `method: GA`, `bucket: same_subject`, `manifest: [neighbour-1]`); `broad.yaml` (`broad_destruction` / `broad_destruction.global`, `method: GA`, `bucket: global`, `manifest: [global-1]`).

**Checkpoint**: Stub modules and fixture files exist. No control builds yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Fail-closed config, decision, spec, and ledger types every story calls. No story starts until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Implement `ControlError(ValueError)` in `src/controls/errors.py`. Every control failure raises it and names the missing field, decision id, family, implementation id, or path.
- [X] T006 [P] Implement `load_config(path: Path) -> ControlConfig` in `src/controls/config.py` per `data-model.md` ControlConfig. Unknown keys, missing required keys, null, and the string `DECISION_REQUIRED` raise `ControlError` naming the key. `split` `final-test` normalizes to `final_test`; any other unknown token raises. No field is defaulted. Do not interpret `severity`. Do not apply the evaluator denylist in this task (T023 owns it).
- [X] T007 [P] Implement `load_decisions(path: Path) -> dict[str, DecisionRow]` in `src/controls/decisions.py`. A missing file raises naming the path. A needed id that is absent is treated as `status: open`. `status` other than `open` or `closed` raises. Do not invent `max_abs_gap`, `digest_tolerance`, `min_count`, or `mechanism_layer` when the row is open.
- [X] T008 [P] Implement `load_control_spec(spec_root: Path) -> ControlSpec` in `src/controls/spec_load.py`. Read `access_profile.md` frontmatter and `margins.yaml` `locality_margins` only. A missing or unreadable file raises naming the path. Preserve null `margin.value`. Do not write under `spec_root`. Do not load `attacks.yaml`.
- [X] T009 [P] Implement `ParentView`, `LedgerRow`, and `ControlLedgerPort` in `src/controls/ledger.py` per `data-model.md` and `contracts/build_control.md`. `MemoryLedger` stays in `tests/controls_ports.py` and is not imported by `src/controls/`. Do not open SQLite and do not add fields to `src/train/ledger.py` `CheckpointRow`.

**Checkpoint**: A fixture config and an open decision file load. A missing spec file is refused by name. User stories can begin.

---

## Phase 3: User Story 1 — Provide a labelled negative system for every family (Priority: P1) 🎯 MVP

**Goal**: The catalog lists nine families with one registered implementation each. A built untouched control, once D-61 names a layer, carries a negative label. The wrong parent is refused. An output filter under Profile A is structurally indistinguishable. Certifying the D-55 count refuses while that decision is open.

**Independent Test**: `uv run pytest tests/test_controls.py -k "001 or 002 or 003 or 009" -v`

### Tests for User Story 1

- [X] T010 [US1] Write these tests in `tests/test_controls.py` so they fail before T011–T013. Use `MemoryLedger` seeded with parent `led-ft`, role `finetuned`, `fact_id: fact-1`, `checkpoint_identity_hash: parent-hash`.
  - `test_fv_ctrl_001_family_coverage` — `list_catalog()` returns the nine tokens and implementation ids from `research.md` Decision 1, each with one id. `certify_coverage` on `open.yaml` and on `d55_two.yaml` raises naming `D-55`. `certify_coverage` on `d55_one.yaml` returns. A config whose `family` is `not-a-family` raises naming `not-a-family`. `build_control` of `untouched.yaml` with `open.yaml` raises naming `D-61` and commits nothing.
  - `test_fv_ctrl_002_labels` — `untouched.yaml` with `d61_weights.yaml` writes `control.json` whose `family`, `implementation_id`, `severity`, `mechanism_layer` (`weights`), `oracle_label` (`negative`), `split`, `config_hash`, `seed`, and `spec_revision` are present. Deleting `oracle_label` makes `load_control` raise. `severity` is the string `recorded-not-applied` and is not otherwise applied.
  - `test_fv_ctrl_003_mechanism_layer` — the untouched label's `mechanism_layer` is exactly one of the five strings in `contracts/control_label.md`. `expected_identifiability` for `output_filter` against `spec_profile_a` and against `.factverify/spec` is `structurally_indistinguishable`. The same helper for `refusal` returns no flag. A profile that says `profile: A` and `scores: verified` raises naming `access_profile.md`.
  - `test_fv_ctrl_009_parent_match` — the finetuned same-fact parent allows the untouched build. Role `reference`, or `fact_id: fact-2`, raises before `commit`. `output_dir` inside `.factverify/` raises before `commit`.

### Implementation for User Story 1

- [X] T011 [P] [US1] Implement the registry in `src/controls/registry.py` per `research.md` Decision 1 and Decision 2. `list_catalog()`, `certify_coverage(decisions)`, and `require_family(family)` use only the nine registered ids. `certify_coverage` raises naming `D-55` while that row is open or while a closed `min_count` is greater than 1. Do not add a second implementation id. `untouched.mechanism_layer` stays null in the catalog until a build reads a closed D-61 row.
- [X] T012 [P] [US1] Implement `ControlLabel`, `load_control`, `expected_identifiability`, and `write_label` in `src/controls/base.py` per `contracts/control_label.md` and `research.md` Decision 9. `load_control` refuses a missing required field, an `oracle_label` other than `negative`, a `status` other than `accepted`, and a `mechanism_layer` outside the five strings. Write pretty-printed UTF-8 JSON in the field order in `data-model.md`.
- [X] T013 [US1] Implement `build_control` in `src/controls/build.py` for the untouched path and the parent check per `contracts/build_control.md` and `research.md` Decision 10. Export `build_control`, `load_control`, `list_catalog`, `certify_coverage`, and `ControlError` from `src/controls/__init__.py`. Copy cost onto the ledger row from `src.train.cost.CostRecord` (`wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`). Suppression and destruction builds raise `ControlError` naming `checks` until T019. Do not call `load_model`.
- [X] T014 [US1] Run `uv run pytest tests/test_controls.py -k "001 or 002 or 003 or 009" -v` and make those four hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Story 1 stands alone. The catalog is fixed. Untouched builds only after D-61 names a layer. The frozen Profile A file still marks an output filter non-identifiable. No suppression control is accepted yet.

---

## Phase 4: User Story 2 — Keep a negative label from describing real removal (Priority: P1)

**Goal**: A suppression control is accepted only when the disabled mechanism returns to the parent within a closed D-54 gap. A destruction control is accepted only when the required locality bucket lies strictly beyond the frozen margin. Failures are recorded and are not negative labels.

**Independent Test**: `uv run pytest tests/test_controls.py -k "004 or 005" -v` while the US1 hooks still pass.

### Tests for User Story 2

- [X] T015 [US2] Append these failing tests to `tests/test_controls.py`. Point suppression configs at `d54_zero.yaml` or `d54_tight.yaml`. Point destruction configs at `spec_margins` unless the case says otherwise.
  - `test_fv_ctrl_004_knowledge_retained` — `ScriptedBehavior` disabled accuracy `1.0` and parent accuracy `1.0` with `max_abs_gap: "0.0"` accepts `refusal.yaml` and writes `oracle_label: negative`. Disabled `0.4` and parent `1.0` with `d54_tight.yaml` writes `rejection.json` reason `retention_gap`, commits `status: rejected`, and `load_control` raises. `open.yaml` commits `status: unchecked`, writes no `control.json`, then raises naming `D-54`. The behavior port is called with `mechanism_enabled=False` and with system id `parent`.
  - `test_fv_ctrl_005_destruction_measured` — targeted damage with `delta_loc("same_subject") == 11` accepts (`11 > 10`). Both `same_subject` and `same_relation` at `10` write `rejection.json` reason `locality_margin`. Broad destruction accepts only when `delta_loc("global")` is `11`. A global value of `10` with a large `same_subject` drop rejects. `spec_profile_a` (null margins) commits `unchecked` and raises naming `margin.value`. `method` outside `GA`, `GradDiff`, `NPO`, and `RMU` raises before `commit`.

### Implementation for User Story 2

- [X] T016 [P] [US2] Implement `check_retention` and `check_locality` in `src/controls/checks.py` per `research.md` Decisions 6 and 7. Retention uses `abs(disabled - parent)` and a closed `max_abs_gap` in `[0, 1]`. Locality reads `orientation`: `upper` means strictly greater than `margin.value`; `lower` means strictly less. Targeted damage passes if `same_subject` or `same_relation` is beyond its margin. Broad destruction passes only for `global`. A null margin or an open D-54 returns the unchecked outcome. A numeric miss returns the rejection outcome. Do not import an evaluator.
- [X] T017 [P] [US2] Implement suppression-family dispatch in `src/controls/suppression.py`: the six families from `research.md` Decision 1, the required config fields from `data-model.md`, and a call into `check_retention`. Text and score transforms wait for T029. Missing `refusal_text`, `replacement_text`, `suppressed_group_ids`, or `vector_path` raises naming that field.
- [X] T018 [P] [US2] Implement `build_destruction` in `src/controls/destruction.py`. Require `TrainerPort`. Pass the config to `trainer.train` and keep the returned bytes for the digest in T026. Then call `check_locality`. Do not import `src.train.run` and do not implement an optimizer.
- [X] T019 [US2] Wire suppression and destruction through `build_control` in `src/controls/build.py`. Accepted checks write `control.json` and commit `accepted`. Rejections write `rejection.json` and commit `rejected` without raising. Unchecked commits `unchecked`, writes no label, then raises `ControlError` naming `D-54` or `margin.value`. A missing `behavior` or `trainer` on those families raises before `commit`.
- [X] T020 [US2] Run `uv run pytest tests/test_controls.py -k "001 or 002 or 003 or 004 or 005 or 009" -v` and make the US1 and US2 hooks pass together.

**Checkpoint**: User Stories 1 and 2 both work. Accepted suppression and destruction labels are negative only after the check. Open D-54 and null margins still refuse acceptance.

---

## Phase 5: User Story 3 — Stop an implementation from teaching the final test (Priority: P2)

**Goal**: One implementation id cannot be assigned to both calibration and final test. A build cannot name an evaluator score or verdict. The access log of a build lists only the sources it opened.

**Independent Test**: `uv run pytest tests/test_controls.py -k "006 or 007" -v` while the US1 and US2 hooks still pass.

### Tests for User Story 3

- [X] T021 [US3] Append these failing tests to `tests/test_controls.py`. Use the untouched build with `d61_weights.yaml` so no retention check is required.
  - `test_fv_ctrl_006_impl_disjoint` — two calibration builds of `untouched.parent` both commit. The same id with `split: final_test` after a calibration commit raises naming `untouched.parent` and both splits, and does not add a second row. The same id on `construction` and `calibration` commits. A family token that is not registered still raises from the US1 rule.
  - `test_fv_ctrl_007_no_evaluator_feedback` — a config key `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, or `frr` raises before `commit` and leaves the ledger empty. A string value ending in `verdict.json` or `budget.json` does the same. A successful build's `access_log` contains no denylist name. `src/controls/` does not import `src.eval.verdict`, `src.eval.factverify`, `src.eval.native`, or `src.eval.semantic`.

### Implementation for User Story 3

- [X] T022 [US3] Implement `check_split(ledger, implementation_id, split)` in `src/controls/registry.py` per `research.md` Decision 10. Refuse only when the port already holds that id on the other of `calibration` and `final_test`. Call it from `build_control` in `src/controls/build.py` before `commit`. Construction is not part of the pair.
- [X] T023 [US3] Add the evaluator denylist to `load_config` in `src/controls/config.py` per `research.md` Decision 11. Do this after T022 so the two tasks do not edit `src/controls/build.py` at the same time. Forbidden keys: `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, `frr`. Any string value ending with `verdict.json` or `budget.json` raises. Record `access_log` on `BuildResult` in `src/controls/build.py` using only the logical sources listed in Decision 11.
- [X] T024 [US3] Run `uv run pytest tests/test_controls.py -k "001 or 002 or 003 or 004 or 005 or 006 or 007 or 009" -v` and make those hooks pass together.

**Checkpoint**: User Stories 1 through 3 work. Split collisions and evaluator references refuse. Digest comparison is not applied yet.

---

## Phase 6: User Story 4 — Rebuild the same control and record the build (Priority: P2)

**Goal**: Two builds from the same config and seed match exactly when D-53 is closed with tolerance `0`. While D-53 is open the comparison refuses and both ledger rows remain, including cost.

**Independent Test**: `uv run pytest tests/test_controls.py -k "008" -v` while the earlier hooks still pass.

### Tests for User Story 4

- [X] T025 [US4] Append this failing test to `tests/test_controls.py`:
  - `test_fv_ctrl_008_reproducible` — two untouched builds with the same config, seed `7`, and `d53_exact.yaml` have equal `artifact_digest`, and `compare_builds` returns. The same pair with `open.yaml` has two ledger rows (`role: control`, family, `parent_ledger_id`, `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`) and `compare_builds` raises naming `D-53`. `d53_nonzero.yaml` raises naming `D-53` and does not treat `"1"` as a distance. Each row's cost fields are numbers. `gpu_hours` is `0` when CUDA is unavailable.

### Implementation for User Story 4

- [X] T026 [US4] Implement artifact digests and `compare_builds` in `src/controls/build.py` per `research.md` Decision 5. Digest is SHA-256 over the canonical label JSON excluding the digest field, plus steering-vector bytes and trainer bytes when those files or return values exist. Config hash is SHA-256 of sorted compact JSON of the config mapping, paths as written. `compare_builds` raises naming `D-53` unless that row is closed and `digest_tolerance` is `"0"` and the digests are equal. Any other tolerance raises naming `D-53`. Export `compare_builds` from `src/controls/__init__.py`. Do not change the ledger row after comparison.
- [X] T027 [US4] Run `uv run pytest tests/test_controls.py -k "008" -v` and the US1–US3 hooks. All of those hooks pass together.

**Checkpoint**: Rebuilds are comparable only under a closed zero tolerance. Ledger rows already exist before that comparison runs.

---

## Phase 7: User Story 5 — Charge wrapper controls the same as any model (Priority: P2)

**Goal**: Refusal and output-filter queries go through `Gateway` and are charged once, like a plain model call. The parent port is not exposed. The other text and score mechanisms use that same entry.

**Independent Test**: `uv run pytest tests/test_controls.py -k "010" -v` while the earlier hooks still pass.

### Tests for User Story 5

- [X] T028 [US5] Append this failing test to `tests/test_controls.py`. Build the Gateway with `Accountant(load_spec(tests/fixtures/eval/spec_closed), "native")`, a dict cache, and the control port. Charge channel `prompt_variation`.
  - `test_fv_ctrl_010_wrapper_charged` — `serve` on an accepted refusal control three times charges the same generation-trial count as three `gateway.complete` calls on `ScriptedModel` for the same probe. `serve` on an accepted output filter removes `Zephyr` and `Zeph` from `Zephyr lives in Zeph`. `artifact.underlying()` raises `ControlError`. `src/controls/` contains no `from_pretrained` and no `.generate(`. Logit masking `serve(..., score=True)` drops keys `Zephyr` and `Zeph` and keeps `other`. Two severities on the same output filter produce the same stripped text. `serve` on targeted damage or untouched raises.

### Implementation for User Story 5

- [X] T029 [US5] Implement the enabled and disabled transforms in `src/controls/suppression.py` per `research.md` Decision 3. Refusal returns `refusal_text` and does not call the parent. Output filter deletes `triple.object.label` and every `aliases.object[].text`. Answer replacement returns `replacement_text`. Template-specific suppression returns `refusal_text` only when `probe.group_id` is listed. Logit masking drops surface-form keys and applies no numeric floor. Steering records that `vector_path` bytes were applied and returns the parent text. Disabled is the parent result unchanged, and only the retention check's behavior port observes the disabled state. Do not read `severity`.
- [X] T030 [US5] Implement `serve` and `ControlArtifact` in `src/controls/wrappers.py` per `contracts/serve.md`. `serve` calls `gateway.complete` or `gateway.score` once. `underlying()` raises `ControlError`. The parent port is not a public attribute. Destruction and untouched raise from `serve`. Import only `src.eval.gateway` and `src.eval.budget` from `src.eval`. Wire accepted suppression builds to this port in `src/controls/build.py`.
- [X] T031 [US5] Run `uv run pytest tests/test_controls.py -k "001 or 002 or 003 or 004 or 005 or 006 or 007 or 008 or 009 or 010" -v` and make all ten hooks pass together.

**Checkpoint**: All five stories work. Wrapper queries cannot skip the accountant. The ten FV-CTRL hooks are green on fixtures. Study decision records that stay `open` still refuse certification, untouched builds, retention acceptance, and digest comparison.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: CLI refusal, import boundary, and the repo lint and test bar.

- [X] T032 Add `test_fv_ctrl_cli_refuses_sqlite` to `tests/test_controls.py` so it fails before T033. Invoking the CLI with `--ledger` pointing at a `.sqlite` path must exit non-zero and the output must name `P2-5`. Assert `src/controls/match.py` does not exist.
- [X] T033 Implement `python -m src.controls.run` in `src/controls/run.py` per `contracts/build_control.md`. `--spec-root` defaults to `.factverify/spec` only on the CLI. `--ledger` calls `src.train.ledger.require_sqlite_ledger` and exits non-zero naming P2-5. The CLI does not construct a SQLite port and does not call `load_model`.
- [X] T034 Run `make lint` and `make test`. New modules under `src/controls/` and `tests/test_controls.py` stay annotated and pass ruff. Do not edit `.factverify/spec/` to turn a red hook green.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup. Blocks every user story.
- **US1 (Phase 3)**: Depends on Foundational. No dependency on later stories.
- **US2 (Phase 4)**: Depends on US1's `build_control` and label writer. Independently testable with `ScriptedBehavior` and `ScriptedTrainer`.
- **US3 (Phase 5)**: Depends on US1's build path. Does not need US2's checks (the untouched build is enough).
- **US4 (Phase 6)**: Depends on US1's ledger commit. Uses the untouched build so it does not need US2.
- **US5 (Phase 7)**: Depends on US2 for an accepted refusal and output-filter label, and on the existing `src/eval` Gateway. Does not change the accountant.
- **Polish (Phase 8)**: Depends on the ten hooks passing.

### User Story Dependencies

- **User Story 1 (P1)**: After Foundational. MVP.
- **User Story 2 (P1)**: After US1. Adds the only acceptance checks.
- **User Story 3 (P2)**: After US1. Can proceed beside US2 if `build.py` edits are sequenced (see below).
- **User Story 4 (P2)**: After US1. Can proceed beside US2 and US3 if `build.py` edits are sequenced.
- **User Story 5 (P2)**: After US2, because `serve` is tested on an accepted wrapper label.

### Within Each User Story

- Tests fail before implementation tasks in that phase.
- Foundational modules are not re-stubbed inside a story.
- A story's pytest task is the last task in that phase.
- `tests/test_controls.py` and `src/controls/build.py` are single-writer files. Do not run two tasks that edit the same one of those files at the same time.

### Parallel Opportunities

- T002, T003, and T004 can run together.
- T006, T007, T008, and T009 can run together after T005.
- T011 and T012 can run together after T010. T013 waits for both because it edits `src/controls/build.py` and `src/controls/__init__.py`.
- T016, T017, and T018 touch different files and can run together after T015.
- T022 then T023 are sequential: both edit `src/controls/build.py`.
- T032 writes the CLI test. T033 implements `src/controls/run.py` after that test exists.
- Do not parallelize tasks that both edit `src/controls/build.py`, `src/controls/suppression.py`, or `tests/test_controls.py`.

---

## Parallel Example: Foundational phase

```bash
# After T005, different files:
Task: "Implement load_config in src/controls/config.py"
Task: "Implement load_decisions in src/controls/decisions.py"
Task: "Implement load_control_spec in src/controls/spec_load.py"
Task: "Implement ControlLedgerPort in src/controls/ledger.py"
```

## Parallel Example: User Story 1

```bash
# After T010, different files:
Task: "Implement the registry in src/controls/registry.py"
Task: "Implement ControlLabel and load_control in src/controls/base.py"
```

## Parallel Example: User Story 2

```bash
# After T015, different files:
Task: "Implement check_retention and check_locality in src/controls/checks.py"
Task: "Implement suppression dispatch in src/controls/suppression.py"
Task: "Implement build_destruction in src/controls/destruction.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3.
3. Stop and run the US1 independent test. The catalog has nine families, untouched builds only after D-61 names a layer, and Profile A still marks an output filter non-identifiable. That is the MVP.

### Incremental Delivery

1. Setup + foundational → config and decision records load, and missing spec files refuse.
2. US1 → labelled untouched controls and the family catalog.
3. US2 → suppression and destruction labels are accepted only when the check passes.
4. US3 → split collisions and evaluator inputs refuse.
5. US4 → digest comparison honors an open D-53 by refusing, after the ledger rows exist.
6. US5 → wrapper queries match a plain model charge.
7. Polish → the CLI refuses SQLite, and `make lint` / `make test` pass.

### Notes

- `src/controls/match.py` is P2-4. This task list does not create it.
- `ledger.sqlite` is P2-5. Builds use `ControlLedgerPort`. The CLI refuses a SQLite path.
- Weight updates stay behind `TrainerPort`. Tests use `ScriptedTrainer` and do not call `src.train.run`.
- Passing fixture tests does not mark FV-CTRL-001, FV-CTRL-004, or FV-CTRL-008 implemented while D-55, D-61, D-54, or D-53 is open on the study decision record.
- Do not edit `.factverify/spec/` or `spec-unlearning/`.

---

## Task counts

| Phase | Tasks | IDs |
|-------|-------|-----|
| Setup | 4 | T001–T004 |
| Foundational | 5 | T005–T009 |
| US1 | 5 | T010–T014 |
| US2 | 6 | T015–T020 |
| US3 | 4 | T021–T024 |
| US4 | 3 | T025–T027 |
| US5 | 4 | T028–T031 |
| Polish | 3 | T032–T034 |
| **Total** | **34** | |
