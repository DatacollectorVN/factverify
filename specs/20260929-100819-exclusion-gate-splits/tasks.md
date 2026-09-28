# Tasks: P1 Exclusion Gate and Entity-Disjoint Splits

**Input**: Design documents from `specs/20260929-100819-exclusion-gate-splits/`
**Feature**: `20260929-100819-exclusion-gate-splits`
**Branch**: `main` (spec slug only; do not create a git branch)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Organization**: Tasks grouped by user story — US1 (record D-65), US2 (exclusion gate), US3 (record D-68), US4 (entity-disjoint splits). Tests are included because `contracts/exclusion_gate.md` and `contracts/splits.md` name the pytest hooks for FV-DATA-013–018 and FV-DATA-035–039.

**Design notes** (read from disk; Obsidian MCP was unavailable): FV-DATA — P1-2 and FV-DATA — P1-6 are `status: draft`. FV-DATA — P1-SIGNOFF is `status: in-progress`. The execution plan is `status: planned`. Do not edit `.factverify/spec/`. Do not `git commit`; suggest a message the user can run.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story label (US1–US4) — required on story phases only
- Suggested commit messages use task IDs (`P1-2: exclusion gate FV-DATA-013`)

---

## Phase 1: Setup

**Purpose**: Targets and empty test modules. No gate or split logic.

- [X] T001 Add `exclusion-gate` and `make-splits` targets to `Makefile`, using the commands in `specs/20260929-100819-exclusion-gate-splits/quickstart.md` (steps 3 and 4). Leave `--cache-decisions`, `--cache-dir`, `--ledger-decisions`, and `--git-commit` as variables the caller must pass. Do not hard-code a cache path inside `.factverify/`.
- [X] T002 [P] Create `tests/test_exclusion_gate.py` with a module docstring naming FV-DATA-013–018. Import `pytest` and `pathlib.Path` only.
- [X] T003 [P] Create `tests/test_splits.py` with a module docstring naming FV-DATA-035–039. Import `pytest` and `pathlib.Path` only.
- [X] T004 [P] Add `tests/fixtures/exclusion/closure_d63.yaml` with class E templates, `extra_premises: []`, for relations `occupation`, `birthplace`, `nationality`, and `genre`. Each relation needs one `primary_family: direct` template with `answer_role: object` and text containing `{subject}`, plus one `primary_family: verification` template with `answer_role: truth_value`, `oracle_label: true`, and text containing `{subject}` and `{object}`. This fixture is the only closure file the unit tests load. Do not edit `.factverify/spec/closure_templates.yaml`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared error type. No story work until this exists.

**⚠️ CRITICAL**: No US1–US4 implementation starts until this phase is complete.

- [X] T005 Add `DataError(Exception)` in `src/data/errors.py` with `message: str` stored on the instance and returned by `str(self)`. Full annotations. Export it from `src/data/__init__.py` if that file already re-exports public names; otherwise leave `__init__.py` unchanged.

**Checkpoint**: `uv run ruff check src/data/errors.py` passes. `python -c "from src.data.errors import DataError"` succeeds.

---

## Phase 3: User Story 1 — Record the guessing baseline (Priority: P1) 🎯 MVP

**Goal**: A closed D-65 row is readable, and an open or blank row refuses before any verdict.

**Independent Test**: With a fixture YAML whose D-65 `status` is `open`, `load_d65` raises `DataError` naming `D-65`. With the closed study row, it returns threshold `0.5`, seeds `[0]`, and `cell_score` `alias_contains`.

### Tests for User Story 1 (write first; they must fail before T007)

- [X] T006 [US1] Add these tests to `tests/test_exclusion_gate.py`, building YAML fixtures under `tmp_path` (do not read `data/controlled/block0_decisions.yaml` inside the tests):
  - `test_d65_open_refuses` — `status: open` raises `DataError` and the message contains `D-65`.
  - `test_d65_blank_threshold_refuses` — `status: closed` with `threshold` omitted raises `DataError` and the message contains `threshold`.
  - `test_d65_closed_values` — the closed field set from `contracts/decisions.md` returns `baseline == "random_choice"`, `threshold == 0.5`, `comparison == "any_direction"`, `cell_score == "alias_contains"`, `decoding_seeds == (0,)`, `decoding["do_sample"] is False`, `decoding["max_new_tokens"] == 16`, and `contamination_trigger == 0.10`.

### Implementation for User Story 1

