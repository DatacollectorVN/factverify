# Tasks: P0-3 Attack Family and Per-Channel Query Budget

**Input**: Design documents from `/specs/20260922-091030-attack-query-budget/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup

**Purpose**: Project initialization, directory structure, dependency verification

- [x] T001 Create directory structure: `.factverify/attacks/audit_manifests/`, `tests/fixtures/attack_spec/valid/`, `tests/fixtures/attack_spec/invalid/`, `tests/fixtures/attack_spec/baselines/`
- [x] T002 [P] Update `tests/conftest.py` with P0-3 path constants: `ATTACK_SPEC_PATH`, `ATTACKS_DIR`, `AT_FIXTURES`, `EVENT_FIXTURES_PATH`
- [x] T003 [P] Verify PyYAML and click are available in `pyproject.toml` dependencies (already present from P0-1/P0-2)

**Checkpoint**: Directories exist, conftest updated, dependencies available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Attack YAML loading, minimal valid fixture, structural helpers — everything else depends on these

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create a minimal valid `attacks.yaml` fixture at `tests/fixtures/attack_spec/valid/minimal_attacks.yaml` — three arms (native, semantic_only, factverify) with one channel each, common cap, accounting rules with all event policies, upstream refs, blocking decisions
- [x] T005 [P] Create a minimal valid event trace fixture at `tests/fixtures/attack_spec/valid/minimal_events.json` — one trace per arm with generation, cache_hit, retry, and reference events following declared charge policies
- [x] T006 Implement YAML loading and structural validation helper in `tools/attack_validator.py` — load attacks.yaml, parse with PyYAML safe_load, validate top-level structure, export reusable functions for the validator

**Checkpoint**: Minimal fixtures validate manually, YAML loader works.

---

## Phase 3: User Story 1 — Publish and Validate Attack Specification (Priority: P1) MVP

**Goal**: Validate attack artifact structure: three arms present, channels resolve, accounting units declared, permission cross-check against access profile.

**Independent Test**: `uv run python tools/validate_spec.py --scope attacks --spec-root .factverify/spec --contracts .factverify/contracts --report reports/p0-3-validation.json` exits 0 on valid specs and nonzero on invalid ones.

### Implementation for User Story 1

- [x] T007 [US1] Implement `--scope attacks` dispatch in `tools/validate_spec.py` — add `"attacks"` to `SUPPORTED_SCOPES`, add `--access-profile`, `--event-fixtures`, `--witness-rule` CLI options, route to attack validation entry point in `tools/attack_validator.py`
- [x] T008 [US1] Implement attack artifact loading and structural validation in `tools/attack_validator.py` — load YAML from `--spec-root`, validate all arms/channels/accounting/upstream_refs/blocking_decisions resolve, reject malformed YAML/duplicate keys/missing fields (FV-SPEC-034)
- [x] T009 [US1] Implement channel permission validation in `tools/attack_validator.py` — cross-check each enabled channel's capability_requirements against the access profile; reject enabled channels exceeding declared capabilities; unavailable permissions never recorded as successful (FV-SPEC-035)
- [x] T010 [US1] Write demonstration attack specification at `.factverify/spec/attacks.yaml` — three arms with illustrative allocations, eight channels (per study guide), accounting rules with all event policies, upstream refs to P0-1/P0-2, blocking decisions D-17–D-29/D-31
- [x] T011 [US1] Create negative test fixtures in `tests/fixtures/attack_spec/invalid/` — malformed YAML (`malformed.yaml`), missing required fields (`missing_required.yaml`), duplicate channel IDs (`duplicate_channels.yaml`), unknown channel reference (`unknown_channel.yaml`), permission violation (`permission_violation.yaml`)
- [x] T012 [US1] Write `tests/test_attack_spec.py::TestFvSpec034Artifact` — verify spec exists and parses; malformed YAML fails; missing fields fail; duplicate keys fail
- [x] T013 [US1] Write `tests/test_attack_spec.py::TestFvSpec035Permissions` — permitted channel passes; enabled channel exceeding access profile fails; disabled channel with no recipe passes

**Checkpoint**: US1 complete — structural validation works end-to-end, demo spec passes, FV-SPEC-034–035 tests pass.

---

## Phase 4: User Story 2 — Validate Matched Allocations and Accounting Units (Priority: P2)

**Goal**: Validate matched allocations (three arms sum to common cap), accounting unit definitions, and event charge policies (cache, retry, failure, reference).

**Independent Test**: Validator checks allocation sums, unit declarations, and replays event fixtures deterministically.

### Implementation for User Story 2

- [x] T014 [US2] Implement accounting unit validation in `tools/attack_validator.py` — verify generation_trial_unit and candidate_scoring_unit are declared with identity_fields and multiplicity_rule; reject mixed generation/scoring without conversion model (FV-SPEC-036)
- [x] T015 [US2] Implement event policy validation in `tools/attack_validator.py` — verify cache/retry/failure/discard/reference policies are declared with charge_rule and observation_charged; distinguish new compute from reused observations (FV-SPEC-037)
- [x] T016 [US2] Implement matched allocation validation in `tools/attack_validator.py` — verify all three arms' totals equal common_cap; reject omitted arm, unequal sum, negative allowance, or enabled operation without budget source; verify allocation-to-channel mapping (FV-SPEC-038)
- [x] T017 [US2] Implement event trace replay in `tools/attack_validator.py` — load `--event-fixtures` JSON, replay each event against declared charge policies, verify charges match; deterministic given same inputs/event order
- [x] T018 [US2] Create negative test fixtures for US2 in `tests/fixtures/attack_spec/invalid/` — unequal allocations (`unequal_allocations.yaml`), negative allowance (`negative_allowance.yaml`), missing accounting unit (`missing_unit.yaml`), mixed units without conversion (`mixed_units.yaml`), undeclared cache policy (`missing_cache_policy.yaml`)
- [x] T019 [US2] Write `tests/test_attack_spec.py::TestFvSpec036Units` — declared units pass; mixed generation/scoring without conversion fails; multiplicity rule verified
- [x] T020 [US2] Write `tests/test_attack_spec.py::TestFvSpec037EventPolicies` — complete policies pass; missing cache/retry/reference policy fails; discarded response still charged
- [x] T021 [US2] Write `tests/test_attack_spec.py::TestFvSpec038Allocations` — equal totals pass; omitted arm fails; unequal sum fails; negative allowance fails; disabled channel with allocation fails

**Checkpoint**: US2 complete — matched allocations validated, accounting units declared, event policies checked, fixture replay deterministic.

---

## Phase 5: User Story 3 — Reserve Confirmation Costs and Bound Adaptive Policies (Priority: P3)

**Goal**: Validate confirmation-route budget reservations and finite adaptive execution policies.

**Independent Test**: Validator cross-checks reservations against witness-rule routes, verifies no double-funding, and replays adaptive policy fixtures deterministically.

### Implementation for User Story 3

- [x] T022 [US3] Implement confirmation reservation validation in `tools/attack_validator.py` — cross-check each reservation against witness-rule routes (if `--witness-rule` provided); verify sufficient trials; reject double-funded shared calls; shared reservations declare competition (FV-SPEC-039)
- [x] T023 [US3] Implement adaptive policy validation in `tools/attack_validator.py` — verify each policy has bounded search_space, declared update/stop rules, discovery/confirmation limits, and budget ceiling; replay on scripted observations produces deterministic results; reject out-of-space actions and cap overruns (FV-SPEC-040)
- [x] T024 [US3] Create negative test fixtures for US3 in `tests/fixtures/attack_spec/invalid/` — missing confirmation reservation (`missing_reservation.yaml`), double-funded reservation (`double_funded.yaml`), unbounded adaptive policy (`unbounded_policy.yaml`), cap overrun in fixture (`cap_overrun_events.json`)
- [x] T025 [US3] Write `tests/test_attack_spec.py::TestFvSpec039Confirmation` — sufficient reservation passes; missing reservation fails; double-funded shared call fails
- [x] T026 [US3] Write `tests/test_attack_spec.py::TestFvSpec040Adaptive` — bounded policy passes; unbounded policy fails; out-of-space action refused; cap overrun refused

**Checkpoint**: US3 complete — confirmation reservations validated, adaptive policies bounded and replayable.

---

## Phase 6: User Story 4 — Target-Exposure Review and Reproducible Transformations (Priority: P4)

**Goal**: Validate clue audit manifests, transformation recipes, and relearning conditions.

**Independent Test**: Validator confirms exposure classifications are version-bound, recipes are complete, and relearning conditions separate target-free from target-exposed.

### Implementation for User Story 4

- [x] T027 [US4] Implement clue audit validation in `tools/attack_validator.py` — load audit manifests from `.factverify/attacks/audit_manifests/`; verify version-bound exposure classifications; route direct disclosures to supplied_answer; route inference-bearing inputs to inference (FV-SPEC-041)
- [x] T028 [US4] Implement transformation recipe validation in `tools/attack_validator.py` — for each enabled transformation channel, verify recipe has algorithm, software_version, parent_checkpoint, tokenizer, decoding_config, fitting_data_exposure, reference_treatment, output_provenance; reject missing fields; cumulative branches require explicit lineage (FV-SPEC-042)
- [x] T029 [US4] Implement relearning condition validation in `tools/attack_validator.py` — verify target_free and target_exposed conditions have distinct reporting; check data_source, schedule, optimizer, trainable_parameters, held_out_evaluation, tolerance_ref; reject unreached thresholds reported as finite times (FV-SPEC-043)
- [x] T030 [US4] Create a demonstration clue audit manifest at `.factverify/attacks/audit_manifests/demo_audit.json` — entries for Hà Nội red-star premises (routed to inference) and direct answer disclosure (routed to supplied_answer)
- [x] T031 [US4] Create negative test fixtures for US4 in `tests/fixtures/attack_spec/invalid/` — missing recipe fields (`incomplete_recipe.yaml`), unversioned audit (`unversioned_audit.json`), unseparated relearning (`unseparated_relearning.yaml`), direct disclosure not flagged (`unflagged_disclosure.json`)
- [x] T032 [US4] Write `tests/test_attack_spec.py::TestFvSpec041ClueAudit` — version-bound audit passes; unversioned audit fails; direct disclosure routed to supplied_answer; inference-bearing input not in equivalence
- [x] T033 [US4] Write `tests/test_attack_spec.py::TestFvSpec042Transformations` — complete recipe passes; missing algorithm/calibration fails; cumulative branch without lineage fails
- [x] T034 [US4] Write `tests/test_attack_spec.py::TestFvSpec043Relearning` — separated conditions pass; unseparated fails; unreached threshold requires censored result

**Checkpoint**: US4 complete — clue audits version-bound, recipes complete, relearning conditions separated.

---

## Phase 7: User Story 5 — Cost Reports, Revision Protection, and Scoped CLI (Priority: P5)

**Goal**: Complete CLI interface, cost-report records, revision protection, and regression verification.

**Independent Test**: Full test suite `tests/test_attack_spec.py` — all 13 hooks pass. P0-1 + P0-2 tests also pass.

### Implementation for User Story 5

- [x] T035 [US5] Implement cost-record generation in `tools/attack_validator.py` — per-arm cost records preserving caps, actual/unused usage, generation trials, score operations, tokens, training steps, exports, wall-clock; missing measurements explicit rather than zeroed (FV-SPEC-044)
- [x] T036 [US5] Implement revision protection in `tools/attack_validator.py` — compare current spec against `--baseline-suite`; reject changed channels, budgets, recipes, prompts, or stopping rules under unchanged revision; identical content passes (FV-SPEC-045)
- [x] T037 [US5] Implement report writer for attacks scope in `tools/attack_validator.py` — output scope, spec_path, spec_digest, upstream_digests, allocation_check, channel_permissions, accounting_check, event_replay, confirmation_check, policy_check, audit_check, transformation_check, relearning_check, cost_records, revision_check, deferred_checks, diagnostics, summary per contracts/validator-interface.md
- [x] T038 [US5] Implement strict mode in `tools/attack_validator.py` — require all applicable blocking decisions resolved (D-17–D-29, D-31); require current audits; require confirmation mappings; require enabled-channel margins; list deferred P0-5/P0-7 checks (FV-SPEC-046)
- [x] T039 [US5] Wire full diagnostic formatting with stable rule IDs (FV-SPEC-034–045) in `tools/attack_validator.py` — each diagnostic carries rule_id, item_id, file, json_pointer, message
- [x] T040 [US5] Create baseline fixture at `tests/fixtures/attack_spec/baselines/attacks.yaml` — copy of minimal valid spec for revision comparison
- [x] T041 [US5] Create review template at `reports/p0-3-review.md` — channel purpose, allocation rationale, exposure review, unresolved decisions, D-17–D-29/D-31 status
- [x] T042 [US5] Write `tests/test_attack_spec.py::TestFvSpec044CostRecords` — per-arm cost records preserve units; missing measurements explicit; cached observations explicit
- [x] T043 [US5] Write `tests/test_attack_spec.py::TestFvSpec045Revision` — identical baseline passes; changed channel without revision bump fails; new revision passes
- [x] T044 [US5] Write `tests/test_attack_spec.py::TestFvSpec046ScopedCli` — valid inputs exit 0 with report; missing spec exits 2; strict with open decisions exits nonzero; unsupported scope exits 2; deferred checks listed
- [x] T045 [US5] Verify P0-1/P0-2 compatibility: run `uv run pytest tests/test_contract_schema.py tests/test_closure_templates.py -v` to confirm all P0-1 + P0-2 tests pass unchanged

**Checkpoint**: US5 complete — full CLI works, all 13 test hooks pass, P0-1/P0-2 compatible.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Final validation, documentation, deterministic output check

- [x] T046 [P] Add invocation documentation as docstring in `tools/attack_validator.py` — command signature, exit semantics, scope limitations, deferred checks
- [x] T047 Run full test suite: `uv run pytest tests/test_attack_spec.py tests/test_closure_templates.py tests/test_contract_schema.py -v` — all P0-1 + P0-2 + P0-3 hooks must pass
- [x] T048 Run quickstart.md validation — execute all 13 integration test scenarios from `specs/20260922-091030-attack-query-budget/quickstart.md`
- [x] T049 Verify deterministic replay — replay event fixtures twice on same input, confirm identical charges and report (excluding timestamps)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — YAML loader and minimal fixtures must exist
- **User Story 2 (Phase 4)**: Depends on User Story 1 — structural validation core must exist before adding allocation/accounting checks
- **User Story 3 (Phase 5)**: Depends on User Story 2 — allocation validation must exist before confirmation/adaptive policy checks
- **User Story 4 (Phase 6)**: Depends on User Story 1 — structural validation must exist before audit/recipe/relearning checks
- **User Story 5 (Phase 7)**: Depends on User Stories 1–4 — CLI and regression fixtures exercise everything
- **Polish (Phase 8)**: Depends on all user stories being complete

### Within Each User Story

- Implementation tasks before tests — tests exercise the built validator
- Demonstration artifacts before negative fixtures — demos establish what "valid" looks like
- CLI wiring after validation logic is implemented

### Parallel Opportunities

Within US1 after the validator core (T007–T009):
- T010 and T011 (demo artifacts + negative fixtures) can run in parallel
- T012 and T013 (independent test classes) can run in parallel

Within US2:
- T019, T020, T021 (independent test classes) can run in parallel

US3 and US4 can potentially run in parallel after US1/US2, since:
- US3 adds confirmation/adaptive checks (independent of audit/recipe)
- US4 adds audit/recipe/relearning checks (independent of confirmation/adaptive)

---

## Parallel Example: User Story 1

```bash
# After validator core (T007–T009), launch demo and fixtures in parallel:
Task: "Write demonstration attack specification at .factverify/spec/attacks.yaml"
Task: "Create negative test fixtures in tests/fixtures/attack_spec/invalid/"

