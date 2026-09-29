# Tasks: P1 Fact Bundle Preparation

**Input**: Design documents from `specs/20260928-224019-p1-bundle-prep/`
**Feature**: `20260928-224019-p1-bundle-prep`
**Branch**: `main`

**Organization**: Tasks grouped by user story — US1 (source bundles), US2 (locality neighbourhoods), US3 (entailment audit). Tests are included because requirement IDs (FV-DATA-019–034) explicitly map to named pytest hooks.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no shared state dependencies)
- **[Story]**: User story label (US1/US2/US3) — required for story phases
- Commit messages must reference task IDs (`P1-3: build_bundles.py FV-DATA-019`)

---

## Phase 1: Setup

**Purpose**: Output directories, Makefile targets, no code logic.

- [x] T001 Add `build-bundles`, `build-neighbourhoods`, and `entailment-audit` Makefile targets to `Makefile` (commands from `quickstart.md`)
- [x] T002 [P] Create empty `data/controlled/sources/`, `data/controlled/leaveout/`, and `results/` directories with `.gitkeep` placeholders
- [x] T003 [P] Create empty test files `tests/test_bundles.py`, `tests/test_neighbourhoods.py`, `tests/test_entailment_audit.py` with module docstrings and `import` stubs

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared data-loading helpers consumed by all three scripts. Must be complete before any user story begins.

**⚠️ CRITICAL**: No US1/US2/US3 implementation can begin until this phase is complete.

- [x] T004 Add `load_accepted_facts(path: Path) -> list[dict]` to `src/data/tofu.py` — reads `facts.jsonl`, returns only rows whose `contract_status` is `"draft"` (or `"frozen"` once P1-2 gate verdicts are written); full type annotations, ruff-clean
- [x] T005 [P] Add `load_template_groups(spec_root: Path) -> dict[str, list[str]]` helper (reads `closure_templates.yaml`, returns `{group_id: [text_patterns]}`) to a new `src/data/spec_readers.py`; used by the template-disjointness check (FR-003)
- [x] T006 [P] Add `sha256_of_ids(record_ids: list[str]) -> str` and `sha256_file(path: Path) -> str` digest utilities to `src/data/digests.py` (these already exist in various forms — consolidate into one module; no duplication with `src/models/identity.py`)

**Checkpoint**: `make lint` and `make test` pass — helper modules importable with no errors.

---

## Phase 3: User Story 1 — Build Source Bundles (Priority: P1) 🎯 MVP

**Goal**: `build_bundles.py` reads accepted facts and adjudicated mentions, produces per-fact source bundles, a record-to-fact index, and leave-out manifests.

**Independent Test**: Run `make build-bundles` against the current `facts.jsonl` + `mentions.jsonl`. Verify `data/controlled/sources/bundles/` has one file per accepted fact, `data/controlled/sources/index.jsonl` exists, and `data/controlled/leaveout/` has one manifest per fact. Run `pytest tests/test_bundles.py` — all pass.

### Tests for US1 (write first, verify they FAIL before implementation)

- [x] T007 [P] [US1] Write `test_fv_data_019_bundle_complete` in `tests/test_bundles.py` — given a fixture index, bundle record set equals index-mapped records for that fact
- [x] T008 [P] [US1] Write `test_fv_data_020_both_directions` in `tests/test_bundles.py` — bundle below D-66 minimum (3) in either direction raises
- [x] T009 [P] [US1] Write `test_fv_data_021_template_disjoint` in `tests/test_bundles.py` — a training record matching an evaluation template group causes a raise naming record and group
- [x] T010 [P] [US1] Write `test_fv_data_022_single_target_records` in `tests/test_bundles.py` — a multi-target record produces a transformation entry and results in single-target records
- [x] T011 [P] [US1] Write `test_fv_data_023_index_complete` in `tests/test_bundles.py` — every record in records.jsonl appears in the index; absent records cause validation failure
- [x] T012 [P] [US1] Write `test_fv_data_024_leaveout_clean` in `tests/test_bundles.py` — no record in a leave-out manifest is indexed to the excluded fact; manifest carries a dataset digest
- [x] T013 [P] [US1] Write `test_fv_data_018_gate_before_train` in `tests/test_bundles.py` — building a bundle for a fact without a `pass` verdict raises

### Implementation for US1

