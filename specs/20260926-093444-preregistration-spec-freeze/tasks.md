# Tasks: P0-7 Pre-registration and Spec Freeze

**Input**: Design documents from `specs/20260926-093444-preregistration-spec-freeze/`  
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

**Tests**: Included — FV-SPEC-078 through FV-SPEC-088 each declare explicit test hooks in `tests/test_preregistration_freeze.py`.

**Organization**: Foundational phase wires the new scope and creates skeletons; each user story then delivers one check function + fixtures + test hook independently.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Maps to user story from spec.md (US1–US11)

---

## Phase 1: Setup (Directories and Spec Artifact Skeletons)

**Purpose**: Create the directory scaffolding and skeleton input files before any validation or freeze logic is written.

- [x] T001 Create fixture directories `tests/fixtures/preregistration/valid/` and `tests/fixtures/preregistration/invalid/`
- [x] T002 [P] Create skeleton `.factverify/spec/preregistration.md` with YAML frontmatter (`status: draft`, all required fields empty/placeholder) and the 11 required section headings
- [x] T003 [P] Create skeleton `.factverify/decisions/register.yaml` listing all D-IDs from FV-SPEC P0-7 §5 with `status: open`
- [x] T004 [P] Create skeleton `.factverify/milestones/milestones.yaml` with the three milestone entries (`spec-v1`, `thresholds-v1`, `protocol-v1`), each with a `staged_rule` block
- [x] T005 [P] Create skeleton `.factverify/exposure/exposure_record.md` with YAML frontmatter (`status: draft`, `registration_status: local-only`, empty `access_events: []`) and a brief body

**Checkpoint**: All required input file paths exist; none contain normative values yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire the new `preregistration` scope into `validate_spec.py`, extend `conftest.py`, and create skeletons for the three new source files. All Phase 3+ work depends on this.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [x] T006 Add `"preregistration"` to `SUPPORTED_SCOPES` and add four new CLI options (`--preregistration`, `--decisions-register`, `--exposure-record`, `--milestones`) with path-defaulting defaults in `tools/validate_spec.py`; add `_run_preregistration_validation()` stub (exits 0) and wire it into the scope dispatch chain
- [x] T007 [P] Add P0-7 path constants (`PREREGISTRATION_MD`, `DECISIONS_DIR`, `MILESTONES_DIR`, `EXPOSURE_DIR`, `PR_VALID`, `PR_INVALID`, `P0_7_REPORT`) and corresponding `@pytest.fixture(scope="session")` entries to `tests/conftest.py`
- [x] T008 [P] Create `tools/preregistration_validator.py` with: `_NO_MODEL_CALLS = True`; `load_preregistration(path)` and `load_yaml_artifact(path)` loaders; 11 stub check functions (`check_fv_spec_078_artifact` through `check_fv_spec_088_cli`) each returning `[]`; and a `validate_preregistration()` orchestrator that calls all stubs
- [x] T009 [P] Create `tools/freeze.py` with: `click` CLI accepting `--spec-root`, `--tag`, `--dry-run` (default), `--execute`, `--verify`, `--report`, `--decisions-register`, `--exposure-record`, `--milestones`; mutual exclusion enforced at startup; all three modes stub out with a TODO and exit 0 for now
- [x] T010 Create `tests/test_preregistration_freeze.py` with imports from `tools.preregistration_validator` and `tests.conftest`; 11 stub test functions (`test_fv_spec_078_artifact` through `test_fv_spec_088_cli`) each calling `pytest.skip("not yet implemented")`
- [x] T011 Verify `pytest tests/test_preregistration_freeze.py` runs (all 11 skip), and `python tools/validate_spec.py --scope preregistration --spec-root .factverify/spec --report reports/p0-7-validation.json` exits 0

**Checkpoint**: Foundation ready — all 11 user stories can now be implemented in parallel.

---

## Phase 3: User Story 1 — Author the Study Commitment Document (Priority: P1) 🎯

