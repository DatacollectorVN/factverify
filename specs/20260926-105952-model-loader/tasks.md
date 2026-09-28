# Tasks: FV-MODEL — P2-0 Model Loader

**Feature**: `20260926-105952-model-loader`  
**Input**: Design documents from `specs/20260926-105952-model-loader/`  
**Prerequisites**: plan.md ✅ · spec.md ✅ · research.md ✅ · data-model.md ✅ · contracts/ ✅

**Tests**: Included — the verification matrix in `FV-MODEL — P2-0.md` requires nine named pytest hooks (FV-MODEL-001 through 009) as formal evidence of conformance. These are not optional.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other [P] tasks in the same phase (different files, no unresolved dependencies)
- **[Story]**: Which user story this task belongs to (US1/US2/US3)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the package skeleton and self-contained test fixture that all phases depend on. No real model downloads — the fixture model is tiny and committed to the repo.

- [X] T001 Create `src/models/` package skeleton: `__init__.py` (empty), `errors.py` (stub), `spec.py` (stub), `verify.py` (stub), `identity.py` (stub), `adapters.py` (stub), `loader.py` (stub) — each file contains only a module docstring and `pass`
- [X] T002 Create `tests/fixtures/tiny_model/` with a minimal Hugging Face–compatible model structure: `config.json` (tiny GPT-2-style config with 2 layers, 4 heads, hidden_size=64), `tokenizer_config.json`, `vocab.json`, `merges.txt`, and `model.safetensors` (randomly initialised weights matching the config) — compute and record the SHA-256 digest of each file for use in T003
- [X] T003 Create `tests/fixtures/models.yaml` declaring one role `"tiny_base"` with fields: `repo_id` (any placeholder string), `revision` (any 40-char hex string), `tokenizer_revision` (same or different 40-char hex string), `dtype: "float32"`, `attn_impl: "eager"`, and `files` mapping each fixture filename to its SHA-256 digest computed in T002
- [X] T004 [P] Create `tests/fixtures/tiny_adapter/` with minimal PEFT adapter files (`adapter_config.json`, `adapter_model.safetensors`) and a `fv_adapter_meta.json` whose `base_identity_hash` equals the identity hash that will be computed for `"tiny_base"` from the T003 `models.yaml` fields (compute this hash manually using the canonical payload + SHA-256 algorithm defined in `research.md` Decision 1)
- [X] T005 [P] Create `tests/fixtures/tiny_adapter_wrong/` — copy of `tiny_adapter/` but with `fv_adapter_meta.json` containing a deliberately wrong `base_identity_hash` (e.g., 64 `"0"` characters) to drive the mismatch test in US2
- [X] T006 Add a `spec_root` pytest fixture to `tests/conftest.py` that returns `Path("tests/fixtures/")` — reused by all test functions in `test_models_loader.py`

**Checkpoint**: Fixture model exists, digests are recorded, package skeleton exists — no implementation yet.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data structures and utilities that all three user stories depend on. Must be complete before any `load_model` implementation begins.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T007 Implement `FactVerifyLoaderError(ValueError)` in `src/models/errors.py` — a `ValueError` subclass with no extra fields; used as the single error type raised by all loader failure paths
- [X] T008 Implement `ModelSpec` dataclass and `load_model_spec(role: str, spec_root: Path) -> ModelSpec` in `src/models/spec.py` — parse `models.yaml`, validate that the requested role exists and all normative fields (`repo_id`, `revision`, `tokenizer_revision`, `dtype`, `attn_impl`, `files`) are present and non-null; raise `FactVerifyLoaderError` on any missing or null field
- [X] T009 [P] Implement `verify_files(spec: ModelSpec, local_dir: Path) -> None` in `src/models/verify.py` — for each file declared in `spec.files`: check the file exists locally, compute its SHA-256 digest, compare to the declared value, and raise `FactVerifyLoaderError` naming the file on any mismatch, absence, or extra undeclared file
- [X] T010 [P] Implement `build_identity_payload(spec: ModelSpec, adapter_digest: str | None) -> dict` and `compute_identity_hash(payload: dict) -> str` in `src/models/identity.py` — payload is `{"role", "base_repo", "base_revision", "tokenizer_revision", "dtype", "attn_impl", "adapter_digest"}` with keys sorted; hash is `hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()`
- [X] T011 Define the `LoadedModel` frozen dataclass in `src/models/loader.py` — fields: `model`, `tokenizer`, `identity_hash: str`, `identity_payload: dict`, `role: str`

**Checkpoint**: Foundation ready — all shared types, parsers, and utilities exist. User story implementation can now begin.

---

## Phase 3: User Story 1 — Load Any Checkpoint Reproducibly (Priority: P1) 🎯 MVP

**Goal**: `load_model("tiny_base", spec_root=Path("tests/fixtures/"))` returns a `LoadedModel` with correct identity hash; all failure paths (unknown role, digest mismatch, missing file, precision mismatch) raise `FactVerifyLoaderError` before returning anything.

