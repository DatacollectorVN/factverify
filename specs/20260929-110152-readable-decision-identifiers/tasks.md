---

description: "Task list for readable-decision-identifiers"
---

# Tasks: Readable Decision Identifiers

**Input**: Design documents from `/specs/20260929-110152-readable-decision-identifiers/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/decisions-api.md ✅

**Tests**: Included — spec acceptance criteria and constitution require regression tests for collision coverage.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

> **Implementation note — priority vs dependency order**: US2 (Single-Source Lookup, P2)
> is implemented before US1 (Actionable Diagnostics, P1) because the catalog and resolver
> are blocking prerequisites for the diagnostic formatter. US1 delivers the visible user value;
> US2 is the structural foundation that makes it possible.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1–US4)
- Include exact file paths in all descriptions

## Path Conventions

- Single project: `src/`, `tests/`, `config/`, `tools/`, `docs/` at repository root

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new package skeleton and configuration directory.

- [ ] T001 Create `src/decisions/__init__.py` as an empty package init (exposes nothing at this stage)
- [ ] T002 Create `config/decisions/catalog.yaml` with a stub header comment and an empty `decisions: []` list

**Checkpoint**: Package skeleton exists; catalog file is present but empty.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared types and error class that every user story imports. Must be complete before any story phase begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [ ] T003 [P] Create `src/decisions/types.py` — define `DecisionCatalogEntry` (frozen dataclass: `legacy_id`, `key`, `title`, `description`, `domain`, `owner`, `consumers`, `required_fields`, `status`, `legacy_aliases`) and `DecisionDiagnostic` (frozen dataclass: `key`, `legacy_id`, `title`, `status`, `missing_field`, `consuming_op`, `owner`) per `data-model.md`
- [ ] T004 [P] Create `src/decisions/errors.py` — define `DecisionError(Exception)` with a plain string message; must NOT subclass any module-specific error
- [ ] T005 [P] Create `tests/fixtures/decisions/catalog_valid.yaml` — three-entry catalog containing `D-01`/`stats.error_rates.frr_cap`, `D-65`/`data.exclusion_gate.policy`, and `D-08` as a collision entry (`status: collision`, `key: null`) following the YAML schema in `data-model.md`
- [ ] T006 [P] Create `tests/fixtures/decisions/catalog_dup_key.yaml` — two entries that share the semantic key `data.exclusion_gate.policy` (used to test uniqueness violation detection)
- [ ] T007 [P] Create `tests/fixtures/decisions/catalog_dup_legacy.yaml` — two entries that share the legacy ID `D-65` (used to test legacy-ID collision detection)

**Checkpoint**: Foundation ready — shared types exist, error class defined, test fixtures in place.

---

## Phase 3: User Story 2 — Single-Source Decision Lookup (Priority: P2)

**Goal**: A canonical catalog that can be queried by either semantic key or legacy ID, with uniqueness validation.

> **Why before US1**: The diagnostic formatter (US1) depends on the resolver. US2 is implemented first so US1 can be completed in one pass.

**Independent Test**: Load `tests/fixtures/decisions/catalog_valid.yaml`; call `resolve("D-65", path)` and `resolve("data.exclusion_gate.policy", path)` and assert both return the same entry. Call `resolve("D-99", path)` and assert `DecisionError` is raised.

- [ ] T008 [P] [US2] Write `tests/unit/test_decisions_catalog.py` — test `load_catalog` with valid fixture (asserts three entries), missing file (raises `DecisionError`), malformed YAML (raises `DecisionError`); test `validate_catalog` with `catalog_valid.yaml` (returns `[]`), `catalog_dup_key.yaml` (returns non-empty errors list), `catalog_dup_legacy.yaml` (returns non-empty errors list)
- [ ] T009 [P] [US2] Write `tests/unit/test_decisions_resolver.py` — test `resolve` by legacy ID (`"D-65"` finds entry), by semantic key (`"data.exclusion_gate.policy"` finds same entry), not-found raises `DecisionError`; test `resolve_or_none` not-found returns `None`; test index is cached (two calls with same path do not re-read file)
- [ ] T010 [US2] Implement `src/decisions/catalog.py` — `load_catalog(catalog_path: Path) -> list[DecisionCatalogEntry]` reads YAML, validates required fields per entry, raises `DecisionError` on missing file or malformed YAML; `validate_catalog(entries: list[DecisionCatalogEntry]) -> list[str]` runs four uniqueness checks from `contracts/decisions-api.md` (duplicate `legacy_id`, duplicate non-null `key`, `legacy_aliases` clash, `status == "closed"` with null `key`) (depends T003, T004, T005)
- [ ] T011 [US2] Implement `src/decisions/resolver.py` — `resolve(identifier: str, catalog_path: Path) -> DecisionCatalogEntry` and `resolve_or_none(identifier: str, catalog_path: Path) -> DecisionCatalogEntry | None`; maintain a module-level `dict[Path, CatalogIndex]` cache keyed on the resolved path so repeated calls do not re-read the file (depends T010)
- [ ] T012 [US2] Populate `config/decisions/catalog.yaml` with all 69 entries (D-01 through D-69 including gaps/absences) following the ticket's inventory tables in `docs/tickets/readable-decision-identifiers.md`; set `status: collision` and `key: null` for D-08, D-09, D-17, D-22, D-42; set `status: absent` and `key: null` for D-30; include a human title, description, domain, owner, consumers, and required_fields for every entry (depends T010)

**Checkpoint**: US2 fully functional — catalog loads, both lookup paths work, uniqueness violations are detected and reported.

---

## Phase 4: User Story 1 — Actionable Decision Diagnostics (Priority: P1)

**Goal**: Every blocked-decision error shows semantic key, legacy ID, title, missing field, and consuming operation instead of a bare `D-*` code.

**Independent Test**: Create a YAML decision file with `status: open` for D-65. Call `load_d65(path)` from `src/data/decisions.py`. Assert the raised `DataError` message contains `"data.exclusion_gate.policy"`, `"legacy D-65"`, and `"Knowledge-exclusion gate policy"`.

- [ ] T013 [P] [US1] Write `tests/unit/test_decisions_diagnostic.py` — test `format_diagnostic` with a normal closed entry (key present), with a collision entry (key is `None`), with `missing_field` argument set, with `consuming_op` argument set, with neither optional argument; assert all expected substrings appear in the output string
- [ ] T014 [US1] Implement `src/decisions/diagnostic.py` — `format_diagnostic(entry: DecisionCatalogEntry, missing_field: str | None = None, consuming_op: str | None = None) -> str` produces the multi-line format from `contracts/decisions-api.md`; `format_diagnostic_by_id(legacy_id: str, catalog_path: Path, missing_field: str | None = None, consuming_op: str | None = None) -> str` calls the resolver and falls back to a minimal bare-ID string if the catalog cannot resolve the ID (compatibility mode) (depends T011, T012)
- [ ] T015 [P] [US1] Update `src/data/decisions.py` — in `_require_closed`, replace `raise DataError(decision_id)` with `raise DataError(format_diagnostic_by_id(decision_id, _CATALOG, consuming_op=consuming_op))` where `_CATALOG = Path(__file__).parents[2] / "config" / "decisions" / "catalog.yaml"`; add `consuming_op: str` parameter to `_require_closed`; thread correct consuming-op strings through `load_d65` (`"exclusion gate"`) and `load_d68` (`"split construction"`); also enrich `_item` not-found raise with `format_diagnostic_by_id` (depends T014)
- [ ] T016 [P] [US1] Update `src/stats/decisions.py` — in `load_decision` and `_rows`, replace all bare `raise StatsError(decision_id)` / `raise StatsError(str(decision_id))` with `raise StatsError(format_diagnostic_by_id(decision_id, _CATALOG, consuming_op="stats decision"))` using the same `_CATALOG` path pattern (depends T014)
- [ ] T017 [P] [US1] Update `src/controls/decisions.py` — replace bare control-error raises with `format_diagnostic_by_id` calls using consuming-op labels matching each decision's role (e.g. `"behaviour matching"` for D-54/D-58/D-59, `"control registry"` for D-55, `"determinism check"` for D-53, `"untouched-model check"` for D-61) (depends T014)
- [ ] T018 [P] [US1] Update `src/cache/decisions.py` — replace bare cache-error raises with `format_diagnostic_by_id("D-60", _CATALOG, consuming_op="cache key construction")` (depends T014)
- [ ] T019 [P] [US1] Update `src/ledger/decisions.py` — replace bare `LedgerError("D-56")` with `format_diagnostic_by_id("D-56", _CATALOG, consuming_op="tier assignment")` (depends T014)
- [ ] T020 [US1] Update `src/eval/spec_load.py` — in `require_closed`, resolve each open legacy ID via `resolve_or_none` and build the error message in the form `"<key> (legacy <id>)"` when a key is available, else `"<id>"` (depends T014, T011); in `require_resolved_policies`, enrich the `FactVerifyEvalError` messages the same way
- [ ] T021 [US1] Write `tests/integration/test_data_decisions.py` — using an open D-65 fixture file, call `load_d65(path)`, catch `DataError`, and assert the message contains `"data.exclusion_gate.policy"`, `"legacy D-65"`, `"Knowledge-exclusion gate policy"`, and `"exclusion gate"` (depends T015)

**Checkpoint**: US1 fully functional — no new code path emits only a bare legacy ID.

---

## Phase 5: User Story 3 — Dual-ID Traceability in Outputs (Priority: P3)

**Goal**: Newly generated ledger rows that reference a specific decision include both the semantic key and the legacy ID.

**Independent Test**: Write a ledger row that references D-56 via the updated `src/ledger/api.py`. Read the written row back from `ledger.sqlite`. Assert the row contains both `decision_id: "D-56"` and `decision_key: "ledger.checkpoints.tier_vocabulary"`.

- [ ] T022 [US3] Update `src/ledger/api.py` — wherever a row is written that contains a `decision_id` field, also write a `decision_key` field resolved via `resolve_or_none(decision_id, _CATALOG)` (returns `None` and writes `null` if not in catalog); add `_CATALOG` path constant at module top (depends T011, T012)
- [ ] T023 [P] [US3] Write `tests/integration/test_ledger_decisions.py` — write a test ledger row for D-56 via `src/ledger/api.py`, read it back, and assert the row contains `decision_key == "ledger.checkpoints.tier_vocabulary"` and `decision_id == "D-56"` (depends T022)

**Checkpoint**: US3 fully functional — ledger rows carry both identifiers for all referenced decisions.

---

## Phase 6: User Story 4 — Catalog Integrity Enforcement (Priority: P4)

**Goal**: New decision definitions without a semantic key are rejected; the reference document is deterministic and CI-verified.

**Independent Test**: Run `tools/generate_decision_ref.py --catalog config/decisions/catalog.yaml --output /tmp/ref1.md` twice. Assert the two output files are byte-identical. Run `validate_catalog(load_catalog(path))` on `config/decisions/catalog.yaml` and assert it returns `[]`.

- [ ] T024 [P] [US4] Implement `tools/generate_decision_ref.py` — reads `config/decisions/catalog.yaml`, writes a Markdown document to a `--output` path with entries sorted by `legacy_id` in ascending order; outputs one table per domain; add a `--check` flag that reads the existing output file and exits non-zero if it differs from the freshly generated content (depends T010, T012)
- [ ] T025 [P] [US4] Write `tests/integration/test_generate_decision_ref.py` — run the generator twice with a fixed catalog fixture, assert outputs are byte-identical (determinism); run once with `--check` on a stale file, assert non-zero exit (depends T024)
- [ ] T026 [US4] Add catalog validation step to `tools/validate_spec.py` (or create `tools/validate_decisions.py` if `validate_spec.py` is in the frozen spec namespace) — load catalog and call `validate_catalog`; fail with a non-zero exit and print all errors if any are returned; add a note in `docs/decision_reference.md` generation step (depends T010, T024)
- [ ] T027 [US4] Run `tools/generate_decision_ref.py` to produce the initial `docs/decision_reference.md` and commit it alongside `config/decisions/catalog.yaml` (depends T024, T012)

**Checkpoint**: US4 fully functional — new definitions without `key` rejected, reference doc auto-verifiable.

---

## Phase N: Polish & Cross-Cutting Concerns

**Purpose**: Quality, formatting, and full-suite confirmation.

- [ ] T028 [P] Run `ruff check src/decisions/ src/data/decisions.py src/stats/decisions.py src/controls/decisions.py src/cache/decisions.py src/ledger/decisions.py src/ledger/api.py src/eval/spec_load.py tools/` and fix all reported issues
- [ ] T029 [P] Run `ruff format src/decisions/ src/data/decisions.py src/stats/decisions.py src/controls/decisions.py src/cache/decisions.py src/ledger/decisions.py src/ledger/api.py src/eval/spec_load.py tools/` and apply formatting
- [ ] T030 Run `uv run pytest tests/` (full suite) and confirm zero regressions — all pre-existing tests must continue to pass with no semantic changes
- [ ] T031 Follow `specs/20260929-110152-readable-decision-identifiers/quickstart.md` steps 1–7 end-to-end to validate the complete system

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Setup — **BLOCKS all user story phases**
- **US2 (Phase 3)**: Depends on Foundational — US1, US3, US4 cannot start until US2 is done
- **US1 (Phase 4)**: Depends on US2 (Phase 3) — diagnostic formatter needs resolver + populated catalog
- **US3 (Phase 5)**: Depends on US2 (Phase 3) — resolver needed to enrich ledger rows
- **US4 (Phase 6)**: Depends on US2 (Phase 3) — catalog loader + populated catalog needed for validator and generator
- **Polish (Phase N)**: Depends on all user story phases completing

### User Story Dependencies

- **US2 (P2)**: Can start after Foundational. No dependency on other stories. **Unblocks US1, US3, US4.**
- **US1 (P1)**: Can start after US2 completes. No dependency on US3 or US4.
- **US3 (P3)**: Can start after US2 completes. Independent of US1 and US4.
- **US4 (P4)**: Can start after US2 completes. Independent of US1 and US3.

> US3 and US4 can run in parallel once US2 is complete, and both are independent of US1.

### Within Each User Story

- Tests (T008, T009, T013) should be written first and will fail until implementation is complete
- Catalog.yaml population (T012) can run in parallel with the loader/resolver implementation (T010, T011)
- Per-module updates (T015–T019) are independent of each other and can run in parallel
- T020 (eval/spec_load.py) depends on T011 (resolver) but not on T015–T019
- T022 (ledger/api.py) depends on T011 but not on the diagnostic formatter

### Parallel Opportunities

- T003 + T004 + T005 + T006 + T007 (Phase 2): all parallel
- T008 + T009 (Phase 3 tests): parallel, can be written while T010 is in progress
- T010 + T012 (catalog loader + populate catalog.yaml): T012 can start in parallel once T010 schema is agreed
- T013 (Phase 4 test): can be written against the expected interface while T014 is in progress
- T015 + T016 + T017 + T018 + T019 (per-module updates): all parallel once T014 is done
- T022 + T024 (Phase 5 ledger + Phase 6 generator): parallel once US2 complete
- T028 + T029 (ruff check + format): parallel

---

## Parallel Example: Phase 3 (US2)

```bash
# Launch tests and implementation in parallel:
Task: "Write tests/unit/test_decisions_catalog.py (T008)"
Task: "Write tests/unit/test_decisions_resolver.py (T009)"
# (both can run while T010 is being implemented)

