# Contract: Provenance Binding

**Feature**: `20260929-225846-model-role-config`

Every new model-dependent result stores:

| Field | New-write value |
|---|---|
| `study_role` | Canonical role |
| `model_config_id` | Configuration `config_id` |
| `model_config_digest` | `sha256:` + file digest |
| `model_identity_hash` | Version-2 identity |
| `identity_schema_version` | `2` |
| Governing spec revision | Existing `spec_tag` or `spec_revision`, equal to the policy |

A missing field on a new write fails the write.

## Exclusion gate

Each JSONL row and the Markdown report include the six items. The report lists them once in a provenance block. The JSONL repeats them on every row.

`require_pass` and the training precheck accept a report only when its `model_identity_hash` and `model_config_digest` equal the model just loaded. A report that lacks either field is not evidence for that load. The old report file is left unchanged.

## Ledger

Additive nullable columns on `checkpoints` and `evaluation_runs`:

- `study_role`
- `model_config_id`
- `model_config_digest`
- `model_identity_hash`
- `identity_schema_version`

`schema_version` stays `"1"`. Columns are added with `ALTER TABLE` when missing, same as `decision_key`.

`checkpoints.identity_hash` remains the checkpoint-row id. `checkpoints.role` remains `reference`, `control`, `candidate`, or the other values that table already allows. New checkpoint inserts from `src/train/run.py` fill the binding columns. New evaluation inserts copy the binding from the load that produced the run. Inserts do not update older rows.

## Cache

`CacheRequest` gains `model_config_digest`, `study_role`, `model_config_id`, `identity_schema_version`, and `governing_spec_revision`.

The cache key payload adds `model_config_digest` beside the existing `identity_hash` (that field is the model identity). The other four are stored on the `entries` row so a reader can see them, and they are required on new writes. Existing rows keep nulls. Keys already stored are not rewritten; a new request misses them.

`export_cache` manifest entries include `model_identity_hash` and `model_config_digest` for rows that have them. Rows without them export with those fields null. `import_cache` still refuses a manifest digest that does not match the entry bytes.

## What is not rewritten

Historical gate reports, ledger rows, cache files, and `.factverify/spec/models.yaml` are not migrated. Version-1 identities remain verifiable through `verify_identity_hash` and are not recomputed as version 2.
