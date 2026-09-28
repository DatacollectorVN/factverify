# Contract: D-65 and D-68 decision file

**Feature**: 20260929-100819-exclusion-gate-splits

## File

Caller path. Study file: `data/controlled/block0_decisions.yaml`.

The loader is `src.data.decisions.load_decision(path, decision_id)`.

| Call | Result |
|---|---|
| Path missing | Raise, naming the path |
| Id absent | Raise, naming the id, status treated as open |
| `status` other than `open` or `closed` | Raise, naming the id |
| `status: open` | Raise, naming the id, before any verdict or split file |
| `status: closed` with a blank required field | Raise, naming the field |

## D-65 closed fields

| Field | Type | Study value |
|---|---|---|
| `baseline` | string | `random_choice` |
| `threshold` | float | `0.5` |
| `comparison` | string | `any_direction` |
| `cell_score` | string | `alias_contains` |
| `decoding_seeds` | list of int | `[0]` |
| `decoding.do_sample` | bool | `false` |
| `decoding.max_new_tokens` | int | `16` |
| `contamination_trigger` | float | `0.10` |
| `contamination_decision` | string or null | null until an owner records one |
| `note` | string | required and non-empty when a contamination decision is set |

`comparison` other than `any_direction`, or `cell_score` other than `alias_contains`, raises. Those are the only rules this feature implements.

## D-68 closed fields

| Field | Type | Study value |
|---|---|---|
| `counts.construction` | int | `8` |
| `counts.calibration` | int | `8` |
| `assign_final_test` | bool | `false` |
| `relations` | list of string | occupation, birthplace, nationality, genre |
| `block` | string | `block0` |

`assign_final_test: true` raises. This feature does not draw a final-test pool.

## Tests

Fixtures cover an open D-65, a closed D-65 with a blank `threshold`, an open D-68, and a closed D-68 whose counts the assignment actually uses (so a fixture with counts 1 and 1 still drives the writer).
