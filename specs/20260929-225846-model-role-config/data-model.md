# Data Model: Model Role Names and Versioned Model Configuration

## ModelPolicy

**File**: `.factverify/spec/model_policy.yaml`
**Role**: Frozen rules for model selection. It names no repository and no revision.

| Field | Required | Rule |
|---|---|---|
| `schema_version` | yes | `"1"` |
| `governing_spec_revision` | yes | `"spec-v2"` in this amendment. A run whose `spec_revision` differs is refused. |
| `identity_schema_version` | yes | `2`. New records write this version. |
| `required_roles` | yes | Map with exactly `controlled_fact_base` and `pretrained_fact_confirmation`. Each value has `purpose` (non-empty) and `required_capabilities` (non-empty list). |
| `required_identity_fields` | yes | `repo_id`, `model_revision`, `tokenizer_revision`, `variant`, `dtype`, `attn_impl`, `licence`, `files` |
| `role_aliases` | yes | `blocks_0_2` → `controlled_fact_base`; `block_3_confirmation` → `pretrained_fact_confirmation`. Alias keys must not also appear in `required_roles`. |

`controlled_fact_base.required_capabilities` is `offline_weights`, `tokenizer`, `parameter_updates`.
`pretrained_fact_confirmation.required_capabilities` is `offline_weights`, `tokenizer`, and `staged_commitment` is allowed. The confirmation role may be pending. The base role may not.

The policy fails validation if any concrete pin appears: a `repo_id`, a 40-character revision, or a `files` map with entries.

## ModelConfiguration

**File**: one YAML file under `config/models/`. The Block 0 file is `config/models/block0-debug-pythia-410m.yaml`.
**Role**: One immutable selection. Replacing a model means a new file.

| Field | Required | Rule |
|---|---|---|
| `schema_version` | yes | `"1"` |
| `config_id` | yes | Non-empty stable name. The Block 0 file uses `block0-debug-pythia-410m-v1`. |
| `study_stage` | yes | Non-empty label. The Block 0 file uses `block0_debug`. It is not a role name and it is not used to choose a file. |
| `roles` | yes | Map. Every policy role appears once, either resolved or pending. |

Resolved role entry:

| Field | Rule |
|---|---|
| `repo_id` | Non-empty. Not `DECISION_REQUIRED`. |
| `model_revision` | 40 lowercase hex characters. Branch names, tags, and short hashes fail. |
| `tokenizer_revision` | Same rule as `model_revision`. |
| `variant` | `base` or `instruct`. |
| `dtype` | Non-empty. The Block 0 file uses `float32`. |
| `attn_impl` | Non-empty. The Block 0 file uses `eager`. |
| `licence` | Non-empty. SPDX-style text is stored, not interpreted beyond the existing access-profile check. |
| `files` | Map of relative filename to `sha256:` + 64 hex characters. `{}` is valid as "not yet downloaded" and is reported pending by FV-SPEC-091. `load_model` refuses it. |

Pending role entry:

| Field | Rule |
|---|---|
| `status` | `pending` |
| `deadline` | ISO date, or null. Null is a warning. An invalid date fails. A date before today fails when a command needs the role. |
| Identity fields | May be `DECISION_REQUIRED`. They are not loaded. |

A configuration that contains both `blocks_0_2` and `controlled_fact_base`, or both `block_3_confirmation` and `pretrained_fact_confirmation`, is invalid.

## Resolved selection

What `load_model` holds after a successful read. Not a file.

| Field | Source |
|---|---|
| `study_role` | Canonical role after alias resolution |
| `alias_used` | The input name when it was an alias; otherwise null |
| `repo_id`, `model_revision`, `tokenizer_revision`, `variant`, `dtype`, `attn_impl`, `licence`, `files` | The resolved role entry |
| `config_id` | Configuration field |
| `config_digest` | `sha256:` + SHA-256 of the file bytes |
| `identity_schema_version` | From the policy (`2`) |
| `governing_spec_revision` | From the policy |

`local_dir`, when present on a fixture entry, is an optional absolute or spec-root-relative directory for tests. Production configurations omit it. The loader then uses its existing local-cache resolution.

## Identity payloads

### Version 2 (written)

Fields: `repo_id`, `model_revision`, `tokenizer_revision`, `dtype`, `adapter_digest`.
Encoding: `json.dumps(..., sort_keys=True, ensure_ascii=False)` with default separators.
Value: `sha256:` + hex. A change to any of the five fields changes the identity. A change only to the role name, `attn_impl`, `variant`, or `licence` does not.

### Version 1 (verify only)

Fields: `adapter_digest`, `attn_impl`, `base_repo`, `base_revision`, `dtype`, `role`, `tokenizer_revision`.
Encoding: `json.dumps(..., sort_keys=True, separators=(",", ":"))`, UTF-8, no prefix.
Used only to check a record that declares schema version 1, or a historical record with no schema version whose hash matches this payload. It is not written on new loads.

## Provenance binding

Stored together on every new model-dependent result:

| Item | Column or field | Notes |
|---|---|---|
| Study role | `study_role` | Canonical name |
| Configuration name | `model_config_id` | |
| Configuration fingerprint | `model_config_digest` | `sha256:` + file digest |
| Model identity | `model_identity_hash` | Version-2 string on new writes |
| Identity schema version | `identity_schema_version` | `2` on new writes |
| Governing spec revision | `spec_tag` or `spec_revision` | Existing field. Must equal the policy value |

Ledger `checkpoints.identity_hash` and `checkpoints.role` are not these fields.

Rows written before this feature have null binding columns. They are not updated. A new training or evaluation run does not treat a gate report as evidence unless the report's `model_identity_hash` and `model_config_digest` equal the loaded binding.

## State of a role inside one configuration

```text
absent  → invalid configuration
pending, deadline null → validator warning; load of that role refuses
pending, deadline in the future → load of that role refuses
pending, deadline passed → validator failure; load refuses
resolved, files empty → validator digest check pending; load refuses
resolved, files present, digests match → load may construct, offline
resolved, digest mismatch or movable revision → refuse before construction and before network
```

## Relationships

- One policy governs many configurations.
- One configuration fills both required roles.
- One run names one configuration and one role.
- Many gate rows, checkpoint rows, cache entries, and evaluation rows may cite the same binding.
- An adapter digest enters the version-2 identity and does not enter the configuration file. Two adapters on the same base configuration have different model identities and the same `model_config_digest`.