- [x] T014 [US1] Define `TrainingRecord` and `SourceBundle` dataclasses (from `data-model.md`) in `scripts/build_bundles.py` — frozen dataclasses, full type annotations
- [x] T015 [US1] Implement `build_record_index(mentions, facts) -> dict[str, list[str]]` in `scripts/build_bundles.py` — maps each accepted mention's source row to the fact it expresses; handles multi-mention rows
- [x] T016 [US1] Implement `detect_multi_fact_records(index) -> list[str]` and `apply_d66_policy(record_id, facts) -> TransformationResult` in `scripts/build_bundles.py` — splits where possible, excludes otherwise, writes to `transformations.jsonl`
- [x] T017 [US1] Implement `check_template_disjoint(record_text, template_groups) -> bool` in `scripts/build_bundles.py` — calls `load_template_groups()` from T005; raises on match (FV-DATA-021)
- [x] T018 [US1] Implement `build_bundle(fact_id, index, records) -> SourceBundle` in `scripts/build_bundles.py` — assembles forward/inverse record IDs, validates D-66 minimum of 3 per direction, raises if below
- [x] T019 [US1] Implement `write_index(index, out_path: Path) -> None` in `scripts/build_bundles.py` — writes `data/controlled/sources/index.jsonl` one object per record
- [x] T020 [US1] Implement `build_leaveout_manifest(fact_id, all_record_ids, bundle_record_ids) -> LeaveOutManifest` in `scripts/build_bundles.py` — excludes bundle records, computes SHA-256 digest with `sha256_of_ids()` from T006
- [x] T021 [US1] Implement the `build` click command in `scripts/build_bundles.py` — wires T015–T020; reads `--facts`, `--mentions`, `--source`, `--spec-root`, `--out`, `--leaveout`, `--transforms`; writes all outputs; prints summary counts
- [x] T022 [US1] Run `pytest tests/test_bundles.py` — all 7 tests must pass; fix until green
- [x] T023 [US1] Run `make lint` — `ruff check scripts/build_bundles.py src/data/` and `ruff format --check` must pass

**Checkpoint**: `make build-bundles` succeeds on live data; `pytest tests/test_bundles.py` green; `data/controlled/sources/` and `data/controlled/leaveout/` populated.

---

## Phase 4: User Story 2 — Populate Locality Neighbourhoods (Priority: P2)

**Goal**: `build_neighbourhoods.py` replaces all `[P1-5 stub]` entries in fact contracts with sourced neighbourhood items across all four locality buckets.

**Independent Test**: Run `make build-neighbourhoods` after Phase 3. Verify `data/controlled/neighbourhoods.jsonl` exists with no `[P1-5 stub]` text in any `statement` field. Run `pytest tests/test_neighbourhoods.py` — all pass.

### Tests for US2 (write first, verify they FAIL before implementation)

- [x] T024 [P] [US2] Write `test_fv_data_030_bucket_coverage` in `tests/test_neighbourhoods.py` — fact short in any bucket raises naming fact and bucket
- [x] T025 [P] [US2] Write `test_fv_data_031_retained_sources` in `tests/test_neighbourhoods.py` — same_subject/same_relation item not in leave-out manifest causes a raise
- [x] T026 [P] [US2] Write `test_fv_data_032_global_source` in `tests/test_neighbourhoods.py` — global item traced to a finetuning record causes validation failure
- [x] T027 [P] [US2] Write `test_fv_data_033_compositional_independent` in `tests/test_neighbourhoods.py` — fixture compositional item that requires the target fact is rejected
- [x] T028 [P] [US2] Write `test_fv_data_034_split_isolation` in `tests/test_neighbourhoods.py` — fictional entity in a different split from the target causes a validation failure

### Implementation for US2

- [x] T029 [US2] Define `NeighbourhoodItem` dataclass (from `data-model.md`) in `scripts/build_neighbourhoods.py` — frozen, full type annotations including `bucket` as `Literal["same_subject","same_relation","compositional","global"]`
- [x] T030 [US2] Implement `load_leaveout_index(leaveout_dir: Path) -> dict[str, set[str]]` in `scripts/build_neighbourhoods.py` — maps `fact_id → record_ids` for retained-source checks (FV-DATA-031)
- [x] T031 [US2] Implement `find_same_subject_items(fact, all_facts, leaveout_index) -> list[NeighbourhoodItem]` in `scripts/build_neighbourhoods.py` — co-present accepted facts about the same subject entity that appear in the leave-out manifest
- [x] T032 [US2] Implement `find_same_relation_items(fact, all_facts, leaveout_index) -> list[NeighbourhoodItem]` in `scripts/build_neighbourhoods.py` — other accepted facts with the same relation that appear in the leave-out manifest
- [x] T033 [US2] Implement `load_global_source(tofu_dir: Path, configs: list[str]) -> list[NeighbourhoodItem]` in `scripts/build_neighbourhoods.py` — loads TOFU `real_authors` and `world_facts` configs; validates no finetuning record is indexed to each item (FV-DATA-032)
- [x] T034 [US2] Implement `validate_split_isolation(item, target_split, splits: dict) -> None` in `scripts/build_neighbourhoods.py` — raises for fictional entities belonging to a different split (FV-DATA-034); global items exempt
- [x] T035 [US2] Implement stub-replacement logic in `scripts/build_neighbourhoods.py` — for each fact, replace all `[P1-5 stub]` retained_neighbourhood entries with real items from T031–T033; raise if any bucket stays below minimum of 1 (D-38)
- [x] T036 [US2] Implement the `build` click command in `scripts/build_neighbourhoods.py` — wires T030–T035; writes `data/controlled/neighbourhoods.jsonl`; prints stub count before/after
- [x] T037 [US2] Run `pytest tests/test_neighbourhoods.py` — all 5 tests must pass; fix until green
- [x] T038 [US2] Run `make lint` on `scripts/build_neighbourhoods.py`

