# Tasks: Base Model Selection and Pinning (P0-8)

**Input**: Design documents from `specs/20260926-101858-base-model-pinning/`
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/cli.md ✅ · quickstart.md ✅

**Tests**: Included — the spec and CLAUDE.md both require pytest tests for every validator check. The requirements note (FV-SPEC-P0-8 §6) lists a named test hook for each of the 7 requirements.

**Organization**: Organized by user story. The foundational phase creates the skeleton files (models.yaml, validator skeleton, CLI wiring, conftest paths). Each user story phase then implements one or two FV-SPEC checks plus the corresponding test.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no shared state)
- **[Story]**: Maps to user story from spec.md (US1–US5)

---

## Phase 1: Setup (Fixtures and Directory Structure)

**Purpose**: Create all test fixtures so that every later phase can be implemented with a red/green cycle from the start. No source code yet.

- [X] T001 Create fixture directory tree: `tests/fixtures/models_spec/{valid,invalid,model_dir,downstream}/`
- [X] T002 [P] Create `tests/fixtures/models_spec/model_dir/config.json` — `{"model_type": "test", "hidden_size": 64}` (synthetic weight-free model directory)
- [X] T003 [P] Create `tests/fixtures/models_spec/model_dir/tokenizer.json` — `{"version": "1.0", "model": "test"}` (synthetic tokenizer file)
- [X] T004 [P] Create `tests/fixtures/models_spec/valid/models_complete.yaml` — fully resolved entry for `blocks_0_2` (synthetic 40-char hex revisions, computed `sha256:` digests for the two files in `model_dir/`, `variant: base`, `dtype: float32`, `licence: apache-2.0`); `block_3_confirmation` with `status: pending` and `deadline: "2027-01-01"`
- [X] T005 [P] Create `tests/fixtures/models_spec/valid/models_staged_block3.yaml` — identical to T004 but `block_3_confirmation` omits `deadline` to test deadline-warning path separately
- [X] T006 [P] Create invalid fixtures (five files, one failure mode each):
  - `tests/fixtures/models_spec/invalid/missing_field.yaml` — `blocks_0_2` omits `licence`
  - `tests/fixtures/models_spec/invalid/mutable_revision.yaml` — `model_revision: "main"`
  - `tests/fixtures/models_spec/invalid/short_hash_revision.yaml` — `model_revision: "abc1234"` (7 chars)
  - `tests/fixtures/models_spec/invalid/placeholder_value.yaml` — `dtype: "DECISION_REQUIRED"`
  - `tests/fixtures/models_spec/invalid/pending_no_deadline.yaml` — `status: pending`, `deadline: null`
- [X] T007 [P] Create `tests/fixtures/models_spec/downstream/valid_exclusion_gate.json` and `tests/fixtures/models_spec/downstream/mismatched_gate.json` — `valid` carries the identity hash computed from `models_complete.yaml`; `mismatched` carries `sha256:` + 64 zeros

---

## Phase 2: Foundational (Skeleton Files — Blocking Prerequisites)

**Purpose**: Three skeleton files must exist before any user story phase can implement its feature: `models.yaml` (the spec artifact), `models_validator.py` (the validator module with load/report functions but stub checks), and the wiring in `validate_spec.py` and `conftest.py`.

**⚠️ CRITICAL**: No user story implementation can begin until T008–T011 are complete.

