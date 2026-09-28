# Contract: Job configuration

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26  
**File**: a single YAML document passed as `--config`

---

## Shape

```yaml
role: finetuned            # finetuned | reference | candidate
method: finetune           # finetune | GA | GradDiff | NPO | RMU
base_role: <models.yaml key>
seed: <int>
split: <string>
spec_revision: <string>    # not null, not DECISION_REQUIRED
hardware_class: <string>
determinism_policy: exact  # exact | tolerant
digest_tolerance: "0"      # non-negative integer as a string
target_fact_id: <string>
bundle_id: <string>
source_bundle:
  - <document id>
corpus_dir: <path>         # contains {id}.txt
output_dir: <path>
tier: <string>             # passed through; D-56 decides the vocabulary
optimizer: adamw
learning_rate: <number>
epochs: <int>
batch_size: <int>
max_length: <int>
weight_decay: <number>
manifest:
  train: [<id>, ...]       # only the lists the method requires
lora:                      # finetune only; numbers are D-52
  r: <int>
  alpha: <int>
  dropout: <number>
  target_modules: [<module name>, ...]
```

Reference jobs add `paired_finetune_config: <path>`. Candidate jobs add `parent_adapter: <path>` and replace `lora` with the method fields:

| Method | Extra fields |
|--------|----------------|
| `GA` | `manifest.forget` |
| `GradDiff` | `manifest.forget`, `manifest.retain`, `retain_coeff` |
| `NPO` | `manifest.forget`, `beta` |
| `RMU` | `manifest.forget`, `manifest.retain`, `steering_coeff`, `steering_layer` |

## Hash

`config_hash` = SHA-256 hex of `json.dumps(mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True)` encoded UTF-8. Paths are stored as the strings written in the file, not as resolved absolute paths, so the hash does not depend on the machine's checkout location. The paired-finetune hash is a separate field computed the same way over the paired file.

## Rejection

The loader of this file raises `FactVerifyHarnessError` before any training step when:

- a required key is absent, null, or `DECISION_REQUIRED`
- a key is present that this method does not declare
- `role` and `method` disagree (see data-model role table)
- a manifest list that the method requires is missing or empty
- `optimizer` is not `adamw`
- `determinism_policy` is not `exact` or `tolerant`
- `digest_tolerance` is not a canonical decimal string of a non-negative integer

No key is given a default.
