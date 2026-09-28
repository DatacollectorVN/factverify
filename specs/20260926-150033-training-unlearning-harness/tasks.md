# Tasks: FV-HARN — P2-1 Training and Unlearning Harness

**Feature**: `20260926-150033-training-unlearning-harness`  
**Input**: Design documents from `specs/20260926-150033-training-unlearning-harness/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅ · quickstart.md ✅

**Tests**: Included. `FV-HARN — P2-1.md` (draft) requires ten named pytest hooks, `test_fv_harn_001` through `test_fv_harn_010`, as the verification matrix. Write each story's tests before that story's implementation, and confirm they fail first.

**Organization**: Tasks are grouped by user story. Do not choose study values for D-51, D-52, or D-53. Numbers that appear below belong only in `tests/fixtures/harness/`.

**Design notes** (read from disk; Obsidian MCP was unavailable when the plan was written): Execution Plan (status: planned), "Phase 2 — Harness and run ledger", task P2-1. Retain-Only Reference Model (status: needs-review), "How It Works". Handbook (status: draft): I6, I7, I8.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other `[P]` tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: User story this task belongs to (US1, US2, US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Package skeleton and the tiny offline fixture. Reuse the existing `tiny_base` model. Do not download weights.

- [X] T001 Create stub modules under `src/train/`: `__init__.py`, `errors.py`, `config.py`, `seeding.py`, `manifests.py`, `data.py`, `cost.py`, `ledger.py`, `checkpoint.py`, `run.py`, and `methods/__init__.py`, `methods/finetune.py`, `methods/ga.py`, `methods/graddiff.py`, `methods/npo.py`, `methods/rmu.py`. Each file has a module docstring and no behaviour yet.
- [X] T002 [P] Create `tests/fixtures/harness/corpus/fact_doc.txt`, `retain_a.txt`, and `retain_b.txt`, each one short sentence. These ids are the only training texts the fixture jobs may name.
- [X] T003 [P] Create `tests/fixtures/harness/jobs/finetune.yaml` and `tests/fixtures/harness/jobs/finetune_missing_lr.yaml` per `contracts/job_config.md`. Both use `role: finetuned`, `method: finetune`, `base_role: tiny_base`, `spec_revision: spec-v1`, `determinism_policy: exact`, `digest_tolerance: "0"`, `optimizer: adamw`, `epochs: 1`, `batch_size: 1`, `max_length: 16`, `weight_decay: 0`, `learning_rate: 0.0001` (omit `learning_rate` in the missing file), `lora.r: 2`, `lora.alpha: 4`, `lora.dropout: 0`, `lora.target_modules: ["c_attn"]`, `manifest.train: [retain_a]`, `source_bundle: [fact_doc]`, `bundle_id: bundle-fact`, `target_fact_id: fact-1`, `corpus_dir` pointing at `tests/fixtures/harness/corpus`, and a temporary-style `output_dir` the tests will override. These numbers are fixture inputs, not Block 0–2 settings.
- [X] T004 [P] Add session fixtures to `tests/conftest.py`: `harness_spec_root` returns `tests/fixtures/models_loader` (existing `tiny_base` `models.yaml`), `harness_corpus` returns `tests/fixtures/harness/corpus`, and `harness_finetune_config` returns `tests/fixtures/harness/jobs/finetune.yaml`.

**Checkpoint**: Skeleton and fixture files exist. No trainer runs yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Types and checks every story calls. No story starts until this phase is done.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T005 Implement `FactVerifyHarnessError(ValueError)` in `src/train/errors.py`. All harness failures raise this type and name the field, document id, item id, seed, or path.
- [X] T006 [P] Implement `JobConfig`, `load_job_config(path) -> JobConfig`, and `config_hash(config) -> str` in `src/train/config.py` per `contracts/job_config.md` and `data-model.md`. Reject a missing, null, or `DECISION_REQUIRED` field, an unknown key, a role/method mismatch, an empty required manifest list, an `optimizer` other than `adamw`, and a bad `determinism_policy` or `digest_tolerance`. Do not fill defaults. Hash is SHA-256 of sorted compact JSON of the file mapping, with paths left as written. Leave procedure comparison for T020.
- [X] T007 [P] Implement `CheckpointRow`, `LedgerPort` (`split_for_seed`, `commit_checkpoint`) in `src/train/ledger.py` per `contracts/ledger_port.md`. `commit_checkpoint` returns a row id and raises `FactVerifyHarnessError` on rejection without storing the row. Do not open SQLite.
- [X] T008 [P] Implement `apply_seed(seed: int, determinism_policy: str) -> None` in `src/train/seeding.py`. Set `random`, `numpy` (when importable), and `torch` seeds, including CUDA when present. `exact` enables deterministic algorithms and deterministic cuDNN with benchmark off. `tolerant` sets seeds only. A non-zero digest comparison is not implemented here (D-53).
- [X] T009 [P] Implement `DataCatalog` in `src/train/data.py`. `get(item_id)` reads `{corpus_dir}/{item_id}.txt` only when `item_id` is in the allowed set, appends it to `access_log`, and raises `FactVerifyHarnessError` naming the id otherwise. `assert_closed()` raises when `access_log` is not equal to the allowed set.
- [X] T010 [P] Implement `CostRecord` in `src/train/cost.py` with `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`, `training_steps`, and `training_examples`. GPU-hours are `elapsed_seconds * cuda_device_count / 3600` when CUDA is available, else `0`. Peak memory is CUDA peak allocated bytes, else process max RSS. Start and finish methods must populate all five fields even when a caller stops early.

**Checkpoint**: Configs hash, the ledger port accepts rows, seeds apply, and the catalog refuses unlisted ids. User stories can begin.

---

## Phase 3: User Story 1 — One auditable checkpoint from one config and one seed (Priority: P1) 🎯 MVP

**Goal**: A `finetuned` / `finetune` job reads only its manifest, seeds data order and adapter init, writes `metadata.json` and `fv_adapter_meta.json`, and returns success only after one ledger row with five cost fields. Incomplete configs, unlisted reads, metadata failures, and ledger failures do not publish a checkpoint.

**Independent Test**: `uv run pytest tests/test_harness.py -k "001 or 002 or 006 or 007 or 008 or 009" -v`

### Tests for User Story 1

- [X] T011 [US1] Write these tests in `tests/test_harness.py` so they fail before T012–T017 (missing `run_job` or a failed assertion). Use `harness_spec_root`, an in-memory `LedgerPort` defined in `tests/harness_ledger.py`, and a temp `output_dir`.
  - `test_fv_harn_001_config_complete` — a complete file yields a `config_hash` in `metadata.json` equal to the hash of that file; `finetune_missing_lr.yaml` raises `FactVerifyHarnessError` naming `learning_rate`, and no adapter directory is created.
  - `test_fv_harn_002_seeded` — two runs of the same config and seed record the same `data_order` and the same adapter digest when `digest_tolerance` is `"0"`; two seeds record different `data_order` values and each metadata `seed` matches its job.
  - `test_fv_harn_006_manifest_only` — after success, the catalog access set equals `manifest.train`; a direct `DataCatalog.get` of `fact_doc` on that job raises naming `fact_doc`.
  - `test_fv_harn_007_metadata` — `metadata.json` has non-null `base_identity_hash`, `parent_checkpoint_hash` (equal to the base hash for this finetune), `config_hash`, `seed`, `role`, and `method`; `fv_adapter_meta.json` repeats `base_identity_hash`. Force a metadata write failure (read-only staging parent or a patched writer) and assert the job is `failed` and `output_dir` is absent.
  - `test_fv_harn_008_ledger_row` — success leaves exactly one `succeeded` row whose `checkpoint_identity_hash` equals `load_model("tiny_base", spec_root=..., adapter_path=output_dir).identity_hash`. A ledger `commit_checkpoint` that raises leaves `status=failed` and no published directory.
  - `test_fv_harn_009_cost` — the success row has all five cost fields set, and `training_examples >= 1`. A trainer exception still commits one `failed` row with `adapter_published` false and the partial cost fields populated.

### Implementation for User Story 1

- [X] T012 [P] [US1] Implement `train_finetune` in `src/train/methods/finetune.py`. It takes the `JobConfig`, a model already in train mode, the tokenizer, and a `DataCatalog` whose allowed ids are `manifest.train`. Shuffle ids with `torch.Generator` seeded by `config.seed`, record that list as `data_order`, and optimize causal-LM cross-entropy with AdamW using only `learning_rate`, `weight_decay`, `epochs`, `batch_size`, and `max_length` from the config. If the tokenizer has no pad token, set it to the eos token. Return `data_order` and the step and example counts. No numeric default for any hyperparameter.
- [X] T013 [P] [US1] Implement `publish_adapter` and `discard_adapter` in `src/train/checkpoint.py` per `contracts/checkpoint_metadata.md`. Save PEFT weights to a staging directory, write `fv_adapter_meta.json` and `metadata.json`, and rename into `output_dir` only after both JSON files exist. On a metadata failure, delete staging and do not rename. `discard_adapter` removes `output_dir` if it exists.
- [X] T014 [US1] Implement `run_job(config_path, *, spec_root, ledger) -> JobResult` for `role=finetuned` and `method=finetune` in `src/train/run.py`, following the state order in `data-model.md`. Call `load_model` (never `from_pretrained`), then `model.train()`, `apply_seed` before LoRA `get_peft_model`, `train_finetune`, `publish_adapter`, `load_model` again for `checkpoint_identity_hash`, then `ledger.commit_checkpoint`. A commit failure deletes the published directory and returns `failed`. A caught training exception writes one `failed` row with partial cost and publishes nothing. An unknown method raises before the catalog is constructed and before `load_model`.
- [X] T015 [US1] Add the CLI in `src/train/run.py`: `python -m src.train.run --config PATH --spec-root PATH --ledger PATH`, default spec root `.factverify/spec`. `--ledger` is required. Because P2-5 does not exist yet, a CLI ledger path raises `FactVerifyHarnessError` naming the missing SQLite port and exits non-zero. Exit 0 only when `JobResult.status` is `succeeded`.
- [X] T016 [US1] Export `run_job`, `JobResult`, and `FactVerifyHarnessError` from `src/train/__init__.py`.
- [X] T017 [US1] Run `uv run pytest tests/test_harness.py -k "001 or 002 or 006 or 007 or 008 or 009" -v` and make those six hooks pass. Do not weaken an assertion to get a green result.

**Checkpoint**: User Story 1 stands alone. A finetune job is reproducible from its file and seed, and it is not a success without metadata and a ledger row.

---

## Phase 4: User Story 2 — Retain-only reference that differs only by the missing fact (Priority: P2)

**Goal**: A `reference` / `finetune` job uses the same procedure as its paired finetune, refuses any source-bundle document on its manifest, refuses a seed already stored for that fact on another split, and records `excluded_bundle_id` plus `paired_finetune_config_hash`.

**Independent Test**: `uv run pytest tests/test_harness.py -k "003 or 004 or 010" -v` while the US1 hooks still pass.

### Tests for User Story 2

- [X] T018 [P] [US2] Add fixture jobs under `tests/fixtures/harness/jobs/`: `reference_ok.yaml` (same procedure fields as `finetune.yaml`, `role: reference`, different `seed`, `manifest.train: [retain_a, retain_b]`, `paired_finetune_config` pointing at `finetune.yaml`, different `split` and `output_dir`); `reference_leak.yaml` (same, but `manifest.train` includes `fact_doc`); `reference_bad_lr.yaml` (same as `reference_ok.yaml` with a different `learning_rate`).
- [X] T019 [US2] Append these failing tests to `tests/test_harness.py`:
  - `test_fv_harn_003_bundle_excluded` — `reference_ok.yaml` succeeds and `metadata.json` `excluded_bundle_id` is `bundle-fact`; `reference_leak.yaml` raises naming `fact_doc` before any checkpoint exists.
  - `test_fv_harn_004_matched_procedure` — `reference_ok.yaml` succeeds and `paired_finetune_config_hash` equals the hash of `finetune.yaml`; `reference_bad_lr.yaml` raises listing `learning_rate`.
  - `test_fv_harn_010_seed_disjoint` — with an in-memory ledger that already has `fact-1` and this job's seed on a different split, the job raises naming the seed and does not train; a seed with no prior row proceeds.

### Implementation for User Story 2

- [X] T020 [P] [US2] Implement `procedure_differences(reference: JobConfig, finetune: JobConfig) -> list[str]` in `src/train/config.py`. Compare the resolved mappings and ignore only `role`, `seed`, `manifest`, `split`, `output_dir`, and `paired_finetune_config` (`research.md` Decision 2). Return sorted dotted paths. No differences means the procedures match.
- [X] T021 [P] [US2] Implement `leaked_bundle_documents(manifest_train: list[str], source_bundle: list[str]) -> list[str]` in `src/train/manifests.py`. Return the sorted ids present in both lists.
- [X] T022 [US2] Extend `run_job` in `src/train/run.py` for `role=reference`. Before `load_model`: require `paired_finetune_config`, fail listing `procedure_differences` when non-empty, fail naming the first leaked document when the leak list is non-empty, and fail naming the seed when `ledger.split_for_seed(target_fact_id, seed)` is not `None` and differs from this job's split. On success, write `excluded_bundle_id` and `paired_finetune_config_hash` into `metadata.json` via `checkpoint.py`.
- [X] T023 [US2] Run `uv run pytest tests/test_harness.py -k "001 or 002 or 003 or 004 or 006 or 007 or 008 or 009 or 010" -v` and make the US1 and US2 hooks pass together.

**Checkpoint**: User Stories 1 and 2 both work. A reference is the same finetune procedure with a disjoint manifest and its own seed.

---

## Phase 5: User Story 3 — Select an unlearning method by name (Priority: P3)

**Goal**: `GA`, `GradDiff`, `NPO`, and `RMU` each continue `parent_adapter` and record the method name and its hyperparameters. An unknown method fails before data is loaded.

**Independent Test**: `uv run pytest tests/test_harness.py -k "005" -v` while US1 and US2 hooks still pass.

### Tests for User Story 3

- [X] T024 [US3] Add `tests/fixtures/harness/jobs/candidate_ga.yaml`, `candidate_graddiff.yaml`, `candidate_npo.yaml`, `candidate_rmu.yaml`, and `candidate_unknown.yaml`. Each candidate uses `role: candidate`, `base_role: tiny_base`, `parent_adapter` set by the test to the US1 finetune `output_dir`, and the extra fields from `data-model.md` (`retain_coeff`, `beta`, `steering_coeff`, `steering_layer` as fixture numbers only). `candidate_unknown.yaml` sets `method: NOT_A_METHOD`. Append `test_fv_harn_005_methods` to `tests/test_harness.py`: each of the four names produces a checkpoint whose metadata `method` and `hyperparameters` match the job; the unknown name raises `FactVerifyHarnessError` and the corpus file access times do not change (no read). The test must fail before T025–T029.

### Implementation for User Story 3

- [X] T025 [P] [US3] Implement `train_ga` in `src/train/methods/ga.py`: negative causal-LM cross-entropy on `manifest.forget` only, hyperparameters from the job, same seeding and `data_order` rules as finetune.
- [X] T026 [P] [US3] Implement `train_graddiff` in `src/train/methods/graddiff.py`: negative forget loss plus `retain_coeff` times retain cross-entropy. Read `retain_coeff` from the job. Allowed ids are the union of `manifest.forget` and `manifest.retain`.
- [X] T027 [P] [US3] Implement `train_npo` in `src/train/methods/npo.py`: negative preference loss of the trainable adapter against a frozen forward of the parent, coefficient `beta` from the job, forget ids only.
- [X] T028 [P] [US3] Implement `train_rmu` in `src/train/methods/rmu.py`: at `steering_layer`, push forget hidden states with `steering_coeff` and keep retain hidden states close to the frozen parent. Both coefficients come from the job. Allowed ids are the forget and retain union.
- [X] T029 [US3] Register `GA`, `GradDiff`, `NPO`, and `RMU` in `src/train/methods/__init__.py`. Extend `run_job` in `src/train/run.py` for `role=candidate`: resolve the method name before opening the catalog or calling `load_model`; load `parent_adapter` through `load_model`; do not build a new LoRA; set `parent_checkpoint_hash` to that loaded identity hash and `base_identity_hash` to the base-only hash; train; publish; commit one ledger row.
- [X] T030 [US3] Run `uv run pytest tests/test_harness.py -v` and make all ten hooks pass.

**Checkpoint**: All three stories work. Method comparisons differ by the declared name and the hyperparameters stored in metadata.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Style gate, the loader boundary, and a full-suite check.

- [X] T031 [P] Run `uv run ruff check src/train tests/test_harness.py tests/harness_ledger.py` and `uv run ruff format --check` on those paths. Fix annotations and style in the files ruff names. Do not add `# noqa` to hide a missing annotation.
- [X] T032 [P] Run `uv run pytest tests/test_models_loader.py -k "009" -v` and confirm `src/train/` adds no `from_pretrained` call. If it fails, move the load back to `load_model`.
- [X] T033 Search `src/train/` for numeric literals used as hyperparameter defaults (`1e-4`, rank, beta, layer, tolerance). Remove any that are not a measurement definition from `contracts/ledger_port.md` (`3600` seconds per hour is allowed). Fixture numbers stay in `tests/fixtures/harness/`.
- [X] T034 Run `uv run pytest tests/test_harness.py tests/test_models_loader.py -v` and confirm the ten harness hooks and the existing loader hooks pass.
- [X] T035 Read `specs/20260926-150033-training-unlearning-harness/quickstart.md` against the CLI in `src/train/run.py`. Update the quickstart only if a flag name drifted. Do not write Block 0–2 hyperparameter values into it.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Phase 1. Blocks every story.
- **User Story 1 (Phase 3)**: Depends on Phase 2. No dependency on US2 or US3.
- **User Story 2 (Phase 4)**: Depends on Phase 3, because it edits `src/train/run.py` and `tests/test_harness.py` after the finetune path exists.
- **User Story 3 (Phase 5)**: Depends on Phase 3 (a published finetune adapter is the parent). Starts after Phase 4 so the two stories do not edit `run.py` at the same time.
- **Polish (Phase 6)**: Depends on Phases 3–5.