- [X] T008 Create `.factverify/spec/models.yaml` — YAML skeleton exactly as specified in `plan.md` Step 1: two roles (`blocks_0_2`, `block_3_confirmation`), all value fields set to `DECISION_REQUIRED`, `block_3_confirmation.status: pending`, `block_3_confirmation.deadline: null`, `files: {}`
- [X] T009 Create `tools/models_validator.py` skeleton with: `load_models_spec(spec_root) → dict` (raises `SystemExit` on missing/malformed file), `compute_identity_hash(role_entry) → str` (canonical JSON → sha256), `write_models_report(checks, ...) → dict` (follows report structure in `data-model.md`), and `validate_models_spec(spec_root, *, model_dir, access_profile_path, downstream_report_path, strict, report_path) → tuple[bool, dict]` entry point calling stub check functions that return `[]`; module follows the `access_profile_validator.py` pattern exactly
- [X] T010 Add `"models"` to `SUPPORTED_SCOPES` in `tools/validate_spec.py`; add `--model-dir` and `--downstream-report` CLI options to `main()`; add `_run_models_validation()` dispatcher function (following the `_run_access_profile_validation()` pattern); route `scope == "models"` in `main()`
- [X] T011 Update `tests/conftest.py` — add `MODELS_SPEC_PATH`, `MS_FIXTURES`, `MS_VALID`, `MS_INVALID`, `MS_MODEL_DIR`, `MS_DOWNSTREAM` path constants following the `AP_*` / `MG_*` pattern; no new pytest fixtures needed yet

**Checkpoint**: `python tools/validate_spec.py --scope models --spec-root .factverify/spec --report reports/p0-8-validation.json` runs without error and writes a report with all checks `pending` or `pass`.

---

## Phase 3: User Story 1 — Record a Verifiable Model Identity (Priority: P1) 🎯 MVP

**Goal**: A `models.yaml` with complete, correctly-formatted identity entries passes the validator; any missing field, placeholder value (strict mode), or mutable revision fails with a named diagnostic.

**Independent Test**: `uv run pytest tests/test_models_spec.py::test_fv_spec_089_identity tests/test_models_spec.py::test_fv_spec_090_immutable_revision tests/test_models_spec.py::test_fv_spec_093_identity_hash -v` — all green.

- [X] T012 [US1] Implement `check_fv_spec_089_identity(roles: dict, strict: bool) → list[dict]` in `tools/models_validator.py` — for each non-pending role, assert all required fields (`repo_id`, `model_revision`, `tokenizer_revision`, `variant`, `dtype`, `licence`) are non-null and non-empty; in strict mode also reject `"DECISION_REQUIRED"` values; pending roles produce no failures; missing `deadline` on a pending role emits a warning-level diagnostic
- [X] T013 [US1] Implement `check_fv_spec_090_immutable_revision(roles: dict) → list[dict]` in `tools/models_validator.py` — for each non-pending role, assert `model_revision` and `tokenizer_revision` match `/^[0-9a-f]{40}$/`; reject branches, tags, short hashes, null, or `"DECISION_REQUIRED"`
- [X] T014 [US1] Implement `check_fv_spec_093_identity_hash(roles: dict) → list[dict]` in `tools/models_validator.py` — for each fully resolved role (all five payload fields present and not `"DECISION_REQUIRED"`), call `compute_identity_hash()` and record the hash in the check's `diagnostics`-free result; roles with any unresolved field produce a `pending` result; verify the hash is deterministic by computing twice and asserting equality
- [X] T015 [P] [US1] Create `tests/test_models_spec.py` with `test_fv_spec_089_identity` — assert: complete entry → `[]`; missing `licence` → 1 diagnostic naming the field; `DECISION_REQUIRED` dtype in strict mode → 1 diagnostic; pending role with all fields `DECISION_REQUIRED` → `[]` (pending, not fail)
- [X] T016 [P] [US1] Add `test_fv_spec_090_immutable_revision` to `tests/test_models_spec.py` — assert: 40-char hex → `[]`; `"main"` → fail; 7-char short hash → fail; null → fail; pending role skipped → `[]`
- [X] T017 [P] [US1] Add `test_fv_spec_093_identity_hash` to `tests/test_models_spec.py` — assert: two calls with same inputs → identical hash strings; change `dtype` in payload → different hash; unresolved role → `pending` status in result; hash string starts with `"sha256:"`

