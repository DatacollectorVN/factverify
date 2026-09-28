# Contract: Checkpoint metadata

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26  
**Directory**: the published adapter path (`output_dir`)

---

## Files

| File | Writer | Reader | In adapter digest |
|------|--------|--------|-------------------|
| `adapter_config.json`, weight file | PEFT `save_pretrained` | `load_model` | yes |
| `fv_adapter_meta.json` | harness | `src/models/adapters.py` | no (loader excludes it) |
| `metadata.json` | harness | ledger, audits, this harness's tests | yes |

The directory is published only when both JSON files have been written. Consumers treat a directory without `metadata.json` as unpublished.

## `fv_adapter_meta.json`

```json
{"base_identity_hash": "<sha256 hex of the base role, no adapter>"}
```

This value is the `identity_hash` from `load_model(base_role, spec_root=spec_root)` with no adapter. It is the same string stored as `base_identity_hash` in `metadata.json`.

## `metadata.json`

Required on every checkpoint:

```json
{
  "base_identity_hash": "<sha256>",
  "parent_checkpoint_hash": "<sha256>",
  "config_hash": "<sha256>",
  "seed": 0,
  "role": "finetuned",
  "method": "finetune",
  "spec_revision": "<string>",
  "split": "<string>",
  "hardware_class": "<string>",
  "data_order": ["<id>", "..."],
  "hyperparameters": {}
}
```

`parent_checkpoint_hash` is `base_identity_hash` when `role` is `finetuned` or `reference`. When `role` is `candidate` it is the `identity_hash` of `load_model(base_role, adapter_path=parent_adapter)`.

`hyperparameters` is the subset of the job that the method consumes (`learning_rate`, `epochs`, `batch_size`, `max_length`, `weight_decay`, `optimizer`, and the method-specific block). It is a copy, not a second source of defaults.

Reference checkpoints also include:

```json
{
  "excluded_bundle_id": "<bundle_id>",
  "paired_finetune_config_hash": "<sha256>"
}
```

Any missing or null field is a metadata failure: the directory is not published.

## Identity of the new checkpoint

After publish, the harness calls `load_model(base_role, spec_root=spec_root, adapter_path=output_dir)` and uses the returned `identity_hash` as `checkpoint_identity_hash` on the ledger row. The harness does not compute that hash itself.
