# Model source and identifier convention

**Relates to**: `.factverify/spec/model_policy.yaml` · `config/models/` · FV-SPEC-089 · FV-SPEC-090 · P0-8

The frozen policy is `.factverify/spec/model_policy.yaml`. Concrete selections live in `config/models/` and use `model_revision` for the weight commit. Callers pass that file explicitly:

```python
load_model(role, model_config=path, spec_root=spec_root)
```

New documents group roles under `roles`.

---

## Is the study locked to Hugging Face Hub?

No. The `config/models/*.yaml` schema does not enforce Hugging Face Hub as the only valid model source. The validator only checks field *format*, not origin.

| Field | What the validator checks | What it does NOT check |
|---|---|---|
| `repo_id` | Non-null, non-empty string | Whether it is a valid HF Hub path |
| `model_revision` | Matches `/^[0-9a-f]{40}$/` (40-char hex) | Whether it resolves on HF Hub |
| `files` | Each value matches `sha256:<64-hex>` | Where the files were downloaded from |

The field names (`repo_id`, `model_revision`) and the 40-character hex revision format **follow HF Hub conventions** because the study's primary model sources (UNLamb, PopQA/Wikidata-derived models) are typically distributed there. This is a convention, not a hard constraint.

---

## Using a non-HF-Hub source

If the chosen model is not on HF Hub — for example, a local checkpoint, a model hosted on a university cluster, or a file downloaded directly from a research lab — the schema still works with the following interpretation:

| Field | Alternative interpretation |
|---|---|
| `repo_id` | Any canonical, human-readable model identifier (e.g. `"org/model-name"`, a DOI, a local path label) |
| `model_revision` | Any 40-character hex string that is **immutable and externally resolvable** — e.g. a Git commit SHA from your own model repo, or a SHA-1 content hash you compute from the weight archive |
| `files` | SHA-256 digests of the local files — source-agnostic |

### What "immutable and externally resolvable" means

The key requirement (from FV-SPEC-090 and plan P0-8) is that someone else — a reviewer, a replicator, a CI job on a different machine — must be able to retrieve the **exact same bytes** from the recorded `repo_id` + `model_revision` combination.

- **HF Hub commit SHA**: satisfies this — the Hub preserves every commit.
- **Git SHA in a public repo**: satisfies this — as long as the repo is not force-pushed.
- **Local file path** (e.g. `/mnt/cluster/models/llama-1b`): does **not** satisfy this — it is machine-specific and mutable.
- **A branch or tag** (e.g. `main`, `v1.0`): does **not** satisfy this — it can move.

If you use a non-standard source, document it in `preregistration.md` under the model-selection decision (D-46) so reviewers know how to resolve the identifier.

---

## Example: local model with a content hash

If you download a model archive outside of HF Hub, you can construct a compliant versioned config like this (`config/models/<config-id>.yaml`):

```yaml
schema_version: "1"
config_id: "local-model-name-1b-v1"
study_stage: "block_0"
roles:
  blocks_0_2:
    repo_id: "research-lab/model-name-1b"          # canonical label for the model
    model_revision: "a3f2c1d4e5b6..."               # sha1 of the model archive, or git SHA
    tokenizer_revision: "99b1f2a3c4d5..."
    variant: base
    dtype: float32
    licence: "custom:https://example.com/licence"
    files:
      model.safetensors: "sha256:..."
      config.json: "sha256:..."
      tokenizer.json: "sha256:..."
```

Record the model source in `preregistration.md`:
> **D-46 resolution**: Model sourced from `<URL or institution>`. The `model_revision` value is the SHA-1 of the downloaded archive `model-name-1b.tar.gz`, verified against the checksum published at `<checksum URL>`.

---

## Summary

The validator enforces **format** (non-null fields, 40-char hex revision, sha256 digest strings). The **semantic** requirement — that the identifier be immutable and externally verifiable — is a methodological rule recorded in `preregistration.md`, not enforced by code. HF Hub is the default and simplest path to satisfying this requirement, but it is not the only one.
