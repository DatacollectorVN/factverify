# Data Model: FV-MODEL — P2-0 Model Loader

**Feature**: `20260926-105952-model-loader`  
**Date**: 2026-09-26

---

## Entities

### LoadedModel

The return value of `load_model`. Immutable once constructed.

| Field | Type | Description | Source |
|-------|------|-------------|--------|
| `model` | `AutoModelForCausalLM` or `PeftModel` | Loaded model object in evaluation mode, dropout disabled | `from_pretrained` + optional `load_peft_model` |
| `tokenizer` | `AutoTokenizer` | Tokenizer at the pinned tokenizer revision | `from_pretrained` |
| `identity_hash` | `str` | SHA-256 hex digest over `identity_payload`; primary key for ledger and cache | `identity.py` |
| `identity_payload` | `dict[str, str \| None]` | Canonical fields the hash was computed from (see below) | `identity.py` |
| `role` | `str` | The role key that was requested | Caller input |

**Identity payload fields** (sorted-key JSON → SHA-256):

| Key | Value | Notes |
|-----|-------|-------|
| `role` | role name string | e.g. `"blocks_0_2"` |
| `base_repo` | HF repository id | from `models.yaml` |
| `base_revision` | full commit hash | from `models.yaml` |
| `tokenizer_revision` | full commit hash | from `models.yaml`; may equal `base_revision` |
| `dtype` | e.g. `"bfloat16"` | from `models.yaml`; pending D-48 |
| `attn_impl` | e.g. `"flash_attention_2"` | from `models.yaml`; pending D-48 |
| `adapter_digest` | SHA-256 hex or `null` | computed over adapter weight + config files; `null` if no adapter |

---

### ModelSpec (read from `models.yaml`)

Represents one role entry in the frozen spec. The loader reads this; it never writes it.

| Field | Type | Description |
|-------|------|-------------|
| `repo_id` | `str` | Hugging Face repository identifier |
| `revision` | `str` | Full 40-char commit hash for model weights |
| `tokenizer_revision` | `str` | Full 40-char commit hash for tokenizer |
| `dtype` | `str` | Weight dtype declaration (pending D-48) |
| `attn_impl` | `str` | Attention implementation declaration (pending D-48) |
| `files` | `dict[str, str]` | Mapping of relative filename → SHA-256 digest for every weight, config, and tokenizer file |

A `models.yaml` may declare multiple roles (e.g. `base`, `finetune_seed0`, `retain_0`, `refusal_control`).

---

### AdapterMeta (read from `fv_adapter_meta.json`)

Sidecar file in every adapter directory produced by P2-1. The loader reads this to verify base compatibility.

| Field | Type | Description |
|-------|------|-------------|
| `base_identity_hash` | `str` | SHA-256 identity hash of the base model this adapter was trained on |

The loader computes the adapter digest independently — it does NOT trust a cached digest from this file.

---

## State Transitions

`load_model` is stateless (no mutable module-level state). The sequence of operations for a single call:

```
CALL load_model(role, spec_root, adapter_path?)
  │
  ├─ 1. Parse models.yaml → ModelSpec for role          [raises: unknown role, missing file, null field]
  ├─ 2. Verify all base model files against digests     [raises: mismatch, missing, extra file]
  ├─ 3. Load base model + tokenizer (local_files_only)  [raises: missing local file, dtype/attn mismatch]
  ├─ 4. Set eval mode, disable dropout
  ├─ 5. If adapter_path provided:
  │     ├─ 5a. Read fv_adapter_meta.json → AdapterMeta  [raises: missing meta, missing base_identity_hash]
  │     ├─ 5b. Verify adapter base_identity_hash matches loaded base identity
  │     ├─ 5c. Compute adapter_digest over adapter files
  │     └─ 5d. Attach adapter (PeftModel)               [raises: base hash mismatch]
  ├─ 6. Compute identity_payload and identity_hash
  └─ 7. Return LoadedModel
```

Every error path raises before returning any model object.

---

## Validation Rules

| Rule | Entity | Condition | Error |
|------|--------|-----------|-------|
| V1 | ModelSpec | `role` must exist as a key in `models.yaml` | `FactVerifyLoaderError: unknown role '{role}'` |
| V2 | ModelSpec | All declared files must be present locally | `FactVerifyLoaderError: missing file '{path}' for role '{role}'` |
| V3 | ModelSpec | Computed SHA-256 of each file must equal declared digest | `FactVerifyLoaderError: digest mismatch for '{path}' (expected {exp}, got {got})` |
| V4 | ModelSpec | No extra files in the local cache directory beyond declared set | `FactVerifyLoaderError: undeclared file '{path}' found for role '{role}'` |
| V5 | ModelSpec | `dtype` and `attn_impl` fields must be present and non-null | `FactVerifyLoaderError: unresolved spec field '{field}' for role '{role}'` |
| V6 | AdapterMeta | `fv_adapter_meta.json` must be present in adapter directory | `FactVerifyLoaderError: missing fv_adapter_meta.json in '{adapter_path}'` |
| V7 | AdapterMeta | `base_identity_hash` must match the loaded base's `identity_hash` | `FactVerifyLoaderError: adapter base hash mismatch (adapter expects '{exp}', base is '{got}')` |
| V8 | LoadedModel | Hardware must support declared `dtype` and `attn_impl` | `FactVerifyLoaderError: hardware cannot honour dtype='{dtype}' attn_impl='{attn}'` |

All errors are raised as `FactVerifyLoaderError` (subclass of `ValueError`) with a message naming the role, file, or field.
