# Tasks: P0-1 Atomic-Fact Contract Schema

**Input**: Design documents from `/specs/20260921-211249-fact-contract-schema/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup

**Purpose**: Project initialization and directory structure

- [x] T001 Create directory structure: `.factverify/spec/`, `.factverify/contracts/`, `tools/`, `tests/fixtures/valid/`, `tests/fixtures/invalid/`, `tests/fixtures/baselines/`, `reports/`
- [x] T002 Add `jsonschema`, `referencing`, `click`, and `pytest` to `pyproject.toml` dependencies via `uv add`
- [x] T003 [P] Ensure `.factverify/` is not excluded in `.gitignore`; add explicit include if needed
- [x] T004 [P] Create `tests/conftest.py` with shared path constants for spec root, contracts dir, and fixtures dir

**Checkpoint**: Dependencies installed, directory layout matches plan.md, `.factverify/` is tracked.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Schema artifact and minimal valid fixture — everything else depends on these

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Write `fact_contract.schema.json` to `.factverify/spec/` from the source-guide schema (P0-1 §2.5.4) with all `$defs`, `required` fields, `additionalProperties: false` at every object, and four `contains` clauses for locality buckets
- [x] T006 Create a minimal valid contract fixture at `tests/fixtures/valid/minimal.json` — required fields only, no optional metadata, one entry per locality bucket, forward + inverse directions
- [x] T007 Verify the schema validates against its own Draft 2020-12 meta-schema (sanity check before building the validator)

**Checkpoint**: Schema published, minimal fixture passes `jsonschema` validation from Python REPL.

---

## Phase 3: User Story 1 - Structural Validation (Priority: P1) MVP

**Goal**: A researcher runs one command and gets pass/fail with actionable diagnostics for every contract.

**Independent Test**: `uv run python tools/validate_spec.py --scope fact-contract --spec-root .factverify/spec --contracts .factverify/contracts --report reports/p0-1-validation.json` exits 0 on valid contracts and nonzero on invalid ones.

### Implementation for User Story 1

- [x] T008 [US1] Implement schema loading and meta-schema check in `tools/validate_spec.py` — load schema from `--spec-root`, validate it against Draft 2020-12 meta-schema, fail closed if missing or malformed
- [x] T009 [US1] Implement contract directory scanning in `tools/validate_spec.py` — enumerate `*.json` files in `--contracts`, fail closed if directory is empty or missing
- [x] T010 [US1] Implement per-contract JSON Schema validation in `tools/validate_spec.py` — validate each contract against the loaded schema, collect all errors with JSON pointers
- [x] T011 [US1] Implement supplemental identity consistency check in `tools/validate_spec.py` — extract Q/P components from `fact_id`, `contract_id`, and `triple.{subject,relation,object}.id`; reject mismatches (FV-SPEC-005)
- [x] T012 [US1] Implement supplemental direction-role consistency check in `tools/validate_spec.py` — enforce forward→subject/object, inverse→object/subject, verification→triple/truth_value (FV-SPEC-007)
- [x] T013 [US1] Implement diagnostic formatting in `tools/validate_spec.py` — each diagnostic carries a stable rule ID (FV-SPEC-NNN), file path, JSON pointer, and human-readable message
- [x] T014 [US1] Implement JSON report writer in `tools/validate_spec.py` — output `scope`, `schema_path`, `schema_digest`, `checked_files`, `diagnostics`, `summary` to `--report` path
- [x] T015 [US1] Implement `click` CLI entry point in `tools/validate_spec.py` — `--scope fact-contract`, `--spec-root`, `--contracts`, `--report`, exit codes 0/1/2 per interface contract
- [x] T016 [US1] Write Hà Nội demonstration contract at `.factverify/contracts/factverify-contract-wd-Q1858-P1376-Q881-v1.json` — real-entity illustration with forward/inverse/verification, 2+ items per locality bucket, Vietnamese aliases, labelled as pretrained (FV-SPEC-012)
- [x] T017 [US1] Write fictional demonstration contract at `.factverify/contracts/factverify-contract-invented_scientist_alma_mater-v1.json` — controlled-fictional contract of a different relation type, project-local IDs, forward/inverse/verification, 2+ items per locality bucket (FV-SPEC-012)
- [x] T018 [US1] Create negative test fixtures in `tests/fixtures/invalid/` — missing required fields (one per semantic-core field), undeclared properties (root and nested), malformed IDs, reversed direction roles, single-bucket neighbourhood, empty clue boundary fields, invalid optional metadata enums
- [x] T019 [US1] Write `tests/test_contract_schema.py::test_fv_spec_001_schema_artifact` — verify schema exists and passes meta-schema validation
- [x] T020 [US1] Write `tests/test_contract_schema.py::test_fv_spec_002_required_core` — remove each required field individually from minimal fixture, assert validation fails each time
- [x] T021 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_003_unknown_properties` — add undeclared properties at root and each nested object, assert rejection
- [x] T022 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_004_identifier_syntax` — valid and malformed IDs for each role, assert correct acceptance/rejection
- [x] T023 [US1] Write `tests/test_contract_schema.py::test_fv_spec_005_canonical_identity` — mismatched Q/P IDs, disagreeing fact_id/contract_id, inverse direction preserving identity
- [x] T024 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_006_aliases` — empty/missing aliases, invalid enum, malformed language, missing argument_order on relation alias, Unicode preservation
- [x] T025 [US1] Write `tests/test_contract_schema.py::test_fv_spec_007_direction_roles` — all valid combinations plus reversed/missing roles
- [x] T026 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_008_locality_coverage` — missing bucket, four-of-one-bucket, unapproved bucket value
- [x] T027 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_009_clue_boundary` — missing fields, empty rules, undeclared policy enum
- [x] T028 [P] [US1] Write `tests/test_contract_schema.py::test_fv_spec_010_optional_metadata` — valid without optional metadata, invalid optional enum/type, null freeze fields remain valid
- [x] T029 [US1] Write `tests/test_contract_schema.py::test_fv_spec_011_cli_contract` — valid run exits 0 with correct report, missing schema exits nonzero, empty contracts exits nonzero, unsupported scope exits nonzero, deterministic output
- [x] T030 [US1] Write `tests/test_contract_schema.py::test_fv_spec_012_demonstration_contracts` — both demo contracts pass validation, each has forward/inverse/verification, 2+ items per bucket
- [x] T031 [US1] Write `tests/test_contract_schema.py::test_fv_spec_015_spec_artifact_inclusion` — verify schema exists at `.factverify/spec/fact_contract.schema.json` from clean checkout, verify `.factverify/` is not gitignored

