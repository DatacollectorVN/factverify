# Contract: Load and Prefetch

**Feature**: `20260929-225846-model-role-config`
**Modules**: `src/models/loader.py`, `src/models/spec.py`, `src/models/identity.py`, `scripts/prefetch_models.py`, `scripts/exclusion_gate.py`

## `load_model`

```text
load_model(
    role: str,
    *,
    model_config: Path,
    spec_root: Path,
    adapter_path: Path | None = None,
) -> LoadedModel
```

`model_config` and `spec_root` are required. There is no default path.

Order:

1. Read the policy from `spec_root / "model_policy.yaml"`. Refuse if it is missing or invalid.
2. Read `model_config`. Refuse on a bad shape, a conflict of alias and canonical name, an unknown role, a pending role, an unresolved field, or a movable revision.
3. If `role` is an alias, resolve it and record a deprecation diagnostic that contains the alias and the canonical name. `LoadedModel.role` is the canonical name.
4. Compute `model_config_digest` from the file bytes.
5. Verify file fingerprints. Refuse when `files` is empty, a file is missing, or a digest mismatches.
6. Only then call `from_pretrained`, still with `local_files_only=True`.

A failure in steps 1–5 happens before model construction and before any network access. Prefetch is the only command that may use the network, and only after steps 1–4 succeed for a resolved role. Prefetch downloads only filenames listed in `files`. An empty map downloads nothing and does not invent filenames.

## `LoadedModel` fields

Existing fields stay. These are added:

| Field | Meaning |
|---|---|
| `role` | Canonical study role |
| `identity_hash` | Version-2 identity, `sha256:` prefixed |
| `identity_payload` | The five version-2 fields |
| `identity_schema_version` | `2` |
| `model_config_id` | From the configuration |
| `model_config_digest` | File fingerprint |
| `governing_spec_revision` | From the policy |

`src/models/__init__.py` continues to export only `load_model`, `LoadedModel`, and `FactVerifyLoaderError`.

## Identity helpers

- `compute_identity_hash_v2(payload) -> str` writes the FV-SPEC-093 string.
- `verify_identity_hash(payload, digest, schema_version) -> bool` accepts version `2`, and version `1` for the loader's historical payload. Unknown versions refuse.
- New loads call the version-2 writer only.

## Commands

Exclusion gate:

```text
python scripts/exclusion_gate.py \
  --model-config config/models/block0-debug-pythia-410m.yaml \
  --role controlled_fact_base \
  --spec-root .factverify/spec \
  ...
```

`--model-config` is required. `--role` is required and has no default.

Prefetch:

```text
python scripts/prefetch_models.py \
  --model-config config/models/block0-debug-pythia-410m.yaml \
  --role controlled_fact_base \
  --spec-root .factverify/spec
```

Training job YAML gains required `model_config` (a path). `base_role` must be a canonical role or a legacy alias. A missing `model_config` raises before `load_model`.

## Test bypass

Tests that supply a stand-in model do not call `load_model`. Production commands have no flag that skips loading.