- [X] T007 [US1] Implement `load_d65(path: Path)` in `src/data/decisions.py` per `contracts/decisions.md`. Return a frozen dataclass. Raise `DataError` when the file is missing, D-65 is absent, `status` is not `open` or `closed`, `status` is `open`, `comparison` is not `any_direction`, `cell_score` is not `alias_contains`, `decoding_seeds` is empty or not a list of ints, `do_sample` is not a bool, `max_new_tokens` is not a positive int, or `contamination_trigger` is not a finite float. `contamination_decision` may be null. A non-null decision must be `regenerate`, `switch_model`, or `proceed` and requires a non-empty `note`. Do not import the ledger or cache decision loaders; their YAML shape is a list under `decisions` only when we choose that shape — use the mapping in `contracts/decisions.md` (`decisions:` list of maps with `decision_id`).
- [X] T008 [US1] Write the D-65 block of `data/controlled/block0_decisions.yaml` exactly as the study values in `contracts/decisions.md`, with `contamination_decision: null` and `note: ""`. Do not add D-68 in this task.
- [X] T009 [US1] Run `uv run pytest tests/test_exclusion_gate.py -k d65` and fix `src/data/decisions.py` until the three tests pass.
- [X] T010 [US1] Run `uv run ruff check src/data/decisions.py tests/test_exclusion_gate.py` and `uv run ruff format --check` on those files.

**Checkpoint**: D-65 loads from the study file. No gate verdicts exist yet.

---

## Phase 4: User Story 2 — Exclude facts the base model already answers (Priority: P1)

**Goal**: Probe applicable class E templates, write `pass` / `excluded_known` / `incomplete`, keep excluded facts, and stop bundle construction when the contamination alarm fires without an owner note.

**Independent Test**: On a fixture of two facts, a fake completer, and the D-63 closure fixture, the gate writes one verdict per fact. Accuracy above 0.5 in one direction is `excluded_known`. A missing cell is `incomplete`. `build_bundles.py --gate-report` refuses when the excluded fraction exceeds the trigger and `contamination_decision` is null.

### Tests for User Story 2 (write first; they must fail before T012)

- [X] T011 [US2] Add the following tests to `tests/test_exclusion_gate.py`. Use `tests/fixtures/exclusion/closure_d63.yaml` as `--spec-root` content by copying that file into a temp spec root the test builds (the loader only needs `closure_templates.yaml` plus, for the hash test, a tiny `models.yaml`). Pass a fake completer. Do not call `from_pretrained` or download Pythia.
  - `test_fv_data_013_model_binding` — a matching identity hash is stored on every row. A completer path that reports a different hash raises and leaves the output path absent.
  - `test_fv_data_014_full_closure` — for one occupation fact, the JSONL cells cover every class E template in the fixture and every declared seed. Delete one template from the expected set in the assertion by omitting its completion and expect verdict `incomplete`.
  - `test_fv_data_015_baseline` — completions that contain the object alias on half the direct cells (accuracy 0.5) yield `pass` with `threshold` 0.5 recorded. A completion that contains the alias on every direct cell and fails verification yields `excluded_known` because one direction is above 0.5.
  - `test_fv_data_016_excluded_recorded` — an `excluded_known` fact remains in the JSONL and `reports/exclusion_gate.md` contains its `fact_id`, relation, direction, and accuracy.
  - `test_fv_data_017_contamination_alarm` — two facts, one `excluded_known`, trigger 0.10: `scripts/build_bundles.py` invoked in-process with `--gate-report` and a decisions file whose `contamination_decision` is null raises and the message names the report path. The same call with `contamination_decision: proceed` and a non-empty `note` does not raise for the alarm. A fact whose verdict is not `pass` still raises, naming that `fact_id`.
  - `test_fv_data_018_gate_before_train` — `src.train.run._precheck` (or `run_job` if `_precheck` cannot see the report) raises when the job's raw mapping contains `gate_report` and the fact is `excluded_known`, `incomplete`, or missing. A job that omits `gate_report` does not raise for lack of a verdict.
  - `test_gate_rerun_and_no_split` — two runs with the same fake completions write the same verdicts. No result object contains a `split` key.
  - Class I templates in the fixture, if you add one, appear under `inference_probes` and do not change accuracy.

### Implementation for User Story 2

