# Data Model: Base Model Selection and Pinning

## Primary Artifact: `.factverify/spec/models.yaml`

```yaml
# .factverify/spec/models.yaml
# Normative model-identity spec artifact — P0-8
# Do not edit after spec-v1 without an amendment record.

roles:
  blocks_0_2:                          # Blocks 0, 1, 2 base model
    repo_id: DECISION_REQUIRED         # D-46: Hugging Face repo path
    model_revision: DECISION_REQUIRED  # D-46: 40-char hex commit SHA
    tokenizer_revision: DECISION_REQUIRED
    variant: DECISION_REQUIRED         # D-49: "base" or "instruct"
    dtype: DECISION_REQUIRED           # D-48: e.g. "float32", "bfloat16"
    licence: DECISION_REQUIRED         # D-46: SPDX identifier or "custom:<url>"
    files: {}                          # filename -> "sha256:<hex>"; filled after download

  block_3_confirmation:                # Block 3 confirmation model
    status: pending                    # staged commitment — fill before P6
    deadline: null                     # set to ISO 8601 date when D-47 resolves
    repo_id: DECISION_REQUIRED
    model_revision: DECISION_REQUIRED
    tokenizer_revision: DECISION_REQUIRED
    variant: DECISION_REQUIRED
    dtype: DECISION_REQUIRED
    licence: DECISION_REQUIRED
    files: {}
```

### Field semantics

| Field | Type | Constraint | Validated by |
|---|---|---|---|
| `repo_id` | string | non-null, non-empty | FV-SPEC-089 |
| `model_revision` | string | `/^[0-9a-f]{40}$/` — 40-char hex SHA | FV-SPEC-090 |
| `tokenizer_revision` | string | same regex | FV-SPEC-090 |
| `variant` | string | one of `"base"`, `"instruct"` | FV-SPEC-089 |
| `dtype` | string | non-null, non-empty (e.g. `"float32"`, `"bfloat16"`) | FV-SPEC-089 |
| `licence` | string | non-null, non-empty; SPDX or `"custom:<url>"` | FV-SPEC-089 |
| `files` | dict | `{filename: "sha256:<64-hex>"}` | FV-SPEC-091 |
| `status` | string or absent | `"pending"` for staged commitments | FV-SPEC-089 |
| `deadline` | ISO 8601 date string or null | required when `status: pending` | FV-SPEC-089 |

**Validation in strict mode (`DECISION_REQUIRED`):** Any field set to the literal string `"DECISION_REQUIRED"` (or null) causes FV-SPEC-089 to fail in strict mode.

**Staged commitment:** A role entry with `status: pending` is not failed by FV-SPEC-089. All other structural checks (revision format, digest format) are `pending` for that role. A `deadline` must be set when `status: pending` — the validator warns if `deadline` is null on a pending entry.

---

## Derived Artifact: Model-Identity Hash

**Definition (FV-SPEC-093):**

```
payload = json.dumps(
    {
        "repo_id": <string>,
        "model_revision": <40-char hex>,
        "tokenizer_revision": <40-char hex>,
        "dtype": <string>,
        "adapter_digest": <"sha256:<hex>" or null>,
    },
    sort_keys=True,
    ensure_ascii=False,
)
identity_hash = "sha256:" + sha256(payload.encode("utf-8")).hexdigest()
```

- `adapter_digest` is `null` at P0-8 time (LoRA adapters are produced by P2-1; they carry their own digest once trained).
- The hash changes if any one of the five fields changes.
- The hash is stable: `sort_keys=True` removes dict-ordering sensitivity; UTF-8 encoding is deterministic.

**Where it appears:**
- Computed and stored in `ledger.sqlite` (P2-5) as `model_identity_hash` column on every checkpoint row.
- Stored as `model_identity_hash` in every generation-cache manifest (P2-7).
- Referenced in the exclusion-gate report (P1-2) as `model_identity_hash`.

---

## Validation Check Entities

Each check produces a result entry in the report:

```json
{
  "rule_id": "FV-SPEC-089",
  "rule_name": "identity_completeness",
  "status": "pass" | "fail" | "pending",
  "diagnostics": ["<message>", ...]
}
```

**Statuses:**
- `pass` — all assertions for this rule succeeded.
- `fail` — at least one assertion failed; `diagnostics` non-empty.
- `pending` — check cannot run because a required upstream artefact is absent (e.g. no downstream report yet produced; no local model directory provided).

---

## Report Structure: `reports/p0-8-validation.json`

```json
{
  "report_id": "<uuid>",
  "timestamp": "<ISO 8601>",
  "spec_root": "<path>",
  "scope": "models",
  "strict": true,
  "checks": [
    {"rule_id": "FV-SPEC-089", "rule_name": "identity_completeness",     "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-090", "rule_name": "immutable_revision",        "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-091", "rule_name": "file_digests",              "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-092", "rule_name": "access_profile_compat",     "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-093", "rule_name": "identity_hash_definition",  "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-094", "rule_name": "downstream_binding",        "status": "...", "diagnostics": []},
    {"rule_id": "FV-SPEC-095", "rule_name": "amendment_protocol",        "status": "...", "diagnostics": []}
  ],
  "identity_hashes": {
    "blocks_0_2": "<sha256:...> or null if pending"
  },
  "pending_artefacts": ["exclusion_gate", "ledger", "cache_manifests"],
  "overall": "pass" | "fail"
}
```

`overall` is `"pass"` only when all checks are `pass` or `pending` (no `fail`). A mix of `pass` and `pending` is a valid pre-implementation state.

---

## Key State Transitions

| State | Condition | FV-SPEC-089 | FV-SPEC-090 | FV-SPEC-091 | FV-SPEC-093 | FV-SPEC-094 | FV-SPEC-095 |
|---|---|---|---|---|---|---|---|
| Pre-D46 (decisions open) | All fields `DECISION_REQUIRED` | fail (strict) / pending (non-strict) | pending | pending | pending | pending | pending |
| Post-D46, pre-download | Fields filled, `files: {}` | pass | pass | pending (no dir) | pass | pending | pending |
| Post-download | `files` populated | pass | pass | pass | pass | pending | pending |
| Post-P1-2 / P2-5 / P2-7 | Downstream artefacts exist | pass | pass | pass | pass | pass | pending |
| Post-freeze | `CHECKSUMS.sha256` exists | pass | pass | pass | pass | pass | pass |

---

## Fixture Layout

```
tests/fixtures/models_spec/
├── valid/
│   ├── models_complete.yaml       — fully resolved entry (synthetic hashes)
│   └── models_staged_block3.yaml  — block_3 is pending; blocks_0_2 complete
├── invalid/
│   ├── missing_field.yaml         — blocks_0_2 missing "licence"
│   ├── mutable_revision.yaml      — model_revision is "main"
│   ├── short_hash_revision.yaml   — model_revision is a 7-char short hash
│   ├── placeholder_value.yaml     — dtype is "DECISION_REQUIRED"
│   └── pending_no_deadline.yaml   — status pending but deadline null
├── model_dir/                     — synthetic local model directory
│   ├── config.json                — {"model_type": "test"}
│   └── tokenizer.json             — {"version": "1.0"}
└── downstream/
    ├── valid_exclusion_gate.json  — model_identity_hash matches computed value
    └── mismatched_gate.json       — model_identity_hash is wrong
```

Synthetic model dir uses text files (no `.safetensors`) since the digest check only needs hashable byte content.