# After T010 is complete:
Task: "Implement src/decisions/resolver.py (T011)"
Task: "Populate config/decisions/catalog.yaml (T012)"
```

## Parallel Example: Phase 4 (US1)

```bash
# After T014 (diagnostic.py) is complete, launch all module updates together:
Task: "Update src/data/decisions.py (T015)"
Task: "Update src/stats/decisions.py (T016)"
Task: "Update src/controls/decisions.py (T017)"
Task: "Update src/cache/decisions.py (T018)"
Task: "Update src/ledger/decisions.py (T019)"
# T020 (eval/spec_load.py) is separate — depends on resolver (T011) not formatter
```

---

## Implementation Strategy

### MVP First (US2 + US1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational
3. Complete Phase 3: US2 (catalog + resolver)
4. Complete Phase 4: US1 (diagnostics + per-module updates)
5. **STOP and VALIDATE**: trigger an open-decision error and confirm enriched message
6. Deploy / share with team

### Incremental Delivery

1. Setup + Foundational → skeleton in place
2. US2 → catalog queryable, uniqueness enforced at load time
3. US1 → all 7 modules emit actionable diagnostics (visible user value delivered)
4. US3 → ledger rows carry both IDs (audit completeness)
5. US4 → CI rejects invalid definitions, reference doc auto-maintained

### Parallel Team Strategy (if applicable)

Once US2 is complete:
- Developer A: US1 (diagnostic formatter + 7 module updates)
- Developer B: US3 (ledger dual-ID) + US4 (validator + reference doc generator)
Both streams are independent after US2.

---

## Notes

- `[P]` tasks = different files, no incomplete-task dependencies
- `[Story]` label maps task to the spec.md user story for traceability
- The priority ordering (US1=P1, US2=P2) reflects business value; the implementation ordering (US2 before US1) reflects technical dependency — this inversion is documented in the dependencies section
- All `_CATALOG` constants use `Path(__file__).parents[N] / "config" / "decisions" / "catalog.yaml"` — adjust `N` based on module depth
- Legacy-only YAML decision files (`decision_id: D-65`, no `decision_key`) must continue to parse without error; the module loaders are NOT changed to require `decision_key`
- The five collision IDs (D-08, D-09, D-17, D-22, D-42) get `status: collision`, `key: null` entries in the catalog — the resolver and formatter handle them specially (see `contracts/decisions-api.md`)
- Never edit files under `.factverify/spec/` or `spec-unlearning/` — this is a hard constitution constraint
