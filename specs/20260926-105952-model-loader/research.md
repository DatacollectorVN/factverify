# Research: FV-MODEL — P2-0 Model Loader

**Feature**: `20260926-105952-model-loader`  
**Date**: 2026-09-26  
**Source notes**: `FV-MODEL — P2-0.md` (draft) · `FV-SPEC — P0-8` (open decisions D-46, D-48, D-50)

---

## Decision 1: Identity-hash canonical form (pending D-48)

**Decision**: Compute SHA-256 over a deterministically serialised JSON payload containing:
`{"role": <str>, "base_repo": <str>, "base_revision": <str>, "tokenizer_revision": <str>, "dtype": <str>, "attn_impl": <str>, "adapter_digest": <str|null>}`.
Keys are sorted; values are the exact strings from `models.yaml`. The adapter digest field is `null` when no adapter is attached.

**Rationale**: Byte-identical on any machine because JSON with sorted keys is deterministic. Including `dtype` and `attn_impl` captures the precision policy (D-48 field references), which changes logits. The `adapter_digest` SHA-256 over adapter weight + config files ensures two adapters at the same path but different contents produce different hashes. This is the simplest scheme compatible with FV-SPEC P0-8 §093's intent; if P0-8 specifies a different canonical form when D-48 closes, the `identity.py` module is the single place to update.

**Alternatives considered**:
- Hash directly over weight bytes: Too slow at load time; not the right abstraction — the hash should cover the *spec identity*, not the *bits in RAM*.
- Use the HF `model.config.to_dict()` hash: Not reproducible across Transformers versions; captures implementation metadata, not spec identity.

**Open decision note**: Until D-48 closes, `dtype` and `attn_impl` values in the payload MUST come from `models.yaml` spec fields, never from runtime inspection of the loaded model.

---

## Decision 2: Adapter metadata format (coordination with P2-1)

**Decision**: Each adapter directory produced by P2-1 (`src/train/`) contains a `fv_adapter_meta.json` file with at minimum `{"base_identity_hash": <str>}`. The loader reads this file to verify base compatibility (FR-005).

**Rationale**: A separate sidecar file is the simplest contract between P2-0 and P2-1. It avoids parsing PEFT's own `adapter_config.json` (which does not carry a FactVerify identity hash) and keeps the metadata format fully under project control.

**Alternatives considered**:
- Embed in `adapter_config.json`: Risks being overwritten or conflated with PEFT internals.
- Derive base identity at attach time by loading the base model separately: Circular and expensive.

**Coordination note**: The `fv_adapter_meta.json` schema must be agreed between P2-0 and P2-1 before either is finalised. Minimum field: `base_identity_hash`. P2-1 is responsible for writing this file when it saves an adapter.

---

## Decision 3: Offline guard implementation (FR-003)

**Decision**: Pass `local_files_only=True` to every `from_pretrained` call within `src/models/`. If a file is missing locally, Transformers raises `OSError` (with a message mentioning the missing file), which the loader wraps into a descriptive `FactVerifyLoaderError` naming the role and the missing file.

**Rationale**: `local_files_only=True` is the canonical Transformers flag for offline operation. It raises before any network socket is opened. This is the minimal and most robust approach.

**Alternatives considered**:
- Monkey-patch or mock the network: Fragile; does not survive library upgrades.
- `TRANSFORMERS_OFFLINE=1` environment variable: Works but is a process-global side effect that could interfere with other tools.

---

## Decision 4: Static entry-point check (FR-009)

**Decision**: Implement as a pytest test (`test_fv_model_009_single_entry_point`) that uses `ast.parse` to scan all `.py` files in the repository (excluding `src/models/` and test fixtures) for attribute accesses named `from_pretrained`. Fail the test if any are found, reporting file and line number.

**Rationale**: An AST scan is deterministic, fast, requires no subprocess, and runs in the standard pytest suite. It covers `AutoModelForCausalLM.from_pretrained`, `AutoTokenizer.from_pretrained`, `PeftModel.from_pretrained`, and any future additions.

**Alternatives considered**:
- `grep` in CI: Brittle to string matching; harder to exclude `src/models/` reliably.
- Import-time hook: Too invasive; would affect production code paths.

---

## Decision 5: Fixture model for tests (no real HF downloads in CI)

**Decision**: Tests use a tiny randomly initialised model saved to `tests/fixtures/tiny_model/` (committed to the repo). The fixture has the same directory structure as a real HF model (config.json, model.safetensors, tokenizer files) and a corresponding `tests/fixtures/models.yaml` that declares the fixture as a role. File digests in the fixture `models.yaml` are computed over the committed fixture files.

**Rationale**: Avoids any network dependency in CI. The fixture need not be a real language model — its purpose is to exercise the loading, verification, and hashing code paths.

**Alternatives considered**:
- Mock `from_pretrained`: Hides the real loading behaviour; makes the offline test (FV-MODEL-003) meaningless.
- Download a small real model in CI: Introduces network dependency and a third-party source.

---

## Summary: All NEEDS CLARIFICATION resolved

| Unknown | Resolution |
|---------|-----------|
| Identity hash canonical form | SHA-256 over sorted-key JSON payload; single source of truth in `identity.py` |
| Adapter metadata format | `fv_adapter_meta.json` sidecar with `base_identity_hash`; agreed with P2-1 |
| Offline guard mechanism | `local_files_only=True` in all `from_pretrained` calls |
| Static entry-point check | AST scan in `test_fv_model_009_single_entry_point` |
| Test fixture strategy | Tiny committed model in `tests/fixtures/tiny_model/` |
