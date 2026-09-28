# Data Model: FV-CTRL — P2-4 Behaviour-Matching Utility

**Feature**: `20260927-144624-behaviour-matching`  
**Date**: 2026-09-27

Field values that are study decisions are loaded from the caller-supplied decision record. They are not defaults in code. See `research.md`.

---

## MatchConfig

The caller-supplied YAML document. Unknown keys refuse. Missing required keys refuse. This is not a P2-3 `ControlConfig`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `family` | string | yes | A family token `require_family` already knows |
| `implementation_id` | string | yes | The registered id for `family` |
| `severity_search` | non-empty list | yes | Each entry is a string or a number, not a bool. Tried in this order, all of them |
| `control_ledger_id` | string | yes | Ledger role `control`, same fact, split not `final_test` |
| `reference_ledger_ids` | non-empty list of string | yes | No duplicates. Each role `reference`, same fact, split `construction` or `calibration`. Count is 2 for `block_0` and at least 3 for `block_1` |
| `fact_id` | string | yes | Shared by the control, the references, and every probe |
| `block` | enum | yes | `block_0` or `block_1`. Any other name refuses |
| `seed` | int | yes | Stored and hashed. Not used to order the search |
| `split` | enum | yes | `construction` or `calibration`. `final_test` and `final-test` refuse |
| `spec_revision` | string | yes | Copied onto the match record |
| `decisions` | path | yes | Decision-record YAML outside `.factverify/spec/` |
| `probes` | path | yes | Probe manifest. Used only when D-58 is closed |
| `output_dir` | path | yes | Where `match.json` is written. Must not be inside `.factverify/` |
| `hard` | bool | no | Absent means false. `true` subjects the selected severity to D-59 |

Forbidden keys, refused before any measurement: `target_accuracy`, `target`, `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, `frr`, `budget`. A string value ending in `verdict.json` or `budget.json` also refuses.

---

## DecisionRecord (fields this feature adds)

Rows the match does not need may be absent. A needed row that is missing is `open`. `status` stays `open` or `closed`. Retention still uses only D-54 `max_abs_gap`.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `decision_id` | enum | yes | Existing ids plus `D-58` and `D-59` |
| `band_summary` | enum | D-54 closed, for a match | `min_max` or `mean`. Any other token raises `D-54` |
| `tolerance` | decimal string | D-54 closed, for a match | In `[0, 1]` |
| `boundary` | enum | D-54 closed, for a match | `inclusive` or `exclusive` |
| `selection_rule` | enum | D-54 closed, for a match | Only `closest_center` is interpreted |
| `dimensions` | list | D-59 closed | Non-empty. Each item: `name`, `tolerance`, `boundary`. A `waiver` on a closed row raises |
| `waiver` | string | D-59 open, hard match only | Non-empty string records a waiver. Empty or absent on an open hard match raises `D-59` |

D-58 has no extra field. `status: closed` authorizes the match document's probe manifest. `status: open` raises `D-58`.

---

## ProbeManifest

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `probe_id` | string | yes | Unique in the manifest |
| `fact_id` | string | yes | Equals the match `fact_id` |
| `template_group_id` | string | yes | Present in `closure_templates.yaml` `groups`, and that group's `split` is not `calibration` or `final_test` |
| `split` | enum | yes | `construction` or `calibration` |
| `kind` | const | yes | `direct_qa` |

---

## SystemView

Read-only ledger row. `MatchLedgerPort.get` returns it or `None`.

| Field | Type | Rule |
|-------|------|------|
| `ledger_id` | string | The requested id |
| `role` | string | `reference` for a reference id. `control` for the control id |
| `fact_id` | string | Equals the match fact |
| `split` | enum | `construction` or `calibration` |

---

## Measurement

Returned by `MatchBehaviorPort.direct_qa_accuracy`. The port owns the accuracy. This package does not recompute it from `output`.

| Field | Type | Rule |
|-------|------|------|
| `accuracy` | float | One direct question-answering accuracy for that system, fact, probe set, and severity |
| `outputs` | list | One item per requested probe: `probe_id`, `system_id`, `output`. Probe ids outside the manifest refuse |

`severity` is null for a reference call and is the declared search entry for a control call.

---

## MatchRecord

Written to `match.json` only after validation and a completed search. A refusal writes nothing.

| Field | Type | Required | Rule |
|-------|------|----------|------|
| `status` | enum | yes | `matched` or `unmatched` |
| `family` | string | yes | |
| `implementation_id` | string | yes | |
| `fact_id` | string | yes | |
| `block` | enum | yes | |
| `control_ledger_id` | string | yes | |
| `reference_ledger_ids` | list of string | yes | Supplied order |
| `reference_accuracies` | list of float | yes | Same order as the ids |
| `target_band` | object | yes | `summary`, `low`, `high`, `center`, `tolerance`, `boundary` |
| `selected_severity` | string or number | yes | First under `closest_center`, then earlier in `severity_search` |
| `achieved_value` | float | yes | Accuracy at `selected_severity`. Also the best value when unmatched |
| `trajectory` | list | yes | One item per declared severity, in order: `severity`, `accuracy` |
| `reads` | list | yes | Probe outputs for every reference and every tried severity. No evaluator field |
| `hard_check` | enum | yes | `not_required`, `passed`, `failed`, or `waived` |
| `dimensions` | list | when measured | `name`, `value`, `tolerance`, `boundary`, `inside` |
| `failed_dimension` | string | when a dimension fails | First failing name in D-59 list order |
| `waiver_reason` | string | when waived | The D-59 waiver string |
| `wall_clock_seconds` | float | yes | From `CostRecord` |
| `gpu_hours` | float | yes | From `CostRecord`. Zero on CPU is recorded |
| `peak_memory_bytes` | int | yes | From `CostRecord` |
| `config_hash` | string | yes | `hash_mapping` of the raw match document |
| `seed` | int | yes | |
| `split` | enum | yes | |
| `spec_revision` | string | yes | |

`load` of a `match.json` that lacks a required field refuses. That file is not a finished match.

---

## PilotInput

A view over a finished `MatchRecord`. `pilot_inputs` emits one per record.

| Field | Type | Rule |
|-------|------|------|
| `control_ledger_id` | string | |
| `family` | string | |
| `status` | enum | |
| `best_value` | float | `achieved_value` |
| `target_band` | object | `low`, `high`, `summary` |

`reject_dropped` fails when an `unmatched` source id is missing from the reported inputs or when family, best value, or band differ.

---

## State

```text
config + spec root + decision record + manifest + ledger rows
        │
        ├─ missing input, open decision, bad probe, short reference set, literal target
        │     └─ raise ControlError; no match.json
        │
        └─ checks pass
              └─ measure every reference and every declared severity
                    ├─ selected accuracy inside the band, and hard check not failed
                    │     └─ match.json status matched
                    └─ selected accuracy outside the band, or a D-59 dimension failed
                          └─ match.json status unmatched
```

`compare_matches` is a separate step. It does not change either record. An open D-53 row raises. A closed `digest_tolerance` of `0` requires equal `selected_severity` and `status`.
