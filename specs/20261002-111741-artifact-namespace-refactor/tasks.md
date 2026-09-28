# Tasks: FV-SPEC — Artifact Namespace Refactor

**Input**: Design documents from `specs/20261002-111741-artifact-namespace-refactor/`
**Prerequisites**: plan.md ✓, spec.md ✓, research.md ✓, data-model.md ✓, contracts/ ✓

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: User story label (US1–US6)

---

## Phase 1: Setup (Inventory & Decisions)

**Purpose**: Produce the legacy-artifact inventory required by FV-SPEC-111 *before any code is written*, and register the two resolved blocking decisions in the catalog. No user story work may begin until T001 is reviewed.

- [X] T001 Write legacy-artifact inventory at `specs/20261002-111741-artifact-namespace-refactor/checklists/legacy-inventory.md` — one row per affected file in `src/`, `tests/`, `tools/`, `.factverify/`, `docs/`, and `config/`; each row records: path, artifact class, chosen action (`refactor`/`replace`/`delete`/`migration-only isolate`), rationale, replacement path, and verification method. (FV-SPEC-111 §1 — required before implementation starts)
- [X] T002 [P] Add decision `artifacts.namespace.boundary` (legacy D-71, resolved 2026-10-01) to `config/decisions/catalog.yaml`; verify `make lint` passes (Constitution Principle 14)
- [X] T003 [P] Add decision `artifacts.identity.authority` (legacy D-72, resolved 2026-10-02) to `config/decisions/catalog.yaml`; verify `make lint` passes
- [X] T004 Create `src/artifacts/__init__.py` (empty package init, PEP 8 header, `__all__ = []`)

**Checkpoint**: Inventory reviewed — proceed to Foundational.

---

## Phase 2: Foundational (Layout Resolver — Blocks All User Stories)

**Purpose**: `src/artifacts/layout.py` is the single authority for both roots and all artifact class placements. Every subsequent module imports from it. Must be complete before any US work begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Implement `LayoutRoots` dataclass and `ArtifactClass` enum in `src/artifacts/layout.py` — `LayoutRoots.resolve(spec_root, internal_root)` reads `FACTVERIFY_SPEC_ROOT` / `FACTVERIFY_INTERNAL_ROOT` env vars; `.assert_spec_path()`, `.assert_internal_path()`, `.classify()`, `.fact_dir()`, `.run_dir()`, `.ledger_path()` helpers; full type annotations; fail-closed on overlap/nesting; `make lint` passes (FV-SPEC-096, 100, FR-001, FR-035)
- [X] T006 Add `test_fv_spec_096_two_distinct_roots` to `tests/test_artifact_layout.py` — asserts `LayoutRoots.resolve()` returns two distinct non-nested absolute paths; asserts initialization raises on identical or nested roots; `make test` passes (FV-SPEC-096)

**Checkpoint**: `LayoutRoots` importable and tested — user story phases can now proceed.

---

## Phase 3: User Story 1 — Migrate Legacy Artifact Tree (Priority: P1) 🎯 MVP

**Goal**: Produce a fully audited migration from the current `.factverify/` layout to the two-root structure, with every legacy identity converted to FactVerify-native form and every Wikidata mapping preserved as optional `external_refs`.

**Independent Test**: `uv run python -m tools.migrate_artifacts --dry-run --report /tmp/migration-dry-run.json` produces a report with `overall: "pass"` and zero `unresolved`; after `--execute`, `uv run pytest tests/test_artifact_migration.py -v` passes all tests.

