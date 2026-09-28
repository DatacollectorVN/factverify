# Tasks: FV-CTRL — P2-4 Behaviour-Matching Utility

**Feature**: `20260927-144624-behaviour-matching`  
**Input**: Design documents from `specs/20260927-144624-behaviour-matching/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included. `FV-CTRL — P2-4.md` (draft) requires seven named pytest hooks, `test_fv_ctrl_011_target_from_refs` through `test_fv_ctrl_017_reproducible`. Write each story's tests before that story's implementation, and confirm they fail first.

**Organization**: Tasks are grouped by user story. Do not close D-54, D-58, D-59, or D-53 in `.factverify/spec/`. Numbers and probe texts below belong only in `tests/fixtures/controls/match/`. Do not import `src.eval.gateway` or `src.eval.budget` from `src/controls/match.py`. Do not open SQLite. Do not call `build_control`.

**Design notes** (read from disk; Obsidian MCP was unavailable when the plan was written): Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-4; "Phase 3 — Block 0", Gate 1 criterion 1 (two reference seeds); "Phase 4 — Block 1" (at least three reference seeds). Proposal v3 (status: draft), "6.2" and "6.3". Fake-Unlearning Controls (status: draft), "How It Works". Handbook (status: draft), I6, I8, and "5.6 Verdict vocabulary".

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: User story this task belongs to (US1, US2, US3, US4, US5, US6)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: CPU fixtures and scripted ports. Do not download weights. Do not edit `.factverify/spec/`.

- [X] T001 [P] Create `tests/fixtures/controls/match/spec/closure_templates.yaml` with a top-level `groups` list of three mappings: `group_id: direct_construction` / `split: construction`; `group_id: direct_calibration` / `split: calibration`; `group_id: direct_final` / `split: final_test`. No other groups.
- [X] T002 [P] Create decision YAML files under `tests/fixtures/controls/match/decisions/`, each a `decisions:` list. `open.yaml`: D-53, D-54, D-58, D-59 all `status: open`. `d54_gap_only.yaml`: D-54 `closed` with only `max_abs_gap: "0.0"`; D-58 `closed`; D-53 and D-59 `open`. `d54_minmax.yaml`: D-54 `closed`, `band_summary: min_max`, `tolerance: "0.0"`, `boundary: inclusive`, `selection_rule: closest_center`; D-58 `closed`; D-53 and D-59 `open`. `d54_mean.yaml`: same as minmax but `band_summary: mean` and `tolerance: "0.1"`. `d54_exclusive.yaml`: minmax fields with `boundary: exclusive`. `d54_bad_rule.yaml`: minmax fields with `selection_rule: earliest`. `d58_open.yaml`: minmax D-54 fields and D-58 `open`. `d59_two.yaml`: minmax D-54, D-58 `closed`, D-59 `closed` with `dimensions` two items (`name: refusal_rate`, `tolerance: "0.0"`, `boundary: inclusive`; `name: fluency`, `tolerance: "0.0"`, `boundary: inclusive`). `d59_waiver.yaml`: minmax D-54, D-58 `closed`, D-59 `open`, `waiver: pilot-waiver`. `d59_closed_waiver.yaml`: `d59_two.yaml` plus `waiver: pilot-waiver` on the closed D-59 row. `d53_exact.yaml`: minmax D-54, D-58 `closed`, D-53 `closed`, `digest_tolerance: "0"`. `d53_nonzero.yaml`: same with `digest_tolerance: "1"`. Do not copy these files into `.factverify/spec/`.
- [X] T003 [P] Create probe manifests under `tests/fixtures/controls/match/probes/`. `ok.yaml`: two probes, `probe_id` `p1` and `p2`, `fact_id: fact-1`, `template_group_id: direct_construction`, `split: construction`, `kind: direct_qa`. `calibration_group.yaml`: one probe whose `template_group_id` is `direct_calibration`. `final_split.yaml`: one probe whose `split` is `final_test` and whose group is `direct_construction`. `not_direct.yaml`: one probe whose `kind` is `equivalence`. `empty.yaml`: `probes: []`.
- [X] T004 [P] Create match YAML files under `tests/fixtures/controls/match/configs/`. Every file uses `family: refusal`, `implementation_id: refusal.serving`, `fact_id: fact-1`, `control_ledger_id: ctrl-1`, `seed: 7`, `split: calibration`, `spec_revision: fixture-match`, `block: block_0`, `severity_search: [s0, s1, s2]`, `reference_ledger_ids: [ref-a, ref-b]`, `decisions` pointing at `d54_minmax.yaml`, `probes` pointing at `ok.yaml`, and `output_dir: /tmp/fv-match-out`. Variants, each changing one thing from that base: `one_ref.yaml` (`reference_ledger_ids: [ref-a]`); `block1_two.yaml` (`block: block_1`); `block1_three.yaml` (`block: block_1`, `reference_ledger_ids: [ref-a, ref-b, ref-c]`); `target.yaml` (add `target_accuracy: 0.5`); `bad_block.yaml` (`block: block_9`); `final_split.yaml` (`split: final_test`); `hard.yaml` (`hard: true`, `decisions` pointing at `d59_two.yaml`); `budget.yaml` (add `budget: budget.json`); `empty_search.yaml` (`severity_search: []`). Tests copy a file into `tmp_path` and rewrite `output_dir` to that directory before calling `match_control`.
- [X] T005 [P] Create `tests/match_ports.py` with `MemoryMatchLedger` and `ScriptedMatchBehavior`. The ledger maps an id to an object with `ledger_id`, `role`, `fact_id`, and `split`, and `get` returns `None` for an unknown id. The behavior port takes reference accuracies, a severity-to-accuracy map, and an optional dimension-name-to-float map. `direct_qa_accuracy` returns the scripted accuracy and one output triple per requested probe id (`probe_id`, `system_id`, `output` text `out-{probe_id}`). `dimension_value` returns the scripted float for that name. No network, no `from_pretrained`, and no import of `src.eval`.

**Checkpoint**: Fixture files and scripted ports exist. `src/controls/match.py` does not exist yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Decision fields and the match document loader every story calls. No story starts until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T006 [P] Extend `DecisionRow` and `load_decisions` in `src/controls/decisions.py` per `research.md` Decision 2. Allow decision ids `D-58` and `D-59` in addition to the existing four. Add optional fields `band_summary`, `tolerance`, `boundary`, `selection_rule`, `dimensions`, and `waiver`. A missing id stays `status: open` via `row_or_open`. Do not invent match fields when they are absent. Do not change `check_retention` in `src/controls/checks.py`: it still reads only `status` and `max_abs_gap`. Existing files under `tests/fixtures/controls/decisions/` must still load.
- [X] T007 [P] Add the dataclasses and protocols in `src/controls/match.py` per `data-model.md` and `contracts/match_control.md`: `SystemView`, `ProbeOutput`, `Measurement`, `MatchRecord`, `PilotInput`, `MatchLedgerPort`, `MatchBehaviorPort`. No `match_control` yet. Do not import `src.eval.gateway` or `src.eval.budget`.
- [X] T008 Implement `load_match_config` in `src/controls/match.py` per `data-model.md` MatchConfig and `research.md` Decision 1. Unknown keys, missing required keys, null, and `DECISION_REQUIRED` raise `ControlError` naming the key. Forbidden keys `target_accuracy`, `target`, `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, `frr`, and `budget` raise before any other work. A string value ending in `verdict.json` or `budget.json` raises. `severity_search` must be a non-empty list of strings or numbers; a bool entry or an empty list raises. `split` `final_test` or `final-test` raises. Absent `hard` is false. `output_dir` inside `.factverify/` raises. No field is defaulted except that absent `hard`. Do not measure and do not write `match.json` in this task.
- [X] T009 Run `uv run pytest tests/test_controls.py -q` and keep the existing P2-3 hooks green. A failure here means T006 changed retention or the decision loader. Do not weaken those assertions.