**Checkpoint**: `make build-neighbourhoods` succeeds; `data/controlled/neighbourhoods.jsonl` has 0 stubs; `pytest tests/test_neighbourhoods.py` green.

---

## Phase 5: User Story 3 — Entailment Audit (Priority: P3)

**Goal**: `entailment_audit.py` classifies every record in each leave-out manifest as `duplicate | entails | clue_bearing | clean`, with human adjudication for flagged records and a random sample, bound to manifest digests.

**Independent Test**: Run `make entailment-audit` after Phase 3 (does not require Phase 4). Verify `results/entailment_audit.jsonl` exists with a row per (unit, record) and `reports/entailment_audit.md` is written. If confirmed failures > 0, remediate and re-run. Run `pytest tests/test_entailment_audit.py` — all pass.

### Tests for US3 (write first, verify they FAIL before implementation)

- [x] T039 [P] [US3] Write `test_fv_data_025_no_expression` in `tests/test_entailment_audit.py` — fixture with an inverse-direction alias in a manifest record causes audit to fail naming the record
- [x] T040 [P] [US3] Write `test_fv_data_026_entailment_screen` in `tests/test_entailment_audit.py` — known-entailing fixture records are flagged with method, score, and threshold stored
- [x] T041 [P] [US3] Write `test_fv_data_027_adjudication_complete` in `tests/test_entailment_audit.py` — audit with an unflagged sample missing a human label reports status `incomplete`
- [x] T042 [P] [US3] Write `test_fv_data_028_remediation` in `tests/test_entailment_audit.py` — confirmed failure without a transformations.jsonl entry causes P3-1 guard to refuse the fact
- [x] T043 [P] [US3] Write `test_fv_data_029_digest_binding` in `tests/test_entailment_audit.py` — manifest with a changed digest causes the training harness to raise

### Implementation for US3

- [x] T044 [US3] Define `AuditResult` dataclass (from `data-model.md`) in `scripts/entailment_audit.py` — frozen, full type annotations; `verdict` as `Literal["duplicate","entails","clue_bearing","clean"]`
- [x] T045 [US3] Implement `exact_match_check(record_text, fact) -> bool` in `scripts/entailment_audit.py` — checks all subject aliases × object aliases × both argument orders (D-39: English-only, contract-declared); returns `True` if duplicate (FV-DATA-025)
- [x] T046 [US3] Implement `ReviewCache` reuse: import or copy the `ReviewCache` class from `scripts/adjudicate_mentions.py` into `src/data/review_cache.py` — single source of truth for the cache pattern; update `adjudicate_mentions.py` to import from there
- [x] T047 [US3] Implement `llm_entailment_judge(record_text, fact, client, cache) -> tuple[bool, float]` in `scripts/entailment_audit.py` — calls Anthropic API with a binary entailment prompt; result cached via `ReviewCache` from T046 (FV-DATA-026)
- [x] T048 [US3] Implement `draw_unflagged_sample(clean_records, fraction=0.10, min_n=5, max_n=20, seed=42) -> list[str]` in `scripts/entailment_audit.py` — deterministic random sample; seed stored in audit output (FV-DATA-027)
- [x] T049 [US3] Implement `record_human_adjudication(result_path, record_id, label, reader_id, notes) -> None` in `scripts/entailment_audit.py` — appends human label to the audit result row; used interactively after automated screen
- [x] T050 [US3] Implement `check_digest_binding(manifest_path, expected_digest) -> None` in `scripts/entailment_audit.py` — computes current manifest digest and raises `AuditDigestMismatch` if it differs (FV-DATA-029)
- [x] T051 [US3] Add digest-binding guard to `src/train/` harness entry point — before any training run, load the audit result for each fact's leave-out manifest and call `check_digest_binding`; raise if audit is missing or digest mismatches (FV-DATA-029 training guard)
- [x] T052 [US3] Implement the `audit` click command in `scripts/entailment_audit.py` — wires T045–T050; reads `--facts`, `--leaveout`, `--index`, `--spec-root`, `--out`, `--report`, `--sample-fraction`, `--sample-min`, `--sample-max`; writes `results/entailment_audit.jsonl` and `reports/entailment_audit.md`
- [x] T053 [US3] Run `pytest tests/test_entailment_audit.py` — all 5 tests must pass; fix until green
- [x] T054 [US3] Run `make lint` on `scripts/entailment_audit.py` and `src/data/review_cache.py`

