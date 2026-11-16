# Phase 3: Pythia-410M forgetter sweep with the updated neighbourhood

The Phase 2 grid (17 forgetter runs, same parameters) re-run after the target fact's
neighbourhood changed. This is a new, separately named sweep. Phase 2 configs and
results are unchanged.

Target: `full_0_jaime_vasquez_hails_from_santiago_chile`.

## What changed from Phase 2

| | Phase 2 | Phase 3 |
|---|---|---|
| Neighbours (from the target's JSON `neighbourhoods`) | true_crime_genre, chukwu (Lagos), anara (Baku), jordan_80, jordan_81 | true_crime_genre, chukwu (Lagos), anara (Baku), jordan_80, **full_13 Jaime Vasquez's father → chef** |
| Learner | `block0-pythia410m-alias-learner` (6 facts) | `phase3-pythia410m-alias-learner` (7 facts: the 6 + full_13) |
| Job names / output dirs | `phase2-…` | `phase3-…` |

Nothing else changed: every training, guard and AFC setting is copied from Phase 2
(`config/jobs/phase2/README.md`).

Why a new learner: neighbour retention is measured against the learner's score. The
block 0 learner never trained on full_13, so "retaining" it would mean nothing, and
that learner checkpoint is no longer on disk. `learner.yaml` uses the block 0 learner
settings (seed 1, lr 2e-5, 50 epochs, patience 10, `alias_aware`), with full_13 added.
full_81 is still learned, but it is no longer a neighbour, so it isn't scored in AFC.

With 5 neighbours, J = 5 and n = 25, the same as Phase 2. The Jordan duplicate is gone,
so all 5 neighbours are now distinct facts. Two of them share the target's subject
(true_crime genre; father → chef).

## Shared settings (copied from Phase 2)

| Setting | Value |
|---|---|
| `alias_aware` | true |
| `stop_on_neighbour_breach` | false |
| `neighbour_retention_thr` | 0.7 |
| `save_best_as` | `val_target_drop` |
| `patience` / `min_delta` | 10 / 0.01 |
| `epochs` | 60 (GA, GradDiff, NPO), 40 (RMU) |
| `batch_size`, seed | 4, 3 |
| `afc.alpha` / `afc.kappa` | 0.05 / 0.8 |

## Grid (copied from Phase 2)

| Method | Runs |
|---|---|
| GA (entropy target 11 bits) | lr {1e-6, 3e-7} × entropy {0.1, 0.3} |
| GradDiff (entropy 0.1) | (1e-6, rc 5), (1e-6, rc 20), (3e-6, rc 20), (3e-7, rc 5) |
| NPO | lr {1e-6, 3e-7} × β {0.1, 0.5} |
| RMU (`no_sinks`, per token) | L7 c300 rc100 lr5e-5; L7 c300 rc300 lr5e-5; L7 c300 rc300 lr3e-5; L7 c90 rc300 lr5e-5; L11 c300 rc300 lr5e-5 |

## Prerequisite

`.factverify/corpuses/full_13_jaime_vasquez_s_father_profession_chef.json` must exist
(75 train / 25 eval English probes, as for the other facts). Without it the learner and
every forgetter stop with `unlisted training item`.

## Run

Learner first, then the forgetters, one at a time:

```bash
uv run python -m src.main --config config/jobs/phase3/learner.yaml
for f in config/jobs/phase3/forgetter-*.yaml; do
  uv run python -m src.main --config "$f"
done
```

## Decision rule (same as Phase 2, fixed before running)

1. Report the AFC verdict for all 17 runs. No run is dropped afterwards.
2. A run with `selected_below_guard` in `afc.json` is reported as such, whatever its verdict.
3. 17 settings tested with no multiplicity correction: a certified run is a candidate,
   not a final result.
4. A certified run still needs the behavioural checks (greedy Q&A and the sampling attack).
5. Changing `kappa`, `alpha` or the grid after seeing results means a new, separately named sweep.
6. Phase 3 verdicts are not directly comparable to Phase 2: the learner and one neighbour
   are different.