**Checkpoint**: A match document and an open decision file load. P2-3 tests still pass. User stories can begin.

---

## Phase 3: User Story 1 — Match a control to the retain-only reference band (Priority: P1) 🎯 MVP

**Goal**: The target band is the closed D-54 summary of the retain-only reference accuracies. The first-ranked severity under `closest_center` is `matched` only when its accuracy is inside that band. A short reference set, a literal target, or an open D-54 row writes no verdict.

**Independent Test**: `uv run pytest tests/test_match.py -k "011 or 012" -v`

### Tests for User Story 1

- [X] T010 [US1] Write these tests in `tests/test_match.py` so they fail before T011. Seed `MemoryMatchLedger` with `ctrl-1` role `control`, and `ref-a`, `ref-b`, `ref-c` role `reference`, all `fact_id: fact-1`, split `calibration`. Point `spec_root` at `tests/fixtures/controls/match/spec`.
  - `test_fv_ctrl_011_target_from_refs` — references `ref-a=0.4`, `ref-b=0.8`, severities `s0=0.0`, `s1=0.6`, `s2=1.0`, decisions `d54_minmax.yaml`. The record's `target_band.summary` is `min_max`, `low` is `0.4`, `high` is `0.8`, `center` is `0.6`, and `reference_ledger_ids` is `[ref-a, ref-b]` with those accuracies. `block1_three.yaml` with `ref-c=0.6` also writes a band. `one_ref.yaml`, `block1_two.yaml`, `bad_block.yaml`, and `target.yaml` raise and leave no `match.json`. `d54_gap_only.yaml` and `open.yaml` raise `ControlError` matching `D-54`. A reference role `finetuned`, a reference `fact_id` of `fact-2`, a `final_test` reference split, and a duplicate id in `reference_ledger_ids` each raise before a file is written. `d54_mean.yaml` yields center `0.6`, low `0.5`, high `0.7`.
  - `test_fv_ctrl_012_tolerance` — the minmax case above is `matched`, `selected_severity` is `s1`, and `achieved_value` is `0.6`. Severities `s0=0.0`, `s1=0.1`, `s2=0.2` are `unmatched` and the selected severity is `s2` (closest to `0.6`). `d54_exclusive.yaml` with a single severity whose accuracy is `0.4` is `unmatched`. `d54_bad_rule.yaml` raises `D-54`. Both in-band severities `s0=0.4` and `s1=0.6` select `s1`.