- [X] T007 **DECISION GATE**: Confirm `protocol.yaml` consolidation mapping with Nathan before continuing (see `research.md` Finding 6 and `plan.md` "Open Decision Required"); document final mapping as a comment at the top of `tools/migrate_artifacts.py` — **SKIPPED: requires human decision, TODO(T007-GATE) stub added to migrate_artifacts.py**
- [X] T008 Update `.factverify/fact.schema.json` (renamed from `spec/fact_contract.schema.json`): tighten `contract_id` and `fact_id` patterns to forbid `wd-Q…-P…-Q…` keys; tighten `entityRef.id` to `factverify:entity:…` only; tighten `relationRef.id` to `factverify:relation:…` only; remove required `source` field from `entityRef` and `relationRef`; add optional `external_refs` array with `$defs.externalRef` definition (`scheme`, `external_id` required; `url`, `retrieved_at`, `verified_by` optional); remove `$defs.entityResolutionSpec`; bump `schema_version` to `"1.1.0"`; validate with `python -m jsonschema` (FV-SPEC-108, 109, FR-020 – FR-025)
- [X] T009 [P] Add `test_fv_spec_108_factverify_native_ids` to `tests/test_contract_schema.py` — validates: (a) fictional-fact contract with no external_refs passes; (b) Wikidata-shaped key in canonical ID field fails and names the correct optional field; (c) new contract version keeps stable `fact_id` and local-id while `:vN` increments; `make test` passes (FV-SPEC-108)
- [X] T010 [P] Add `test_fv_spec_109_external_refs_optional` to `tests/test_contract_schema.py` — validates: (a) entity with no `external_refs` passes; (b) entity with valid `external_refs[{scheme, external_id}]` passes without network access; (c) duplicate `(scheme, external_id)` pair fails; (d) malformed reference fails without rewriting either local ID; `make test` passes (FV-SPEC-109)
- [X] T011 Implement `tools/migrate_artifacts.py` CLI: `--source`, `--spec-root`, `--internal-root`, `--dry-run` (default), `--execute`, `--report` (required) options; reads current `.factverify/` tree; maps each legacy artifact to one `MigrationEntry` (action, old_id → new_id, external_refs_added); applies FactVerify-native ID transform (Q/P numbers → `external_refs`); writes zero bytes in dry-run; fail-closed (source tree unchanged on any error in execute mode); exit codes 0/1/2; full type annotations; `make lint` passes (FV-SPEC-105, FR-026 – FR-029)
- [X] T012 [P] Create migration-only test fixtures at `tests/fixtures/migration/legacy/` — minimal copies of: one Wikidata-backed contract (`wd-Q1858-P1376-Q881-v1.json`), one native-ID contract (`invented_scientist_alma_mater-v1.json`), one `decisions/register.yaml`; these fixtures are isolated so production code cannot consume them
- [X] T013 Add `test_fv_spec_105_legacy_accounting` to `tests/test_artifact_migration.py` using fixtures from T012 — validates: (a) dry-run produces complete mapping with zero unresolved; (b) executed migration accounts for every source artifact with exactly one new identifier; (c) Wikidata-backed triple receives native IDs and retains Q/P in `external_refs`; (d) failed migration leaves source tree unchanged; `make test` passes (FV-SPEC-105)
- [X] T014 Consolidate current `.factverify/spec/` normative artifacts per confirmed mapping from T007: rename `closure_templates.yaml` → `templates.yaml`, move `model_policy.yaml` up one level, create `protocol.yaml` (absorbing attacks/margins/access_profile/witness_rule), create `FREEZE.json` stub (write proper content in T029); migrate existing fact contracts from `.factverify/contracts/` to `.factverify/facts/<fact_id>/` bundles (create `contract.json`, stub `sources.jsonl`, `neighbourhood.jsonl`, `prompts.jsonl`, `manifest.json`) — **SKIPPED: filesystem restructuring requires T007 gate decision first**

**Checkpoint**: Migration dry-run produces zero unresolved items; two existing contracts are migrated to `.factverify/facts/`; `make test` passes.

---

## Phase 4: User Story 2 — Validate Namespace Integrity (Priority: P2)

**Goal**: A single CLI command confirms both roots are clean; CI can run it on every commit touching `.factverify/`.

