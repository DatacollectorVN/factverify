# Tasks: P0-4 Access Profile and the Identifiability Limit

**Input**: Design documents from `/specs/20260922-095456-access-profile-identifiability/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup

**Purpose**: Directory structure, conftest updates, dependency verification

- [x] T001 Create directory structure: `.factverify/access/capability_manifests/`, `.factverify/access/identifiability/`, `.factverify/access/claim_templates/`, `tests/fixtures/access_profile/valid/`, `tests/fixtures/access_profile/invalid/`, `tests/fixtures/access_profile/baselines/`
- [x] T002 [P] Update `tests/conftest.py` with P0-4 path constants: `ACCESS_PROFILE_PATH`, `ACCESS_DIR`, `AP_FIXTURES`, `AP_VALID`, `AP_INVALID`, `AP_BASELINES`
- [x] T003 [P] Verify PyYAML, click, and hashlib are available in `pyproject.toml` dependencies (hashlib is stdlib; PyYAML and click already present from P0-1/P0-2/P0-3)

**Checkpoint**: Directories exist, conftest updated, dependencies available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: YAML frontmatter parser, minimal valid fixture, structural helpers — everything else depends on these

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create a minimal valid `access_profile.md` fixture at `tests/fixtures/access_profile/valid/minimal_profile.md` — YAML frontmatter with version, profile A, measurement_point, two systems (candidate + reference) with per-system capabilities, roles (evaluator + operator), permitted_sources, handling_policies, budget_ref, blocking_decisions (D-13, D-14, D-27, D-28, D-29, D-31), provenance_refs; Markdown body with Observation Boundary, Provenance Procedure, Limitations sections
- [x] T005 [P] Create a minimal valid capability manifest at `tests/fixtures/access_profile/valid/manifest_candidate.json` — manifest_id, system_id, tap_location, intervening_processors, model_identity (name/version/hash), tokenizer_identity (name/version/hash), evidence_source, reviewer_id, review_date
- [x] T006 [P] Create a minimal valid capability manifest at `tests/fixtures/access_profile/valid/manifest_reference.json` — same structure as T005 but for the reference system
- [x] T007 Implement YAML frontmatter parsing helper in `tools/access_profile_validator.py` — load access_profile.md, split YAML frontmatter from Markdown body, parse with PyYAML safe_load, validate top-level structure, export `load_access_profile()` returning `(frontmatter_dict, body_str)` and `validate_frontmatter_schema()` checking required fields

**Checkpoint**: Minimal fixtures exist, frontmatter parser works, structural validation helper loads profiles.

---

## Phase 3: User Story 1 — Publish and Validate the Access Contract (Priority: P1) MVP

**Goal**: Validate access_profile.md artifact structure: version, profile enum, required fields, well-formed frontmatter, cross-file reference resolution, malformed/incomplete rejection.

**Independent Test**: `uv run python tools/validate_spec.py --scope access-profile --spec-root .factverify/spec --report reports/p0-4-validation.json` exits 0 on valid profile; nonzero on malformed/incomplete.

### Implementation for User Story 1

- [x] T008 [US1] Implement `--scope access-profile` dispatch in `tools/validate_spec.py` — add `"access-profile"` to `SUPPORTED_SCOPES`, add `--access-dir` CLI option, route to `_run_access_profile_validation()` calling entry point in `tools/access_profile_validator.py`
- [x] T009 [US1] Implement `check_access_contract_artifact()` in `tools/access_profile_validator.py` — validate all required frontmatter fields (version, profile, measurement_point, systems, roles, permitted_sources, handling_policies, budget_ref, blocking_decisions, provenance_refs), reject unknown profile values, validate version format (semver), check blocking decisions include D-13/D-14/D-27/D-28/D-29/D-31 (FV-SPEC-047)
- [x] T010 [US1] Implement `check_cross_file_references()` in `tools/access_profile_validator.py` — resolve budget_ref, provenance_refs, claim_refs, identifiability_refs as relative paths from spec_root; check file existence; compute and compare SHA-256 digests where declared; list deferred checks for P0-5/P0-6/P0-7 in non-strict mode (FV-SPEC-047 cross-file part)
- [x] T011 [US1] Implement `write_access_profile_report()` in `tools/access_profile_validator.py` — generate JSON report per contracts/validator-interface.md schema: report_id, timestamp, scope, checks[], capabilities, permission_conflicts, review_state, cross_file_checks, input_digests, deferred_checks, overall
- [x] T012 [US1] Write demonstration access profile at `.factverify/spec/access_profile.md` — Profile A with two systems, roles, permitted_sources, handling_policies referencing reporting rules, budget_ref to attacks.yaml, blocking decisions, provenance_refs to demo manifests
- [x] T013 [P] [US1] Create demonstration capability manifests at `.factverify/access/capability_manifests/candidate_manifest.json` and `.factverify/access/capability_manifests/reference_manifest.json`
- [x] T014 [US1] Create negative test fixtures in `tests/fixtures/access_profile/invalid/` — `malformed.yaml` (broken YAML frontmatter), `missing_required.md` (missing version/profile/systems), `unknown_profile.md` (profile: D), `duplicate_keys.md` (duplicate system IDs), `bad_version.md` (non-semver version)
- [x] T015 [US1] Write `tests/test_access_profile.py::TestFvSpec047Artifact` — valid profile passes; malformed frontmatter fails (exit 2); missing required fields fail; unknown profile rejected; version format validated; blocking decisions checked; cross-file references resolve on valid, fail on broken refs
- [x] T016 [US1] Create baseline fixture at `tests/fixtures/access_profile/baselines/access_profile.md` — copy of minimal valid profile for revision comparison

**Checkpoint**: US1 complete — structural validation works end-to-end, demo profile passes, FV-SPEC-047 tests pass.

---

## Phase 4: User Story 2 — Validate Observation Capabilities and Provenance (Priority: P2)

**Goal**: Validate per-system A/B/C capability declarations match serving boundary; detect post-mask/pre-mask mismatches and partial/unrestricted mismatches; validate provenance manifests.

**Independent Test**: Validate profile with correct A/B/C against fixtures; pass. Validate post-mask labelled pre-mask; fail with specific diagnostic.

### Implementation for User Story 2

- [x] T017 [US2] Implement `check_observation_capabilities()` in `tools/access_profile_validator.py` — for each system: validate profile_letter vs individual capability states (A: scores+internals unavailable; B: internals unavailable, scores not unavailable; C: unrestricted); validate score_scope consistency (post_mask scores with pre_mask type fails); check provider_transformations declared; validate capability state enum (declared/verified/unavailable/unverified) (FV-SPEC-048)
- [x] T018 [US2] Implement `check_provenance_verification()` in `tools/access_profile_validator.py` — for each provenance_ref: load manifest JSON, validate required fields (manifest_id, system_id, tap_location, intervening_processors, model_identity, tokenizer_identity, evidence_source, reviewer_id, review_date); check system_id matches a declared system; validate hash format (64-char hex SHA-256); check reviewer_id non-empty; validate review_date ISO 8601 (FV-SPEC-049)
- [x] T019 [P] [US2] Create Profile B fixture at `tests/fixtures/access_profile/valid/profile_b.md` — text+scores system with score_scope (pre_mask, full vocabulary), candidate_scoring declared, manifest refs
- [x] T020 [P] [US2] Create Profile C fixture at `tests/fixtures/access_profile/valid/profile_c.md` — internals-access system with all capabilities verified, manifest refs
- [x] T021 [P] [US2] Create negative fixtures: `tests/fixtures/access_profile/invalid/postmask_premask.md` (B profile with post-mask scores labelled pre_mask), `tests/fixtures/access_profile/invalid/partial_unrestricted.md` (C profile with partial internals labelled unrestricted), `tests/fixtures/access_profile/invalid/bad_manifest.json` (missing required manifest fields), `tests/fixtures/access_profile/invalid/wrong_system_manifest.json` (manifest system_id not in profile)
- [x] T022 [US2] Write `tests/test_access_profile.py::TestFvSpec048Capabilities` — A/B/C consistency checks pass on valid; post-mask/pre-mask mismatch fails; partial/unrestricted mismatch fails; capability state enum validated; score_scope required for B/C
- [x] T023 [US2] Write `tests/test_access_profile.py::TestFvSpec049Provenance` — valid manifest passes; missing fields fail; system_id mismatch fails; bad hash format fails; missing reviewer fails; evidence tied to different artifact flagged

**Checkpoint**: US2 complete — capability and provenance validation works, FV-SPEC-048–049 tests pass.

---

## Phase 5: User Story 3 — Separate Observation from Intervention and Bound Sources (Priority: P3)

**Goal**: Validate intervention permissions independently of observation; enforce role separation; validate permitted sources and historical access attribution.

**Independent Test**: Profile with operator exporting checkpoint for B-only evaluator with separate roles; pass. Unlisted fine-tune or undeclared historical source; fail.

### Implementation for User Story 3

- [x] T024 [US3] Implement `check_observation_intervention_separation()` in `tools/access_profile_validator.py` — for each intervention: validate actor_role matches a declared role_id; validate approved_recipes non-empty; check that intervention does not grant capabilities beyond the actor's system profile; validate artifact_lineage present; verify operator/evaluator role separation (same person cannot be both for same system) (FV-SPEC-050)
- [x] T025 [US3] Implement `check_historical_external_access()` in `tools/access_profile_validator.py` — validate all entries in permitted_sources are recognized categories; validate each historical_access entry has non-empty attribution; check recovery from pre-unlearning model separately attributed; reject undeclared sources (FV-SPEC-051)
- [x] T026 [P] [US3] Create fixture with interventions at `tests/fixtures/access_profile/valid/profile_with_interventions.md` — operator role exports checkpoint, evaluator role observes, separate role declarations, approved recipes, artifact lineage
- [x] T027 [P] [US3] Create negative fixtures: `tests/fixtures/access_profile/invalid/unlisted_finetune.md` (intervention without approved recipe), `tests/fixtures/access_profile/invalid/missing_role.md` (intervention referencing nonexistent role), `tests/fixtures/access_profile/invalid/undeclared_history.md` (historical_access without attribution), `tests/fixtures/access_profile/invalid/exceeds_capabilities.md` (intervention requiring capabilities beyond actor's profile)
- [x] T028 [US3] Write `tests/test_access_profile.py::TestFvSpec050Separation` — valid intervention passes; unlisted fine-tune rejected; role not found fails; B/C does not grant blanket intervention; role separation enforced
- [x] T029 [US3] Write `tests/test_access_profile.py::TestFvSpec051Sources` — declared sources pass; undeclared source fails; historical access with attribution passes; missing attribution fails; pre-unlearning recovery must be separately attributed

**Checkpoint**: US3 complete — intervention/source validation works, FV-SPEC-050–051 tests pass.

---

## Phase 6: User Story 4 — Identifiability Justification and Status Contracts (Priority: P4)

**Goal**: Validate scoped identifiability justifications; enforce four distinct outcome statuses with no silent promotion.

**Independent Test**: Profile with reviewed identifiability justification for synthetic simulator pair; pass. Claiming non-identifiability from one matching refusal; fail. Status fixtures with distinct evidence paths; pass.

### Implementation for User Story 4

- [x] T030 [US4] Implement `check_identifiability_justification()` in `tools/access_profile_validator.py` — for each identifiability_ref: load JSON, validate required fields (justification_id, revision, system_pair, observation_boundary, permitted_queries, historical_access, argument_type, argument_summary, reviewer_id, review_date, limitations); check system_pair entries exist in profile systems; validate revision compatible with profile version; empirical arguments must note finite-observation limitation; constructive arguments must reference synthetic/controlled systems (FV-SPEC-052)
- [x] T031 [US4] Implement `check_status_contracts()` in `tools/access_profile_validator.py` — enforce four statuses (confirmed_recovery, conformance, non_identifiable, incomplete) as an enum; validate handling_policies map each status to a reporting rule; check no automatic promotion path: missing raw score → incomplete (not non_identifiable), known control label → not fabricated witness, completed test without confirmed witness → incomplete (not conformance) (FV-SPEC-053)
- [x] T032 [P] [US4] Create valid identifiability justification fixture at `tests/fixtures/access_profile/valid/justification_synthetic.json` — constructive argument type, synthetic simulator pair, scoped observation boundary, reviewed
- [x] T033 [P] [US4] Create valid identifiability justification fixture at `tests/fixtures/access_profile/valid/justification_empirical.json` — empirical argument type with finite-observation limitation noted
- [x] T034 [P] [US4] Create negative fixtures: `tests/fixtures/access_profile/invalid/finite_matching.json` (empirical argument without finite-observation limitation), `tests/fixtures/access_profile/invalid/wrong_system_pair.json` (system_pair references nonexistent system), `tests/fixtures/access_profile/invalid/missing_justification_fields.json` (missing reviewer/revision)
- [x] T035 [US4] Write `tests/test_access_profile.py::TestFvSpec052Identifiability` — valid constructive justification passes; valid empirical with limitation passes; finite matching without limitation fails; wrong system pair fails; missing fields fail; no justification + non-strict → deferred; no justification + strict → fail
- [x] T036 [US4] Write `tests/test_access_profile.py::TestFvSpec053StatusContracts` — four statuses enforced; missing raw score → incomplete; known control label alone → not witness; completed test without witness → incomplete; no silent promotion; handling_policies must cover all four statuses

**Checkpoint**: US4 complete — identifiability and status validation works, FV-SPEC-052–053 tests pass.

---

## Phase 7: User Story 5 — Predeclared Reporting, Claim Templates, and Scoped CLI (Priority: P5)

**Goal**: Cross-check eligibility/denominator policies; validate claim templates against declared evidence scope; strict mode; baseline comparison; complete CLI integration.

**Independent Test**: Full validation with `--strict` passes only when all decisions resolved, reviews current, cross-file refs agree. Baseline comparison detects changed frozen policy.

### Implementation for User Story 5

- [x] T037 [US5] Implement `check_eligibility_reporting()` in `tools/access_profile_validator.py` — cross-check handling_policies against access profile status definitions; validate eligibility rules reference correct status mappings; check non-identifiable and incomplete have separate counting rules; detect unmapped statuses or outcome-dependent exclusions (FV-SPEC-054)
- [x] T038 [US5] Implement `check_claim_templates()` in `tools/access_profile_validator.py` — for each claim_ref: load JSON, validate required fields (template_id, profile, stage, completed_tests, budget_ref, claim_text, limitations, reviewer_id, review_date); check profile matches access_profile profile; Profile A must include output-simulation limitation; Stage B cannot inherit Stage A causal references; reject universal erasure language (regex for "completely removed", "fully erased", "totally eliminated", etc.); validate budget_ref resolves (FV-SPEC-055)
- [x] T039 [US5] Implement `check_strict_mode()` in `tools/access_profile_validator.py` — when strict=True: all blocking decisions must be resolved; all provenance reviews must be current; all cross-file references (including P0-5/P0-6/P0-7) must resolve; identifiability justifications required if claimed; review_manifest.json must exist with no pending entries (FV-SPEC-056 strict part)
- [x] T040 [US5] Implement `check_baseline_comparison()` in `tools/access_profile_validator.py` — when baseline_suite_path provided: load baseline profile, compare version/revision; detect changed frozen policies under unchanged revision; report changed_fields and revision_match (FV-SPEC-056 baseline part)
- [x] T041 [US5] Implement top-level `validate_access_profile()` entry point in `tools/access_profile_validator.py` — orchestrate all 10 checks (FV-SPEC-047–056) in order, aggregate results, call `write_access_profile_report()`, return `(passed, report)` tuple
- [x] T042 [P] [US5] Create valid claim template fixtures at `tests/fixtures/access_profile/valid/claim_template_a.json` (Profile A with output-simulation limitation), `tests/fixtures/access_profile/valid/claim_template_b.json` (Profile B Stage A), `tests/fixtures/access_profile/valid/claim_template_c.json` (Profile C Stage A)
- [x] T043 [P] [US5] Create negative claim template fixtures: `tests/fixtures/access_profile/invalid/universal_erasure.json` (claim_text with "completely removed"), `tests/fixtures/access_profile/invalid/mismatched_profile.json` (template profile B on access_profile A), `tests/fixtures/access_profile/invalid/stage_b_causal.json` (Stage B inheriting Stage A causal reference), `tests/fixtures/access_profile/invalid/missing_a_limitation.json` (Profile A without output-simulation limitation)
- [x] T044 [US5] Write `tests/test_access_profile.py::TestFvSpec054Reporting` — resolved policies pass; unmapped status fails; outcome-dependent exclusion fails strict; non-identifiable and incomplete counted separately
- [x] T045 [US5] Write `tests/test_access_profile.py::TestFvSpec055ClaimTemplates` — valid A/B/C templates pass; universal erasure rejected; mismatched profile rejected; Stage B causal inheritance rejected; Profile A missing limitation rejected
- [x] T046 [US5] Write `tests/test_access_profile.py::TestFvSpec056ScopedCli` — full validation on valid profile exits 0 with clean report; strict mode with unresolved decisions exits 1; baseline comparison detects changed frozen policy; report contains all required fields; deferred checks listed in non-strict; zero endpoint calls confirmed; deterministic output (two runs produce identical reports excluding timestamp)
- [x] T047 [US5] Create `tests/fixtures/access_profile/valid/review_manifest.json` with review entries covering all manifests and justifications; create `tests/fixtures/access_profile/valid/strict_profile.md` with all decisions resolved and all reviews current

**Checkpoint**: US5 complete — full validation pipeline works end-to-end, all 10 test classes pass, strict/baseline modes verified.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Regression checks, demonstration run, deterministic replay verification

- [x] T048 Run existing P0-1, P0-2, P0-3 test suites (`uv run pytest tests/test_fact_contract_schema.py tests/test_closure_templates.py tests/test_attack_spec.py -v`) to confirm no regressions from P0-4 changes
- [x] T049 [P] Run full P0-4 test suite (`uv run pytest tests/test_access_profile.py -v`) and confirm all tests pass
- [x] T050 Run demonstration validation: `uv run python tools/validate_spec.py --scope access-profile --spec-root .factverify/spec --report reports/p0-4-validation.json` on the demo access_profile.md and confirm clean exit
- [x] T051 Run deterministic replay: execute demonstration validation twice, compare reports (excluding timestamps), confirm identical output

**Checkpoint**: All tests green, no regressions, deterministic output verified.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — provides CLI dispatch and artifact validation
- **User Story 2 (Phase 4)**: Depends on US1 (needs artifact structure validation as baseline)
- **User Story 3 (Phase 5)**: Depends on US1 (needs role declarations from artifact validation)
- **User Story 4 (Phase 6)**: Depends on US1 (needs profile/system references); can run in parallel with US2/US3
- **User Story 5 (Phase 7)**: Depends on US1–US4 (orchestrates all checks, strict mode, baseline)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Foundation only — MVP deliverable
- **US2 (P2)**: US1 (needs profile structure loaded) — can start after US1 checkpoint
- **US3 (P3)**: US1 (needs role declarations) — can start after US1 checkpoint, parallel with US2
- **US4 (P4)**: US1 (needs system references) — can start after US1 checkpoint, parallel with US2/US3
- **US5 (P5)**: US1 + US2 + US3 + US4 — integration layer, must be last story phase

### Within Each User Story

- Validation functions before test fixtures (functions define what fixtures must test)
- Negative fixtures before test classes (tests need the invalid inputs)
- Test classes validate both positive and negative paths

### Parallel Opportunities

- T002 and T003 in Setup (different files)
- T005 and T006 in Foundational (different manifest files)
- T019, T020, T021 in US2 (different fixture files)
- T026, T027 in US3 (different fixture files)
- T032, T033, T034 in US4 (different fixture files)
- T042, T043 in US5 (different fixture files)
- US2, US3, US4 can start in parallel after US1 completes

---

## Parallel Example: After US1 Checkpoint

```bash
# These three user stories can begin in parallel after US1:
# US2: T017 (capabilities) + T018 (provenance) + T019/T020/T021 (fixtures)
# US3: T024 (intervention separation) + T025 (sources) + T026/T027 (fixtures)
# US4: T030 (identifiability) + T031 (status contracts) + T032/T033/T034 (fixtures)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T007)
3. Complete Phase 3: User Story 1 (T008–T016)
4. **STOP and VALIDATE**: `uv run pytest tests/test_access_profile.py::TestFvSpec047Artifact -v`
5. Demo profile validates with clean report

### Incremental Delivery

1. Setup + Foundational → infrastructure ready
2. US1 → access contract artifact validated (MVP)
3. US2 → capability/provenance validation added
4. US3 → intervention/source validation added (parallel with US2)
5. US4 → identifiability/status validation added (parallel with US2/US3)
6. US5 → full pipeline integration, strict mode, baseline comparison
7. Polish → regression check, deterministic replay

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story builds on US1's artifact structure but adds independent validation rules
- Follows P0-3 pattern: thin CLI dispatch in `validate_spec.py`, full engine in `access_profile_validator.py`
- All validation is offline — zero endpoint calls, model execution, or GPU jobs
- Test naming convention: `TestFvSpec047Artifact` through `TestFvSpec056ScopedCli`