### Implementation for User Story 1

- [X] T011 [US1] Implement `match_control` in `src/controls/match.py` per `contracts/match_control.md` steps 1, 3 (D-54 only), 5, and 6, and `research.md` Decisions 1–3 and 8. Require a closed D-54 row with `band_summary` `min_max` or `mean`, `tolerance` in `[0, 1]`, `boundary` `inclusive` or `exclusive`, and `selection_rule` `closest_center`; otherwise raise `ControlError("D-54")` before the behavior port is called. `block_0` needs two references and `block_1` needs at least three; any other block raises `ControlError("block")`. Resolve `control_ledger_id` as role `control` and each reference as role `reference`, same fact, split `construction` or `calibration`. Load probe ids from the manifest (non-empty, `kind: direct_qa`, same `fact_id`) so the port can be called. Group-split refusal is T014. Try every `severity_search` entry. Rank by absolute distance to the center, then earlier index. Write `output_dir/match.json` for both `matched` and `unmatched` with the fields in `contracts/match_record.md`, including `trajectory`, `reads`, `config_hash` from `src.train.config.hash_mapping`, and cost from `src.train.cost.CostRecord`. A refusal writes no file. `hard_check` is `not_required` in this task. Add `load_match_record` that raises when a required provenance, trajectory, or cost field is missing. Do not call `build_control`.
- [X] T012 [US1] Run `uv run pytest tests/test_match.py -k "011 or 012" -v` and make those two hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Story 1 stands alone. A closed D-54 record produces a band from the references. An open D-54 record, a gap-only D-54 record, and a literal target write nothing. No probe-group isolation yet.

---

## Phase 4: User Story 2 — Match only on probes held apart from evaluation (Priority: P1)

**Goal**: A finished match's `reads` list contains only the D-58 manifest probes and the reference or control outputs on them. Calibration groups, final-test probes, evaluator keys, and an open D-58 row are refused before measurement.

**Independent Test**: `uv run pytest tests/test_match.py -k "013 or 011 or 012" -v`

### Tests for User Story 2

- [X] T013 [US2] Add `test_fv_ctrl_013_probe_isolation` to `tests/test_match.py` so it fails before T014. The `ok.yaml` match's `reads` probe ids are exactly `{p1, p2}`, each paired with `ref-a`, `ref-b`, and `ctrl-1` at `s0`, `s1`, and `s2`, and the output text is the scripted `out-{probe_id}`. The file has no key `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, or `frr`. `calibration_group.yaml`, `final_split.yaml`, `not_direct.yaml`, `empty.yaml`, and `d58_open.yaml` raise and write no `match.json`. `budget.yaml` raises naming `budget`. Reading `src/controls/match.py` as text shows no import of `src.eval.gateway` or `src.eval.budget`. A behavior output whose `probe_id` is `p9` raises naming `p9`.

### Implementation for User Story 2