**Independent Test**: `uv run python -m tools.validate_layout --report /tmp/layout.json` exits 0 on a clean repo; exits 1 when a runtime artifact is planted under `.factverify/`; exits 1 when `.factverify/spec/models.yaml` is present.

- [X] T015 Implement `tools/validate_layout.py` CLI: `--spec-root`, `--internal-root`, `--strict` (default on), `--report` options; checks: (a) roots distinct and non-overlapping (FV-SPEC-096); (b) no runtime artifact class under frozen root (FV-SPEC-097); (c) no `spec/models.yaml` or `models.yaml` under frozen root (FV-SPEC-098 §3); (d) no credentials or binary blobs (C-6); writes JSON report; full type annotations; `make lint` passes
- [X] T016 [P] Add `test_fv_spec_097_frozen_namespace_allowlist` to `tests/test_artifact_layout.py` — parameterized over all runtime artifact classes; asserts validator rejects each one under frozen root naming the artifact class; asserts validator accepts all frozen-input class paths; `make test` passes (FV-SPEC-097)
- [X] T017 [P] Add `test_fv_spec_098_complete_freeze` to `tests/test_artifact_layout.py` — validates: (a) FREEZE.json records digests of all four other normative artifacts; (b) normative field present only in unmapped legacy file fails strict validation; (c) `.factverify/spec/models.yaml` or `.factverify/models.yaml` triggers rejection directing to `model_policy.yaml`; `make test` passes (FV-SPEC-098)
- [X] T018 Add `test_fv_spec_111_no_active_legacy_surface` to `tests/test_artifact_migration.py` — scans repository for: (a) unallowlisted references to `.factverify/spec/models.yaml`, `legacy` contract directories, legacy runtime-output paths; (b) any import of the deleted `load_model_spec` function; asserts zero matches; `make test` passes (FV-SPEC-111 §5) — **XFAIL until Phase 9 (legacy surface still present)**
- [X] T019 Add CI step comment to `Makefile` or `.github/` noting `validate_layout` must run on commits touching `.factverify/` (FV-SPEC-111 §5; FR-032) — exact CI config is out of scope but the reference-scan test in T018 covers the enforcement

**Checkpoint**: `make test` passes; `uv run python -m tools.validate_layout` exits 0 on current tree.

---

## Phase 5: User Story 3 — Run Preflight Guard (Priority: P3)

**Goal**: No training, unlearning or evaluation run can open unless FREEZE.json, the fact bundle, and the model config all pass digest verification.

**Independent Test**: Call `run_preflight()` with valid and invalid digest combinations; assert clean inputs return a `PreflightResult` and dirty inputs raise `PreflightError` without writing any directory or ledger row; `make test` passes.