**Goal**: `check_fv_spec_078_artifact` validates that `preregistration.md` contains all 11 required sections, each with an artifact reference, and that no authoritative value appears in more than one file.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_078_artifact` passes all three scenarios.

- [x] T012 [P] [US1] Write `tests/fixtures/preregistration/valid/preregistration_complete.md` — all 11 required section headings each containing a `ref:` citation to an upstream artifact; no inline α or budget values
- [x] T013 [P] [US1] Write `tests/fixtures/preregistration/invalid/preregistration_missing_section.md` — identical to the valid fixture but with the `## Stopping Rules` heading removed
- [x] T014 [P] [US1] Write `tests/fixtures/preregistration/invalid/preregistration_duplicate_alpha.md` — valid fixture plus an inline `alpha: 0.05` assertion that duplicates the value already in `margins.yaml`
- [x] T015 [US1] Implement `check_fv_spec_078_artifact(frontmatter, body, spec_root)` in `tools/preregistration_validator.py`: verify all 11 section headings present; verify each section contains at least one artifact reference (`ref:` or `[[...]]`); scan across all spec files for the same normative key appearing in two locations and return a conflict diagnostic if found
- [x] T016 [US1] Implement `test_fv_spec_078_artifact` (3 scenarios) in `tests/test_preregistration_freeze.py`: complete fixture passes; missing-section fixture fails with section named; duplicate-α fixture fails with conflict diagnostic naming both files
- [x] T017 [US1] Fill in `.factverify/spec/preregistration.md` with the complete study commitment content (all sections, artifact refs, status updated to `needs-review`); cross-check against `margins.yaml`, `attacks.yaml`, `witness_rule.md` to ensure no values are duplicated inline
- [x] T018 [US1] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_078_artifact -v` and confirm all three scenarios pass

**Checkpoint**: US1 independently green; `preregistration.md` contains a complete study commitment.

---

## Phase 4: User Story 2 — Record Prior Exposure and Registration Status (Priority: P1)

**Goal**: `check_fv_spec_079_exposure` validates the exposure record: required frontmatter fields present; no contradiction between access events and registration claims.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_079_exposure` passes all three scenarios.

- [x] T019 [P] [US2] Write `tests/fixtures/preregistration/valid/exposure_record_valid.md` — `status: reviewed`, `registration_status: local-only`, two `access_events` entries (development scope, pilot scope) with empty `outcomes_inspected`
- [x] T020 [P] [US2] Write `tests/fixtures/preregistration/invalid/exposure_contradiction.md` — identical to valid fixture but with an `access_events` entry that has `scope: final_test` and a non-empty `outcomes_inspected` list
- [x] T021 [P] [US2] Write `tests/fixtures/preregistration/invalid/exposure_unregistered_claim.md` — `registration_status: externally-archived` with no `archive_evidence` field
- [x] T022 [US2] Implement `check_fv_spec_079_exposure(exposure_fm)` in `tools/preregistration_validator.py`: check all required frontmatter fields present; detect final-test access with non-empty `outcomes_inspected`; detect `externally-archived` without `archive_evidence`; return FV-SPEC-079 diagnostics
- [x] T023 [US2] Implement `test_fv_spec_079_exposure` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T024 [US2] Fill in `.factverify/exposure/exposure_record.md` to `status: needs-review` with accurate access history for the project so far
- [x] T025 [US2] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_079_exposure -v`

**Checkpoint**: US2 independently green.

---

## Phase 5: User Story 3 — Define Staged Freeze Milestones (Priority: P1)

**Goal**: `check_fv_spec_080_milestones` validates the milestone manifest: all three milestones present; each has either a `git_tag` or a complete `staged_rule`.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_080_milestones` passes all three scenarios.

