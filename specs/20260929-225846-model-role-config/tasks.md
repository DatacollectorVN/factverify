# Tasks: Model Role Names and Versioned Model Configuration

**Input**: Design documents from `specs/20260929-225846-model-role-config/`
**Feature**: `20260929-225846-model-role-config`
**Branch**: `main` (spec slug only; do not create a git branch)

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Included. The ticket acceptance criteria and `quickstart.md` require pytest coverage of new names, old names, alias conflicts, config tampering, identity versions, and downstream binding.

**Design notes** (read from disk; Obsidian MCP was unavailable): execution plan is `status: planned` (P0-8, P6-8). FV-SPEC — P0-8 and FV-MODEL — P2-0 are `status: draft`. Do not edit `.factverify/spec/models.yaml`. Do not create a git tag. Do not set `AMD-001` `authorized: true`. Do not `git commit`; suggest a message the user can run.

## Format: `[ID] [P?] [Story?] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: User story label (US1–US7) — required on story phases only

---

## Phase 1: Setup

**Purpose**: Immutability baseline and the new test module. No parser yet.

- [X] T001 Compute the SHA-256 hex digest of `.factverify/spec/models.yaml` with a binary read and write only that hex line to `tests/fixtures/models_config/models_yaml_sha256.txt`. Do not modify `.factverify/spec/models.yaml`.
- [X] T002 [P] Create `tests/test_model_config.py` with a module docstring pointing at `specs/20260929-225846-model-role-config/spec.md`. Import `pytest` and `pathlib.Path` only.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Shared document types. Story phases add rules, files, and callers.

**⚠️ CRITICAL**: No US1–US7 implementation starts until this phase is complete.

- [X] T003 Add frozen dataclasses `ModelPolicy`, `RoleRequirement`, `ModelConfiguration`, `RoleEntry`, and `ResolvedRole` to `src/models/spec.py`, plus `config_digest(path: Path) -> str` returning `sha256:` + the hex from `src.data.digests.sha256_file`. Add `load_model_policy(spec_root: Path) -> ModelPolicy` and `load_model_configuration(path: Path) -> ModelConfiguration` that require `schema_version: "1"` and a top-level `roles` mapping. Raise `FactVerifyLoaderError` when role names sit at the document root or a role entry uses `revision` instead of `model_revision`. Do not change `load_model_spec` or `load_model` in this task.

**Checkpoint**: `uv run ruff check src/models/spec.py` passes. Existing `tests/test_models_loader.py` still passes unchanged.

---

## Phase 3: User Story 1 — Name each model by the job it does (Priority: P1) 🎯 MVP

**Goal**: The frozen policy names `controlled_fact_base` and `pretrained_fact_confirmation` and states what each one is for.

**Independent Test**: Load `.factverify/spec/model_policy.yaml`. The required role keys are exactly those two names. The base purpose mentions controlled-fact training and retain-only references. The confirmation purpose mentions the 7B–8B confirmation subset and does not use a block number as the role name.

### Tests for User Story 1 (write first; they must fail before T005)

- [X] T004 [US1] Add `test_policy_role_names` to `tests/test_model_config.py`. Parse `.factverify/spec/model_policy.yaml` with `yaml.safe_load`. Assert `required_roles` keys are exactly `controlled_fact_base` and `pretrained_fact_confirmation`. Assert the base `purpose` contains `controlled-fact` and `retain-only`. Assert the confirmation `purpose` contains `confirmation subset` and the key is not `block_3_confirmation`.

### Implementation for User Story 1

- [X] T005 [US1] Create `.factverify/spec/model_policy.yaml` with the document in `specs/20260929-225846-model-role-config/contracts/model-policy.md`. Do not put a `repo_id`, a revision, or a `files` map in this file. Do not edit `.factverify/spec/models.yaml`.
- [X] T006 [US1] Run `uv run pytest tests/test_model_config.py::test_policy_role_names` and `uv run ruff check tests/test_model_config.py`. Fix only those files until the test passes.