- [X] T012 [US2] Add `generate_completion(model: Any, tokenizer: Any, prompt: str, *, max_new_tokens: int, do_sample: bool) -> str` to `src/models/generate.py`. Call `model.generate` and decode new tokens only. Do not call `from_pretrained`. Do not sample when `do_sample` is false.
- [X] T013 [US2] Implement the grid and verdicts in `src/data/exclusion.py` per `data-model.md` and `contracts/exclusion_gate.md`: select class E templates with empty `extra_premises` whose `relation_applicability` contains `triple.relation.label`; direction is `primary_family`; score with `alias_contains` (casefold, collapse whitespace, English alias containment; truth-value uses `oracle_label`); missing `oracle_label` on a verification template is `incomplete`; zero applicable templates is `incomplete` / `no_applicable_templates`; any direction accuracy `> threshold` is `excluded_known`; otherwise `pass`. `excluded_fraction = excluded_known / n_facts`. `require_pass(fact_id, report_path)` raises `DataError` unless that fact's verdict is `pass`. `assert_contamination_cleared(report_path, decision)` raises when `alarm` would be true and `contamination_decision` is null, and raises when any fact verdict is not `pass`.
- [X] T014 [US2] Implement the click command in `scripts/exclusion_gate.py` with the flags in `contracts/exclusion_gate.md`. Load role `blocks_0_2` via `src.models.load_model` only when the caller does not inject a completer (tests call `src.data.exclusion.run_gate` directly with a fake completer and a precomputed hash, so the CLI is the only `load_model` caller). Compare the loaded hash to `compute_identity_hash` of that role with no adapter; on mismatch raise and do not create `--out`. Cache completions through `src.cache.store.get_or_compute`. An open D-60 raises before verdicts. Write JSONL and the markdown report. Record per-fact `wall_clock_seconds`, `gpu_hours`, and `peak_memory_bytes` using `src.train.cost.CostRecord` around each fact. Do not call `Accountant.query`. Do not rewrite `facts.jsonl`.
- [X] T015 [P] [US2] In `scripts/build_bundles.py`, add `--gate-report` and `--decisions`. When `--gate-report` is set, call `assert_contamination_cleared` before building. When the flag is omitted, leave today's draft-contract behavior unchanged so existing bundle tests stay green.
- [X] T016 [P] [US2] In `src/train/run.py` `_precheck`, when `config.raw` contains `gate_report`, call `require_pass(config.target_fact_id, Path(config.raw["gate_report"]))` before reference pairing and before `_execute`. Jobs that omit the key are unchanged.
- [X] T017 [US2] Run `uv run pytest tests/test_exclusion_gate.py tests/test_bundles.py tests/test_harness.py`. All must pass. Fix only the new gate behavior; do not weaken existing assertions.
- [X] T018 [US2] Run `uv run ruff check` and `uv run ruff format --check` on `src/data/exclusion.py`, `src/models/generate.py`, `scripts/exclusion_gate.py`, `scripts/build_bundles.py`, and `src/train/run.py`.

**Checkpoint**: Fixture gate tests pass. A real run against `.factverify/spec/closure_templates.yaml` may mark TOFU facts `incomplete` / `no_applicable_templates`. That result is correct. Do not add templates to the frozen spec.

---

## Phase 5: User Story 3 — Record the split counts (Priority: P2)

**Goal**: A closed D-68 row supplies Block 0 counts, and the loader refuses an open row, a blank count, or `assign_final_test: true`.

**Independent Test**: An open D-68 raises `DataError` naming `D-68`. The study file returns construction 8, calibration 8, `assign_final_test is False`, and the four relation names. A fixture with counts 2 and 2 loads those counts rather than a hard-coded 8.

### Tests for User Story 3 (write first; they must fail before T020)

- [X] T019 [US3] Add these tests to `tests/test_splits.py`, using `tmp_path` YAML:
  - `test_d68_open_refuses` — `status: open` raises `DataError` containing `D-68`.
  - `test_d68_assign_final_test_true_refuses` — `assign_final_test: true` raises `DataError` containing `assign_final_test`.
  - `test_d68_blank_counts_refuses` — missing `counts.calibration` raises `DataError` containing `calibration`.
  - `test_d68_reads_fixture_counts` — a closed row with construction 2, calibration 2, relations `[occupation, birthplace]`, and `assign_final_test: false` returns those values, not 8.

### Implementation for User Story 3

- [X] T020 [US3] Add `load_d68(path: Path)` to `src/data/decisions.py` per `contracts/decisions.md`. Raise `DataError` on a missing file, missing id, bad status, open status, non-positive counts, empty `relations`, or `assign_final_test: true`. Return the counts from the file. Do not default missing counts to 8.
- [X] T021 [US3] Append the D-68 study block to `data/controlled/block0_decisions.yaml`: `block: block0`, construction 8, calibration 8, `assign_final_test: false`, relations occupation, birthplace, nationality, genre. Leave the D-65 block from T008 unchanged.
- [X] T022 [US3] Run `uv run pytest tests/test_splits.py -k d68` and `uv run pytest tests/test_exclusion_gate.py -k d65`. Both selections pass.
- [X] T023 [US3] Run `uv run ruff check src/data/decisions.py tests/test_splits.py` and `uv run ruff format --check` on those files.

