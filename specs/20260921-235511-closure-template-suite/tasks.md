# Tasks: P0-2 Closure Template Suite

**Input**: Design documents from `/specs/20260921-235511-closure-template-suite/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup

**Purpose**: Project initialization, directory structure, dependency verification

- [x] T001 Create directory structure: `.factverify/closure/`, `tests/fixtures/p0_2/valid/`, `tests/fixtures/p0_2/invalid/`, `tests/fixtures/p0_2/baselines/`
- [x] T002 [P] Update `tests/conftest.py` with P0-2 path constants: `CLOSURE_SUITE_PATH`, `CLOSURE_DIR`, `P0_2_FIXTURES`, `BINDINGS_PATH`, `REVIEW_MANIFEST_PATH`
- [x] T003 [P] Verify PyYAML is available in `pyproject.toml` dependencies (already present as `pyyaml>=6.0`)

**Checkpoint**: Directories exist, conftest updated, PyYAML available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Closure YAML schema definition, minimal valid suite fixture, YAML loading infrastructure — everything else depends on these

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Define the closure template suite JSON Schema at `specs/20260921-235511-closure-template-suite/contracts/closure_suite.schema.json` — covers all template record fields, class-specific constraints, group/split structure, per data-model.md
- [x] T005 Create a minimal valid closure suite fixture at `tests/fixtures/p0_2/valid/minimal_suite.yaml` — one E template (direct), one I template, one R template, one X template, one group per class, one split assignment, forward+inverse directions, all six families covered for one relation type
- [x] T006 Create a minimal valid instance bindings fixture at `tests/fixtures/p0_2/valid/minimal_bindings.json` — bindings for the minimal suite against the P0-1 Hà Nội contract
- [x] T007 Implement YAML loading and structural validation helper in `tools/closure_validator.py` — load closure_templates.yaml, parse with PyYAML safe_load, validate structure, export reusable functions for the validator

**Checkpoint**: Closure schema defined, minimal fixtures validate manually, YAML loader works.

---

## Phase 3: User Story 1 — Structural Validation (Priority: P1) MVP

**Goal**: Validate closure artifact structure: class routing, E premise emptiness, I provenance, unique identities, X exclusion.

**Independent Test**: `uv run python tools/validate_spec.py --scope closure-templates --spec-root .factverify/spec --contracts .factverify/contracts --bindings .factverify/closure/instance_bindings.json --report reports/p0-2-validation.json` exits 0 on valid suites and nonzero on invalid ones.

### Implementation for User Story 1

- [x] T008 [US1] Implement `--scope closure-templates` dispatch in `tools/validate_spec.py` — add scope to `SUPPORTED_SCOPES`, route to closure validation entry point in `tools/closure_validator.py`
- [x] T009 [US1] Implement closure artifact loading and structural validation in `tools/closure_validator.py` — load YAML from `--spec-root`, validate all template/group/context/binding references resolve, reject malformed YAML/duplicate keys/missing fields (FV-SPEC-016)
- [x] T010 [US1] Implement class routing validation in `tools/closure_validator.py` — enforce E→`sets.equivalence`, I→`sets.inference`, R/X→`controls`; reject misplaced class or multiple classes per record (FV-SPEC-017)
- [x] T011 [US1] Implement equivalence premise check in `tools/closure_validator.py` — require `extra_premises: []` for every E instance; reject missing or nonempty premises (FV-SPEC-018)
- [x] T012 [US1] Implement inference provenance check in `tools/closure_validator.py` — require subtype, nonempty premises, origins, reasoning/support status, separate_reporting for every I instance (FV-SPEC-019)
- [x] T013 [US1] Implement unique identity check in `tools/closure_validator.py` — reject duplicate template IDs; reject equivalent prompt/context/contract/answer bindings; record primary_family + overlapping_attributes (FV-SPEC-022)
- [x] T014 [US1] Implement exclusion routing check in `tools/closure_validator.py` — reject X instances in equivalence/inference populations; ensure X instances carry exclusion_reason; omit or mark diagnostic-only (FV-SPEC-026)
- [x] T015 [US1] Write demonstration closure suite at `.factverify/spec/closure_templates.yaml` — templates for Hà Nội (capital_of) and fictional scientist (alma_mater) contracts, all six families per relation, E/I/R/X routing, groups and splits
- [x] T016 [US1] Write demonstration instance bindings at `.factverify/closure/instance_bindings.json` — bindings for both demo contracts against the closure suite
- [x] T017 [US1] Create negative test fixtures in `tests/fixtures/closure_templates/invalid/` — misrouted class, nonempty E premises, missing I provenance, duplicate IDs, X in equivalence, malformed YAML, missing required fields
- [x] T018 [US1] Write `tests/test_closure_templates.py::test_fv_spec_016_artifact` — verify suite exists and parses; malformed YAML fails
- [x] T019 [US1] Write `tests/test_closure_templates.py::test_fv_spec_017_class_routing` — E in equivalence passes; E in controls fails; multiple classes fail
- [x] T020 [US1] Write `tests/test_closure_templates.py::test_fv_spec_018_equivalence_premises` — empty premises passes; nonempty premises fails; missing premises fails
- [x] T021 [US1] Write `tests/test_closure_templates.py::test_fv_spec_019_inference_provenance` — full provenance passes; missing subtype/premises/origins fails
- [x] T022 [P] [US1] Write `tests/test_closure_templates.py::test_fv_spec_022_unique_identity` — unique IDs pass; duplicate IDs fail; overlapping attributes recorded not duplicated
- [x] T023 [P] [US1] Write `tests/test_closure_templates.py::test_fv_spec_026_excluded_controls` — X in controls passes; X in equivalence fails; exclusion_reason required

**Checkpoint**: US1 complete — structural validation works end-to-end, demo suite passes, FV-SPEC-016–019, 022, 026 tests pass.

---

## Phase 4: User Story 2 — Contract Bindings and Coverage (Priority: P2)

**Goal**: Validate contract bindings (answer-role mapping), relation-family coverage, verification balance, and retained-control bindings.

**Independent Test**: Validator with `--bindings` checks answer-role mapping against P0-1 contracts, verifies six-family coverage, balanced verification blocks, and retained-control bucket coverage.

### Implementation for User Story 2

- [x] T024 [US2] Implement contract binding validation in `tools/closure_validator.py` — resolve bindings against P0-1 contracts; enforce forward→object, inverse→subject, verification→truth_value; reject unauthorized aliases, unresolved placeholders, mismatched qualifiers; map truth_label explicitly (FV-SPEC-020)
- [x] T025 [US2] Implement relation-family coverage check in `tools/closure_validator.py` — for each approved relation type, verify templates exist across all six families (direct, inverse, cloze, paraphrase, multilingual, verification); require at least four relation types covered (FV-SPEC-021)
- [x] T026 [US2] Implement verification balance check in `tools/closure_validator.py` — per (contract_id, relation, language, split) block, require true/false verification count match; oracle labels in metadata only (FV-SPEC-024)
- [x] T027 [US2] Implement retained-control binding check in `tools/closure_validator.py` — every R control references an approved P0-1 retained_neighbourhood entry; all locality buckets represented (FV-SPEC-025)
- [x] T028 [US2] Create negative test fixtures for US2 in `tests/fixtures/closure_templates/invalid/` — mismatched answer role, missing family coverage, unbalanced verification, unknown retained bucket, unauthorized alias
- [x] T029 [US2] Write `tests/test_closure_templates.py::test_fv_spec_020_contract_bindings` — correct bindings pass; forward→subject fails; unauthorized alias fails; truth_label mapping checked
- [x] T030 [US2] Write `tests/test_closure_templates.py::test_fv_spec_021_relation_family_coverage` — full coverage passes; missing family fails; fewer than four relations fails
- [x] T031 [P] [US2] Write `tests/test_closure_templates.py::test_fv_spec_024_verification_balance` — balanced block passes; unbalanced fails; oracle label withheld
- [x] T032 [P] [US2] Write `tests/test_closure_templates.py::test_fv_spec_025_retained_controls` — all buckets represented passes; missing bucket fails; unknown entry ref fails

**Checkpoint**: US2 complete — contract bindings, coverage, balance, and retained controls validated.

---

## Phase 5: User Story 3 — Group/Split Isolation and Preview (Priority: P3)

**Goal**: Validate group/split assignments, render deterministic previews, enforce metadata separation.

**Independent Test**: Validator with `--split construction --preview reports/p0-2-construction-preview.jsonl` renders preview, verifies group isolation, and confirms no answer keys in model_input.

### Implementation for User Story 3

- [x] T033 [US3] Implement group/split validation in `tools/closure_validator.py` — every template in exactly one group, every group in exactly one split, near-duplicates grouped, calibration/final_test disjoint, no cross-split reuse (FV-SPEC-023)
- [x] T034 [US3] Implement preview renderer in `tools/closure_validator.py` — materialize complete model-visible context (system text, demos, history) as ordered messages; generate stable instance_id; output JSONL; deterministic given fixed revisions (FV-SPEC-027)
- [x] T035 [US3] Implement metadata separation enforcement in `tools/closure_validator.py` — model_input contains only messages; evaluator_metadata holds answer_key, truth_label, class, review rationale, premises; reject any answer key in model_input (FV-SPEC-028)
- [x] T036 [US3] Implement split filtering in preview renderer — only render templates belonging to the requested split; construction must not contain calibration/final_test records (FV-SPEC-023)
- [x] T037 [US3] Wire `--split` and `--preview` CLI options in `tools/validate_spec.py` for `closure-templates` scope
- [x] T038 [US3] Create negative test fixtures for US3 in `tests/fixtures/closure_templates/invalid/` — template in two groups, cross-split group, held-out in construction, answer in model_input
- [x] T039 [US3] Write `tests/test_closure_templates.py::test_fv_spec_023_group_split_isolation` — valid grouping passes; template in two groups fails; cross-split reuse fails; construction preview has no held-out records
- [x] T040 [US3] Write `tests/test_closure_templates.py::test_fv_spec_027_complete_context` — deterministic rendering (two runs identical); unresolved context ref fails
- [x] T041 [P] [US3] Write `tests/test_closure_templates.py::test_fv_spec_028_metadata_separation` — answer_key not in model_input; inference clues visible as approved input; oracle key separate

**Checkpoint**: US3 complete — group/split isolation enforced, previews rendered deterministically, metadata separated.

---

## Phase 6: User Story 4 — Review Records and Revision Protection (Priority: P4)

**Goal**: Require bilingual review, record classification review, protect frozen revisions.

**Independent Test**: Validator with `--strict --review-manifest` checks bilingual approvals, classification review completeness, and baseline revision integrity.

### Implementation for User Story 4

- [x] T042 [US4] Implement review manifest loading in `tools/closure_validator.py` — parse `--review-manifest` JSON, validate structure, match to suite revision/digest
- [x] T043 [US4] Implement bilingual review check in `tools/closure_validator.py` — for each multilingual E instance, require bilingual approval checking relation/direction/qualifiers/negation/answer identity/clue-freedom; use contract's normalization policy; reject missing/stale approvals under strict mode (FV-SPEC-029)
- [x] T044 [US4] Implement classification review check in `tools/closure_validator.py` — verify two-reader independent classification with labels, rationale, disagreements, adjudication against exact revisions; block strict handoff on unresolved disputes (FV-SPEC-030)
- [x] T045 [US4] Implement suite revision protection in `tools/closure_validator.py` — compare current suite against `--baseline-suite`; reject changed wording/binding/class/split/premise/label under unchanged revision; identical content passes (FV-SPEC-031)
- [x] T046 [US4] Wire `--strict` and `--baseline-suite` CLI options in `tools/validate_spec.py` for `closure-templates` scope
- [x] T047 [US4] Create review manifest fixture at `tests/fixtures/closure_templates/valid/minimal_review.json` — minimal valid review manifest for the demo suite
- [x] T048 [US4] Create baseline fixture at `tests/fixtures/closure_templates/baselines/closure_templates.yaml` — copy of minimal valid suite for revision comparison
- [x] T049 [US4] Write `tests/test_closure_templates.py::test_fv_spec_029_bilingual_review` — bilingual approval present passes strict; missing approval fails strict; stale approval (digest mismatch) fails
- [x] T050 [US4] Write `tests/test_closure_templates.py::test_fv_spec_030_classification_review` — complete classification passes; missing reader fails; unresolved dispute blocks handoff
- [x] T051 [US4] Write `tests/test_closure_templates.py::test_fv_spec_031_suite_revision` — identical baseline passes; changed template without revision bump fails; new revision passes

**Checkpoint**: US4 complete — review records checked, revision protection works.

---

## Phase 7: User Story 5 — Scoped CLI and Regression Fixtures (Priority: P5)

**Goal**: Complete CLI interface, ship regression fixtures, verify P0-1 compatibility.

**Independent Test**: Full test suite `tests/test_closure_templates.py` — all 18 hooks pass. P0-1 tests also pass.

### Implementation for User Story 5

- [x] T052 [US5] Implement report writer for closure-templates scope in `tools/closure_validator.py` — output scope, suite_path, suite_digest, coverage, balance, split_isolation, review_status, deferred_checks, diagnostics, summary per contracts/validator-interface.md
- [x] T053 [US5] Implement deferred check listing in `tools/closure_validator.py` — list P0-3 budget, P0-6 witness, and other out-of-scope checks as deferred in the report (FV-SPEC-032)
- [x] T054 [US5] Wire full diagnostic formatting with stable rule IDs (FV-SPEC-016–031) in `tools/closure_validator.py` — each diagnostic carries rule_id, template_id, file, json_pointer, message
- [x] T055 [US5] Create complete positive/negative regression fixture suite at `tests/fixtures/closure_templates/` — one fixture per FV-SPEC requirement boundary (016–032) with requirement-labelled filenames
- [x] T056 [US5] Write `tests/test_closure_templates.py::test_fv_spec_032_scoped_cli` — valid inputs exit 0 with report; missing suite exits 2; strict with open decisions exits 1; unsupported scope exits 2
- [x] T057 [US5] Write `tests/test_closure_templates.py::test_fv_spec_033_regression_fixtures` — offline fixture suite produces requirement-labelled results; P0-1 tests still pass
- [x] T058 [US5] Create semantic review template at `reports/p0-2-semantic-review.md` — structure for two-reader review of closure suite: reviewer IDs, template classifications, bilingual checks, disagreements, D-38–D-43 status
- [x] T059 [US5] Verify P0-1 compatibility: run `uv run pytest tests/test_contract_schema.py -v` to confirm all P0-1 tests pass unchanged

**Checkpoint**: US5 complete — full CLI works, all 18 test hooks pass, P0-1 compatible.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, deterministic output check

- [x] T060 [P] Add invocation documentation as docstring in `tools/closure_validator.py` — command signature, exit semantics, scope limitations, deferred checks
- [x] T061 Run full test suite: `uv run pytest tests/test_closure_templates.py tests/test_contract_schema.py -v` — all P0-1 + P0-2 hooks must pass
- [x] T062 Run quickstart.md validation — execute all 10 integration test scenarios from `specs/20260921-235511-closure-template-suite/quickstart.md`
- [x] T063 Verify deterministic rendering — render preview twice on same input, confirm identical output (excluding timestamps)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — schema and minimal fixtures must exist
- **User Story 2 (Phase 4)**: Depends on User Story 1 — structural validation core must exist before adding binding/coverage checks
- **User Story 3 (Phase 5)**: Depends on User Story 1 — structural validation must exist before group/split and preview
- **User Story 4 (Phase 6)**: Depends on User Story 1 — review and revision checks layer on top of structural validation
- **User Story 5 (Phase 7)**: Depends on User Stories 1–4 — CLI and regression fixtures exercise everything
- **Polish (Phase 8)**: Depends on all user stories being complete

### Within Each User Story

- Implementation tasks before tests — tests exercise the built validator
- Demonstration artifacts before negative fixtures — demos establish what "valid" looks like
- CLI wiring after validation logic is implemented

### Parallel Opportunities

Within US1 after the validator core (T008–T014):
- T015 and T016 (demo artifacts) can run in parallel
- T022 and T023 (schema-only tests) can run in parallel

Within US2:
- T031 and T032 (independent test classes) can run in parallel

US2 and US3 can potentially run in parallel after US1, since they add independent check types.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T007)
3. Complete Phase 3: User Story 1 (T008–T023)
4. **STOP and VALIDATE**: Run `uv run pytest tests/test_closure_templates.py -v` — 6 test hooks should pass (016–019, 022, 026)
5. Run the validator on demonstration suite — should exit 0

### Incremental Delivery

1. Setup + Foundational → YAML schema, minimal fixture validates
2. Add User Story 1 → Structural validation works, 6 tests green (MVP)
3. Add User Story 2 → Binding/coverage/balance checks, 10 tests green
4. Add User Story 3 → Group/split/preview, 13 tests green
5. Add User Story 4 → Review/revision, 16 tests green
6. Add User Story 5 → Full CLI + regression, 18 tests green
7. Polish → All quickstart scenarios pass, deterministic output verified

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Test names follow the FV-SPEC convention: `test_fv_spec_NNN_description`
- All 18 FV-SPEC requirements (016–033) map to exactly one test hook each
- US4 review (FV-SPEC-029/030) is partly a process requirement — automated tests check manifest structure, not scientific judgment
- D-38 through D-43 block `implemented` status but not development with provisional fixtures
- P0-2 validation logic lives in `tools/closure_validator.py` to keep `validate_spec.py` as the thin CLI dispatcher