- [X] T014 [US2] Implement probe isolation in `src/controls/match.py` per `contracts/probes.md` and `research.md` Decision 4. An open or missing D-58 row raises `ControlError("D-58")` before the behavior port is called. Read `{spec_root}/closure_templates.yaml` `groups`. A missing file raises naming `closure_templates.yaml`. Refuse a probe group that is absent or whose `split` is `calibration` or `final_test`, naming that group id. Refuse `kind` other than `direct_qa`, a mismatched `fact_id`, a `final_test` probe split, and a duplicate `probe_id`. After the port returns, refuse an output `probe_id` that is not in the manifest. Do not write the spec file.
- [X] T015 [US2] Run `uv run pytest tests/test_match.py -k "013 or 011 or 012" -v` and make those hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Stories 1 and 2 both work. Construction direct-QA probes are the only probes a match reads. Open D-58 still refuses.

---

## Phase 5: User Story 3 — Keep every unmatched control visible (Priority: P1)

**Goal**: Every unmatched match stays in the set the integrity-pilot report would read, with family, best achieved value, and target band. Removing that row fails the check. The recorded tolerance is the D-54 string.

**Independent Test**: `uv run pytest tests/test_match.py -k "014 or 012" -v`

### Tests for User Story 3

- [X] T016 [US3] Add `test_fv_ctrl_014_unmatched_reported` to `tests/test_match.py` so it fails before T017. Use the unmatched severities from T010 (`s0=0.0`, `s1=0.1`, `s2=0.2`). `pilot_inputs` returns that control with `family` `refusal`, `best_value` `0.2`, and `target_band` low `0.4`, high `0.8`, summary `min_max`. `reject_dropped` returns when the reported tuple is that full list. Dropping the unmatched row, or changing `best_value` to `0.0`, raises `ControlError` matching `unmatched`. The written `target_band.tolerance` is the string `0.0`.

### Implementation for User Story 3

- [X] T017 [US3] Implement `pilot_inputs` and `reject_dropped` in `src/controls/match.py` per `research.md` Decision 5 and `contracts/match_record.md`. `pilot_inputs` emits one `PilotInput` per record, unmatched included. `best_value` is `achieved_value`. `reject_dropped` raises `ControlError("unmatched")` when an unmatched source `control_ledger_id` is missing or when its family, best value, or band low/high/summary differ. Do not add a helper that filters to `matched`. Do not change the tolerance string after measurement.
- [X] T018 [US3] Run `uv run pytest tests/test_match.py -k "014 or 012" -v` and make those hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Stories 1–3 work. An unmatched control remains visible. The tolerance on the record is still the D-54 value.

---

## Phase 6: User Story 4 — Record the search and keep its cost off the evaluator budget (Priority: P2)

**Goal**: The trajectory lists every declared severity and its accuracy, including a search that never enters the band. Wall-clock, GPU-hours, and peak memory are on the record. Matching does not charge an evaluator budget.

**Independent Test**: `uv run pytest tests/test_match.py -k "016 or 013" -v`

### Tests for User Story 4

- [X] T019 [US4] Add `test_fv_ctrl_016_trajectory` to `tests/test_match.py` so it fails before T020. The three-severity unmatched run writes `trajectory` `[s0, s1, s2]` with accuracies `0.0`, `0.1`, `0.2` in that order. `wall_clock_seconds`, `gpu_hours`, and `peak_memory_bytes` are present and are not negative. Deleting `trajectory` from the written JSON makes `load_match_record` raise. The behavior port's call count for the control equals the length of `severity_search` (no early stop). `budget.yaml` still raises, and `src/controls/match.py` still does not import the gateway or the accountant.

### Implementation for User Story 4

- [X] T020 [US4] Finish the search loop and cost copy in `src/controls/match.py` per `research.md` Decision 7. `CostRecord.start()` runs only after validation. `finish(0, 0)` runs after every declared severity has been measured. Copy `wall_clock_seconds`, `gpu_hours`, and `peak_memory_bytes` onto the record. Do not stop the loop when an earlier severity is already inside the band. Do not call `Accountant.query` or `Gateway.complete`. Keep the import ban from T014.
- [X] T021 [US4] Run `uv run pytest tests/test_match.py -k "016 or 013" -v` and make those hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Stories 1–4 work. An exhausted search list is complete. Matching cost is on `match.json` and not on an evaluator budget.

---

## Phase 7: User Story 5 — Repeat the same match from the same seed (Priority: P2)

**Goal**: Two runs of the same document and seed select the same severity and status when D-53 is closed with tolerance `0`. An open D-53 row refuses the comparison and still leaves the seed on any record that was written. The search order does not use the seed.

