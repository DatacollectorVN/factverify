# Data Model: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Feature**: `20260927-161631-ledger-stats-cache`  
**Date**: 2026-09-27

Field values that are study decisions are loaded from the caller-supplied decision record or from a fixture spec root. They are not defaults in code. See `research.md`.

---

## Checkpoint row

One immutable `checkpoints` row. `add_checkpoint` rejects an empty required field by name.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `row_id` | string | generated | Returned after commit. Not supplied by the caller |
| `created_at` | timestamp | generated | Set at insert |
| `identity_hash` | string | yes | Non-empty. A second row must set `supersedes` to the current row of this hash |
| `parent_ledger_id` | string or null | root: null | Non-root must already exist |
| `parent_identity_hash` | string | root: `""` | Must match the parent row when `parent_ledger_id` is set |
| `config_hash` | string | yes | Non-empty |
| `seed` | int | yes | |
| `fact_id` | string | yes | Non-empty |
| `split` | string | yes | `final_test` and `final-test` share the final-test guards. `calibration` is the calibration token |
| `role` | enum | yes | `base`, `finetuned`, `reference`, `control`, `candidate` |
| `tier` | string | yes | Must be a member of closed D-56 `tiers`. Open D-56 raises before insert |
| `family` | string | yes | Non-empty |
| `method` | string | yes | Non-empty |
| `implementation_id` | string | control: yes | Non-empty for `control`. Other roles may pass `""` |
| `spec_tag` | string | yes | Non-empty |
| `git_commit` | string | yes | Non-empty. Supplied by the caller. The ledger does not read git |
| `dirty` | bool | yes | `true` on a final-test row raises `dirty` |
| `tokens` | int | yes | ≥ 0 |
| `scored_candidates` | int | yes | ≥ 0 |
| `training_steps` | int | yes | ≥ 0 |
| `training_examples` | int | yes | ≥ 0 |
| `exports` | int | yes | ≥ 0 |
| `wall_clock_seconds` | float | yes | ≥ 0 |
| `gpu_hours` | float | yes | ≥ 0 |
| `peak_memory_bytes` | int | yes | ≥ 0 |
| `status` | string | yes | Non-empty. No status vocabulary is declared |
| `supersedes` | string or null | no | When set, must be the current row id of the same `identity_hash` |

---

## Evaluation-run row

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `run_id` | string | generated | |
| `created_at` | timestamp | generated | |
| `checkpoint_ledger_id` | string | yes | Must exist |
| `arm` | string | yes | Non-empty |
| `split` | string | yes | Same final-test tokens as checkpoints |
| `spec_tag` | string | yes | Non-empty |
| `thresholds_tag` | string | yes | Non-empty on every run, including calibration |
| `budget_used` | object | yes | Keys: `tokens`, `scored_candidates`, `training_steps`, `exports`, `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`. All present |
| `pass_number` | int | yes | ≥ 1. On a final-test split, a value other than 1 raises unless an incident references pass 1 |
| `git_commit` | string | yes | Non-empty |
| `dirty` | bool | yes | `true` on a final-test run raises `dirty` |

---

## Incident row

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `incident_id` | string | generated | |
| `created_at` | timestamp | generated | |
| `split` | string | yes | The final-test split being unlocked |
| `references_pass_number` | int | yes | Must be 1 to unlock a later pass. Any other number leaves the guard closed |
| `note` | string | yes | Non-empty. No incident vocabulary |

---

## Disjointness report

| Field | Type | Rule |
|-------|------|------|
| `ok` | bool | False when any dimension overlaps |
| `counts` | object | Distinct values of `fact`, `reference_seed`, and `control_implementation` on `calibration` and on `final_test` |
| `offenders` | list | Row ids that share a value across those splits. Empty when `ok` |

---

## Cache request

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `identity_hash` | string | yes | Non-empty model identity |
| `model_input` | string | yes | Exact post-template text. No trim, no case fold |
| `decoding` | object | yes | Every field enters the key. Empty object is allowed and is still part of the key |
| `seed` | int | yes | |
| `sample_index` | int | yes | ≥ 1 |
| `request_kind` | enum | yes | `generate` or `score` |
| `producer_run_id` | string | yes | Stored on the entry. Not part of the lookup key |
| `software_versions` | object | when D-60 says true | Non-empty string-to-string map. Omitted from the key when the closed row says false |

D-60 `open` raises before a key is built.

---

## Cache entry and event

| Field | Type | Rule |
|-------|------|------|
| `body` | string or object | Completion text, or a score object |
| `token_count` | int | ≥ 0. Returned by `compute` |
| `created_at` | timestamp | Set on first insert |
| `content_digest` | string | sha256 of the canonical body |
| `producer_run_id` | string | From the request |
| `event` | enum | Exactly one of `hit`, `miss`, `conflict`, `corrupt` |

`conflict` carries `stored_digest` and `new_digest` and does not replace the row.

---

## Verdict row

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `row_id` | string | yes | Named in load errors |
| `checkpoint_ledger_id` | string | yes | Must resolve on the ledger port |
| `evaluation_run_id` | string | yes | Must resolve, and that run's checkpoint must match |
| `fact_id` | string | yes | |
| `arm` | string | yes | |
| `verdict` | string | yes | |
| `oracle_label` | string | yes | |
| `control_family` | string | yes | Empty string allowed only when the row is not a control |
| `split` | string | yes | |
| `prompt_id` | string | yes | Nested observation. Not a resample unit for `estimate` |
| `threshold_id` | string | threshold selection | Groups the FRR bound |
| `rejected` | bool | threshold selection | Numerator of FRR for a genuine reference |

A missing or unknown ledger id fails the load and names `row_id`.

---

## Estimate table

Returned and written as JSON. Present only when the decisions that estimate needs are closed. See `research.md` for which call raises.

| Field | Type | Rule |
|-------|------|------|
| `purpose` | enum | `threshold_selection` or `final_report` |
| `seed` | int | The seed argument |
| `replicate_count` | int | From closed D-57 |
| `design` | string | `nested` or `crossed` |
| `spec_version` | string | `margins.yaml` `version` |
| `input_digest` | string | sha256 of the canonical verdicts |
| `rows` | list | One overall row and, when D-10 is closed, one row per `control_family` |
| `estimates` | object | `frr`, `fcr`, and `delta_fcr` against each baseline arm present in the table |
| `interval` | object | Percentile bounds when D-57 says `percentile` |
| `n` | int | Case count. A family with no cases has `n: 0` and no rate |
| `point` | decimal or absent | Absent when `n` is 0 |

---

## Decision records this feature reads

Caller-supplied YAML. `status` is `open` or `closed`. A missing id is `open`.

| Id | Closed fields | Rule |
|----|---------------|------|
| D-56 | `tiers` | Non-empty list of strings. Checkpoint `tier` must be a member |
| D-60 | `include_software_versions` | `true` or `false` |
| D-07 | `resampling_contract`, `design` | `paired_block_bootstrap`, and `nested` or `crossed` |
| D-06 | `case_weights` | `uniform` only. Open does not block the unweighted same-case check |
| D-10 | `per_family`, `overall` | Both `mean` |
| D-03 | `procedure` | `one_sided_exact` |
| D-08 | `procedure` | `holm`, `bh`, or `by` |
| D-57 | `interval_type`, `replicate_count`, `coverage_tolerance` | `percentile`, a positive int, a decimal string |

D-20 is not read. Charge rules stay in `attacks.yaml`.
