# Contract: Versioned Model Configuration

**Feature**: `20260929-225846-model-role-config`
**Directory**: `config/models/`
**Parser**: `src/models/spec.py`, used by the validator, the loader, and prefetch

## Block 0 document

`config/models/block0-debug-pythia-410m.yaml`:

```yaml
schema_version: "1"
config_id: block0-debug-pythia-410m-v1
study_stage: block0_debug

roles:
  controlled_fact_base:
    repo_id: EleutherAI/pythia-410m
    model_revision: 9879c9b5f8bea9051dcb0e68dff21493d67e9d4f
    tokenizer_revision: 9879c9b5f8bea9051dcb0e68dff21493d67e9d4f
    variant: base
    dtype: float32
    attn_impl: eager
    licence: Apache-2.0
    files: {}
  pretrained_fact_confirmation:
    status: pending
    deadline: null
```

Do not create a Block 1 file. Do not fill the confirmation model.

## Validation

`tools/models_validator.py` validates a caller-supplied configuration path against the policy. It keeps rule ids FV-SPEC-089 through FV-SPEC-095.

| Condition | Result |
|---|---|
| Missing required role | FV-SPEC-089 fail, names the role |
| Resolved role missing an identity field, or value `DECISION_REQUIRED` in strict mode | FV-SPEC-089 fail, names the role and field |
| `status: pending` and `deadline: null` | FV-SPEC-089 warning |
| `status: pending` and deadline already passed | FV-SPEC-089 fail |
| `model_revision` or `tokenizer_revision` is not 40 lowercase hex characters | FV-SPEC-090 fail |
| `files` empty and no model directory | FV-SPEC-091 pending |
| A declared file digest does not match, or a file is missing or extra | FV-SPEC-091 fail |
| Licence or capabilities cannot satisfy the access profile | FV-SPEC-092 fail |
| Both an alias and its canonical role are keys | Fail, names both keys. Not an alias success |
| Alias only (`blocks_0_2` or `block_3_confirmation`) | Resolves to the canonical role and emits a deprecation line containing both names |
| Flat document with role names at the root, or a field named `revision` | Fail, names the shape |
| `models.yaml` bytes differ from the stored snapshot digest | FV-SPEC-095 fail. An amendment entry does not authorize that edit |

Validation does not construct a model and does not open a network connection.

## Fingerprint

`model_config_digest` = `sha256:` + hex SHA-256 of the file bytes from `src.data.digests.sha256_file`.

Editing the file and keeping `config_id` produces a different digest. Consumers treat it as a different configuration.