**Checkpoint**: User Story 1 is fully functional — validator CLI works end-to-end, both demonstration contracts pass, all FV-SPEC-001–012 and FV-SPEC-015 tests pass.

---

## Phase 4: User Story 2 - Revision Detection (Priority: P2)

**Goal**: Detect silent edits to frozen contracts by comparing against a baseline.

**Independent Test**: Supply `--baseline-contracts` with a prior snapshot. Change an alias without bumping version. Validator rejects the change.

### Implementation for User Story 2

- [x] T032 [US2] Implement baseline loading in `tools/validate_spec.py` — parse `--baseline-contracts` directory, validate baseline contracts first, match by `contract_id` fact key
- [x] T033 [US2] Implement revision comparison in `tools/validate_spec.py` — compare parsed JSON (excluding `freeze_policy.frozen_at` and `freeze_policy.content_sha256`), detect semantic changes, check version increment, reject changed triple with unchanged fact_id
- [x] T034 [US2] Implement revision check reporting in `tools/validate_spec.py` — `revision_check` field in report: `not_requested` when no baseline, structured result with changed fields when baseline supplied
- [x] T035 [US2] Create baseline fixtures in `tests/fixtures/baselines/` — copy of minimal valid contract for revision comparison tests
- [x] T036 [US2] Write `tests/test_contract_schema.py::test_fv_spec_013_frozen_revision` — identical passes, alias change without version bump fails, version bump passes, changed triple with old fact_id fails, no baseline returns `not_requested`