- [x] T026 [P] [US3] Write `tests/fixtures/preregistration/valid/milestones_valid.yaml` — all three milestones with complete `staged_rule` blocks (no `git_tag` yet); all sub-fields non-empty
- [x] T027 [P] [US3] Write `tests/fixtures/preregistration/invalid/milestones_tbd.yaml` — `thresholds-v1` entry has `staged_rule: null` and `git_tag: null`
- [x] T028 [P] [US3] Write `tests/fixtures/preregistration/invalid/milestones_missing.yaml` — omit the `protocol-v1` entry entirely
- [x] T029 [US3] Implement `check_fv_spec_080_milestones(milestones)` in `tools/preregistration_validator.py`: verify all three names present; for each entry verify either `git_tag` is non-null or `staged_rule` has all three sub-fields non-empty and non-TBD; return FV-SPEC-080 diagnostics
- [x] T030 [US3] Implement `test_fv_spec_080_milestones` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T031 [US3] Populate `.factverify/milestones/milestones.yaml` with the final milestone definitions (staged rules for `thresholds-v1` and `protocol-v1`; `spec-v1` can note its own gate)
- [x] T032 [US3] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_080_milestones -v`

**Checkpoint**: US3 independently green.

---

## Phase 6: User Story 4 — Validate Split and Source Provenance (Priority: P1)

**Goal**: `check_fv_spec_081_splits` validates that split manifests record all required isolation dimensions and that unmaterialised splits are reported pending, not verified.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_081_splits` passes all three scenarios.

- [x] T033 [P] [US4] Write `tests/fixtures/preregistration/valid/splits_valid.yaml` — construction/calibration/final manifests each recording entity/fact, reference-seed, template-group, and control-implementation isolation fields
- [x] T034 [P] [US4] Write `tests/fixtures/preregistration/invalid/splits_tofu_no_mapping.yaml` — a TOFU-derived record with `atomic_fact_mapping: null`
- [x] T035 [P] [US4] Write `tests/fixtures/preregistration/invalid/splits_unmaterialised.yaml` — final split with `materialised: false` and no `gate` field
- [x] T036 [US4] Implement `check_fv_spec_081_splits(splits_manifest)` in `tools/preregistration_validator.py`: check all four isolation dimensions recorded per manifest; detect TOFU records missing `atomic_fact_mapping`; detect unmaterialised splits missing a `gate` reference; produce "pending (gate N)" status for valid staged splits; return FV-SPEC-081 diagnostics
- [x] T037 [US4] Implement `test_fv_spec_081_splits` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T038 [US4] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_081_splits -v`

**Checkpoint**: US4 independently green.

---

## Phase 7: User Story 5 — Specify Primary Analysis and Reporting Contract (Priority: P1)

**Goal**: `check_fv_spec_082_analysis` cross-checks that FRR cap, budgets, weighting, FCR, and cost reporting fields agree across P0-3 (`attacks.yaml`), P0-5 (`margins.yaml`), P0-6 (`witness_rule.md`), and `preregistration.md`.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_082_analysis` passes all three scenarios.

- [x] T039 [P] [US5] Write `tests/fixtures/preregistration/valid/analysis_consistent/` — minimal copies of the four relevant artifact sections with all cross-referenced fields agreeing
- [x] T040 [P] [US5] Write `tests/fixtures/preregistration/invalid/analysis_frr_conflict/` — same fixture set but with the FRR cap declared differently in `margins.yaml` vs an inline assertion in `preregistration.md`
- [x] T041 [P] [US5] Write `tests/fixtures/preregistration/invalid/analysis_missing_denominator/` — `preregistration.md` fixture with one baseline denominator field empty
- [x] T042 [US5] Implement `check_fv_spec_082_analysis(prereg_fm, prereg_body, spec_root)` in `tools/preregistration_validator.py`: load normative values from `margins.yaml`, `attacks.yaml`, `witness_rule.md`; compare against any values referenced in `preregistration.md`; detect conflicts (same key, different value) and missing denominators; return FV-SPEC-082 diagnostics naming source file and field
- [x] T043 [US5] Implement `test_fv_spec_082_analysis` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T044 [US5] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_082_analysis -v`

**Checkpoint**: US5 independently green. All five P1 validator checks are now implemented.

---

## Phase 8: User Story 9 — Verify Immutable Snapshot Integrity (Priority: P1)

**Goal**: `freeze.py` can compute and write `CHECKSUMS.sha256` (non-self-referential); `freeze.py --verify` detects tampered bytes and receipt/tag mismatches.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_086_integrity` passes all three scenarios.