**Checkpoint**: A reader can name both jobs from the policy alone. No loader reads it yet.

---

## Phase 4: User Story 2 — Change a model without editing the frozen specification (Priority: P1)

**Goal**: The Block 0 pin lives in a new configuration file. The historical model document and an unauthorized amendment record the split.

**Independent Test**: `.factverify/spec/models.yaml` still matches `tests/fixtures/models_config/models_yaml_sha256.txt`. The policy has no repository and no 40-character revision. `config/models/block0-debug-pythia-410m.yaml` pins EleutherAI/pythia-410m at `9879c9b5f8bea9051dcb0e68dff21493d67e9d4f` with `attn_impl: eager`, and `pretrained_fact_confirmation` is `pending`. `AMD-001` is `authorized: false`.

### Tests for User Story 2 (write first; they must fail before T008)

- [X] T007 [US2] Add these tests to `tests/test_model_config.py`:
  - `test_models_yaml_bytes_unchanged` — SHA-256 of `.factverify/spec/models.yaml` equals the hex in `tests/fixtures/models_config/models_yaml_sha256.txt`.
  - `test_policy_has_no_concrete_pin` — the policy text has no `repo_id` and no 40-hex revision.
  - `test_block0_config_copies_pythia_pin` — `config/models/block0-debug-pythia-410m.yaml` has `config_id: block0-debug-pythia-410m-v1`, `controlled_fact_base.repo_id == EleutherAI/pythia-410m`, both revisions `9879c9b5f8bea9051dcb0e68dff21493d67e9d4f`, `variant: base`, `dtype: float32`, `attn_impl: eager`, `licence: Apache-2.0`, `files: {}`, and `pretrained_fact_confirmation.status == pending` with `deadline: null`.

### Implementation for User Story 2

- [X] T008 [P] [US2] Create `config/models/block0-debug-pythia-410m.yaml` exactly as `specs/20260929-225846-model-role-config/contracts/model-config.md`. Do not create a Block 1 file. Do not invent a confirmation repository.
- [X] T009 [P] [US2] Append `AMD-001` from `specs/20260929-225846-model-role-config/contracts/model-policy.md` to `amendment_log` in `.factverify/spec/preregistration.md`. Leave `authorized: false` and `post_hoc: false`. Recompute `digest` with `tools.freeze.compute_contract_digest` and write that return value. Do not hand-edit the digest. Do not run `freeze.py --execute`. Do not create a git tag.
- [X] T010 [P] [US2] Add `model_policy.yaml` to `SPEC_ARTIFACTS` in `tools/freeze.py`. Keep `models.yaml` in that list.
- [X] T011 [US2] Run `uv run pytest tests/test_model_config.py tests/test_preregistration_freeze.py tests/test_models_spec.py`. If a digest assertion fails, recompute the preregistration digest. Do not delete a check and do not edit `.factverify/spec/models.yaml`.

**Checkpoint**: The snapshot file is unchanged. The new pin is a separate file. The amendment is not authorized.

---

## Phase 5: User Story 3 — Check and load the same document (Priority: P1)

**Goal**: The validator and the parser accept one shape: `roles` plus `model_revision`. A flat document or a `revision` field is refused.

**Independent Test**: A configuration the parser accepts is the document `validate_models_spec` accepts, including the same `model_revision`. A root-level role map and a `revision` field fail both. Existing `tests/test_models_spec.py` fixtures under `tests/fixtures/models_spec/` still pass.

### Tests for User Story 3 (write first; they must fail before T013)

