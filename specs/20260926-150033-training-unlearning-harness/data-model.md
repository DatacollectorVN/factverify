# Data Model: FV-HARN — P2-1 Training and Unlearning Harness

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26

---

## Entities

### JobConfig

The resolved operator file. Immutable after validation. No field is invented during resolution.

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `role` | enum | yes | `finetuned`, `reference`, or `candidate` |
| `method` | enum | yes | `finetune`, `GA`, `GradDiff`, `NPO`, `RMU` |
| `base_role` | string | yes | Key in `models.yaml`, loaded via `load_model` |
| `seed` | int | yes | Update seed. Non-negative. |
| `split` | string | yes | Recorded on the ledger row. Compared for FV-HARN-010. |
| `spec_revision` | string | yes | Refused when null or `DECISION_REQUIRED` |
| `hardware_class` | string | yes | Declared class for digest comparisons |
| `determinism_policy` | enum | yes | `exact` or `tolerant`. Study choice is D-53. |
| `digest_tolerance` | string | yes | Non-negative integer as text. Study choice is D-53. |
| `target_fact_id` | string | yes | Fact this job is about |
| `bundle_id` | string | yes | Source-bundle identifier recorded on references |
| `source_bundle` | list of string | yes | Document ids in that bundle |
| `corpus_dir` | path | yes | Directory of `{id}.txt` files |
| `manifest` | object | yes | Lists required by the method; see below |
| `output_dir` | path | yes | Final adapter directory |
| `paired_finetune_config` | path | reference only | Paired $M_{FT}$ job file |
| `parent_adapter` | path | candidate only | Published adapter the method continues |
| `learning_rate` | number | yes | D-51 / shared procedure. No code default. |
| `epochs` | int | yes | |
| `batch_size` | int | yes | |
| `max_length` | int | yes | |
| `weight_decay` | number | yes | |
| `optimizer` | enum | yes | `adamw` only |
| `lora` | object | `finetune` | `r`, `alpha`, `dropout`, `target_modules`. Values are D-52. |
| `retain_coeff` | number | `GradDiff` | D-51 |
| `beta` | number | `NPO` | D-51 |
| `steering_coeff` | number | `RMU` | D-51 |
| `steering_layer` | int | `RMU` | D-51 |
| `tier` | string | yes | Passed through to the ledger. Vocabulary is D-56 (FV-LEDG), not checked here. |

`manifest` keys:

| Method | Required lists | Forbidden lists |
|--------|----------------|-----------------|
| `finetune` | `train` (non-empty) | `forget`, `retain` |
| `GA` | `forget` (non-empty) | `train`, `retain` |
| `GradDiff` | `forget`, `retain` (both non-empty) | `train` |
| `NPO` | `forget` (non-empty) | `train`, `retain` |
| `RMU` | `forget`, `retain` (both non-empty) | `train` |

Role and method constraints:

| `role` | Allowed `method` |
|--------|------------------|
| `finetuned` | `finetune` |
| `reference` | `finetune` |
| `candidate` | `GA`, `GradDiff`, `NPO`, `RMU` |

### TrainingItem

One document the job may read.

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | Filename stem under `corpus_dir` |
| `text` | string | Read only by `DataCatalog.get` |

### DataCatalog

The only reader of training text.

| Field | Type | Notes |
|-------|------|-------|
| `allowed_ids` | set of string | Union of the manifest lists for this method |
| `access_log` | set of string | Ids actually returned. Must equal `allowed_ids` at completion. |

### AdapterCheckpoint

A published directory.

| File | Contents |
|------|----------|
| PEFT weights and `adapter_config.json` | Produced by `save_pretrained` |
| `fv_adapter_meta.json` | `base_identity_hash` only |
| `metadata.json` | Lineage and procedure record. Included in the adapter digest. |

### CheckpointMetadata

`metadata.json`. Every field non-null.

| Field | When | Notes |
|-------|------|-------|
| `base_identity_hash` | always | Base model identity, no adapter |
| `parent_checkpoint_hash` | always | Base identity for `finetuned` and `reference`. Full parent identity for `candidate`. |
| `config_hash` | always | Decision 1 |
| `seed` | always | |
| `role` | always | |
| `method` | always | |
| `spec_revision` | always | |
| `split` | always | |
| `hardware_class` | always | |
| `data_order` | always | Manifest ids in yielded order |
| `hyperparameters` | always | The method's declared hyperparameter object, copied from the job |
| `excluded_bundle_id` | `reference` | Equals `bundle_id` |
| `paired_finetune_config_hash` | `reference` | Hash of the paired job file |