**Checkpoint**: `uv run pytest tests/test_models_spec.py -k "089 or 090 or 093" -v` — all green; `python tools/validate_spec.py --scope models --spec-root .factverify/spec --report reports/p0-8-validation.json` exits 0 with FV-SPEC-089, FV-SPEC-090, FV-SPEC-093 all `pending` (since models.yaml still has DECISION_REQUIRED values).

---

## Phase 4: User Story 2 — Verify File Integrity Without Network Access (Priority: P2)

**Goal**: The digest check passes when a local model directory matches the recorded SHA-256s and fails (naming each file) on any mismatch, missing file, or extra file — with no network call. Returns `pending` when no directory is provided.

**Independent Test**: `uv run pytest tests/test_models_spec.py::test_fv_spec_091_file_digests -v` — green.

- [X] T018 [US2] Implement `check_fv_spec_091_digests(roles: dict, model_dir: Path | None, role_name: str) → list[dict]` in `tools/models_validator.py` — if `model_dir is None` or `files == {}`: return `[{"status": "pending", ...}]`; otherwise walk `files` dict, recompute `sha256:` for each path under `model_dir`, fail on mismatch; also fail on files listed in manifest but absent from disk, and on files present on disk but absent from manifest
- [X] T019 [P] [US2] Add `test_fv_spec_091_file_digests` to `tests/test_models_spec.py` — use `MS_MODEL_DIR` and digests from `models_complete.yaml`; assert: matching dir → `[]`; absent `model_dir` arg → pending result; modify one file in a temp copy → fail naming that file; delete one file → fail; add extra file → fail

**Checkpoint**: `uv run pytest tests/test_models_spec.py::test_fv_spec_091_file_digests -v` — green.

---

## Phase 5: User Story 5 — Ensure Declared Models Match the Access Profile (Priority: P2)

**Goal**: The cross-check reads `access_profile.md` and confirms every declared model can provide the channels the profile enables. Returns `pending` when the profile file is absent; fails when a model's licence forbids a required intervention.

**Independent Test**: `uv run pytest tests/test_models_spec.py::test_fv_spec_092_access_profile -v` — green.

- [X] T020 [US5] Implement `check_fv_spec_092_access_profile(roles: dict, profile_path: Path) → list[dict]` in `tools/models_validator.py` — if `profile_path` is absent: return `[{"status": "pending", ...}]`; load `access_profile.md` via `yaml.safe_load`; for each `interventions` entry requiring `fine_tune` or `export_checkpoint`, check that no declared model has `licence` containing `"api_only"` or set to `"DECISION_REQUIRED"` (in strict mode); pass if profile is A with no fine-tuning interventions (the current study default)
- [X] T021 [P] [US5] Add `test_fv_spec_092_access_profile` to `tests/test_models_spec.py` — assert: valid model + current `access_profile.md` (Profile A, no fine-tune interventions) → `[]`; absent profile path → pending; `licence: "api_only"` entry when profile has a fine-tune intervention in a synthetic fixture → fail naming the channel

**Checkpoint**: `uv run pytest tests/test_models_spec.py::test_fv_spec_092_access_profile -v` — green.

---

## Phase 6: User Story 3 — Confirm Downstream Evidence Is Bound to the Frozen Model (Priority: P3)

**Goal**: When a downstream exclusion-gate report exists, its `model_identity_hash` must match the hash computed from `models.yaml`; a mismatch fails; an absent report is `pending`.

**Independent Test**: `uv run pytest tests/test_models_spec.py::test_fv_spec_094_downstream_binding -v` — green.

- [X] T022 [US3] Implement `check_fv_spec_094_downstream(roles: dict, downstream_report: Path | None) → list[dict]` in `tools/models_validator.py` — if `downstream_report is None`: return `[{"status": "pending", "rule_name": "downstream_binding", ...}]`; parse JSON report, read `model_identity_hash`, compute expected hash from first resolved role in `roles` using `compute_identity_hash()`, compare; fail on mismatch naming both hashes; ledger and cache checks always `pending` at this phase (static `[{"status": "pending", ...}]` entries for `ledger` and `cache_manifests`)
- [X] T023 [P] [US3] Add `test_fv_spec_094_downstream_binding` to `tests/test_models_spec.py` — assert: `valid_exclusion_gate.json` with matching hash → `[]` failures; `mismatched_gate.json` → fail with diagnostic showing both hashes; `downstream_report=None` → pending; absent file path → pending