- [X] T012 [US3] Add these tests to `tests/test_model_config.py`, using temp files (do not point them at `.factverify/spec/models.yaml`):
  - `test_shared_shape_model_revision` — `load_model_configuration` on a copy of the Block 0 file returns `controlled_fact_base.model_revision == 9879c9b5f8bea9051dcb0e68dff21493d67e9d4f`.
  - `test_flat_document_refused` — a document whose only role key is at the root raises `FactVerifyLoaderError` and the message contains `roles`.
  - `test_revision_field_refused` — a `roles` entry that has `revision` and no `model_revision` raises `FactVerifyLoaderError` and the message contains `model_revision`.
  - `test_validator_reads_same_revision` — `tools.models_validator.validate_models_spec` called with the Block 0 path reports no failure whose message says the weight revision is missing. Pass `spec_root=.factverify/spec` and `model_config` once that parameter exists; until then this test is expected to fail.

### Implementation for User Story 3

- [X] T013 [US3] Finish `load_model_configuration` and `load_model_policy` in `src/models/spec.py` per `specs/20260929-225846-model-role-config/data-model.md`: 40-lowercase-hex revisions, `variant` in `{base, instruct}`, required identity fields, `files` values matching `sha256:` + 64 hex or an empty map, pending roles with deadline states. Empty `files` is allowed at parse time. Do not resolve aliases in this task.
- [X] T014 [US3] Add optional `model_config: Path | None` to `validate_models_spec` in `tools/models_validator.py` and to `_run_models_validation` in `tools/validate_spec.py` (`--model-config`). When the path is set, validate that file with the shared parser against the policy and keep rule ids FV-SPEC-089 through FV-SPEC-095. When it is omitted, keep today's `models.yaml` checks. A byte change to `.factverify/spec/models.yaml` still fails FV-SPEC-095; `AMD-001` does not authorize that edit. Compare the file to `tests/fixtures/models_config/models_yaml_sha256.txt`.
- [X] T015 [US3] Run `uv run pytest tests/test_model_config.py tests/test_models_spec.py` and `uv run ruff check src/models/spec.py tools/models_validator.py tools/validate_spec.py tests/test_model_config.py`.

**Checkpoint**: One parser accepts the Block 0 file. The historical validator fixtures still pass. `load_model` still uses the old flat reader.

---

## Phase 6: User Story 4 — Choose the configuration explicitly and refuse it before any fetch (Priority: P2)

**Goal**: Production loads name a configuration file and a role. Invalid selections stop before `from_pretrained` and before network access.

**Independent Test**: `load_model` without `model_config` raises `TypeError`. A pending role and a movable revision raise `FactVerifyLoaderError` with no `from_pretrained` call. The exclusion gate and prefetch require `--model-config` and have no default role. Harness tests still train the tiny local model.

### Tests for User Story 4 (write first; they must fail before T017)

- [X] T016 [US4] Add these tests to `tests/test_model_config.py`. Monkeypatch `transformers.AutoModelForCausalLM.from_pretrained` and `huggingface_hub.hf_hub_download` to raise `AssertionError` if called.
  - `test_load_model_requires_model_config` — `load_model("controlled_fact_base", spec_root=tmp)` raises `TypeError`.
  - `test_pending_role_refuses_before_network` — `load_model("pretrained_fact_confirmation", model_config=<block0 path>, spec_root=.factverify/spec)` raises `FactVerifyLoaderError` and neither monkeypatch was called.
  - `test_movable_revision_refuses_before_network` — a temp config with `model_revision: main` raises `FactVerifyLoaderError` containing `model_revision`, and neither monkeypatch was called.
  - `test_exclusion_gate_cli_requires_config` — invoke `scripts.exclusion_gate.main` through Click's runner with no `--model-config` and no `--role`; exit code is not 0.

### Implementation for User Story 4