- [x] T045 [US9] Implement `compute_checksums(spec_root)` and `write_checksums(spec_root, output_path)` in `tools/freeze.py`: enumerate all seven spec artifacts; compute SHA-256 for each; write in shasum-compatible format excluding `CHECKSUMS.sha256` itself
- [x] T046 [US9] Implement `verify_checksums(spec_root, checksums_path)` in `tools/freeze.py`: re-read `CHECKSUMS.sha256`; recompute each artifact's SHA-256; return list of mismatched paths
- [x] T047 [US9] Implement `compute_contract_digest(preregistration_path)` in `tools/freeze.py`: serialize the canonical payload (all frontmatter fields except `digest`, all section headings+bodies) as deterministic JSON with sorted keys; return `"sha256:<hex>"`
- [x] T048 [US9] Implement `check_fv_spec_086_integrity(spec_root, checksums_path)` in `tools/preregistration_validator.py`: call `verify_checksums`; check receipt `tag_target_commit` matches `git rev-parse <tag>^{}`; return FV-SPEC-086 diagnostics
- [x] T049 [US9] Write test fixtures for US9: `tests/fixtures/preregistration/valid/snapshot_valid/` (correct CHECKSUMS + 7 spec artifact stubs); `tests/fixtures/preregistration/invalid/snapshot_tampered/` (one artifact byte changed); `tests/fixtures/preregistration/invalid/snapshot_stale_receipt/` (receipt with wrong commit SHA)
- [x] T050 [US9] Implement `test_fv_spec_086_integrity` (3 scenarios using `tmp_path` git repos) in `tests/test_preregistration_freeze.py`
- [x] T051 [US9] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_086_integrity -v`

**Checkpoint**: US9 independently green; checksum write and verify logic confirmed working.

---

## Phase 9: User Story 10 — Gate the Freeze Operation (Priority: P1)

**Goal**: `freeze.py --dry-run` runs all 8 gate checks without writing; `freeze.py --execute` writes CHECKSUMS, commits, tags, writes receipt; both refuse on gate failure; tag overwrite is refused.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_087_freeze` passes all three scenarios.