**Checkpoint**: `uv run pytest tests/test_models_spec.py::test_fv_spec_094_downstream_binding -v` — green.

---

## Phase 7: User Story 4 — Change a Model Only via the Amendment Protocol (Priority: P4)

**Goal**: After freeze, any change to `models.yaml` without a recorded amendment fails; a change with a valid amendment passes. Pre-freeze returns `pending`.

**Independent Test**: `uv run pytest tests/test_models_spec.py::test_fv_spec_095_amendment -v` — green.

- [X] T024 [US4] Implement `check_fv_spec_095_amendment(spec_root: Path) → list[dict]` in `tools/models_validator.py` — locate `CHECKSUMS.sha256` at `spec_root.parent / "CHECKSUMS.sha256"`; if absent: return `[{"status": "pending", ...}]`; compute `sha256:` of current `models.yaml`; extract stored digest from `CHECKSUMS.sha256` for the `models.yaml` line; if match: return `[]`; if mismatch: read `preregistration.md` and search for an amendment entry referencing `models.yaml` (a line or section containing `models.yaml` and `amendment`); if found: return `[]`; if not found: return one failure diagnostic
- [X] T025 [P] [US4] Add `test_fv_spec_095_amendment` to `tests/test_models_spec.py` using `tmp_path` fixtures — assert: no `CHECKSUMS.sha256` → pending; `CHECKSUMS.sha256` with matching digest → `[]`; changed `models.yaml` with no `CHECKSUMS.sha256` update + no amendment in `preregistration.md` → fail; changed `models.yaml` with amendment text in `preregistration.md` → `[]`

**Checkpoint**: `uv run pytest tests/test_models_spec.py -v` — all 7 test functions green (28+ individual assertions).

---

## Final Phase: Polish and Integration

**Purpose**: Wire all checks into the entry point, add the eighth artifact to the freeze list, run the end-to-end CLI, and confirm the full test suite is green.

- [X] T026 Update `validate_models_spec()` in `tools/models_validator.py` to call all seven check functions in order (089 → 090 → 091 → 092 → 093 → 094 → 095), collect results into `checks` list, and pass to `write_models_report()`; ensure `overall` is `"pass"` when all checks are `pass` or `pending`, `"fail"` otherwise
- [X] T027 Update `tools/freeze.py` — add `"models.yaml"` to the `SPEC_ARTIFACTS` list (making it 8 entries); update the docstring comment in `_check_artifacts_present()` from "seven" to "eight spec artifacts"; update any test fixture for the freeze validator that asserts a count of 7
- [X] T028 Update `tools/preregistration_validator.py` (or whichever module contains the V01 required-file check) to include `models.yaml` in the required-file list — this is the eighth-artifact reconciliation flagged in FV-SPEC-087 and the spec assumptions
- [X] T029 Run end-to-end validation: `python tools/validate_spec.py --scope models --spec-root .factverify/spec --report reports/p0-8-validation.json` — confirm exit 0, report written, all checks `pending` (correct pre-decision state)
- [X] T030 Run `uv run pytest tests/test_models_spec.py -v` — confirm all tests green, no warnings
- [X] T031 [P] Run `uv run pytest tests/test_preregistration_freeze.py -v` — confirm freeze tests still pass after adding the eighth artifact (regression check)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; all T001–T007 are parallelizable after T001 creates the directory
- **Phase 2 (Foundational)**: Depends on Phase 1 completion — **BLOCKS** all user story phases
- **Phase 3 (US1, P1)**: Depends on Phase 2 — highest priority, implement first
- **Phase 4 (US2, P2) and Phase 5 (US5, P2)**: Both depend on Phase 2; independent of each other — can run in parallel
- **Phase 6 (US3, P3)**: Depends on Phase 2 + `compute_identity_hash()` from Phase 3 (T014)
- **Phase 7 (US4, P4)**: Depends on Phase 2 only; can start after Foundational
- **Final Phase**: Depends on all user story phases complete

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (T009 — validator skeleton)
- **US2 (P2)**: Depends on Foundational; independent of US1
- **US5 (P2)**: Depends on Foundational; independent of US1 and US2
- **US3 (P3)**: Depends on `compute_identity_hash()` from US1 (T014) — must run after US1
- **US4 (P4)**: Depends on Foundational; independent of all other stories