**Independent Test**: `uv run pytest tests/test_models_loader.py -k "001 or 002 or 003 or 004 or 007 or 008" -v` — all six US1 hooks pass green.

### Test stubs for User Story 1

- [X] T012 [US1] Write the six US1 test function stubs in `tests/test_models_loader.py` using the `spec_root` conftest fixture — stubs raise `NotImplementedError` so they fail immediately; one function per requirement:
  - `test_fv_model_001_pinned_revision` — asserts loaded model uses declared revision; asserts unknown role raises
  - `test_fv_model_002_digest_check` — asserts clean files load; asserts modified file raises naming the file
  - `test_fv_model_003_offline` — asserts load succeeds with network disabled (monkeypatch `socket.socket`); asserts missing file raises rather than downloading
  - `test_fv_model_004_identity_hash` — asserts `identity_hash` and `identity_payload` are byte-identical on two calls with same inputs; asserts different dtype produces different hash
  - `test_fv_model_007_precision` — asserts loaded model parameters have declared dtype; asserts unsupported dtype raises
  - `test_fv_model_008_eval_mode` — asserts `model.training` is `False`; asserts identical logits on two forward passes with the same seed

### Implementation for User Story 1

- [X] T013 [US1] Implement `load_model(role: str, *, spec_root: Path, adapter_path: Path | None = None) -> LoadedModel` in `src/models/loader.py` — call `load_model_spec`, call `verify_files`, call `AutoModelForCausalLM.from_pretrained` and `AutoTokenizer.from_pretrained` with `local_files_only=True` and the declared revision and dtype/attn_impl, set `model.eval()`, call `build_identity_payload` and `compute_identity_hash`, return `LoadedModel`; raise `FactVerifyLoaderError` on hardware mismatch (catch `RuntimeError` from dtype cast) and any missing spec field
- [X] T014 [US1] Export `load_model`, `LoadedModel`, `FactVerifyLoaderError` from `src/models/__init__.py`
- [X] T015 [US1] Run `uv run pytest tests/test_models_loader.py -k "001 or 002 or 003 or 004 or 007 or 008" -v` and confirm all six hooks pass green; fix any failures before proceeding

**Checkpoint**: User Story 1 is fully functional. `load_model` loads, verifies, and hashes a pinned base model. Downstream components (P1-2, P2-2, P2-5, P2-7) can begin integration.

---

## Phase 4: User Story 2 — Attach a LoRA Adapter to a Verified Base (Priority: P2)

**Goal**: `load_model("tiny_base", ..., adapter_path=Path("tests/fixtures/tiny_adapter/"))` returns a `LoadedModel` whose `identity_payload` includes `adapter_digest`; passing `tiny_adapter_wrong/` raises `FactVerifyLoaderError` before any attachment occurs.

**Independent Test**: `uv run pytest tests/test_models_loader.py -k "005 or 006" -v` — both US2 hooks pass green. US1 hooks continue to pass.

### Test stubs for User Story 2

- [X] T016 [US2] Write two US2 test function stubs in `tests/test_models_loader.py`:
  - `test_fv_model_005_adapter_base_match` — asserts valid adapter attaches and digest appears in payload; asserts wrong-base adapter raises before any attachment
  - `test_fv_model_006_adapter_digest` — asserts unchanged adapter directory produces identical digest on two loads; asserts one changed adapter byte produces a different digest and therefore different identity hash

### Implementation for User Story 2

- [X] T017 [US2] Implement `compute_adapter_digest(adapter_path: Path) -> str` and `attach_adapter(model, adapter_path: Path, base_identity_hash: str) -> "PeftModel"` in `src/models/adapters.py` — read `fv_adapter_meta.json`, raise `FactVerifyLoaderError` if missing or if `base_identity_hash` mismatches, compute SHA-256 digest over all adapter weight and config files (sorted by path), attach via PEFT `PeftModel.from_pretrained` with `local_files_only=True`, return the wrapped model
- [X] T018 [US2] Integrate `adapter_path` handling into `load_model()` in `src/models/loader.py` — after base model loads successfully, if `adapter_path` is provided call `attach_adapter`, pass the returned `adapter_digest` to `build_identity_payload`
- [X] T019 [US2] Run `uv run pytest tests/test_models_loader.py -k "001 or 002 or 003 or 004 or 005 or 006 or 007 or 008" -v` and confirm all eight hooks pass green

**Checkpoint**: User Stories 1 and 2 are both functional. Adapter-based checkpoints ($M_{FT}$, $M_R^{(k)}$, controls, candidates) can now be loaded with full provenance.

---

## Phase 5: User Story 3 — Enforce the Single Loading Gate (Priority: P3)

**Goal**: A pytest test scans the entire repository AST and fails if any `from_pretrained` attribute access is found outside `src/models/`. The test passes on the current codebase.

**Independent Test**: `uv run pytest tests/test_models_loader.py -k "009" -v` — hook passes green.