### User Story Dependencies

- **US1 (P1)**: First story. Delivers the MVP finetune path.
- **US2 (P2)**: Uses the US1 finetune trainer and `run_job`. Its tests do not need a candidate.
- **US3 (P3)**: Needs one published US1 adapter as `parent_adapter`. It does not need a reference job.

### Within Each User Story

- Tests fail before implementation tasks in that phase.
- Foundational modules are not re-stubbed inside a story.
- A story's pytest task is the last task in that phase.

### Parallel Opportunities

- T002, T003, and T004 can run together after the corpus ids in T002 are agreed (they are fixed in the task text).
- T006, T007, T008, T009, and T010 can run together after T005.
- T012 and T013 touch different files and can run together.
- T020 and T021 can run together.
- T025, T026, T027, and T028 can run together.
- T031 and T032 can run together.
- Do not parallelize tasks that both edit `src/train/run.py` or `tests/test_harness.py`.

---

## Parallel Example: Foundational phase

```bash
# After T005, different files:
Task: "Implement JobConfig and config_hash in src/train/config.py"
Task: "Implement LedgerPort in src/train/ledger.py"
Task: "Implement apply_seed in src/train/seeding.py"
Task: "Implement DataCatalog in src/train/data.py"
Task: "Implement CostRecord in src/train/cost.py"
```