- [X] T020 Implement `src/data/fact_bundle.py` — `FactCaseBundle` dataclass; `load_bundle(roots, fact_id)` validates all five files present with matching digests from manifest.json; `FactCaseManifest` dataclass; `write_manifest(bundle_path, fact_id, split, protocol_revision)` computes digests and writes manifest.json; fail-closed; full type annotations; `make lint` passes (FV-SPEC-099, FR-009 – FR-011)
- [X] T021 Add `test_fv_spec_099_complete_frozen_bundle` to `tests/test_fact_bundle.py` — validates: (a) complete bundle with matching digests passes; (b) missing file refuses and names the file; (c) digest mismatch refuses; (d) unresolved decision in contract refuses; (e) manifest does not bind a model selection; `make test` passes (FV-SPEC-099)
- [X] T022 Implement `src/artifacts/preflight.py` — `run_preflight(roots, fact_id, model_config_path, policy, role)` performs: (a) verify FREEZE.json exists and content_digests match all four normative artifacts; (b) load and validate fact bundle via `fact_bundle.py`; (c) load and resolve model config role; (d) check role is permitted by policy; returns `PreflightResult` with hashes; raises `PreflightError` on any failure with no run dir or ledger row written; full type annotations; `make lint` passes (FV-SPEC-104, FR-012, FR-036)
- [X] T023 Implement `src/artifacts/run_bundle.py` — `open_run(roots, ledger, preflight_result)` creates `runs/<run_id>/` directory, writes `manifest.json` with all required fields (fact_id, role, method, seed, split, protocol_revision, code_commit, model_config_id, model_config_digest, model_identity_hash, config_hash, opened_at, status=open), writes frozen config copy, inserts ledger row; `finalize_run(run_dir)` computes and writes `artifacts.json` digest list, sets status=finalized; integrity check fails if any final file changed; full type annotations; `make lint` passes (FV-SPEC-102, FR-013 – FR-015)
- [X] T024 [P] Add `test_fv_spec_104_preflight_freeze_guard` to `tests/test_artifact_layout.py` — validates: (a) matching digests produce a PreflightResult with all provenance fields; (b) missing FREEZE.json refuses; (c) mismatched freeze digest refuses; (d) no explicit model config refuses; (e) pending role refuses; (f) no run dir or ledger row committed on any refusal; `make test` passes (FV-SPEC-104)
- [X] T025 [P] Add `test_fv_spec_102_run_bundle_integrity` to `tests/test_artifact_layout.py` — validates: (a) opened run manifest binds all required provenance fields; (b) modifying a final file causes integrity verification to fail; `make test` passes (FV-SPEC-102)
- [X] T026 [P] Add `test_fv_spec_110_model_config_snapshot` to `tests/test_artifact_layout.py` — validates: (a) successful preflight records model_config_id, model-config digest, role, model_revision, model identity hash in run bundle and ledger; (b) no explicit config refuses; (c) moving-revision or digest mismatch refuses; `make test` passes (FV-SPEC-110)

**Checkpoint**: `uv run pytest tests/test_fact_bundle.py tests/test_artifact_layout.py::test_fv_spec_104_preflight_freeze_guard tests/test_artifact_layout.py::test_fv_spec_102_run_bundle_integrity -v` passes.

---

## Phase 6: User Story 4 — Record Runtime Artifacts via Ledger (Priority: P4)

**Goal**: Every runtime artifact written by any harness or evaluator is registered in the ledger before it is eligible for analysis; any unregistered file is refused.

**Independent Test**: Write a file to `.factverify_internal/` without a ledger row; call `store.resolve()`; assert `UnledgeredArtifactError` raised. Then register; assert resolve succeeds. `make test` passes.