- [X] T020 [US3] Write `test_fv_model_009_single_entry_point` in `tests/test_models_loader.py` — walk all `.py` files in the repository root (excluding `src/models/` and `tests/fixtures/`), parse each with `ast.parse`, traverse the AST looking for `ast.Attribute` nodes where `.attr == "from_pretrained"`, collect all matches with file path and line number, assert the collection is empty (message lists each violation)
- [X] T021 [US3] Run `uv run pytest tests/test_models_loader.py -k "009" -v` and confirm the hook passes green on the current codebase; if any violations appear, they are bugs — do not suppress them, report them

**Checkpoint**: All three user stories are independently functional. All nine required test hooks exist.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Prefetch command, full suite validation, and confirming the integration surface.

- [X] T022 [P] Implement `scripts/prefetch_models.py` as a `click` CLI command `prefetch-models --role ROLE --spec-root PATH [--cache-dir PATH]` — parse `models.yaml` for the requested role, download each declared file from the HF hub at the pinned revision using `huggingface_hub.hf_hub_download`, compute and verify the digest of each downloaded file against the spec, save to local cache; this is the only place in the project where network access to HF is permitted
- [ ] T023 [P] Write a smoke test in `tests/test_models_loader.py` (or a separate file) that runs the quickstart.md usage example end-to-end against the fixture: `load_model("tiny_base", spec_root=Path("tests/fixtures/"))`, assert `identity_hash` is a 64-char hex string, assert `model.training` is False, assert `tokenizer` is not None
- [X] T024 Run full suite `uv run pytest tests/test_models_loader.py -v` and confirm all nine named hooks plus the smoke test pass green with no warnings

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion — **BLOCKS all user stories**
- **US1 (Phase 3)**: Depends on Phase 2 — no dependency on US2 or US3
- **US2 (Phase 4)**: Depends on Phase 2 and Phase 3 (reuses `load_model` from T013/T014) — no dependency on US3
- **US3 (Phase 5)**: Depends on Phase 2 only — can start after Phase 2, independently of US1/US2
- **Polish (Phase 6)**: Depends on all user story phases

### User Story Dependencies

- **US1 (P1)**: After Phase 2 — independent
- **US2 (P2)**: After Phase 2 and Phase 3 (extends `load_model` in-place)
- **US3 (P3)**: After Phase 2 — independent of US1/US2 (pure AST scan, no model loading)

### Within Each Phase

- Test stubs before implementation (stubs must FAIL before implementation begins)
- `errors.py` (T007) before `spec.py` (T008), `verify.py` (T009), `identity.py` (T010)
- `verify.py` (T009) and `identity.py` (T010) can run in parallel after T007 is done
- `loader.py` implementation (T013) after T008, T009, T010, T011

---

## Parallel Opportunities

### Phase 1

```
T001 → T002 → T003 → [T004 ‖ T005] → T006
```

T004 and T005 can run in parallel after T003 (both write to different fixture directories).

### Phase 2

```
T007 → T008 → [T009 ‖ T010] → T011
```

T009 and T010 can run in parallel after T008 (different files: `verify.py` vs `identity.py`).

### Phase 3 (US1)

```
T012 (write test stubs, confirm FAIL)
  ↓
T013 (implement load_model)
  ↓
T014 (wire __init__.py)
  ↓
T015 (confirm 6 hooks pass)
```

Sequential within story — all touch `loader.py` or `__init__.py`.

### Phase 5 (US3) and Phase 4 (US2)

US3 (T020–T021) can run in parallel with US2 (T016–T019) after Phase 2, since US3 has no dependency on `load_model` internals — it only scans for `from_pretrained` in the AST.

### Phase 6

T022 and T023 can run in parallel (different files).

---

## Implementation Strategy

### MVP (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational — CRITICAL, blocks everything
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: `uv run pytest tests/test_models_loader.py -k "001 or 002 or 003 or 004 or 007 or 008" -v`
5. P1-2 exclusion gate and P2-2 evaluators can now call `load_model` for base models

### Incremental Delivery

1. Phase 1 + Phase 2 → foundation ready
2. Phase 3 → US1 complete → base model loading verified (enables P1-2, P2-2, P2-5, P2-7)
3. Phase 4 → US2 complete → adapter loading verified (enables P2-1 finetuned checkpoints and controls)
4. Phase 5 → US3 complete → provenance gate active in CI
5. Phase 6 → prefetch command + full suite

---

## Notes

- Every task that touches `tests/test_models_loader.py` adds or modifies a **named** function (`test_fv_model_00N_*`); do not rename these — the names are fixed by the requirements verification matrix.
- `from_pretrained` appears in `src/models/loader.py` and `src/models/adapters.py` only. Any other location is a bug caught by T020.
- Open decisions D-46, D-48, D-50: write all spec-field references against `models.yaml` keys, never literal model names or dtype strings. Tests use `dtype="float32"` and `attn_impl="eager"` from the fixture `models.yaml` — these will not change when D-48 closes.
- Commit messages should reference task IDs and requirement IDs: e.g. `FV-MODEL-001: implement pinned-revision loading (T013)`.
