# Quickstart: FV-HARN — P2-1 Training and Unlearning Harness

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26

This harness trains one checkpoint from one job file and one seed. It does not choose study hyperparameters. D-51, D-52, and D-53 are still open.

## What you need first

1. A frozen spec root (default `.factverify/spec`) that `load_model` can read, including `models.yaml`.
2. A base role whose files are already on disk (P2-0 prefetch). The harness does not download weights.
3. A corpus directory of `{id}.txt` files and a manifest that lists only the ids this job may read.
4. A ledger implementing `LedgerPort` (P2-5). Until that exists, library tests inject an in-memory port. Do not invent a second SQLite file here.

## Run a job

```text
python -m src.train.run \
  --config configs/train/<job>.yaml \
  --spec-root .factverify/spec \
  --ledger <ledger path>
```

Exit code 0 means the adapter directory exists, `metadata.json` and `fv_adapter_meta.json` are present, and exactly one succeeded ledger row was committed. Any other outcome is a non-zero exit and a message that names the field, document, item, or seed.

## Three job kinds

| Role | Method | What is different from the finetune |
|------|--------|--------------------------------------|
| `finetuned` | `finetune` | The job that teaches the fact |
| `reference` | `finetune` | Manifest and seed only, plus the six identity fields in `research.md` Decision 2. Manifest must miss the whole source bundle. Seed must be new for that fact on this split. |
| `candidate` | `GA`, `GradDiff`, `NPO`, or `RMU` | Starts from `parent_adapter`. Records that parent as `parent_checkpoint_hash`. |

An unknown method name fails before any training file is opened.

## Check the checkpoint

Published `output_dir` contains PEFT weights, `fv_adapter_meta.json` (`base_identity_hash`), and `metadata.json` (config hash, seed, role, method, parent, data order). Reference metadata also contains `excluded_bundle_id` and `paired_finetune_config_hash`.

Loading that directory back through `load_model` yields the identity hash stored on the ledger row.

## Failure cases worth knowing

- A missing hyperparameter raises and names the field. There is no code default.
- A reference manifest that includes a bundle document raises and names the document. Nothing is trained.
- A reference seed already stored under another split raises and names the seed.
- A metadata or ledger failure does not leave a published adapter behind.
- An exception during training writes a failed ledger row with the cost gathered so far.

## Tests

```text
uv run pytest tests/test_harness.py
```

The ten hooks are `test_fv_harn_001_config_complete` through `test_fv_harn_010_seed_disjoint`. They use `tests/fixtures/harness/` and do not need a GPU. Fixture numbers in that directory are not Block 0–2 settings.

## Out of scope for this command

Model loading and hashing (P2-0), fake controls (P2-3), evaluators and the query budget (P2-2), the SQLite ledger (P2-5), the relearning attack policy in `attacks.yaml`, and the Block 3 learning-rate sweep (P6-4).