**Independent Test**: `uv run pytest tests/test_match.py -k "017" -v`

### Tests for User Story 5

- [X] T022 [US5] Add `test_fv_ctrl_017_reproducible` to `tests/test_match.py` so it fails before T023. Run `d53_exact.yaml` twice with seed `7`. `compare_matches` returns, and both records have `selected_severity` `s1` and status `matched` for the in-band script from T010. `compare_matches` on `open.yaml` raises `ControlError` matching `D-53` and does not delete either record; each record's `seed` is `7`. `d53_nonzero.yaml` raises `D-53`. A second document that is identical except `seed: 8` stores `8` and still has a config hash different from the seed-7 record. The severity call order is `s0`, `s1`, `s2` on both seeds.

### Implementation for User Story 5

- [X] T023 [US5] Implement `compare_matches` in `src/controls/match.py` per `research.md` Decision 7. Load the decision path. Missing, open, or a `digest_tolerance` other than `"0"` raises `ControlError("D-53")`. Tolerance `"0"` requires equal `selected_severity` and `status`. Do not compare wall-clock. Do not use `seed` to order or sample severities. `match_control` still writes a record when D-53 is open. Export `match_control`, `compare_matches`, `pilot_inputs`, `reject_dropped`, `load_match_record`, and `ControlError` from `src/controls/__init__.py`, and replace the module docstring that says behaviour matching is not exported.
- [X] T024 [US5] Run `uv run pytest tests/test_match.py -k "017" -v` and make that hook pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Stories 1–5 work. Same inputs and seed agree under a closed zero tolerance. An open D-53 row blocks only the comparison.

---

## Phase 8: User Story 6 — Match a hard control on the extra dimensions (Priority: P3)

**Goal**: A control tagged `hard` is `matched` only when every closed D-59 dimension is inside its tolerance at the selected severity. A miss names the dimension and stays `unmatched`. An open D-59 row refuses unless it carries a waiver string. A control that is not tagged `hard` ignores D-59.

**Independent Test**: `uv run pytest tests/test_match.py -k "015 or 012" -v`

### Tests for User Story 6

- [X] T025 [US6] Add `test_fv_ctrl_015_hard_dimensions` to `tests/test_match.py` so it fails before T026. `hard.yaml` with both dimension values `0.0` is `matched`, `hard_check` is `passed`, and both names are stored. `fluency` value `0.2` with tolerance `"0.0"` and inclusive boundary is `unmatched`, `failed_dimension` is `fluency`, and `trajectory` still has three entries. The base config with `hard` absent and decisions `d59_two.yaml` is judged on accuracy only (`hard_check` `not_required`) and does not call `dimension_value`. `hard: true` with `d54_minmax.yaml` (D-59 open, no waiver) raises `D-59` and writes no file. `d59_waiver.yaml` writes `hard_check: waived` and `waiver_reason: pilot-waiver` and does not call `dimension_value`. `d59_closed_waiver.yaml` raises `D-59`.

### Implementation for User Story 6

- [X] T026 [US6] Implement the hard-dimension gate in `src/controls/match.py` per `research.md` Decision 6. `hard: false` or absent does not read D-59. `hard: true` and an open D-59 row without a non-empty `waiver` raises `ControlError("D-59")` before measurement. A non-empty waiver on an open row sets `hard_check` to `waived` and copies `waiver_reason`; dimensions are not measured. A closed row requires a non-empty `dimensions` list and raises if `waiver` is also set. After accuracy ranking, call `dimension_value` for the selected severity only, in list order. Store each value. The first failure sets status to `unmatched`, `hard_check` to `failed`, and `failed_dimension` to that name. Later dimensions are still measured. Do not hardcode `refusal_rate`, `fluency`, or utility as a required list. Do not search for a different severity to satisfy a dimension.
- [X] T027 [US6] Run `uv run pytest tests/test_match.py -k "015 or 012" -v` and make those hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: All six stories work. A hard control that misses one recorded dimension stays unmatched and names that dimension. Open D-59 still refuses a hard match that has no waiver.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: The full hook set and the existing control tests stay green. The frozen spec is untouched.