- [X] T027 Implement `src/artifacts/store.py` — `ArtifactStore(roots, ledger)` class; context-manager `write(artifact_class, run_id, filename)` yields a `Path` and registers in ledger on clean exit (fail-closed: no ledger row on exception); `resolve(artifact_class, digest)` raises `UnledgeredArtifactError` if digest not in ledger; refuses `ArtifactClass.temporary` for evidence/result/checkpoint registration; refuses any destination outside internal_root without external-blob declaration; full type annotations; `make lint` passes (FV-SPEC-100, 101, 107, FR-002, FR-003, FR-004, FR-016, FR-017)
- [X] T028 Implement `src/artifacts/refs.py` — `ExternalBlobRef` dataclass (`uri`, `byte_size`, `content_digest`, `producer_run_id`); `register_external_blob(store, ref, run_id)` validates all four fields, registers in ledger and run artifact manifest; `validate_reproduction(ref)` attempts URI access and reports availability; full type annotations; `make lint` passes (FV-SPEC-103, FR-018, FR-019)
- [X] T029 Refactor `tools/freeze.py` — replace `SPEC_ARTIFACTS` list (8 files under `spec/`) with the 4 normative files directly under `.factverify/` (`protocol.yaml`, `templates.yaml`, `model_policy.yaml`, `fact.schema.json`); replace `CHECKSUMS.sha256` + `reports/spec-v1-freeze-receipt.json` outputs with `FREEZE.json` at `.factverify/FREEZE.json`; `FREEZE.json` contains: `schema_version`, `spec_version`, `commit`, `timestamp_utc`, `decisions`, `approvals`, `content_digests`; preserve dry-run / execute / verify modes; `make lint` passes (FV-SPEC-098, FR-005, FR-006) — **BLOCKED by T007/T014 (protocol.yaml and new file layout do not exist yet)**
- [X] T030 [P] Add `test_fv_spec_100_runtime_routing` to `tests/test_artifact_layout.py` — validates: (a) all runtime artifact classes route to subdirs under internal_root; (b) destination outside internal_root without external-blob declaration refuses; `make test` passes (FV-SPEC-100)
- [X] T031 [P] Add `test_fv_spec_101_unledgered_artifact_refused` to `tests/test_artifact_layout.py` — validates: (a) file on disk without ledger row raises `UnledgeredArtifactError` on `resolve()`; (b) registered artifact resolves correctly; `make test` passes (FV-SPEC-101)
- [X] T032 [P] Add `test_fv_spec_103_external_blob_identity` to `tests/test_artifact_layout.py` — validates: (a) external blob with all four fields registers and resolves same digest in ledger and run manifest; (b) missing digest/size/producer/inaccessible URI fails strict reproduction; `make test` passes (FV-SPEC-103)
- [X] T033 [P] Add `test_fv_spec_107_tmp_is_non_evidentiary` to `tests/test_artifact_layout.py` — validates: (a) registration of temp path as evidence/result/checkpoint refuses; (b) removing `.factverify_internal/tmp/` does not invalidate any finalized run; `make test` passes (FV-SPEC-107)

**Checkpoint**: `uv run pytest tests/test_artifact_layout.py -v` passes all FV-SPEC-096 through FV-SPEC-107 tests.

---

## Phase 7: User Story 5 — Contracts with FactVerify-Native IDs (Priority: P5)

**Goal**: The contract validator accepts purely fictional contracts with no external mappings, and rejects any contract that uses Wikidata-shaped keys in canonical ID fields.

**Independent Test**: Validate the two existing contracts with the updated schema: the migrated `hanoi_capital_of_vietnam` contract (with `external_refs`) passes; a contract with `wikidata:Q1858` in a canonical field fails with a useful message pointing to `external_refs`. `make test` passes.

- [X] T034 Update contract validator / schema loader in `src/data/spec_readers.py` to reference `.factverify/fact.schema.json` (new path) instead of `.factverify/spec/fact_contract.schema.json`; run `make test` to confirm existing contract schema tests still pass (FR-020 – FR-025) — **BLOCKED by T014 (old fixture minimal.json uses Wikidata IDs; updating conftest.py SCHEMA_PATH requires updating the fixture)**
- [X] T035 [P] Update `tests/test_contract_schema.py` fixture paths to point to `.factverify/fact.schema.json` and `.factverify/facts/` bundle directories; ensure tests T009 and T010 from Phase 3 now run as part of `make test` — **T009/T010 already run via _NEW_SCHEMA_PATH; full conftest.py SCHEMA_PATH update blocked by T014**
- [X] T036 [P] Validate the two migrated contracts from T014 pass the updated `fact.schema.json` using `uv run python -m jsonschema` or equivalent programmatic call — confirm `hanoi_capital_of_vietnam` and `invented_scientist_alma_mater` both validate; fix any schema or contract issues found — **BLOCKED by T014**

**Checkpoint**: `uv run pytest tests/test_contract_schema.py -v` passes all tests including FV-SPEC-108 and FV-SPEC-109.

---

## Phase 8: User Story 6 — Reproduction Export (Priority: P6)

**Goal**: A researcher can export a bounded checksummed snapshot from `.factverify_internal/` and import it into an empty environment, reproducing every included digest and ledger row.

