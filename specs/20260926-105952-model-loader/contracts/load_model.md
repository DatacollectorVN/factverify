# Contract: `src/models` Public Interface

**Feature**: `20260926-105952-model-loader`  
**Date**: 2026-09-26  
**Module**: `src/models/__init__.py`

---

## Public exports

```python
from src.models import load_model, LoadedModel, FactVerifyLoaderError
```

Only `load_model`, `LoadedModel`, and `FactVerifyLoaderError` are public. All other names in `src/models/` are internal.

---

## `load_model`

```
load_model(
    role: str,
    *,
    spec_root: Path,
    adapter_path: Path | None = None,
) -> LoadedModel
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `role` | `str` | yes | Key in `models.yaml` identifying which checkpoint to load |
| `spec_root` | `Path` | yes (keyword-only) | Path to the frozen spec directory containing `models.yaml` |
| `adapter_path` | `Path \| None` | no (keyword-only) | Path to a LoRA adapter directory produced by P2-1; `None` loads the base model only |

### Return value

Returns `LoadedModel` — an immutable dataclass with fields:

| Field | Type | Description |
|-------|------|-------------|
| `model` | `AutoModelForCausalLM \| PeftModel` | Model in evaluation mode, dropout disabled |
| `tokenizer` | `AutoTokenizer` | Tokenizer at the pinned revision |
| `identity_hash` | `str` | SHA-256 hex digest; primary key for ledger and cache |
| `identity_payload` | `dict[str, str \| None]` | Canonical fields used to compute the hash |
| `role` | `str` | The role that was loaded |

### Errors

All error paths raise `FactVerifyLoaderError` (a `ValueError` subclass) **before** returning any model object. The message names the role, file, or field that caused the failure.

| Trigger | Message pattern |
|---------|----------------|
| Unknown role | `"unknown role '{role}' in {models_yaml}"` |
| Caller-supplied revision override attempted | `"revision override not permitted; use models.yaml"` |
| Missing local file | `"missing file '{path}' for role '{role}'"` |
| Digest mismatch | `"digest mismatch for '{path}' (expected {exp}, got {got})"` |
| Undeclared extra file | `"undeclared file '{path}' found for role '{role}'"` |
| Unresolved spec field | `"unresolved spec field '{field}' for role '{role}'"` |
| Hardware mismatch | `"hardware cannot honour dtype='{dtype}' attn_impl='{attn}'"` |
| Missing adapter meta | `"missing fv_adapter_meta.json in '{adapter_path}'"` |
| Adapter base hash mismatch | `"adapter base hash mismatch (adapter expects '{exp}', base is '{got}')"` |

### Guarantees

- **Offline**: Never opens a network connection. All files must be pre-fetched via `scripts/prefetch_models.py`.
- **Deterministic**: Given identical inputs and seed, the returned model produces identical logits on the same device.
- **Eval mode**: `model.training` is `False`; stochastic layers are disabled.
- **Fail closed**: Any bad input raises before a model object is constructed or returned.
- **Stable identity**: `identity_hash` is byte-identical across machines for the same `(role, spec_root, adapter_path)`.

---

## `FactVerifyLoaderError`

```python
class FactVerifyLoaderError(ValueError): ...
```

All loader errors are instances of this class. Callers that want to catch loader failures specifically should catch `FactVerifyLoaderError`; callers that want any `ValueError` may catch `ValueError`.

---

## `LoadedModel`

```python
@dataclass(frozen=True)
class LoadedModel:
    model: AutoModelForCausalLM | PeftModel
    tokenizer: AutoTokenizer
    identity_hash: str
    identity_payload: dict[str, str | None]
    role: str
```

Frozen dataclass — fields are set once at construction and cannot be reassigned. Callers that need training mode must call `model.train()` explicitly on the `model` attribute.

---

## What is NOT in scope

| Capability | Lives in |
|-----------|---------|
| Choosing or pinning models | `FV-SPEC — P0-8`, `models.yaml` |
| Downloading model files | `scripts/prefetch_models.py` |
| Finetuning or unlearning | `src/train/` (P2-1, FV-HARN) |
| Prompt formatting / chat templates | `src/eval/` (P2-2, FV-EVAL) |
| Writing ledger rows | `scripts/ledger.py` (P2-5, FV-LEDG) |
| Cache storage | `src/cache/` (P2-7, FV-CACHE) |
| Quantised exports | P6-6 |
