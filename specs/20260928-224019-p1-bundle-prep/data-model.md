# Data Model: P1 Fact Bundle Preparation

**Feature**: 20260928-224019-p1-bundle-prep
**Date**: 2026-09-28

---

## Entities

### TrainingRecord

A single TOFU row (or a derived split/rewrite of one) that will be used to finetune the base model on a target fact.

| Field | Type | Description |
|---|---|---|
| `record_id` | `str` | Stable unique ID: `{source_config}_{row_index}_{direction}` (or `_split{n}` suffix for derived records) |
| `text` | `str` | The training text (question or answer field from TOFU, or a split/rewritten version) |
| `direction` | `"forward" \| "inverse"` | Which argument order this record trains |
| `source_row` | `dict` | `{"config": str, "row_index": int, "field": str}` — provenance back to the pinned TOFU row |
| `derived_from` | `str \| None` | Parent `record_id` if this is a split or rewrite; else `null` |

**Validation rules**:
- `record_id` must be unique across all records.
- `text` must not instantiate any evaluation template group from `closure_templates.yaml`.
- A record may not be indexed to more than one target fact (single-target invariant from D-66).

**State transitions**: Once written to `records.jsonl`, a record is immutable. Transformations create new records with `derived_from` set.

---

### SourceBundle

The complete set of training records that express a given target fact, organised by direction.

| Field | Type | Description |
|---|---|---|
| `fact_id` | `str` | Matches `fact_id` in `facts.jsonl` |
| `forward_record_ids` | `list[str]` | Record IDs covering the forward direction (given subject → answer object) |
| `inverse_record_ids` | `list[str]` | Record IDs covering the inverse direction (given object → answer subject) |
| `bundle_digest` | `str` | SHA-256 of the sorted record ID list — used by the audit to detect changes |

**Validation rules**:
- `len(forward_record_ids) >= D-66 minimum` (3 for Block 0).
- `len(inverse_record_ids) >= D-66 minimum` (3 for Block 0).
- Every record ID must exist in the record index.

---

### RecordFactIndex

Many-to-many map from training record ID to the set of fact IDs it expresses (target or retained).

Stored as JSONL: one object per record.

| Field | Type | Description |
|---|---|---|
| `record_id` | `str` | Training record ID |
| `fact_ids` | `list[str]` | All facts this record expresses (may be empty for neutral records) |

**Validation rules**:
- Every record in `records.jsonl` must appear in the index.
- No record may map to more than one target fact (single-target invariant).

---

### LeaveOutManifest

The set of training records used to train $M_R^{(k)}$ — all records except those in fact k's bundle.

Stored as JSON: one file per leave-out unit (`data/controlled/leaveout/<fact_id>.json`).

| Field | Type | Description |
|---|---|---|
| `unit_id` | `str` | Matches `fact_id` of the excluded fact |
| `record_ids` | `list[str]` | All training records excluding the unit's bundle |
| `dataset_digest` | `str` | SHA-256 of sorted `record_ids` — bound to the audit |
| `excluded_fact_ids` | `list[str]` | Facts provably absent from this manifest (for D-69 fact-level: just `[unit_id]`) |

**Validation rules**:
- No `record_id` in `record_ids` may be indexed to any fact in `excluded_fact_ids`.
- `dataset_digest` must be recomputed and checked whenever the manifest is read by the training harness.

---

### NeighbourhoodItem

A single retain probe in one locality bucket for a given target fact.

Stored as JSONL rows in `data/controlled/neighbourhoods.jsonl`.

| Field | Type | Description |
|---|---|---|
| `target_fact_id` | `str` | The fact this item is a neighbourhood of |
| `item_id` | `str` | Stable unique ID: `retain:{target_fact_id}:{bucket}:{n}` |
| `bucket` | `"same_subject" \| "same_relation" \| "compositional" \| "global"` | Locality bucket |
| `statement` | `str` | Human-readable probe statement (no stubs) |
| `expected_answers` | `list[str]` | Acceptable answer strings |
| `language` | `str` | ISO 639-1 language code (`"en"` for Block 0) |
| `source` | `dict` | `{"fact_id": str}` or `{"tofu_config": str, "row_index": int}` — provenance |

**Validation rules**:
- `statement` must not contain `[P1-5 stub]`.
- For same_subject and same_relation: `source.fact_id` must appear in the target's leave-out manifest.
- For global: `source.tofu_config` must be `real_authors` or `world_facts` (or D-38-declared alternative); no training record may be indexed to it.
- For compositional: must pass entailment screen against target with result `clean`.
- Fictional entity names in the statement must belong to the same study split as the target.

---

### AuditResult

Per (unit, record, target) classification from the entailment audit.

Stored as JSONL rows in `results/entailment_audit.jsonl`.

| Field | Type | Description |
|---|---|---|
| `unit_id` | `str` | Leave-out unit (fact ID) |
| `record_id` | `str` | Training record being audited |
| `target_fact_id` | `str` | The fact being checked against (same as unit_id for fact-level leave-out) |
| `verdict` | `"duplicate" \| "entails" \| "clue_bearing" \| "clean"` | Automated classification |
| `method` | `str` | Detection method: `"exact_match"` or `"llm_judge"` |
| `score` | `float \| None` | Judge confidence or null for exact match |
| `threshold` | `float \| None` | Threshold used for flagging or null for exact match |
| `human_adjudication` | `dict \| None` | `{"label": str, "reader_id": str, "notes": str}` — present for flagged records and the random sample |
| `manifest_digest` | `str` | Digest of the leave-out manifest at time of audit |

**Validation rules**:
- Every record in a leave-out manifest must have exactly one `AuditResult` row per target fact in that unit.
- Flagged records (`verdict != "clean"`) must have a non-null `human_adjudication`.
- `manifest_digest` must match the current leave-out manifest digest when the training harness reads it.

---

## File Layout

```text
data/controlled/
├── facts.jsonl                        # input — accepted fact contracts (pass verdict)
├── sources/
│   ├── records.jsonl                  # all training records (new + derived)
│   ├── index.jsonl                    # record_id → fact_ids (many-to-many)
│   └── bundles/
│       ├── <fact_id>.json             # SourceBundle per accepted fact
│       └── ...
├── leaveout/
│   ├── <fact_id>.json                 # LeaveOutManifest per leave-out unit
│   └── ...
└── neighbourhoods.jsonl               # NeighbourhoodItem rows (all facts)

data/tofu_derived/
└── transformations.jsonl              # appended by build_bundles.py for splits/excludes

results/
└── entailment_audit.jsonl             # AuditResult rows

reports/
└── entailment_audit.md                # human-readable audit summary
```

---

## Transformation Record (appended to existing transformations.jsonl)

| Field | Type | Description |
|---|---|---|
| `action` | `"split" \| "exclude" \| "rewrite"` | What happened to the source row |
| `source_record_id` | `str` | Original TOFU row reference |
| `derived_record_ids` | `list[str]` | New record IDs created (empty if `exclude`) |
| `reason` | `str` | Why the transformation was applied |
| `phase` | `"P1-3" \| "P1-4"` | Which pipeline step triggered the transformation |
