# Quickstart: Model Role Names and Versioned Model Configuration

## What you are changing

The frozen policy says what a model role must mean. A file under `config/models/` says which weights fill that role for one stage. `.factverify/spec/models.yaml` stays the historical snapshot. Do not edit it.

## Check the policy and the Block 0 selection

```bash
uv run python tools/validate_spec.py --scope models \
  --spec-root .factverify/spec \
  --model-config config/models/block0-debug-pythia-410m.yaml
```

A valid result reports `pretrained_fact_confirmation` as pending and does not offer a repository for it. `controlled_fact_base` is EleutherAI/pythia-410m at the revision already in `models.yaml`, with `attn_impl: eager`.

## Run a command

```bash
uv run python scripts/exclusion_gate.py \
  --model-config config/models/block0-debug-pythia-410m.yaml \
  --role controlled_fact_base \
  --spec-root .factverify/spec \
  --facts data/controlled/facts.jsonl \
  --decisions data/controlled/block0_decisions.yaml \
  --cache-decisions <cache-decisions> \
  --cache-dir <cache-dir> \
  --out results/exclusion_gate.jsonl \
  --report reports/exclusion_gate.md
```

Leaving out `--model-config` or `--role` stops the command. `--role blocks_0_2` still runs during the transition, prints a deprecation line naming `controlled_fact_base`, and writes the new role into the report.

Loading the confirmation role from the Block 0 file stops before any download. `files: {}` on the Pythia role also stops a load until fingerprints exist. The validator may still report that digest check as pending.

## Replace a model later

Add a new file, for example `config/models/block1-controlled-validation.yaml`. Do not edit the Block 0 file. Point the command at the new path. The new report's `model_config_digest` and `model_identity_hash` differ from the Block 0 report. Training refuses a Block 0 exclusion report for the new file.

## Tests

```bash
uv run pytest tests/test_models_spec.py tests/test_models_loader.py tests/test_model_config.py
```

The suite covers a new-name load, an old-name load with a deprecation line, a document that contains both names, a tampered configuration fingerprint, version-1 and version-2 identity checks, and a training precheck that rejects a gate report bound to another configuration.

## Owner stop

`AMD-001` in `.factverify/spec/preregistration.md` is `authorized: false`. This feature does not create the `spec-v2` tag. Before that amendment is in force, replace `deadline_before_final_access` if `2027-03-01` is wrong, set `authorized: true`, recompute the preregistration digest, and tag `spec-v2` yourself.