**Checkpoint**: Both decision rows load. No `splits.json` yet.

---

## Phase 6: User Story 4 — Assign authors to disjoint splits (Priority: P2)

**Goal**: Eligible authors are packed into the D-68 counts, the digest and seed land in the ledger, and final-test loads are refused unless the role is `final_test_pass`.

**Independent Test**: A fixture with closed counts 2 and 2 writes those sizes, lists leftover authors as `unassigned`, repeats the same digest on a second seed-matched run, and records that seed and digest on a `study_artifacts` row. A non-final-test role cannot load final-test facts.

### Tests for User Story 4 (write first; they must fail before T025)

- [X] T024 [US4] Add these tests to `tests/test_splits.py`. Build small fact lists, a gate report, and an audit JSONL in `tmp_path`. Use D-68 counts of 2 and 2 so the tests do not need 16 facts. Eligible means gate verdict `pass` and every audit row for that fact is `clean`, with at least one audit row.
  - `test_fv_data_035_entity_disjoint` — no author id appears under two labels. A hand-built file that assigns one author's facts to two labels fails validation.
  - `test_fv_data_036_sizes` — construction and calibration fact counts equal the closed D-68 counts. Too few eligible facts raises and the previous output file bytes are unchanged.
  - `test_fv_data_037_deterministic` — two outputs from the same facts and seed have the same digest. `add_study_artifact` then `open_ledger` reads that seed and digest back.
  - `test_fv_data_038_relation_balance` — each assigned split contains every relation on the D-68 row. A pool that cannot meet the rule raises, the message includes the counts, and no output file is created.
  - `test_fv_data_039_final_guard` — `load_split(..., "final_test", role="calibration")` raises and appends a JSON line with `reason` `role` to the access log. `role="final_test_pass"` loads a fixture file that does contain final-test facts. The Block 0 writer emits no `final_test` value. `final_test_pass` against a Block 0 file raises `empty_split` and logs that reason.
  - Authors are `triple.subject.id`. An object id that is also some fact's subject must share that subject's label or validation fails. Objects that are never subjects stay out of `entities`.
  - Facts that are not `pass`, or that lack an all-clean audit, are omitted. They are not `unassigned`. `unassigned` is only eligible authors beyond the counts.

### Implementation for User Story 4

- [X] T025 [US4] In `src/ledger/schema.py`, add `CREATE TABLE IF NOT EXISTS study_artifacts` and append-only update/delete triggers, keeping `SCHEMA_VERSION = "1"`. Columns match `data-model.md`: `artifact_id`, `created_at`, `kind`, `seed`, `digest`, `config_hash`, `spec_tag`, `git_commit`, `dirty`, `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`. Do not change checkpoint or evaluation-run columns.
- [X] T026 [US4] Add frozen dataclass `StudyArtifact` and `add_study_artifact(ledger, record) -> str` to `src/ledger/api.py`. Insert one row inside the same immediate transaction style as `add_checkpoint`. Refuse an empty `kind`, empty `digest`, empty `spec_tag`, or negative cost. Do not require D-56 tiers for this insert. Existing `add_checkpoint` behavior stays unchanged.
- [X] T027 [US4] Implement `assign_splits` and `load_split` in `src/data/splits.py` per `contracts/splits.md` and `research.md` ("Who counts as an author", "Assignment algorithm", "Eligibility", "Final-test guard"). Digest is SHA-256 of canonical JSON of `{entities, facts}` with sorted keys and no whitespace (`src.train.config.hash_mapping` if that already produces that digest; otherwise hash the same canonical JSON in this module). Shuffle author groups with `random.Random(seed)` over sorted author ids. On failure, do not replace an existing output file. `load_split` appends a JSON line to `access_log` before raising on a refused final-test read.
- [X] T028 [US4] Implement the click command in `scripts/make_splits.py` with the flags in `contracts/splits.md`. Call `load_d68` first and refuse while it raises. Read the gate report and the audit file; a missing audit raises and writes nothing. On success, write `splits.json` then `add_study_artifact` with kind `split_assignment`, the assignment seed, the file digest, the SHA-256 of the decisions file bytes, and a `CostRecord` for the process. `--dirty` is a flag. Do not label any author `final_test`.
- [X] T029 [US4] Run `uv run pytest tests/test_splits.py tests/test_ledger.py`. Existing ledger tests must still pass on schema version `1`.
- [X] T030 [US4] Run `uv run ruff check` and `uv run ruff format --check` on `src/data/splits.py`, `src/ledger/schema.py`, `src/ledger/api.py`, `scripts/make_splits.py`, and `tests/test_splits.py`.

