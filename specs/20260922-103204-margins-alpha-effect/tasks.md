# Tasks: P0-5 Alpha and Practical Effect Size

**Input**: Design documents from `/specs/20260922-103204-margins-alpha-effect/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4, US5)

---

## Phase 1: Setup

**Purpose**: Directory structure, conftest updates, dependency verification

- [x] T001 Create directory structure: `.factverify/margins/approvals/`, `tests/fixtures/margins_spec/valid/`, `tests/fixtures/margins_spec/invalid/`, `tests/fixtures/margins_spec/baselines/`
- [x] T002 [P] Update `tests/conftest.py` with P0-5 path constants: `MARGINS_PATH`, `MARGINS_DIR`, `MG_FIXTURES`, `MG_VALID`, `MG_INVALID`, `MG_BASELINES`
- [x] T003 [P] Verify PyYAML, click, and hashlib are available in `pyproject.toml` dependencies (stdlib hashlib; PyYAML and click already present from P0-1–P0-4)

**Checkpoint**: Directories exist, conftest updated, dependencies available.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: YAML loader, quantity helpers, minimal valid fixture — everything else depends on these

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Create a minimal valid margins fixture at `tests/fixtures/margins_spec/valid/minimal_margins.yaml` — version, status `unresolved_worksheet`, quantity-shaped `frr_cap` / `confidence_error_probability` / `minimum_fcr_reduction_absolute` (null values + units + domains + decision_refs), `delta_definition`, `practical_success` (both comparators, `require_both_baselines: true`), `threshold_selection` (`calibration_only`, eligibility rule, tie rule, `forbid_final_test_inputs: true`), `estimands` (FRR/FCR shapes, weights, aggregation, status_mappings), `uncertainty` block, `channel_margins` for enabled demo channels, `locality_margins` for `same_subject`/`same_relation`/`compositional`/`global`, `relearning_tolerance`, `sample_size_handoff` with `final_n: null`, `approval_refs`, `blocking_decisions` for D-01–D-16 and D-38
- [x] T005 [P] Create synthetic rate fixture at `tests/fixtures/margins_spec/valid/synthetic_rates.json` — genuine: 3 rejections / 100 eligible; fake: 12 acceptances / 40 eligible; empty-denominator case marked undefined
- [x] T006 Implement YAML load + quantity helpers in `tools/margins_validator.py` — `load_margins()` via PyYAML `safe_load`, `validate_quantity()` (finite, unit, domain), export constants for required fields / locality buckets / required blocking decisions; reject unknown top-level keys in a schema helper

**Checkpoint**: Minimal fixture exists, loader works, quantity validation helper is callable.

---

## Phase 3: User Story 1 — Publish and Validate the Margins Contract (Priority: P1) MVP

**Goal**: Validate `margins.yaml` structure: versioned typed fields, units/domains, fail-closed on null coercion / unknown fields / non-finite / mixed units; no threshold-for-alpha substitution; CLI dispatch and report skeleton.

**Independent Test**: `uv run python tools/validate_spec.py --scope margins --spec-root .factverify/spec --report reports/p0-5-validation.json` exits 0 on a structurally valid unresolved worksheet; nonzero on malformed/mixed-unit artifacts.

### Implementation for User Story 1

- [x] T007 [US1] Implement `--scope margins` dispatch in `tools/validate_spec.py` — add `"margins"` to `SUPPORTED_SCOPES`, add `--margins-dir` CLI option, route to `_run_margins_validation()` calling `validate_margins()` in `tools/margins_validator.py` (keep `--contracts` optional for this scope)
- [x] T008 [US1] Implement `check_margins_contract_artifact()` in `tools/margins_validator.py` — required fields present; semver version; quantity units/domains; reject unknown fields, non-finite values, mixed probability/percentage_points; ensure thresholds are not substituted for `frr_cap` (FV-SPEC-057)
- [x] T009 [US1] Implement `write_margins_report()` in `tools/margins_validator.py` — JSON report per `contracts/validator-interface.md`: report_id, timestamp, scope `margins`, checks[], decision_status, input_digests, deferred_checks, baseline_comparison, overall
- [x] T010 [US1] Write demonstration margins artifact at `.factverify/spec/margins.yaml` — unresolved worksheet aligned with Study Guide §13 field names; null policy values with decision_refs; channel margins for currently enabled `attacks.yaml` channels; locality buckets from fact-contract enum; blocking_decisions open
- [x] T011 [P] [US1] Create negative fixtures in `tests/fixtures/margins_spec/invalid/` — `malformed.yaml`, `missing_required.yaml`, `unknown_field.yaml`, `non_finite.yaml`, `mixed_units.yaml`, `threshold_as_alpha.yaml`
- [x] T012 [US1] Write `tests/test_margins_spec.py::TestFvSpec057Artifact` — valid minimal passes; malformed exits 2; missing required / unknown / non-finite / mixed units / threshold-for-alpha fail
- [x] T013 [US1] Create baseline fixture at `tests/fixtures/margins_spec/baselines/margins.yaml` — copy of minimal valid margins for revision comparison

**Checkpoint**: US1 complete — structural validation works end-to-end, demo worksheet loads, FV-SPEC-057 tests pass.

---

## Phase 4: User Story 2 — Record Policy Justification and Approvals (Priority: P2)

**Goal**: Require approval records for FRR cap and practical-success policy; fail strict readiness on illustrative/unapproved values.

**Independent Test**: Approvals with population, consequences, minimum worthwhile benefit, approver, date, revision → pass. Illustrative 0.05 without approval under `--strict` → fail.

### Implementation for User Story 2

- [x] T014 [US2] Implement `check_policy_approval()` in `tools/margins_validator.py` — load `approval_refs` from margins_dir; validate required approval fields; bind `artifact_revision` to margins version; strict mode fails if `frr_cap` or `practical_success` lack current approvals or if illustrative teaching values lack approval (FV-SPEC-058)
- [x] T015 [P] [US2] Create valid approval fixtures at `tests/fixtures/margins_spec/valid/approval_frr_cap.json` and `tests/fixtures/margins_spec/valid/approval_practical_success.json`
- [x] T016 [P] [US2] Create negative fixtures: `tests/fixtures/margins_spec/invalid/missing_approval_fields.json`, `tests/fixtures/margins_spec/invalid/illustrative_unapproved.yaml` (frr_cap.value 0.05 without approval_refs)
- [x] T017 [US2] Write `tests/test_margins_spec.py::TestFvSpec058Approval` — complete approvals pass; missing fields fail; illustrative unapproved fails strict; non-strict may list pending decisions without inventing values
- [x] T018 [US2] Create demo approval stubs and `review_manifest.json` under `.factverify/margins/` — approvals may mark decisions open; review entries present for demo artifacts

**Checkpoint**: US2 complete — approval validation works, FV-SPEC-058 tests pass.

---

## Phase 5: User Story 3 — Define Estimands, Denominators, and Calibration Selection (Priority: P3)

**Goal**: FRR/FCR estimands over explicit populations; empty denominators undefined; calibration-only selection under UCB(FRR) ≤ α with deterministic ties; no final-test leakage or silent cap relaxation.

**Independent Test**: Synthetic 3/100 → 0.03 FRR and 12/40 → 0.30 FCR; empty denom undefined. Selection with final-test inputs or point-estimate-only eligibility → fail; infeasible → reported.

### Implementation for User Story 3

- [x] T019 [US3] Implement `check_estimands_denominators()` in `tools/margins_validator.py` — validate estimand shapes, weights, aggregation, status_mappings; compute unweighted rates from synthetic fixture; empty denominators → undefined never 0.0 (FV-SPEC-059)
- [x] T020 [US3] Implement `check_calibration_selection()` in `tools/margins_validator.py` — require `data: calibration_only`, eligibility `ucb_frr_le_frr_cap` (or approved equivalent), deterministic `tie_rule`, `no_feasible_threshold: report_infeasible`, `forbid_final_test_inputs: true`; reject silent cap relaxation and final-test leakage fixtures (FV-SPEC-060)
- [x] T021 [P] [US3] Create fixtures: `tests/fixtures/margins_spec/valid/calibration_candidates.json` (feasible UCB set), `tests/fixtures/margins_spec/invalid/empty_denom_as_zero.yaml`, `tests/fixtures/margins_spec/invalid/final_test_in_selection.yaml`, `tests/fixtures/margins_spec/invalid/point_estimate_only_selection.yaml`, `tests/fixtures/margins_spec/invalid/infeasible_selection.json`
- [x] T022 [US3] Write `tests/test_margins_spec.py::TestFvSpec059Estimands` — rates 0.03/0.30; empty denom undefined; status mappings required
- [x] T023 [US3] Write `tests/test_margins_spec.py::TestFvSpec060Calibration` — feasible calibration passes; final-test inputs rejected; point-estimate-only fails; infeasible reported; no silent α relaxation

**Checkpoint**: US3 complete — estimand and calibration contract validation works, FV-SPEC-059–060 tests pass.

---

## Phase 6: User Story 4 — Practical Success, Uncertainty, and Margin Coverage (Priority: P4)

**Goal**: Both-baseline practical success under common budget; uncertainty/dependence contract; oriented margin per enabled channel and locality bucket.

**Independent Test**: Delta −0.12 (12 pp) with only one baseline meeting criterion → primary success false. Illegal resampling contract → fail. Missing channel/bucket margin → fail.

### Implementation for User Story 4

- [x] T024 [US4] Implement `check_practical_effect()` in `tools/margins_validator.py` — require both `native` and `semantic_only`; resolve `common_budget_ref` to attacks.yaml; delta in percentage_points; primary success is conjunction; optional UCB(delta) rule only if explicitly adopted; fixture 0.18 vs 0.30 → −0.12 (FV-SPEC-061)
- [x] T025 [US4] Implement `check_uncertainty_dependence()` in `tools/margins_validator.py` — require dependence_structure, seed_types, weighting, simultaneous_family, confidence_target, paired resampling, zero_errors_policy; reject independent correlated-prompt resampling and separate intervals labelled joint coverage (FV-SPEC-062)
- [x] T026 [US4] Implement `check_channel_locality_coverage()` in `tools/margins_validator.py` — cross-check enabled channels from `.factverify/spec/attacks.yaml` and locality buckets from fact-contract enum; each needs oriented statistic/unit/reference/margin; reject raw-rank+correctness aggregation; do not import superseded privacy margins (FV-SPEC-063)
- [x] T027 [P] [US4] Create fixtures: `tests/fixtures/margins_spec/valid/effect_both_baselines.json`, `tests/fixtures/margins_spec/invalid/single_baseline_success.yaml`, `tests/fixtures/margins_spec/invalid/illegal_resampling.yaml`, `tests/fixtures/margins_spec/invalid/missing_channel_margin.yaml`, `tests/fixtures/margins_spec/invalid/missing_bucket_margin.yaml`, `tests/fixtures/margins_spec/invalid/rank_correctness_mix.yaml`
- [x] T028 [US4] Write `tests/test_margins_spec.py::TestFvSpec061Effect` — delta −0.12; both baselines required; optional UCB rule gated
- [x] T029 [US4] Write `tests/test_margins_spec.py::TestFvSpec062Uncertainty` — valid contract passes; illegal resampling fails; zero errors still require uncertainty policy
- [x] T030 [US4] Write `tests/test_margins_spec.py::TestFvSpec063Coverage` — enabled channels + four buckets covered; missing margin fails; invalid aggregation fails

**Checkpoint**: US4 complete — effect/uncertainty/coverage validation works, FV-SPEC-061–063 tests pass.

---

## Phase 7: User Story 5 — Sample-Size Handoff, Revision Protection, and Scoped CLI (Priority: P5)

**Goal**: Pilot sample-size contract without inventing final N; revision/amendment protection; orchestrate all checks; strict/baseline modes; deterministic offline report.

**Independent Test**: Full non-strict validation on demo margins exits 0 with digests and deferred work. Strict with unresolved decisions exits 1. Baseline detects frozen-policy change under same version. Two runs identical excluding timestamps.

### Implementation for User Story 5

- [x] T031 [US5] Implement `check_sample_size_handoff()` in `tools/margins_validator.py` — required handoff fields; `final_n` must be null; flag power-against-zero used to justify exceeding d_min; underpowered/mismatch explicit (FV-SPEC-064)
- [x] T032 [US5] Implement `check_revision_protection()` / `check_baseline_comparison()` in `tools/margins_validator.py` — compare baseline suite; changed frozen policy under unchanged version fails; missing amendment authorization disallows confirmatory claim metadata (FV-SPEC-065)
- [x] T033 [US5] Implement `check_strict_mode()` and top-level `validate_margins()` in `tools/margins_validator.py` — orchestrate FV-SPEC-057–066 in order; aggregate report; strict requires resolved applicable decisions, current reviews, consistent cross-file policies; list deferred P0-6/P0-7/P2-6/P4 in non-strict (FV-SPEC-066)
- [x] T034 [P] [US5] Create fixtures: `tests/fixtures/margins_spec/valid/sample_size_handoff.yaml` (or block within minimal), `tests/fixtures/margins_spec/invalid/invented_final_n.yaml`, `tests/fixtures/margins_spec/invalid/power_against_zero.yaml`, `tests/fixtures/margins_spec/valid/strict_margins.yaml` + matching approvals/reviews with resolved decisions for strict-path unit tests where applicable
- [x] T035 [US5] Write `tests/test_margins_spec.py::TestFvSpec064Power` — valid handoff passes; invented final_n fails; power-against-zero vs d_min flagged
- [x] T036 [US5] Write `tests/test_margins_spec.py::TestFvSpec065Revision` — baseline match passes; policy change without version bump fails; missing amendment disallows confirmatory claim
- [x] T037 [US5] Write `tests/test_margins_spec.py::TestFvSpec066ScopedCli` — demo validation exit 0; strict unresolved exit 1; malformed exit 2; report required fields; deferred listed non-strict; deterministic replay excluding timestamps; zero model/GPU/threshold-fitting confirmed by offline-only path

**Checkpoint**: US5 complete — full pipeline works, all 10 test classes pass, strict/baseline verified.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Regression checks, demonstration run, deterministic replay

- [x] T038 Run existing P0-1–P0-4 suites (`uv run pytest tests/test_contract_schema.py tests/test_closure_templates.py tests/test_attack_spec.py tests/test_access_profile.py -v`) to confirm no regressions from P0-5 CLI changes
- [x] T039 [P] Run full P0-5 suite (`uv run pytest tests/test_margins_spec.py -v`) and confirm all tests pass
- [x] T040 Run demonstration validation: `uv run python tools/validate_spec.py --scope margins --spec-root .factverify/spec --report reports/p0-5-validation.json` and confirm clean non-strict exit with digests + deferred work listed
- [x] T041 Run deterministic replay: execute demonstration validation twice writing `reports/p0-5-validation.json` and `reports/p0-5-validation-replay.json`, compare excluding timestamps, confirm identical output

**Checkpoint**: All tests green, no regressions, deterministic output verified.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — CLI + artifact validation MVP
- **User Story 2 (Phase 4)**: Depends on US1 (needs loaded margins + report path)
- **User Story 3 (Phase 5)**: Depends on US1 (needs estimand/selection fields present)
- **User Story 4 (Phase 6)**: Depends on US1; benefits from US3 estimands; can start after US1 checkpoint in parallel with US2/US3 if staffing allows
- **User Story 5 (Phase 7)**: Depends on US1–US4 (orchestrates all checks, strict/baseline)
- **Polish (Phase 8)**: Depends on all user stories complete

### User Story Dependencies

- **US1 (P1)**: Foundation only — MVP deliverable
- **US2 (P2)**: US1 — approvals attach to validated fields
- **US3 (P3)**: US1 — estimands/selection on loaded artifact
- **US4 (P4)**: US1 — effect/uncertainty/coverage; parallelizable with US2/US3 after US1
- **US5 (P5)**: US1–US4 — integration layer last

### Within Each User Story

- Validation functions before fixtures that assert them (or fixtures first when defining inputs for TDD)
- Negative fixtures before test classes
- Test classes cover positive and negative paths named per FV-SPEC hooks

### Parallel Opportunities

- T002 and T003 in Setup
- T005 in Foundational (with T004/T006 sequential for shared module)
- T011, T015, T016, T021, T027, T034 fixture batches marked [P]
- After US1 checkpoint: US2, US3, US4 can proceed in parallel
- T038 and T039 in Polish (different suites)

---

## Parallel Example: After US1 Checkpoint

```bash
# US2: approvals (T014–T018)
# US3: estimands + calibration (T019–T023)
# US4: effect + uncertainty + coverage (T024–T030)
# Then US5 orchestration (T031–T037)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Foundational (T004–T006)
3. Complete Phase 3: User Story 1 (T007–T013)
4. **STOP and VALIDATE**: `uv run pytest tests/test_margins_spec.py::TestFvSpec057Artifact -v`
5. Demo margins validate structurally with clean non-strict report

### Incremental Delivery

1. Setup + Foundational → infrastructure ready
2. US1 → margins contract validated (MVP)
3. US2 → approval gate for policy values
4. US3 → estimands + calibration selection contract
5. US4 → practical success, uncertainty, channel/locality coverage
6. US5 → sample-size handoff, revision protection, full CLI/strict/baseline
7. Polish → regressions + deterministic replay

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Build against **named fields and decision IDs** — never freeze illustrative α = 0.05 without approval
- Follows P0-4 pattern: thin CLI in `validate_spec.py`, engine in `margins_validator.py`
- All validation is offline — zero model/GPU/threshold-fitting/bootstrap execution
- Test naming: `TestFvSpec057Artifact` through `TestFvSpec066ScopedCli`
- Null policy values mean unresolved, not zero tolerance
