# Phase 2: Pythia-410M forgetter sweep (all methods)

17 forgetter runs, all starting from the block 0 alias-aware learner and targeting
`full_0_jaime_vasquez_hails_from_santiago_chile`. This is a new, separately named
sweep. Block 0 configs and results are unchanged.

Written before any Phase 2 run. The grid is informed by block 0 results, which is
why it is a separate sweep and not an extension of the block 0 grid.

## Shared settings

| Setting | Value | Why |
|---|---|---|
| `alias_aware` | true | Same as the learner checkpoint |
| `stop_on_neighbour_breach` | false | A breach no longer ends the run, so every run reaches AFC |
| `neighbour_retention_thr` | 0.7 | Now only decides which epochs are preferred as the best checkpoint |
| `save_best_as` | `val_target_drop` | Largest drop among epochs above the guard |
| `patience` / `min_delta` | 10 / 0.01 | A breaching epoch counts as non-improving |
| `epochs` | 60 (GA, GradDiff, NPO), 40 (RMU) | Upper limit; patience usually ends the run first |
| `batch_size`, seed | 4, 3 | As in block 0 |
| `afc.alpha` / `afc.kappa` | 0.05 / 0.8 | Frozen here, before any Phase 2 result exists |

## Grid

| Method | Runs | Reasoning from block 0 |
|---|---|---|
| GA (entropy target 11 bits) | lr {1e-6, 3e-7} × entropy {0.1, 0.3} | Only 1e-6 passed, with a cliff one epoch later and answer replacement |
| GradDiff (entropy 0.1) | (1e-6, rc 5), (1e-6, rc 20), (3e-6, rc 20), (3e-7, rc 5) | Never tried below 3e-6; the higher `retain_coeff` was less destructive |
| NPO | lr {1e-6, 3e-7} × β {0.1, 0.5} | Never tried below 1e-5; smaller β collapsed harder |
| RMU (`no_sinks`, per token) | see below | `retain_coeff` 100 was needed; `no_sinks` had the least leakage |

RMU runs:

| Layer | `steering_coeff` | `retain_coeff` | lr |
|---|---|---|---|
| 7 | 300 | 100 | 5e-5 (anchor) |
| 7 | 300 | 300 | 5e-5 |
| 7 | 300 | 300 | 3e-5 |
| 7 | 90 | 300 | 5e-5 |
| 11 | 300 | 300 | 5e-5 |

GA and NPO have no retain term, so `retain_coeff` is not part of their grids.

## Run

```bash
for f in config/jobs/phase2/forgetter-*.yaml; do
  uv run python -m src.main --config "$f"
done
```

Run one at a time; the GPU fits one job. Upper bound is about 29 hours, if every run
reached its epoch limit. Runs that collapse end after about 10 epochs (about 20 minutes).

Each run writes `afc.json` next to `drop_retention.json` in its output directory.

## Decision rule (fixed before running)

1. Report the AFC verdict for all 17 runs. No run is dropped afterwards.
2. A run with `selected_below_guard` in `afc.json` is reported as such, whatever its verdict.
3. Testing 17 settings raises the chance of a lucky pass, and nothing here corrects for it,
   so a certified run is a candidate, not a final result.
4. A certified run still needs the behavioural checks (greedy Q&A and the sampling attack)
   before calling it forgotten. AFC cannot detect a model that still says the answer but
   cannot stop, or one that only produces garbled text.
5. Changing `kappa`, `alpha` or the grid after seeing results means a new, separately named sweep.