**Checkpoint**: Fixture splits match the closed counts in the fixture, not a silent shrink. The study decisions file still says 8 and 8.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Full suite and a frozen-spec check.

- [X] T031 [P] Read `specs/20260929-100819-exclusion-gate-splits/quickstart.md` against the click flags in `scripts/exclusion_gate.py` and `scripts/make_splits.py`. Update the quickstart only if a flag name drifted.
- [ ] T032 Run `make lint` and `make test`. Both must pass. `make lint` covers `src/` and `tools/`; also `uv run ruff check scripts/exclusion_gate.py scripts/make_splits.py scripts/build_bundles.py`.
- [X] T033 Run `git diff -- .factverify/spec` and confirm it is empty. If it is not, revert those edits. D-63 closure templates are a later spec amendment, not this feature.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. Blocks every user story.
- **US1 (Phase 3)**: depends on Foundational. Blocks US2 and US3 because both call `src/data/decisions.py`.
- **US2 (Phase 4)** and **US3 (Phase 5)**: either may start after US1. They touch different functions. US3 edits `decisions.py`; US2 does not. Do not run them in the same worktree edit of `decisions.py`.
- **US4 (Phase 6)**: depends on US3 (`load_d68`). Gate-report fixtures are written inside the tests, so US4 does not need a real US2 run. The study command in the quickstart still needs both outputs.
- **Polish (Phase 7)**: depends on the stories you intend to keep. Full `make test` waits until US4 is in.

### User Story Dependencies

- **US1 (P1)**: after Foundational. No other story.
- **US2 (P1)**: after US1. Independently testable with fixture decisions and a fake completer.
- **US3 (P2)**: after US1. Independently testable with fixture YAML. Does not need the gate.
- **US4 (P2)**: after US3. Independently testable with fixture reports. Does not need Pythia.

### Within Each User Story

- Tests fail before the implementation task in that phase.
- One module lands before the click command that calls it.
- Story checkpoint is green before the next phase.

### Parallel Opportunities

- T002, T003, and T004 can run together with T001 (four different files).
- After US1, US2 and US3 can proceed in parallel in two worktrees.
- T015 and T016 can run together after T014 (bundle script vs train precheck).
- T031 can run while T032 is not yet started; T032 waits until the suite is expected to pass.

---

## Parallel Example: User Story 2

```bash
# After T014 (exclusion.py and the CLI exist), different files:
# T015 scripts/build_bundles.py --gate-report
# T016 src/train/run.py _precheck gate_report
```

---

## Implementation Strategy

### MVP First (User Story 1, then User Story 2)

1. Phase 1 and Phase 2.
2. Phase 3 — D-65 loads and refuses when open.
3. Phase 4 — fixture gate tests pass.
4. Stop. A real Pythia run is optional here and will mark current TOFU facts `incomplete` until closure templates for those relations exist under a spec amendment.

### Incremental Delivery

1. US1 — decision record for the baseline.
2. US2 — gate report and the bundle/train guards.
3. US3 — decision record for the counts.
4. US4 — `splits.json` and the ledger digest.
5. Polish — `make lint`, `make test`, frozen spec untouched.

### Parallel Team Strategy

1. Together: Setup, Foundational, US1.
2. Then one person on US2 and another on US3.
3. US4 after US3. The US2 person can review the gate report shape against `data-model.md` while US4 uses fixtures.

---

## Notes

- Tests in one file are a single task so two editors do not rewrite `tests/test_exclusion_gate.py` or `tests/test_splits.py` at once.
- Fixture D-68 counts of 2 and 2 prove the writer reads the file. The study YAML stays at 8 and 8.
- Do not charge `src.eval.budget.Accountant` from the gate.
- Do not put a split digest on a checkpoint row.
- Suggested commits, for the user to run: `P1-2: record D-65 guessing baseline`, `P1-2: exclusion gate FV-DATA-013-018`, `P1-6: record D-68 split counts`, `P1-6: entity-disjoint splits FV-DATA-035-039`.