**Checkpoint**: `make entailment-audit` completes; `results/entailment_audit.jsonl` and `reports/entailment_audit.md` written; 0 unresolved confirmed failures; `pytest tests/test_entailment_audit.py` green.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T055 [P] Run full `make test` — `pytest tests/test_bundles.py tests/test_neighbourhoods.py tests/test_entailment_audit.py` — all must pass
- [x] T056 [P] Run `make lint` across all new files — `ruff check scripts/build_bundles.py scripts/build_neighbourhoods.py scripts/entailment_audit.py src/data/` — zero violations
- [x] T057 Update `reports/status.md` gate table to reflect P1-3, P1-4, P1-5 completion status (weekly update per CLAUDE.md convention)
- [x] T058 Run the full quickstart sequence from `quickstart.md` end to end — `make build-bundles && make build-neighbourhoods && make entailment-audit` — verify all outputs exist and are non-empty
- [x] T059 [P] Commit with task-ID-referenced messages: `P1-3: build_bundles.py FV-DATA-019–024`, `P1-5: build_neighbourhoods.py FV-DATA-030–034`, `P1-4: entailment_audit.py FV-DATA-025–029`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T001–T003 fully parallel
- **Phase 2 (Foundational)**: Depends on Phase 1; T004–T006 parallel after T001
- **Phase 3 (US1)**: Depends on Phase 2 completion — BLOCKS Phase 4 and Phase 5 (both need the index and manifests)
- **Phase 4 (US2)**: Depends on Phase 3 (needs `index.jsonl` and `leaveout/` manifests); independent of Phase 5
- **Phase 5 (US3)**: Depends on Phase 3 (needs `leaveout/` manifests and `index.jsonl`); independent of Phase 4
- **Phase 6 (Polish)**: Depends on Phases 3, 4, 5 all complete

### User Story Dependencies

- **US1**: Must complete first — its outputs are inputs to US2 and US3
- **US2 and US3**: Can proceed in parallel once US1 is done (different files, no shared writes)

### Within Each User Story

- Write tests first (T007–T013, T024–T028, T039–T043) — verify they FAIL before implementation
- Dataclasses before logic (T014, T029, T044)
- Helpers before CLI command (T015–T020 before T021; T030–T035 before T036; T045–T050 before T052)
- CLI command before test green run (T021 before T022; T036 before T037; T052 before T053)

### Parallel Opportunities

- T002, T003 parallel with T001 (different files)
- T004, T005, T006 parallel (different modules)
- T007–T013 all parallel (same file, different functions — write sequentially to avoid conflicts)
- T024–T028 all parallel (same constraint)
- T039–T043 all parallel (same constraint)
- US2 (Phase 4) and US3 (Phase 5) fully parallel once US1 done
- T055, T056 parallel (read-only)

---

## Parallel Example: After US1 Complete

```text
# US2 and US3 can run simultaneously:

Stream A (US2 — Neighbourhoods):
  T024 → T025 → T026 → T027 → T028  [tests]
  T029 → T030 → T031 → T032 → T033 → T034 → T035 → T036  [impl]
  T037 → T038  [verify]

Stream B (US3 — Audit):
  T039 → T040 → T041 → T042 → T043  [tests]
  T044 → T045 → T046 → T047 → T048 → T049 → T050 → T051 → T052  [impl]
  T053 → T054  [verify]
```

---

## Implementation Strategy

### MVP (US1 Only — minimum to unblock Phase 3 training)

1. Phase 1: Setup (T001–T003)
2. Phase 2: Foundational (T004–T006)
3. Phase 3: US1 — Source Bundles (T007–T023)
4. **STOP and VALIDATE**: `make build-bundles` + `pytest tests/test_bundles.py`
5. Phase 3 pilot training can now begin with bundles and manifests available

### Full Completion

1. Setup + Foundational
2. US1 → validate
3. US2 + US3 in parallel → validate each
4. Polish (T055–T059)
5. P1 sign-off: all 6 tasks in FV-DATA-P1-SIGNOFF checked off

---

## Notes

- `[P]` tasks operate on different files and have no shared-write dependencies
- Test tasks (T007–T013, T024–T028, T039–T043) must be written and confirmed FAILING before their implementation tasks begin
- Commit message convention: `P1-3: <description> FV-DATA-<NNN>` per CLAUDE.md
- `make lint` (ruff) must pass before any task is marked complete — no deferred style debt
- Open decisions D-66 minimum (3), D-38 minimum (1), D-67 sample fraction (0.10) are provisional Block-0 values; they live in config/spec, not hard-coded in scripts
