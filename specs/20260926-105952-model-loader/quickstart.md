# Quickstart: FV-MODEL — P2-0 Model Loader

**Feature**: `20260926-105952-model-loader`  
**Date**: 2026-09-26

---

## Prerequisites

1. Models pre-fetched to local storage:
   ```
   python scripts/prefetch_models.py --role base --spec-root .factverify/spec/
   ```
2. `models.yaml` at `spec-v1` (frozen — do not edit).
3. Adapter directories (if needed) produced by `src/train/` (P2-1); each must contain `fv_adapter_meta.json`.

---

## Load the base model for a role

```python
from pathlib import Path
from src.models import load_model

result = load_model(
    "base",
    spec_root=Path(".factverify/spec/"),
)

model = result.model        # AutoModelForCausalLM, eval mode
tokenizer = result.tokenizer
print(result.identity_hash) # SHA-256 — record in ledger / cache key
```

---

## Load a finetuned or unlearned checkpoint (base + adapter)

```python
result = load_model(
    "finetune_seed0",
    spec_root=Path(".factverify/spec/"),
    adapter_path=Path("checkpoints/finetune_seed0/"),
)

# identity_hash reflects both base and adapter
print(result.identity_payload)
# {'role': 'finetune_seed0', 'base_revision': 'abc123...', ..., 'adapter_digest': 'def456...'}
```

---

## Pass the identity hash to the ledger

```python
from scripts.ledger import record_checkpoint

record_checkpoint(
    identity_hash=result.identity_hash,
    identity_payload=result.identity_payload,
    role=result.role,
    # ... other ledger fields from run config
)
```

---

## What the loader will NOT do

- **Download missing files** — if a file is absent, it raises. Run `prefetch_models.py` first.
- **Accept a revision override** — revisions come from `models.yaml` only.
- **Fall back on hardware mismatch** — if your hardware can't run `bfloat16`, it raises. Configure your environment.
- **Return a model in training mode** — always returns eval mode. Call `result.model.train()` yourself if P2-1 needs it.

---

## Common errors

| Error message | Fix |
|---------------|-----|
| `unknown role 'foo' in models.yaml` | Check the role key exists in `models.yaml` at `spec-v1` |
| `missing file '...' for role '...'` | Run `prefetch_models.py` for this role |
| `digest mismatch for '...'` | Local file is corrupted; re-fetch |
| `adapter base hash mismatch` | Adapter was trained on a different base; check adapter provenance |
| `hardware cannot honour dtype='bfloat16'` | Use a GPU that supports bf16, or wait for D-48 to close with an alternative precision policy |

---

## Running the test suite

```bash
uv run pytest tests/test_models_loader.py -v
```

All 9 hooks (FV-MODEL-001 through FV-MODEL-009) should pass green. Tests use a tiny fixture model in `tests/fixtures/tiny_model/` — no real model downloads required.