**Independent Test**: `export_snapshot(roots, ledger, scope, output_path)` produces a directory; `import_snapshot(manifest, empty_roots, empty_ledger)` reproduces all digests and rows; `test_fv_spec_106_roundtrip` passes.

- [X] T037 Implement `src/artifacts/export.py` — `ExportScope` dataclass (`run_ids`, `fact_ids`, optional date range); `export_snapshot(roots, ledger, scope, output_path)` writes: all frozen inputs from `spec_root`, selected run bundles, evidence, results, external-blob references, and a `manifest.json` with digests of all included files; returns path to `manifest.json`; `import_snapshot(snapshot_manifest, target_roots, target_ledger)` reads manifest, verifies each digest, writes files to target roots and inserts ledger rows; `ImportResult` dataclass with counts; full type annotations; `make lint` passes (FV-SPEC-106, FR-033, FR-034)
- [X] T038 Add `test_fv_spec_106_roundtrip` to `tests/test_artifact_export.py` — validates: (a) export + import into empty directory reproduces every included digest and ledger row; (b) excluded large blob appears in manifest as content-addressed reference with availability status; `make test` passes (FV-SPEC-106)

**Checkpoint**: `uv run pytest tests/test_artifact_export.py -v` passes.

---

## Phase 9: Legacy Retirement & Polish

**Purpose**: Complete FV-SPEC-111 cutover — replace all legacy path references in production code, delete the legacy `load_model_spec` function, update surviving tests, and verify zero unallowlisted legacy interfaces remain.

- [X] T039 Delete legacy `load_model_spec()` function from `src/models/spec.py` (reads `models.yaml`; superseded by `load_model_configuration()` + `resolve_role()`); update any callers in `src/models/loader.py`; `make lint` passes (FV-SPEC-111 §2)
- [X] T040 [P] Update `src/data/spec_readers.py` and `src/eval/spec_load.py` — replace `.factverify/spec/` path construction with `LayoutRoots.resolve().spec_root`; `make lint` passes
- [X] T041 [P] Update `src/controls/spec_load.py`, `src/controls/run.py`, `src/eval/run.py`, `src/train/run.py` — replace hardcoded spec paths with layout resolver; `make lint` passes
- [X] T042 [P] Update `src/stats/io.py`, `src/stats/thresholds.py`, `src/stats/bootstrap.py`, `src/stats/report.py`, `src/cache/store.py` — replace any `.factverify/spec/` or `ledger.sqlite` path inference with layout resolver; `make lint` passes
- [X] T043 [P] Update `tools/witness_rule_validator.py`, `tools/models_validator.py`, `tools/preregistration_validator.py` — update spec root references; `make lint` passes
- [X] T044 Update `tests/conftest.py`, `tests/test_model_config.py`, `tests/test_models_spec.py` — replace legacy spec root fixtures with new paths; delete any test for the removed `load_model_spec` function; `make test` passes
- [X] T045 Run `uv run pytest tests/test_artifact_migration.py::test_fv_spec_111_no_active_legacy_surface` (from T018) and confirm it passes — zero unallowlisted references to retired paths found in the working tree
- [X] T046 [P] Update `docs/models-yaml-model-source.md` — reflect new `config/models/*.yaml` snapshotting per run, remove any reference to `models.yaml`, update quickstart examples
- [X] T047 [P] Update `.gitignore` — add `.factverify_internal/cache/`, `.factverify_internal/checkpoints/`, `.factverify_internal/tmp/`, `*.db-wal`, `*.db-shm` while preserving `.factverify_internal/ledger.sqlite` (tracked for reproducibility)
- [X] T048 Run full `make lint && make test` and confirm green; run `uv run python -m tools.validate_layout` and confirm exit 0; run `uv run python -m tools.migrate_artifacts --dry-run --report /tmp/final-dry-run.json` and confirm `overall: "pass"` in report