### Within Each Phase

- Implementation task before its test task (tests are written against the implemented function)
- `compute_identity_hash()` (T014 part of skeleton in T009) before `check_fv_spec_093_identity_hash()` (T014) and `check_fv_spec_094_downstream()` (T022)
- `validate_models_spec()` wiring (T026) must be last validator change before end-to-end run (T029)

### Parallel Opportunities

- All Phase 1 fixture tasks (T002–T007) after T001 creates directories
- US2 and US5 implementation + test tasks (T018–T021)
- US4 implementation + test (T024–T025) alongside US3 (T022–T023)
- Final phase: T030 and T031 run in parallel after T026–T029

---

## Parallel Example: Phase 1 (Setup)

```bash
# After T001 (mkdir), launch all fixture creation tasks in parallel:
Task T002: "Create tests/fixtures/models_spec/model_dir/config.json"
Task T003: "Create tests/fixtures/models_spec/model_dir/tokenizer.json"
Task T004: "Create tests/fixtures/models_spec/valid/models_complete.yaml"
Task T005: "Create tests/fixtures/models_spec/valid/models_staged_block3.yaml"
Task T006: "Create all five invalid fixture YAML files"
Task T007: "Create downstream exclusion gate JSON fixtures"
```

## Parallel Example: Phase 4 + Phase 5 (both P2)

```bash
# Run simultaneously after Phase 2 is complete:
Task T018: "Implement check_fv_spec_091_digests in tools/models_validator.py"
Task T020: "Implement check_fv_spec_092_access_profile in tools/models_validator.py"
# Note: different functions in the same file — coordinate to avoid conflicts
```

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Complete Phase 1: Fixtures
2. Complete Phase 2: Foundational skeletons
3. Complete Phase 3: US1 (FV-SPEC-089, 090, 093 + 3 tests)
4. **STOP and VALIDATE**: `uv run pytest tests/test_models_spec.py -k "089 or 090 or 093" -v` all green
5. Delivers: A validator that correctly enforces model-identity completeness and immutable revisions

### Incremental Delivery

1. Phases 1–3 → US1 green → MVP: identity pinning works
2. Phase 4 → US2 green → offline digest integrity works
3. Phase 5 → US5 green → access-profile compatibility check works
4. Phase 6 → US3 green → downstream binding check works
5. Phase 7 → US4 green → amendment protocol enforced
6. Final Phase → all tests green, freeze list updated, eighth-artifact reconciled

---

## Notes

- All 7 test functions in `tests/test_models_spec.py` map 1:1 to FV-SPEC-089 through FV-SPEC-095 (the requirement note's verification matrix in §6)
- `compute_identity_hash()` is used by both FV-SPEC-093 (definition) and FV-SPEC-094 (downstream binding) — implement it once in the skeleton (T009) and reuse
- The four open study decisions (D-46, D-47, D-48, D-49) affect which values fill `models.yaml`, not the validator's structure — the validator correctly handles `DECISION_REQUIRED` as `pending` until the researcher fills them in
- Do not hardcode any example model name, revision, or repo path — always read from `models.yaml` or fixture files
- The `tests/fixtures/models_spec/valid/models_complete.yaml` `files` dict must contain the actual SHA-256 digests of `model_dir/config.json` and `model_dir/tokenizer.json` — compute these at fixture-creation time (T004)