**Checkpoint**: User Story 2 is fully functional — revision detection works end-to-end, FV-SPEC-013 test passes.

---

## Phase 5: User Story 3 - Semantic Review (Priority: P3)

**Goal**: Record independent two-reader semantic review of demonstration contracts.

**Independent Test**: `reports/p0-1-semantic-review.md` exists with two reader classifications and adjudication.

### Implementation for User Story 3

- [x] T037 [US3] Create review template at `reports/p0-1-semantic-review.md` — structure for two-reader review: reviewer IDs, contract revisions, classification items from the P0-1 guide exercise, disagreement/adjudication fields, decision resolution status (D-38/D-39/D-40)
- [x] T038 [US3] Write `tests/test_contract_schema.py::test_fv_spec_014_semantic_review_manifest` — verify review file exists, contains required sections (reviewer IDs, classifications, adjudications), references exact contract revisions, flags unresolved D-38/D-39/D-40

**Checkpoint**: Review template is in place. Actual two-reader review is a manual process — test verifies the manifest structure only.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, final validation, and cleanup

- [x] T039 [P] Add invocation documentation to repository — command signature, exit semantics, format policy, scope limitations (could be a section in an existing doc or a docstring in `tools/validate_spec.py`)
- [x] T040 [P] Run full test suite: `uv run pytest tests/test_contract_schema.py -v` — all 15 hooks must pass
- [x] T041 Run quickstart.md validation — execute all 5 integration test scenarios from `specs/20260921-211249-fact-contract-schema/quickstart.md` and verify expected outcomes
- [x] T042 Verify deterministic output — run validator twice on same input, confirm identical ordered diagnostics (excluding timestamps)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — the schema and minimal fixture must exist
- **User Story 2 (Phase 4)**: Depends on User Story 1 — the validator core must exist before adding revision comparison
- **User Story 3 (Phase 5)**: Depends on User Story 1 — demonstration contracts must exist for review
- **Polish (Phase 6)**: Depends on all user stories being complete

### Within Each User Story

- Validator implementation (T008–T015) before demonstration contracts (T016–T017)
- Demonstration contracts before negative fixtures (T018) — use demo contracts as reference for what "valid" looks like
- Implementation before tests (T019–T031) — tests exercise the built validator
- US2 baseline loading (T032) depends on US1 validator core
- US3 review template (T037) depends on US1 demonstration contracts

### Parallel Opportunities

Within User Story 1, after the validator core (T008–T015) is built:
- T016 and T017 (demonstration contracts) can run in parallel
- T021, T022, T024, T026, T027, T028 (schema-only tests) can run in parallel
- T023, T025 (supplemental-check tests) depend on T011, T012

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T004)
2. Complete Phase 2: Foundational (T005–T007)
3. Complete Phase 3: User Story 1 (T008–T031)
4. **STOP and VALIDATE**: Run `uv run pytest tests/test_contract_schema.py -v` — 13 tests should pass
5. Run the validator on demonstration contracts — should exit 0

### Incremental Delivery

1. Setup + Foundational → Schema published, minimal fixture validates
2. Add User Story 1 → Validator CLI works, demo contracts pass, 13 tests green (MVP)
3. Add User Story 2 → Revision detection works, 14 tests green
4. Add User Story 3 → Review template in place, 15 tests green
5. Polish → All quickstart scenarios pass, deterministic output verified

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Test names follow the FV-SPEC convention: `test_fv_spec_NNN_description`
- All 15 FV-SPEC requirements map to exactly one test hook each
- US3 (semantic review) is a process requirement — the automated test checks manifest structure, not scientific judgment
- D-38/D-39/D-40 block handoff (US3 completion) but not structural implementation (US1/US2)