# Then launch independent test classes in parallel:
Task: "Write tests/test_attack_spec.py::TestFvSpec034Artifact"
Task: "Write tests/test_attack_spec.py::TestFvSpec035Permissions"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006)
3. Complete Phase 3: User Story 1 (T007–T013)
4. **STOP and VALIDATE**: Run `uv run pytest tests/test_attack_spec.py -v` — 2 test hooks should pass (034, 035)
5. Run the validator on demonstration spec — should exit 0 (with expected diagnostics for unresolved decisions)

### Incremental Delivery

1. Setup + Foundational -> YAML loader, minimal fixture validates
2. Add User Story 1 -> Structural validation works, 2 tests green (MVP)
3. Add User Story 2 -> Allocation/accounting/replay checks, 5 tests green
4. Add User Story 3 -> Confirmation/adaptive checks, 7 tests green
5. Add User Story 4 -> Audit/recipe/relearning checks, 10 tests green
6. Add User Story 5 -> Full CLI + cost/revision/strict, 13 tests green
7. Polish -> All quickstart scenarios pass, deterministic replay verified

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Test names follow the FV-SPEC convention: `test_fv_spec_NNN_description`
- All 13 FV-SPEC requirements (034–046) map to exactly one test hook each
- US4 clue audit (FV-SPEC-041) is partly a process requirement — automated tests check manifest structure, not scientific judgment
- D-17 through D-29/D-31 block `implemented` status but not development with provisional fixtures
- P0-3 validation logic lives in `tools/attack_validator.py` to keep `validate_spec.py` as the thin CLI dispatcher
- US3 and US4 are parallelizable after US2 since they add independent check types
