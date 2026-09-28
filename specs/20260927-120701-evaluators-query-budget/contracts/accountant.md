# Contract: `Accountant`

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27  
**Module**: `src/eval/budget.py`

Evaluators do not construct this type. `evaluate_case` does, after the start checks in `evaluate_case.md`.

---

## `Accountant.query`

```python
Accountant.query(self, channel_id: str, request: QueryRequest) -> ChargeResult
```

| Result field | Type | Meaning |
|--------------|------|---------|
| `outcome` | `Literal["charged", "refused"]` | |
| `generation_trials` | int | Added to the channel's observation count when the policy says the observation is charged |
| `new_compute_trials` | int | Zero when `charge_rule` is `zero_new_compute` |
| `scored_candidates` | int | Non-zero only for `kind=candidate_score` |
| `remaining` | int | Channel remainder after a charge. Unchanged on a refusal |
| `refused_request` | QueryRequest or null | Set when `outcome` is `refused` |

### Charge rules

| `request.kind` | Policy field | Allocation effect |
|----------------|--------------|-------------------|
| `generation` | generation trial unit | `prompt_count * sample_count` observations on `channel_id`, and the same number of new-compute trials |
| `cache_hit` | `cache_policy` | Follow `observation_charged` and `charge_rule` |
| `retry` | `retry_policy` | The new attempt and the original failure are both charged when the policy says so |
| `transport_failure` | `failure_policy` | Attempt recorded. No raw completion when `observation_charged` is false |
| `discard` | `discard_policy` | Follow that policy's two flags |
| `candidate_score` | `candidate_scoring_unit` | Scored-candidate line only, unless the unit field also names generation trials |
| `reference` | `reference_cost_policy` | Separate reference line. Does not consume the arm channel when `charge_rule` is `separately_reported` |

`confirmation` is charged only when `channel_id` is `confirmation`. A discovery `channel_id` with `spend_confirmation=true` is refused unless `accounting.unused_confirmation_reallocation` is `true`. When it is refused, the confirmation remainder stays as it was.

When the observation charge is greater than the channel remainder, `query` raises `BudgetExhaustedError` after storing the refused request. It does not apply a partial charge.

### What `query` does not do

- It does not call the model or the cache.
- It does not read `budget_per_fact`. That constructor is not part of this module.
- It does not invent a cap when the spec field is missing.

---

## Budget record

`Accountant.budget_record() -> BudgetRecord`

Returned for a finished arm and for an arm that stopped early. `remaining` on each channel is `permitted - charged_observations` and is kept when it is above zero. Field list: `data-model.md`, Budget record.

`tokens` equals `input_tokens + output_tokens`. Input and output stay as their own fields.

---

## Gateway order

`src/eval/gateway.py` is the only caller of `ModelPort` and `CachePort` under `src/eval/`. One case runs on one thread. `ensure_capacity` and `query` share that thread's lock.

1. `cache.get` for a generation.
2. On a hit, `query(channel, kind=cache_hit)` and return the stored completion. No model call.
3. On a miss, `ensure_capacity(channel, prompt_count * sample_count)`. On `BudgetExhaustedError`, do not call the model. This check does not charge.
4. `model.complete`.
5. When a completion returns, `query(channel, kind=generation)`, then `cache.put`, then append the raw record.
6. When the model port raises a transport error, `query(channel, kind=transport_failure)` using the failure policy. That path does not also charge a generation trial. A later retry charges the new attempt and, when `retry_policy` says so, the original failure.

`ensure_capacity(channel_id, trials) -> None` raises `BudgetExhaustedError` and stores the refused request when `trials` is greater than the channel remainder.

Score calls skip the cache. They call `ensure_capacity` for the scoring unit, then `model.score_candidate`, then `query(channel, kind=candidate_score)`, after `channels.py` has allowed the capability.