- [X] T017 [US4] Change `load_model` in `src/models/loader.py` to `load_model(role, *, model_config: Path, spec_root: Path, adapter_path: Path | None = None)`. Read the policy and the configuration through `src/models/spec.py`. Resolve only canonical role names in this task. Refuse a pending role, an empty `files` map, and a movable revision before `verify_files` and before `from_pretrained`. Rename `ModelSpec.revision` to `model_revision` and update readers in `src/models/loader.py`. In `src/models/verify.py`, compare digests as `sha256:` + computed hex. Keep `local_files_only=True`.
- [X] T018 [P] [US4] Rewrite `tests/fixtures/models_loader/models.yaml` to a `schema_version: "1"` configuration with `roles.tiny_base`, `model_revision`, `sha256:`-prefixed file digests, `variant: base`, and `licence: Apache-2.0`. Add `tests/fixtures/models_loader/model_policy.yaml` whose `governing_spec_revision` is `spec-v1`. Update call sites in `tests/test_models_loader.py` to pass `model_config`. Do not change the tiny weight files.
- [X] T019 [P] [US4] In `scripts/exclusion_gate.py` and `scripts/prefetch_models.py`, add required `--model-config` and required `--role` with no default. Both call the shared parser. Prefetch downloads only names listed in `files` and only after the document validates; an empty `files` map downloads nothing. Prefetch remains the only module that may call `huggingface_hub`.
- [X] T020 [P] [US4] Add required `model_config` to the allowed keys and the `JobConfig` accessor in `src/train/config.py`. Pass that path from `src/train/run.py` into `load_model`. Update `tests/harness_model.py` so `build_tiny_spec` writes a policy (`governing_spec_revision` equal to the job's existing `spec_revision`, which stays `spec-v1`) and a configuration in the new shape with `sha256:`-prefixed digests. Add `model_config` to every file in `tests/fixtures/harness/jobs/`. Do not change job `spec_revision` values.
- [X] T021 [US4] Run `uv run pytest tests/test_model_config.py tests/test_models_loader.py tests/test_harness.py` and `uv run ruff check src/models scripts/exclusion_gate.py scripts/prefetch_models.py src/train/config.py src/train/run.py tests/harness_model.py tests/test_models_loader.py`.

**Checkpoint**: A missing configuration cannot load a model. The tiny harness model still trains. Alias names are not accepted yet.

---

## Phase 7: User Story 6 — Rename a role without changing what the model is (Priority: P2)

**Goal**: New identities use FV-SPEC-093 and omit the role name. The current loader payload remains verifiable as version 1.

**Independent Test**: Two version-2 hashes of the same repository, revisions, dtype, and adapter digest match when only the role name differs. Changing any of those five fields changes the hash. A payload built the way `src/models/identity.py` works today verifies under schema version 1 and is not rewritten as version 2.

This phase is before User Story 5 because new provenance stores the version-2 string.

### Tests for User Story 6 (write first; they must fail before T023)

- [X] T022 [US6] Add these tests to `tests/test_model_config.py`:
  - `test_v2_hash_ignores_role` — two calls of the version-2 writer with different role names and the same `repo_id`, `model_revision`, `tokenizer_revision`, `dtype`, and `adapter_digest` return the same `sha256:`-prefixed digest.
  - `test_v2_hash_changes_with_revision` — a different `model_revision` changes the digest.
  - `test_v2_encoding_matches_validator` — the digest equals `tools.models_validator.compute_identity_hash` for the same five fields, including default `json.dumps` separators and `ensure_ascii=False`.
  - `test_v1_hash_still_verifies` — `verify_identity_hash` returns true for schema version 1 on a payload with keys `adapter_digest`, `attn_impl`, `base_repo`, `base_revision`, `dtype`, `role`, `tokenizer_revision` encoded with `separators=(",", ":")` and no `sha256:` prefix, and returns false when the role character changes.

### Implementation for User Story 6

- [X] T023 [US6] In `src/models/identity.py`, add `compute_identity_hash_v2` and `verify_identity_hash` per `specs/20260929-225846-model-role-config/research.md`. Keep a version-1 builder that reproduces today's payload exactly, including compact separators and the raw hex. `load_model` in `src/models/loader.py` writes version 2 into `LoadedModel.identity_hash` and sets `identity_schema_version` to `2`. Do not put `role` or `attn_impl` in the version-2 payload.
- [X] T024 [US6] Update `test_fv_model_004_identity_hash` in `tests/test_models_loader.py` so it expects the `sha256:` prefix and a stable version-2 digest, not a bare 64-character hex string.
- [X] T025 [US6] Run `uv run pytest tests/test_model_config.py tests/test_models_loader.py` and `uv run ruff check src/models/identity.py src/models/loader.py tests/test_models_loader.py tests/test_model_config.py`.

**Checkpoint**: A role rename does not change a new identity. An old loader hash still verifies.

---

## Phase 8: User Story 5 — Bind every result to the exact selection (Priority: P2)

**Goal**: New gate rows, ledger rows, cache entries, training runs, and evaluation runs store the configuration binding. A different fingerprint cannot reuse the previous gate report or cache entry.

**Independent Test**: A gate JSONL row and the Markdown report contain `study_role`, `model_config_id`, `model_config_digest`, `model_identity_hash`, `identity_schema_version`, and the governing spec revision. A training precheck raises when the report digest differs. A cache key changes when `model_config_digest` changes. Existing checkpoint rows are not updated.

### Tests for User Story 5 (write first; they must fail before T027)

- [X] T026 [US5] Add these tests to `tests/test_model_config.py`, `tests/test_exclusion_gate.py`, `tests/test_cache.py`, and `tests/test_ledger.py`. Do not download Pythia.
  - In `tests/test_model_config.py`, `test_gate_row_carries_binding` — a fake completer and a temp Block 0-shaped config produce a JSONL row and a report containing all six binding fields, with `identity_schema_version == 2`.
  - In `tests/test_exclusion_gate.py`, `test_require_pass_rejects_other_digest` — `require_pass` raises when the report's `model_config_digest` differs from the loaded digest, and the report file bytes are unchanged.
  - In `tests/test_cache.py`, extend the key test so two `CacheRequest`s that differ only in `model_config_digest` produce different keys.
  - In `tests/test_ledger.py`, `test_checkpoint_binding_columns` — a new training-style insert stores the five new columns, and `checkpoints.identity_hash` is still the value passed as the checkpoint identity. An older row read back has null binding columns.

### Implementation for User Story 5

- [X] T027 [P] [US5] In `src/ledger/schema.py`, add nullable columns `study_role`, `model_config_id`, `model_config_digest`, `model_identity_hash`, and `identity_schema_version` to `checkpoints` and `evaluation_runs` with the same `ALTER TABLE` pattern as `decision_key`. Leave `schema_version` as `"1"`. In `src/ledger/api.py`, write those columns from `commit_checkpoint` and from evaluation inserts. Keep writing `checkpoints.identity_hash` from the training row's existing checkpoint identity (today that is `loaded.identity_hash`). Do not replace control-row `uuid` identities. Leave the new columns null when the caller does not supply them. Do not `UPDATE` existing rows.
- [X] T028 [P] [US5] Add `model_config_digest`, `study_role`, `model_config_id`, `identity_schema_version`, and `governing_spec_revision` to `CacheRequest` in `src/cache/key.py`. Include `model_config_digest` in the key payload next to `identity_hash`. Add the five binding columns to cache `entries` in `src/cache/store.py` with `ALTER TABLE`, required on new writes, null on old rows. Do not rewrite stored keys. Extend `export_cache` in `src/cache/export.py` so manifest entries include `model_identity_hash` and `model_config_digest` (null when the row has none). `import_cache` still refuses a mismatched manifest digest.
- [X] T029 [P] [US5] In `src/data/exclusion.py`, store the six binding fields on every JSONL row and in one provenance block in the Markdown report. `require_pass` accepts a report only when `model_identity_hash` and `model_config_digest` equal the loaded binding. A report missing either field raises `DataError` and is not rewritten. Pass the binding from `scripts/exclusion_gate.py`. The governing revision is the policy's `governing_spec_revision`.
- [X] T030 [US5] In `src/train/run.py`, copy the loaded binding into the checkpoint row and refuse to start when a supplied exclusion-gate report's `model_identity_hash` or `model_config_digest` differs from the load. Compare the job's existing `spec_revision` to the policy's `governing_spec_revision` and raise `FactVerifyHarnessError` on a mismatch. Do not change harness fixture `spec_revision` values; their temp policy already matches.
- [X] T031 [US5] Run `uv run pytest tests/test_model_config.py tests/test_exclusion_gate.py tests/test_cache.py tests/test_ledger.py tests/test_harness.py` and `uv run ruff check src/ledger src/cache src/data/exclusion.py src/train/run.py scripts/exclusion_gate.py`.

**Checkpoint**: A new run names its configuration. An old report is not reused for a different fingerprint and is not rewritten.

---

## Phase 9: User Story 7 — Read old role names during the transition (Priority: P3)

**Goal**: `blocks_0_2` and `block_3_confirmation` resolve to the new names with a deprecation line. A document that contains both an old name and its new name is refused.

**Independent Test**: Loading a config whose only base key is `blocks_0_2` returns `study_role == controlled_fact_base` and a diagnostic containing both names. A document with both keys raises. A newly written gate row stores `controlled_fact_base`, not `blocks_0_2`.

### Tests for User Story 7 (write first; they must fail before T033)

- [X] T032 [US7] Add these tests to `tests/test_model_config.py`:
  - `test_legacy_alias_resolves` — a temp config that uses `blocks_0_2` instead of `controlled_fact_base`, and keeps the confirmation role pending, resolves `study_role` to `controlled_fact_base`. The captured diagnostic contains `blocks_0_2` and `controlled_fact_base`.
  - `test_alias_conflict_refused` — a document with both `blocks_0_2` and `controlled_fact_base` raises `FactVerifyLoaderError` and the message contains both keys, even when the two entries are equal.
  - `test_new_output_uses_canonical_role` — after an alias load, the binding's `study_role` is `controlled_fact_base`.

### Implementation for User Story 7

- [X] T033 [US7] In `src/models/spec.py`, apply `role_aliases` from the policy before role lookup. Emit one deprecation string that contains the alias and the canonical name. Refuse when both keys are present. `load_model` in `src/models/loader.py` and `scripts/exclusion_gate.py` surface that string on stderr. Stored `study_role` is always the canonical name.
- [X] T034 [US7] Run `uv run pytest tests/test_model_config.py` and `uv run ruff check src/models/spec.py src/models/loader.py scripts/exclusion_gate.py tests/test_model_config.py`.

**Checkpoint**: Old names still load. New records use the new names. Dual keys fail.

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Operator docs and a full check of the files this feature touched.

- [X] T035 [P] Update `docs/model-loader-architecture.md` and `docs/models-yaml-model-source.md` so they describe `model_policy.yaml`, `config/models/`, `model_revision`, and `load_model(..., model_config=...)`. Do not edit notes under `specs/20260926-*` or `specs/20260929-100819-exclusion-gate-splits/`. Do not write to the Obsidian vault.
- [X] T036 Run `uv run ruff check src tools scripts tests/test_model_config.py tests/test_models_loader.py tests/test_models_spec.py tests/harness_model.py` and `uv run ruff format --check` on those paths. Then run `uv run pytest tests/test_model_config.py tests/test_models_loader.py tests/test_models_spec.py tests/test_exclusion_gate.py tests/test_cache.py tests/test_ledger.py tests/test_harness.py tests/test_preregistration_freeze.py`.
- [X] T037 Re-read `tests/fixtures/models_config/models_yaml_sha256.txt` against `.factverify/spec/models.yaml`. If they differ, restore the model document from git and do not "fix" the golden digest. Confirm `AMD-001` in `.factverify/spec/preregistration.md` is still `authorized: false` and that `git tag -l spec-v2` is empty.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: no dependencies.
- **Foundational (Phase 2)**: depends on Setup. Blocks every user story.
- **US1 (Phase 3)**: depends on Foundational. No dependency on later stories.
- **US2 (Phase 4)**: depends on US1 because it extends `model_policy.yaml`'s companion files and the amendment. Independently testable once the policy file exists.
- **US3 (Phase 5)**: depends on US1 and US2. The parser tests use the Block 0 file.
- **US4 (Phase 6)**: depends on US3. Switches `load_model` to the shared parser.
- **US6 (Phase 7)**: depends on US4. Placed before US5 because new rows store the version-2 digest.
- **US5 (Phase 8)**: depends on US4 and US6.
- **US7 (Phase 9)**: depends on US3. Can proceed in parallel with US4–US6 only if it does not edit `load_model` until US4 has landed. Default order is after US5.
- **Polish (Phase 10)**: depends on the stories you intend to keep.

### User Story Dependencies

- **US1 (P1)**: after Foundational. MVP document.
- **US2 (P1)**: after US1. File split and unauthorized amendment.
- **US3 (P1)**: after US2. One parser.
- **US4 (P2)**: after US3. Explicit configuration on the load path.
- **US6 (P2)**: after US4. Identity versions.
- **US5 (P2)**: after US6. Provenance.
- **US7 (P3)**: after US3, and after US4 if the same `load_model` edit would conflict. Alias behavior.

### Within Each User Story

- Tests fail before the implementation task in that phase.
- Do not start the next story's implementation while this story's pytest task is red.

### Parallel Opportunities

- T001 and T002.
- T008, T009, and T010 after T007.
- T018, T019, and T020 after T017.
- T027, T028, and T029 after T026. T030 waits for those three.
- T035 in parallel with nothing else that edits the same docs; it waits until the behavior is stable.

---

## Parallel Example: User Story 2

```bash
# After T007 is written and failing:
Task: "Create config/models/block0-debug-pythia-410m.yaml"
Task: "Append AMD-001 to .factverify/spec/preregistration.md"
Task: "Add model_policy.yaml to SPEC_ARTIFACTS in tools/freeze.py"
```

## Parallel Example: User Story 5

```bash
# After T026 is written and failing, and US6 has landed:
Task: "Ledger binding columns in src/ledger/schema.py and src/ledger/api.py"
Task: "Cache key and entry columns in src/cache/key.py and src/cache/store.py"
Task: "Gate report binding in src/data/exclusion.py"
```

---

## Implementation Strategy

### MVP First (User Story 1)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3. The policy names both jobs.
3. Stop and read the policy. Do not load a model yet.

### First usable increment

1. Add Phase 4 and Phase 5.
2. The Block 0 file and the parser agree, and `models.yaml` is unchanged.
3. Stop before switching `load_model` if you want a review of the documents.

### Incremental Delivery

1. US4 makes production commands name the file.
2. US6 locks the identity versions.
3. US5 writes the binding and blocks reuse.
4. US7 accepts the old names with a deprecation line.

### Parallel Team Strategy

After Phase 5, one person can take US4 while another drafts US7's tests. Do not edit `src/models/loader.py` from both. US5 starts only after US6.

---

## Notes

- Suggested commit message when the user asks to commit: `P0-8: separate model policy from versioned selections`.
- Do not modify `.factverify/spec/models.yaml`.
- Do not set `authorized: true` and do not create `spec-v2`.
- `attn_impl: eager` belongs only on the Block 0 debug configuration. Do not create the Block 1 model.
- Catalog keys `model.blocks_0_2.identity` and `model.block_3.identity` stay as they are.
