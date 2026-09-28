# Contract: `LedgerPort`

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26  
**Implemented by**: P2-5 (`FV-LEDG`, draft). Consumed by `run_job`.

This is the only ledger surface P2-1 uses. The SQLite schema, append-only triggers, role vocabulary enforcement, tier vocabulary (D-56), git dirty checks, and `scripts/ledger.py` belong to FV-LEDG. A study run waits until that implementation exists. Tests use an in-memory object with the same two methods.

---

## Operations

```python
class LedgerPort(Protocol):
    def split_for_seed(self, fact_id: str, seed: int) -> str | None:
        """Return the split already stored for this fact and seed, or None."""

    def commit_checkpoint(self, row: CheckpointRow) -> str:
        """Append one row. Return the ledger row id.

        Raise FactVerifyHarnessError (or a ledger error the harness wraps)
        when the row is rejected. A rejection leaves storage unchanged.
        """
```

`split_for_seed` is called only for `role=reference`, after config validation and before `load_model`. If the returned split is not `None` and differs from the job's split, `run_job` fails naming the seed and does not train.

`commit_checkpoint` is called:

- once with `status="succeeded"` after the adapter is published and `load_model` has returned its identity hash
- once with `status="failed"` when training, metadata, or publish fails after a config hash exists

A successful job has exactly one `succeeded` row for that `checkpoint_identity_hash`. A failed attempt does not also write a `succeeded` row.

## `CheckpointRow`

| Field | Success | Failure before an adapter exists |
|-------|---------|----------------------------------|
| `checkpoint_identity_hash` | loader identity hash | `unfinished:` + `config_hash` (not a model identity) |
| `parent_checkpoint_hash` | as in `metadata.json` | base identity if loading succeeded; otherwise the job's known parent or empty only when loading never happened — then the field is the string `unknown-parent` and `status` is `failed` |
| `config_hash` | required | required |
| `seed` | required | required |
| `fact_id` | `target_fact_id` | same |
| `split` | required | required |
| `role` | required | required |
| `tier` | required | required |
| `method` | required | required |
| `spec_revision` | required | required |
| `status` | `succeeded` | `failed` |
| `adapter_published` | `true` | `false` |
| `adapter_path` | published path | `null` |
| `wall_clock_seconds` | measured | partial |
| `gpu_hours` | measured | partial |
| `peak_memory_bytes` | measured | partial |
| `training_steps` | measured | partial, may be `0` |
| `training_examples` | measured | partial, may be `0` |

Cost formulas (measurement definitions, not hyperparameters):

- `wall_clock_seconds`: perf-counter duration of the attempt
- `gpu_hours`: `wall_clock_seconds * cuda_device_count / 3600` when CUDA is available, else `0`
- `peak_memory_bytes`: CUDA peak allocated bytes when CUDA is available, else process maximum RSS

FV-LEDG must refuse to treat `status != succeeded`, `adapter_published=false`, or an `unfinished:` identity as a checkpoint an evaluator can load. That rule is the ledger side of FV-LEDG-001.