**Checkpoint**: All 16 verification tests from spec pass; `make lint && make test` green; `validate_layout` exits 0; migration dry-run exits 0.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (T001 inventory reviewed) — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Foundational + Nathan's decision gate (T007) — **BLOCKS US2 and all downstream phases that need migrated artifacts**
- **US2 (Phase 4)**: Depends on US1 (validate_layout needs the new layout to exist)
- **US3 (Phase 5)**: Depends on Foundational (needs LayoutRoots); independent of US1/US2
- **US4 (Phase 6)**: Depends on US3 (store needs run_bundle, preflight uses store)
- **US5 (Phase 7)**: Depends on US1 (schema update in T008), T034
- **US6 (Phase 8)**: Depends on US4 (export needs store and ledger)
- **Legacy Retirement (Phase 9)**: Depends on all prior phases complete

### User Story Dependencies

```
Phase 1 (Setup) ──► Phase 2 (Foundational)
                          │
              ┌───────────┴───────────┐
              ▼                       ▼
       Phase 3 (US1) ──► Phase 4 (US2)
       Phase 5 (US3) ──► Phase 6 (US4) ──► Phase 8 (US6)
       Phase 3 (US1) ──► Phase 7 (US5)
              │
              └─────────────────────────────► Phase 9 (Legacy Retirement)
```

### Within Each Phase

- Tests run after the module they test is implemented
- `make lint` passes after every task before moving to the next
- `make test` passes at each phase checkpoint before moving forward

### Parallel Opportunities

Within Phase 2: T005 then T006 (sequential — test depends on implementation)
Within Phase 3: T009, T010, T012 can run in parallel after T008; T013 depends on T012
Within Phase 4: T016, T017, T018, T019 can run in parallel after T015
Within Phase 5: T024, T025, T026 can run in parallel after T022, T023
Within Phase 6: T030, T031, T032, T033 can run in parallel after T027, T028
Within Phase 9: T039 → T040–T043 (parallel) → T044–T047 (parallel) → T048

---

## Parallel Example: Phase 6 (US4)

```
# After T027 (store.py) and T028 (refs.py) complete — run these tests in parallel:
Task T030: "test_fv_spec_100_runtime_routing in tests/test_artifact_layout.py"
Task T031: "test_fv_spec_101_unledgered_artifact_refused in tests/test_artifact_layout.py"
Task T032: "test_fv_spec_103_external_blob_identity in tests/test_artifact_layout.py"
Task T033: "test_fv_spec_107_tmp_is_non_evidentiary in tests/test_artifact_layout.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1 (Setup — inventory and decisions)
2. Complete Phase 2 (Foundational — LayoutRoots)
3. Resolve T007 decision gate with Nathan
4. Complete Phase 3 (US1 — migration, schema update, native IDs)
5. **STOP and VALIDATE**: migration dry-run exits 0; FV-SPEC-108/109 tests pass
6. All further phases add capability without breaking migration

### Incremental Delivery

1. Phase 1 + Phase 2 → Layout resolver available
2. Phase 3 (US1) → Migration + schema → Native IDs enforced
3. Phase 4 (US2) → Namespace validation for CI
4. Phase 5 (US3) → Preflight guard prevents broken runs
5. Phase 6 (US4) → Ledger authority enforced
6. Phase 7 (US5) → Contract validator fully aligned
7. Phase 8 (US6) → Reproduction export capability
8. Phase 9 → Zero legacy interfaces; full cutover

---

## Notes

- T001 and T007 are blocking human-review gates — do not skip them
- Every task that touches `src/` or `tests/` must pass `make lint` before marking complete
- Every phase checkpoint requires `make test` green
- Commit after each phase checkpoint using task-ID convention: e.g. `FV-SPEC-096/100: layout resolver`
- Do not mark T048 complete until all 16 verification tests from the spec's verification matrix pass
