# Data Model: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27

Field values that are study decisions are loaded from the spec root. They are not defaults in code. See `research.md` Decisions 2–4.

---

## Case

The evaluation unit: one checkpoint and one fact on one split.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `case_id` | string | yes | Unique within the run |
| `checkpoint_ledger_id` | string | yes | Copied onto the verdict. Not looked up in SQLite here |
| `fact_id` | string | yes | |
| `split` | enum | yes | `construction`, `calibration`, `final_test`. Input `final-test` normalizes to `final_test`. Any other token refuses |
| `spec_revision` | string | yes | Must match the loaded `attacks.yaml` `revision` |
| `access_label` | string | yes | Profile letter from the loaded access profile, copied onto the verdict |
| `identifiability` | enum | yes | `identifiable` or `structurally_indistinguishable`. Missing refuses |
| `answers` | list of string | yes | Contracted answers for text metrics. Empty refuses |
| `probes` | list of Probe | yes | At least one. See Probe |

A `structurally_indistinguishable` case yields status `non-identifiable under this profile` and does not emit a pass or a rejection.

---

## Probe

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `probe_id` | string | yes | |
| `probe_class` | enum | yes | `native` or `template` |
| `template_id` | string or null | when `template` | Must resolve in `closure_templates.yaml` |
| `group_id` | string or null | when `template` | `groups[].split` must equal `case.split` for a primary equivalence or locality probe |
| `prompt` | string | yes | |
| `family_id` | string or null | no | Used by confirmation route A |

Resolution against the closure file overrides a wrong `probe_class`: an id that exists in the closure file is never scored by the native arm.

Inference: `extra_premises` non-empty, or class `I`. Refused for the primary equivalence score. Recorded on the inference output.

Class `X` is refused for the primary score.

---

## Arm allocation

Loaded from `attacks.yaml` `arms[]`. Not constructed by the caller.

| Field | Type | Rule |
|-------|------|------|
| `arm_id` | enum | `native`, `semantic_only`, `factverify` |
| `total` | int ≥ 0 | Must equal the sum of its channel `trials` |
| `channels` | map of channel id → remaining trials | Starts at the declared `trials` |

All three `total` values must be equal, and equal to `common_cap` when that key is present. This comparison is reached only when D-22 is `closed` in the loaded file. An inconsistent sum refuses before that comparison.

---

## Query request

Input to `Accountant.query`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `channel_id` | string | yes | Must be an enabled channel on this arm, and permitted by the access profile |
| `kind` | enum | yes | `generation`, `candidate_score`, `cache_hit`, `retry`, `transport_failure`, `discard`, `reference` |
| `prompt_count` | int ≥ 0 | for `generation` | |
| `sample_count` | int ≥ 0 | for `generation` | Charge is `prompt_count * sample_count` generation trials |
| `probe_id` | string | yes | |
| `decoding` | map | yes | Includes `seed` when the call generates |
| `spend_confirmation` | bool | yes | `true` only for a confirmation-line request. A discovery channel with this flag set is the reallocation request |

A charge larger than the channel remainder raises `BudgetExhaustedError` and appends a refused-request record. The remainder does not change.

---

## Budget record

One per case per arm. Written when the case finishes, including when the arm stops early.

| Field | Type | Rule |
|-------|------|------|
| `arm_id` | enum | |
| `permitted_total` | int | The arm total that was checked at start |
| `channels` | list | For each channel: `permitted`, `charged_observations`, `new_compute_trials`, `refused`, `remaining` |
| `confirmation_remaining` | int | Not moved onto a discovery channel unless reallocation was allowed |
| `generated_trials` | int | |
| `scored_candidates` | int | |
| `input_tokens` | int | |
| `output_tokens` | int | |
| `tokens` | int | Sum of input and output, so the spec's `tokens` cost field is present |
| `exports` | int | |
| `training_steps` | int | |
| `wall_clock_seconds` | number | Measured by the gateway |
| `gpu_hours` | number | Measured by the gateway. Zero is a real measurement when no GPU was used |
| `peak_memory_bytes` | int | Measured by the gateway |
| `permitted_vs_actual` | map | `permitted` and `actual` per channel. `actual` less than `permitted` leaves `remaining` set |