- [x] T052 [US10] Implement all 8 gate check functions in `tools/freeze.py`: `_check_artifacts_present`, `_check_preregistration_valid` (calls validate_spec as subprocess), `_check_prior_specs` (regression check), `_check_decisions_resolved`, `_check_exposure_reviewed`, `_check_milestones_complete`, `_check_no_existing_tag`, `_check_no_leaked_files`
- [x] T053 [US10] Implement `run_gate_checks(spec_root, tag, decisions_path, exposure_path, milestones_path)` in `tools/freeze.py`: run all 8 checks in sequence; collect diagnostics; return `(all_passed: bool, results: list[dict])`
- [x] T054 [US10] Implement `--dry-run` mode body in `tools/freeze.py`: call `run_gate_checks`; write JSON report if `--report` provided; print summary; exit 0 if all passed, 1 if any failed; make no filesystem or git writes
- [x] T055 [US10] Implement `--execute` mode body in `tools/freeze.py`: call `run_gate_checks` (fail-fast on any failure); write `CHECKSUMS.sha256`; `git add .factverify/CHECKSUMS.sha256`; commit; create annotated tag; write `reports/spec-v1-freeze-receipt.json` with `git rev-parse <tag>^{}`
- [x] T056 [US10] Write gate test fixture repos: `tests/fixtures/preregistration/valid/freeze_allpass/` (git-init'd tmp dir with all gates green); `tests/fixtures/preregistration/invalid/freeze_open_decision/` (one D-ID has `status: open`); `tests/fixtures/preregistration/invalid/freeze_existing_tag/` (a `spec-v1` tag already present)
- [x] T057 [US10] Implement `test_fv_spec_087_freeze` (3 scenarios using `tmp_path` fixture repos) in `tests/test_preregistration_freeze.py`
- [x] T058 [US10] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_087_freeze -v`

**Checkpoint**: US10 independently green; freeze execute/dry-run logic complete. All P1 user stories done.

---

## Phase 10: User Story 6 — Declare Stopping and Deviation Recovery (Priority: P2)

**Goal**: `check_fv_spec_083_deviations` verifies all 8 deviation event categories are covered and that "patch and resume" is not accepted as a broken-final-pass recovery.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_083_deviations` passes all three scenarios.

- [x] T059 [P] [US6] Write `tests/fixtures/preregistration/valid/preregistration_deviations_valid.md` — section `## Stopping Rules` enumerating all 8 categories with named recovery procedures; final-pass rule specifies full re-run on fresh split
- [x] T060 [P] [US6] Write `tests/fixtures/preregistration/invalid/preregistration_missing_category.md` — `## Stopping Rules` section missing the `budget_overrun` category
- [x] T061 [P] [US6] Write `tests/fixtures/preregistration/invalid/preregistration_patch_and_resume.md` — `## Stopping Rules` section declaring "patch and resume" for broken final pass
- [x] T062 [US6] Implement `check_fv_spec_083_deviations(frontmatter, body)` in `tools/preregistration_validator.py`: scan `## Stopping Rules` section for all 8 required categories; detect "patch and resume" or equivalent phrasing for broken-pass rule; return FV-SPEC-083 diagnostics
- [x] T063 [US6] Implement `test_fv_spec_083_deviations` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T064 [US6] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_083_deviations -v`

**Checkpoint**: US6 independently green.

---

## Phase 11: User Story 7 — Constrain and Audit Policy Amendments (Priority: P2)

**Goal**: `check_fv_spec_084_amendments` validates each `amendment_log` entry has all required fields, no `post_hoc: true`, and a `deadline_before_final_access` date.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_084_amendments` passes all three scenarios.

- [x] T065 [P] [US7] Write `tests/fixtures/preregistration/valid/preregistration_amendment_valid.md` — frontmatter with one `amendment_log` entry containing all required fields, `authorized: false` (pending), `post_hoc: false`, valid deadline
- [x] T066 [P] [US7] Write `tests/fixtures/preregistration/invalid/preregistration_amendment_missing_approver.md` — `amendment_log` entry missing the `approver` field
- [x] T067 [P] [US7] Write `tests/fixtures/preregistration/invalid/preregistration_amendment_post_hoc.md` — `amendment_log` entry with `post_hoc: true`
- [x] T068 [US7] Implement `check_fv_spec_084_amendments(frontmatter)` in `tools/preregistration_validator.py`: iterate `amendment_log`; check each entry for required fields; reject any entry with `post_hoc: true`; return FV-SPEC-084 diagnostics naming the missing field or entry ID
- [x] T069 [US7] Implement `test_fv_spec_084_amendments` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T070 [US7] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_084_amendments -v`

**Checkpoint**: US7 independently green.

---

## Phase 12: User Story 8 — Label Confirmatory vs Exploratory Claims (Priority: P2)

**Goal**: `check_fv_spec_085_claims` detects any analysis entry that lacks a claim label consistent with its timing, stage, and data-access history.

**Independent Test**: `pytest tests/test_preregistration_freeze.py::test_fv_spec_085_claims` passes all three scenarios.

- [x] T071 [P] [US8] Write `tests/fixtures/preregistration/valid/preregistration_claims_valid.md` — all secondary/Stage B analyses in `## Reporting` section carry `label: exploratory` with access notes; primary endpoint carries `label: confirmatory`
- [x] T072 [P] [US8] Write `tests/fixtures/preregistration/invalid/preregistration_unlabelled_exploratory.md` — one Stage B analysis entry lacks any `label` field
- [x] T073 [P] [US8] Write `tests/fixtures/preregistration/invalid/preregistration_postfreeze_paraphrase_confirmatory.md` — a post-freeze paraphrase analysis listed under the primary confirmatory section without `label: exploratory`
- [x] T074 [US8] Implement `check_fv_spec_085_claims(frontmatter, body)` in `tools/preregistration_validator.py`: parse claim entries from `## Reporting`; detect missing labels; detect Stage B or post-freeze entries carrying `confirmatory` label; return FV-SPEC-085 diagnostics
- [x] T075 [US8] Implement `test_fv_spec_085_claims` (3 scenarios) in `tests/test_preregistration_freeze.py`
- [x] T076 [US8] Run `pytest tests/test_preregistration_freeze.py::test_fv_spec_085_claims -v`

**Checkpoint**: US8 independently green.

---

## Phase 13: User Story 11 — Offline Validation and Freeze Fixtures (Priority: P2)

**Goal**: `freeze.py --verify` works correctly; `_run_preregistration_validation()` in `validate_spec.py` is fully wired to call all 11 check functions; the complete test suite passes offline.

**Independent Test**: `pytest tests/test_preregistration_freeze.py -v` — all 11 hooks pass with no network calls.

- [x] T077 [US11] Implement `--verify` mode body in `tools/freeze.py`: call `verify_checksums`; read receipt JSON; run `git rev-parse <tag>^{}` and compare to receipt `tag_target_commit`; verify `checksums_digest` matches SHA-256 of current CHECKSUMS file; exit 0 if all match, 1 otherwise with named diagnostics
- [x] T078 [US11] Fully implement `_run_preregistration_validation()` in `tools/validate_spec.py`: load all four input files; call `validate_preregistration()` from `preregistration_validator`; build ReadinessReport JSON (all 11 check results, open decisions, staged obligations, input digests); write to `--report`; print summary; exit 0/1
- [x] T079 [P] [US11] Write `tests/fixtures/preregistration/invalid/freeze_publication_no_receipt/` — tmp git repo fixture where `freeze.py --execute` has been requested with a publication flag but no freeze receipt exists
- [x] T080 [P] [US11] Write `tests/fixtures/preregistration/valid/freeze_partial_prep/` — tmp git repo where `CHECKSUMS.sha256` exists but the tag has not yet been created (partial preparation state)
- [x] T081 [US11] Implement `test_fv_spec_088_cli` (3 scenarios) in `tests/test_preregistration_freeze.py`: all 11 hooks pass offline; publication-without-receipt returns non-zero; partial-preparation dry-run reports pending without fabricating a completed snapshot
- [x] T082 [US11] Run `pytest tests/test_preregistration_freeze.py -v` — confirm all 11 hooks pass with zero network calls (verify `_NO_MODEL_CALLS = True` is asserted in each test module)

**Checkpoint**: US11 independently green; all 11 FV-SPEC test hooks pass.

---

## Phase 14: Polish and Live Spec Validation

**Purpose**: Regression, live-artifact validation, and freeze readiness confirmation.

- [x] T083 [P] Resolve all blocking D-IDs in `.factverify/decisions/register.yaml` that are applicable to the current phase (D-42, D-44, D-45 per FV-SPEC P0-7 §5); mark remaining open decisions `status: open` with owner and notes; mark any applicable-but-not-yet-resolvable decisions with `status: pending`
- [ ] T084 [P] Update `.factverify/exposure/exposure_record.md` to `status: reviewed` once supervisor sign-off is obtained; fill in `review_date` and `reviewer` fields
- [ ] T085 [P] Update `.factverify/spec/preregistration.md` to `status: reviewed` once supervisor sign-off is obtained; compute and set `digest` field using `compute_contract_digest()`
- [x] T086 Run full prior-spec regression: `pytest tests/ -v --ignore=tests/test_preregistration_freeze.py` — confirm all P0-1 through P0-6 tests remain green
- [ ] T087 Run `python tools/validate_spec.py --scope preregistration --spec-root .factverify/spec --strict --report reports/p0-7-validation.json` against the live spec root and confirm all checks pass
- [x] T088 Run `python tools/freeze.py --spec-root .factverify/spec --tag spec-v1 --dry-run --report reports/p0-7-validation.json` and confirm all 8 gate checks pass (or document which gates are still pending with reasons)
- [x] T089 Update `reports/status.md` gate-status table with P0-7 outcome

---

## Dependencies and Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — start immediately; T002–T005 in parallel
- **Phase 2 (Foundational)**: Depends on Phase 1 — BLOCKS all user stories; T007–T009 in parallel after T006
- **Phases 3–7 (US1–US5, P1)**: All depend on Phase 2 — can proceed in parallel across stories
- **Phase 8 (US9)**: Depends on Phase 2 (freeze.py skeleton); independent of Phases 3–7
- **Phase 9 (US10)**: Depends on Phase 8 (checksum logic must exist)
- **Phases 10–12 (US6–US8, P2)**: Depend on Phase 2; can proceed in parallel with Phases 3–9
- **Phase 13 (US11)**: Depends on Phase 9 (freeze.py --verify) and Phase 2 (full CLI wiring)
- **Phase 14 (Polish)**: Depends on all user story phases complete

### User Story Dependencies

- **US1–US5 (P1 validators)**: All independent of each other after Foundational
- **US9 (integrity)**: Independent of US1–US5; depends on Foundational
- **US10 (gate)**: Depends on US9 (checksums); independent of US1–US8
- **US6–US8 (P2 validators)**: Independent of each other and of US1–US5 after Foundational
- **US11 (offline CLI)**: Depends on US9 + US10; integrates US1–US8 as a final check

### Within Each User Story

- Fixture writing [P] and check function implementation are independent (different files)
- Test implementation depends on both the fixture and the check function
- Live spec artifact population is independent of validator code

---

## Parallel Example: Phase 3 (US1) through Phase 7 (US5)

```bash
# After Phase 2 completes, all five can be started simultaneously:
Task T012-T018: US1 (preregistration sections + refs check)
Task T019-T025: US2 (exposure record check)
Task T026-T032: US3 (milestone manifest check)
Task T033-T038: US4 (split provenance check)
Task T039-T044: US5 (analysis cross-file check)

# Within each story, fixtures and implementation are parallel:
Task T012 (fixture: valid)         ← parallel with →   Task T015 (implement check)
Task T013 (fixture: missing-section)
Task T014 (fixture: duplicate-alpha)
```

## Parallel Example: Phase 10–12 (US6–US8, P2)

```bash
# All three can start immediately after Phase 2 completes:
Task T059-T064: US6 (deviation recovery check)
Task T065-T070: US7 (amendment constraint check)
Task T071-T076: US8 (claim labelling check)
```

---

## Implementation Strategy

### MVP First (P1 User Stories)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — **CRITICAL, blocks all stories**
3. Complete Phases 3–7 (US1–US5) and Phase 8 (US9) — run in parallel
4. Complete Phase 9 (US10) — depends only on Phase 8
5. **STOP and VALIDATE**: Run `pytest tests/test_preregistration_freeze.py -k "078 or 079 or 080 or 081 or 082 or 086 or 087"` to confirm all P1 hooks pass
6. Run dry-run freeze gate check — this is the P1 deliverable

### Incremental Delivery

1. Setup + Foundational → skeletons ready
2. US1–US5 in parallel → validator handles all five commitment-document checks
3. US9 + US10 → freeze.py can gate and execute
4. US6–US8 in parallel → remaining P2 validator checks
5. US11 → full offline test suite + complete CLI wiring
6. Polish → live spec artifacts validated, dry-run gate green

---

## Notes

- `[P]` tasks operate on different files and have no incomplete-task dependencies
- Each `[Story]` phase is independently testable via its named pytest marker
- Fixtures are synthetic; no GPU, model, or network calls in any test
- The `_NO_MODEL_CALLS = True` sentinel in `preregistration_validator.py` is asserted by the test suite
- Commit after each phase with a task-ID message: e.g., `P0-7 T015: check_fv_spec_078_artifact implemented`
- At Phase 14 T088, if the dry-run gate is not fully green, document which specific decisions are still open rather than loosening gate criteria — a partial gate status is itself a valid finding
