# Data Model: FV-CTRL — P2-3 Fake-Unlearning Controls

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27

Field values that are study decisions are loaded from the caller-supplied decision record. They are not defaults in code. See `research.md`.

---

## ControlConfig

The caller-supplied YAML document. Unknown keys refuse. Missing required keys refuse. No key is filled by code.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `family` | enum | yes | One of the nine family tokens in `research.md` Decision 1 |
| `implementation_id` | string | yes | Must be the registered id for `family` |
| `severity` | string, number, or mapping | yes | Stored and hashed. Never read to change behavior |
| `parent_ledger_id` | string | yes | Looked up on the ledger port |
| `fact_id` | string | yes | Must equal the parent row's `fact_id` |
| `seed` | int | yes | Recorded on the label. No default |
| `split` | enum | yes | `construction`, `calibration`, `final_test`. Input `final-test` normalizes to `final_test` |
| `spec_revision` | string | yes | Copied onto the label. No default |
| `decisions` | path | yes | Decision-record YAML outside `.factverify/spec/` |
| `fact_contract` | path | yes | A fact-contract JSON file |
| `output_dir` | path | yes | Where `control.json` is written. Must not be inside `.factverify/` |
| `refusal_text` | string | refusal and template-specific | Non-empty. Absent for other families |
| `replacement_text` | string | answer replacement | Non-empty |
| `suppressed_group_ids` | list of string | template-specific | Non-empty |
| `vector_path` | path | reversible steering | File must exist. Bytes enter the digest |
| `method` | enum | destruction families | `GA`, `GradDiff`, `NPO`, or `RMU` |
| `bucket` | enum | destruction families | Targeted: `same_subject` or `same_relation`. Broad: `global` |
| `manifest` | list of string | destruction families | Non-empty |

Forbidden keys, refused before any other read: `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, `frr`. A string value ending in `verdict.json` or `budget.json` also refuses.

---

## DecisionRecord

One YAML mapping. Rows the build does not need may be absent. A row that is needed and missing is `open`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `decision_id` | enum | yes | `D-53`, `D-54`, `D-55`, or `D-61` |
| `status` | enum | yes | `open` or `closed` |
| `digest_tolerance` | decimal string | when D-53 is closed | Only `0` is interpreted. Any other value raises |
| `max_abs_gap` | decimal string | when D-54 is closed | Inclusive absolute gap in `[0, 1]` between disabled accuracy and parent accuracy |
| `min_count` | int | when D-55 is closed | Certification passes only if `min_count` is ≤ the registered count (1) |
| `mechanism_layer` | enum | when D-61 is closed | One of the five layers. Read only for `untouched` |

---

## ControlLabel

Written to `control.json` only when `status` is `accepted`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `family` | enum | yes | |
| `implementation_id` | string | yes | |
| `severity` | as configured | yes | |
| `mechanism_layer` | enum | yes | Exactly one of `prompt/serving`, `output post-processing`, `logits`, `activations`, `weights` |
| `oracle_label` | const | yes | `negative` |
| `split` | enum | yes | |
| `fact_id` | string | yes | |
| `parent_ledger_id` | string | yes | |
| `seed` | int | yes | |
| `spec_revision` | string | yes | |
| `config_hash` | string | yes | SHA-256 of canonical config JSON |
| `artifact_digest` | string | yes | SHA-256 defined in `research.md` Decision 5 |
| `status` | const | yes | `accepted` |
| `expected_identifiability` | const | output filter only | `structurally_indistinguishable` when the loaded profile is Profile A as in Decision 9. Omitted for every other family |

`load_control` refuses a file that lacks any required field, whose `oracle_label` is not `negative`, whose `status` is not `accepted`, or whose `mechanism_layer` is not one of the five.

---

## LedgerRow

Committed through `ControlLedgerPort`. Not a `src.train.ledger.CheckpointRow`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `ledger_id` | string | yes | Returned by `commit` |
| `role` | const | yes | `control` |
| `family` | enum | yes | |
| `implementation_id` | string | yes | |
| `parent_ledger_id` | string | yes | |
| `fact_id` | string | yes | |
| `split` | enum | yes | |
| `config_hash` | string | yes | |
| `seed` | int | yes | |
| `spec_revision` | string | yes | |
| `status` | enum | yes | `accepted`, `rejected`, or `unchecked` |
| `wall_clock_seconds` | float | yes | |
| `gpu_hours` | float | yes | Same measurement as `src/train/cost.py`: elapsed seconds times visible CUDA devices, divided by 3600. Otherwise 0 |
| `peak_memory_bytes` | int | yes | |

`accepted` is written only with a `control.json` negative label. `rejected` is written with a rejection record and no negative label. `unchecked` is written when D-54 is open or a required locality margin is null. `load_control` refuses `rejected` and `unchecked`.

Early refusals (bad parent, forbidden key, unknown family, split collision, missing field) raise before `commit`.

---

## RejectionRecord

JSON beside the output directory when a numeric check fails. Not a negative label.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `family` | enum | yes | |
| `implementation_id` | string | yes | |
| `fact_id` | string | yes | |
| `reason` | enum | yes | `retention_gap` or `locality_margin` |
| `measured` | mapping | yes | The accuracies or the bucket deltas the check compared |
| `threshold` | string | yes | The decision value or the margin value that was applied |

---

## ParentView

Returned by `ControlLedgerPort.get_parent`. This feature does not write parent rows.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `ledger_id` | string | yes | |
| `role` | string | yes | Must be `finetuned` |
| `fact_id` | string | yes | Must equal the config `fact_id` |
| `checkpoint_identity_hash` | string | yes | Copied into the untouched artifact pointer when D-61 is closed |

---

## CatalogEntry

Returned by `list_catalog`. Not loaded from the spec.

| Field | Type | Rule |
|-------|------|------|
| `family` | enum | Nine tokens |
| `implementation_ids` | list of string | Length 1 today |
| `mechanism_layer` | string or null | Null only for `untouched` while D-61 is open |
| `buildable` | bool | False for `untouched` while D-61 is open |

---

## State transitions

```text
config
  ├─ invalid / bad parent / split collision / forbidden key → raise, no row
  ├─ untouched while D-61 open → raise, no row
  ├─ suppression or destruction, check cannot run (open D-54 or null margin)
  │     → ledger status unchecked, no control.json, then raise naming the gap
  ├─ check runs and fails → ledger status rejected + rejection record, no control.json
  └─ check passes, or family needs no check and the build finishes
        → ledger status accepted + control.json (oracle_label negative)
```

Families that need no acceptance check before a negative label: none of the six suppression families (they need D-54) and neither destruction family (they need a margin). `untouched`, once D-61 is closed, has no retention check and no locality check; the parent pointer is the artifact. Wrapper serving is not an acceptance check.

`compare_builds` is not a state change. It reads two accepted digests and either returns or raises. It does not rewrite labels.