Every key in `accounting.cost_vector_fields` is present. Remaining allowance is the unused count, including when the arm stops early.

### Call state

`pending` → `charged` or `refused`. A refused call stores the request and the channel remainder at refusal. There is no transition back to pending.

### Run state

`loaded` → `refused_at_start` or `running` → `finished`.

`refused_at_start` happens before any `query`. Reasons include an open decision, unequal totals, an unresolved policy field, a bad spec root, or a raw-store path inside `.factverify/`.

---

## Verdict row

One per case per arm. Schema in `contracts/verdict_row.md`.

| Field | Type | Rule |
|-------|------|------|
| `status` | enum of four phrases | Exactly one |
| `status_code` | enum | The spec token paired in `research.md` Decision 8 |
| `access_label` | string | From the case |
| `scores` | list of ChannelScore | One entry per channel that ran. No average field |
| `diagnostics.raw_maximum` | number or null | Set when a probe crosses its bound. Not a status |
| `confirmation_route` | string or null | Required when status is confirmed recovery witness |
| `checkpoint_ledger_id` | string | |
| `fact_id` | string | |
| `split` | enum | |
| `arm_id` | enum | |
| `spec_revision` | string | |
| `thresholds_tag` | string or null | `thresholds-v1` on `final_test`. Null on other splits |
| `inference_output` | list | Inference probes only. Empty when none were drawn |

### ChannelScore

| Field | Type | Rule |
|-------|------|------|
| `channel_id` | string | |
| `score` | number | This channel only |
| `bound` | number | This channel only |

Correctness, probability, rank, and sampling frequency are separate channel or metric entries. Emitting their arithmetic mean refuses.

### Decision state

Bound crossing without a successful enabled route does not enter `confirmed_recovery`.

A successful enabled route (witness-rule route A when `enabled: true`; route B or C only when that route's `enabled` is true) with its reservation charged on `confirmation` may enter `confirmed_recovery`.

`identifiability: structurally_indistinguishable` short-circuits to `non_identifiable` after the budget gate and does not require a score.

---

## Raw generation

One JSON object per charged generation that returned a completion.

| Field | Type | Required |
|-------|------|----------|
| `case_id` | string | yes |
| `checkpoint_ledger_id` | string | yes |
| `fact_id` | string | yes |
| `split` | enum | yes |
| `arm_id` | enum | yes |
| `channel_id` | string | yes |
| `probe_id` | string | yes |
| `prompt` | string | yes |
| `completion` | string | yes |
| `decoding` | map | yes |
| `seed` | int | yes |

Line count at finish equals the count of charged generations with a completion. A transport failure with `observation_charged: false` is not a line.

---

## Thresholds record

Used only for `split: final_test`. See `contracts/thresholds.md`.

| Field | Type | Rule |
|-------|------|------|
| `tag` | string | Must be `thresholds-v1` |
| `path` | path | `results/thresholds.json` |
| `digest` | string | SHA-256 of the working-tree bytes, equal to the tag blob |

Other splits carry a `Bounds` object with `split` set to that case's split and one bound per channel. A `Bounds.split` of `final_test` is refused on those paths.

---

## Relationships

```text
Case 1──* Probe
Case 1──1 Arm allocation        (the arm being run)
Case 1──1 Budget record
Case 1──1 Verdict row
Case 1──* Raw generation
Verdict row *──1 Thresholds record   (final_test only)
Probe *──1 closure group            (template probes only)
```

Three arm allocations are loaded at start even when the caller runs a single arm, so the equal-total check sees all three.