- [X] T028 Run `uv run pytest tests/test_match.py tests/test_controls.py -q` from the repository root. All seven `test_fv_ctrl_011`–`test_fv_ctrl_017` hooks and the existing P2-3 hooks pass.
- [X] T029 [P] Run `make lint` and fix any new findings in `src/controls/match.py`, `src/controls/decisions.py`, `src/controls/__init__.py`, and `tests/test_match.py`. Do not silence a new annotation or style error.
- [X] T030 Confirm `git status -- .factverify/spec spec-unlearning` shows no edits from this feature. Confirm `src/controls/match.py` contains no `from_pretrained` and no import of `src.eval.gateway` or `src.eval.budget`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T001–T005 touch different files and can run together.
- **Foundational (Phase 2)**: Depends on Setup. T006 and T007 can run together. T008 depends on T007. T009 depends on T006. Blocks every user story.
- **User Stories (Phase 3+)**: Depend on Foundational. They share `src/controls/match.py` and `tests/test_match.py`, so they run in order: US1 → US2 → US3 → US4 → US5 → US6.
- **Polish (Phase 9)**: Depends on US1–US6.

### User Story Dependencies

- **User Story 1 (P1)**: Starts after Phase 2. No later story is required. This is the MVP.
- **User Story 2 (P1)**: Starts after US1. Adds group and D-58 refusals on the same function. US1 fixtures already close D-58 and use construction probes, so they stay green.
- **User Story 3 (P1)**: Starts after US1 has an unmatched record. Does not need US2's group checks to assert `pilot_inputs`.
- **User Story 4 (P2)**: Starts after US1 writes a trajectory. The import ban is already required by US2.
- **User Story 5 (P2)**: Starts after US1 writes `seed` and `selected_severity`. Comparison is a separate function.
- **User Story 6 (P3)**: Starts after US1's ranking. Dimension checks run on the selected severity only.

### Within Each User Story

- The story's tests are written first and fail before the implementation task.
- The story's pytest task is the checkpoint. Do not start the next story on a red checkpoint.

### Parallel Opportunities

- T001, T002, T003, T004, and T005 are different files.
- T006 (`decisions.py`) and T007 (`match.py` types) are different files.
- T029 (`make lint`) can run beside a documentation pass; T028 and T030 are sequential checks.
- User-story implementation tasks edit `src/controls/match.py` and are not parallel with each other.

---

## Parallel Example: Setup

```bash
# After the feature directory exists, different files:
Task: "Create tests/fixtures/controls/match/spec/closure_templates.yaml"
Task: "Create tests/fixtures/controls/match/decisions/*.yaml"
Task: "Create tests/fixtures/controls/match/probes/*.yaml"
Task: "Create tests/fixtures/controls/match/configs/*.yaml"
Task: "Create tests/match_ports.py"
```

## Parallel Example: Foundational

```bash
# Different files, before load_match_config:
Task: "Extend load_decisions in src/controls/decisions.py"
Task: "Add match dataclasses in src/controls/match.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3.
3. Stop and run the US1 independent test. A closed D-54 record produces a reference band, and an open record writes no verdict. That is the MVP.

### Incremental Delivery

1. Setup + foundational → match documents load, and P2-3 tests still pass.
2. US1 → band and tolerance.
3. US2 → probe isolation.
4. US3 → unmatched rows stay in the pilot inputs.
5. US4 → full trajectory and cost, still off the evaluator budget.
6. US5 → same seed compares; open D-53 refuses only the comparison.
7. US6 → hard dimensions, or a recorded waiver.
8. Polish → `make lint` and `make test`.

### Notes

- Passing a fixture does not mark FV-CTRL-011, FV-CTRL-012, FV-CTRL-013, FV-CTRL-015, or FV-CTRL-017 implemented while D-54, D-58, D-59, or D-53 is open on a study decision record. Fixture files under `tests/fixtures/controls/match/decisions/` may close only the row that hook asserts.
- `ledger.sqlite` is P2-5. This feature reads ledger rows through `MatchLedgerPort` and does not write SQLite.
- Weight updates stay in `src/train/`. Tests use `ScriptedMatchBehavior` and do not call `load_model`.
- Do not edit `.factverify/spec/` or `spec-unlearning/`.
- Do not add `discovery_and_calibration_cost` to `attacks.yaml`. Matching stays uncharged because `match.py` never calls the accountant.

---

## Task counts

| Phase | Tasks | IDs |
|-------|-------|-----|
| Setup | 5 | T001–T005 |
| Foundational | 4 | T006–T009 |
| US1 | 3 | T010–T012 |
| US2 | 3 | T013–T015 |
| US3 | 3 | T016–T018 |
| US4 | 3 | T019–T021 |
| US5 | 3 | T022–T024 |
| US6 | 3 | T025–T027 |
| Polish | 3 | T028–T030 |
| **Total** | **30** | |