### LedgerRow

What the harness submits. P2-5 stores it.

| Field | Type | Notes |
|-------|------|-------|
| `checkpoint_identity_hash` | string | From `load_model` on success. `unfinished:` + config hash when no adapter was published. |
| `parent_checkpoint_hash` | string | Same as metadata when an adapter exists. Base identity, or absent parent, on a failure before load — failure rows still carry the parent they knew. |
| `config_hash` | string | |
| `seed` | int | |
| `fact_id` | string | `target_fact_id` |
| `split` | string | |
| `role` | string | |
| `tier` | string | Unchecked here (D-56) |
| `method` | string | |
| `spec_revision` | string | |
| `status` | enum | `succeeded` or `failed` |
| `adapter_published` | bool | |
| `adapter_path` | path or null | Null when nothing was published |
| `wall_clock_seconds` | number | |
| `gpu_hours` | number | `elapsed_seconds * cuda_device_count / 3600`, or `0` when CUDA is absent |
| `peak_memory_bytes` | int | CUDA peak allocation, or process max RSS when CUDA is absent |
| `training_steps` | int | |
| `training_examples` | int | |

### JobResult

Return value of `run_job`.

| Field | Type | Notes |
|-------|------|-------|
| `status` | enum | `succeeded` or `failed` |
| `adapter_path` | path or null | Set only when `status` is `succeeded` |
| `config_hash` | string | Set once validation has produced a hash |
| `checkpoint_identity_hash` | string or null | Set when `load_model` has hashed the published adapter |
| `error` | string or null | Names the field, document, item, or seed on failure |

---

## Relationships

```
JobConfig --paired_finetune_config--> JobConfig     (reference → finetuned)
JobConfig --parent_adapter--> AdapterCheckpoint     (candidate → prior checkpoint)
JobConfig --manifest--> TrainingItem[]
AdapterCheckpoint --metadata--> CheckpointMetadata
AdapterCheckpoint --identity--> LedgerRow           (one success row per published checkpoint)
DataCatalog.access_log == manifest union            (after a completed read phase)
```

A `reference` config and its paired `finetuned` config share one procedure (Decision 2). Their manifests differ: the reference manifest is disjoint from `source_bundle`.

---

## State transitions

```
load job file
  │  missing file, bad YAML, missing key, null, DECISION_REQUIRED, unknown key
  │  unknown method, role/method mismatch
  ▼
validated JobConfig + config_hash          ← fail here: no corpus open, no load_model
  │
  ├─ reference: procedure match against paired file
  ├─ reference: manifest ∩ source_bundle = ∅
  └─ reference: ledger.split_for_seed(fact, seed) is absent or equals this split
  ▼
seeded run
  │  load_model(base) or load_model(base, parent_adapter)
  │  train; DataCatalog.get is the only text read
  ▼
staging directory + metadata
  │  metadata write fails → delete staging, failed ledger row, return failed
  ▼
rename to output_dir
  │
  ▼
load_model(output_dir) → checkpoint_identity_hash
  │
  ▼
LedgerPort.commit_checkpoint(status=succeeded)
  │  commit fails → delete output_dir, return failed
  ▼
JobResult(status=succeeded)

Any exception after training has started:
  record CostRecord so far, commit status=failed, delete unpublished dirs, return failed
```

Validation failures happen before the first training step and do not write a success row. They still write a failed ledger row when a port is attached and a config hash exists. A failure that happens before the hash exists (unreadable file) returns `failed` with no row, because there is no identity to record; the error names the file.

---

## Validation rules

| Rule | Condition | Error names |
|------|-----------|-------------|
| V1 | Required key missing, null, or `DECISION_REQUIRED` | the field |
| V2 | Unknown key, unknown method, role/method mismatch | the field or the method |
| V3 | Reference procedure differs outside the allowlist | dotted paths of the differing fields |
| V4 | Reference manifest contains a source-bundle document | the document id |
| V5 | `split_for_seed(fact, seed)` returns a different split | the seed |
| V6 | `DataCatalog.get` on an id outside the manifest | the item id |
| V7 | Metadata write fails | the metadata path; adapter not published |
| V8 | Ledger commit fails | ledger failure; adapter not left published |
| V9 | Access log ≠ manifest union at the end of training | the symmetric difference |
| V10 | `spec_root` missing, or `models.yaml` unreadable by `load_model` | the path or the loader error |

All harness errors are `FactVerifyHarnessError` (a `ValueError`). Loader errors propagate as `FactVerifyLoaderError` and are treated as a failed job: no success row, no published adapter.
