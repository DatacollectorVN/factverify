# Contract: match.json

**Feature**: `20260927-144624-behaviour-matching`  
**Path**: `{output_dir}/match.json`

Written only when the search finishes. `matched` and `unmatched` both write this file. A refused match leaves the directory without this file.

## Status

| Status | When |
|--------|------|
| `matched` | The selected severity's accuracy is inside the D-54 band, and the hard check is `not_required`, `passed`, or `waived` |
| `unmatched` | The selected accuracy is outside the band, or `hard_check` is `failed` |

`selected_severity` is the first-ranked entry under `closest_center` (smaller distance to the center, then earlier in `severity_search`). `achieved_value` is that entry's accuracy. On an unmatched record, `achieved_value` is the best value the pilot input reports.

## Target band

`target_band.summary` is the D-54 `band_summary` token that was applied (`min_max` or `mean`). `low` and `high` are the tolerance band after that summary. `center` is the raw midpoint for `min_max` and the mean for `mean`. `tolerance` and `boundary` are the decision-record strings, copied unchanged.

`reference_accuracies` is the port's number for each `reference_ledger_ids` entry, in the same order. The band is computed from those numbers.

## Trajectory and reads

`trajectory` has one object per `severity_search` entry, same order, each with `severity` and `accuracy`. An exhausted list is still complete.

`reads` contains the port's output triples for every reference and every tried severity. Every `probe_id` belongs to the manifest. The file has no key named `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, or `frr`.

## Hard check

| `hard_check` | Record also has |
|--------------|-----------------|
| `not_required` | No dimension list. `hard` was absent or false |
| `passed` | `dimensions` with every `inside` true |
| `failed` | `dimensions` and `failed_dimension` naming the first failing D-59 name. Status is `unmatched` |
| `waived` | `waiver_reason` copied from the open D-59 row. Dimensions were not measured |

## Provenance and cost

Required on every written file: `config_hash`, `seed`, `split`, `spec_revision`, `control_ledger_id`, `reference_ledger_ids`, `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes`.

A reader that loads `match.json` and finds any of those missing raises `ControlError` and does not treat the file as finished.

## Pilot view

`pilot_inputs` copies `control_ledger_id`, `family`, `status`, `achieved_value` as `best_value`, and `target_band` (`low`, `high`, `summary`). Unmatched rows are included. `reject_dropped` raises `ControlError("unmatched")` if a later list omits one or changes those fields.