## Parallel Example: User Story 3 trainers

```bash
# After T024, different method files:
Task: "Implement train_ga in src/train/methods/ga.py"
Task: "Implement train_graddiff in src/train/methods/graddiff.py"
Task: "Implement train_npo in src/train/methods/npo.py"
Task: "Implement train_rmu in src/train/methods/rmu.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Finish Phase 1 and Phase 2.
2. Finish Phase 3.
3. Stop and run the US1 independent test. A finetune checkpoint with metadata, a config hash, a seed, and one ledger row is the MVP.

### Incremental Delivery

1. Setup + foundational → shared types exist.
2. US1 → finetune jobs are auditable.
3. US2 → retain-only references match that procedure and exclude the bundle.
4. US3 → the four unlearning names produce candidates from a parent adapter.
5. Polish → ruff, the loader boundary, and the full harness file.

### Notes

- `ledger.sqlite` is P2-5. This task list stops at `LedgerPort` plus the in-memory test double.
- A non-zero `digest_tolerance` must raise rather than apply an invented distance (D-53). Fixture jobs use `"0"`.
- No requirement is marked implemented while D-51, D-52, or D-53 is open. Passing fixture tests does not close those decisions.

---

## Task counts

| Phase | Tasks | IDs |
|-------|-------|-----|
| Setup | 4 | T001–T004 |
| Foundational | 6 | T005–T010 |
| US1 | 7 | T011–T017 |
| US2 | 6 | T018–T023 |
| US3 | 7 | T024–T030 |
| Polish | 5 | T031–T035 |
| **Total** | **35** | |
