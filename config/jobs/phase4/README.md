# Phase 4: Llama-3.2-3B forgetter sweep (Phase 3 settings, different model)

Identical to Phase 3 in every training, guard and AFC setting, target, facts and
neighbourhood. The only change is the model: `config/models/block0-debug-llama-3.2-3b.yaml`
(`meta-llama/Llama-3.2-3B`, bfloat16, eager attention) instead of Pythia-410M.
Job names and output dirs use `phase4-llama3.2-3b-alias-…`. Phase 3 is unchanged.

## Deliberate change from Phase 3: RMU `steering_coeff`

Chosen before any Phase 4 run, from model activations only (not from outcomes).
`steering_coeff` is the norm of the target the hidden states are pushed toward, so it is only
meaningful relative to the activation norm at the steered layer. Mean per-token norm over the
`no_sinks` tokens of 40 English training probes of the target fact (the tokens RMU trains on):

| Layer | Pythia-410M | Llama-3.2-3B | Ratio |
|---|---|---|---|
| 7 | 20.9 | 7.5 | 0.359 |
| 11 | 20.6 | 9.2 | 0.447 |

Phase 3's c = 300 is about 14x Pythia's typical norm. Phase 4 keeps that multiple:
c300 -> 108 (L7), c300 -> 134 (L11), c90 -> 32 (L7). `retain_coeff`, learning rates,
epochs and everything else are unchanged: both loss terms scale with the squared activation
norm, so their balance is preserved. Job and file names keep the Phase 3 labels (`c300`, `c90`)
so runs pair with the Phase 3 grid; the actual values are in each YAML. The GA, GradDiff and NPO
configs are unchanged from Phase 3. This means Phase 4 RMU is not a pure model swap.

## Deliberate change from Phase 3: epochs and patience (requested after the first run started)

At your request, the 16 forgetter configs not yet started use `epochs: 15` and `patience: 5`
(Phase 3: 60/10 for GA, GradDiff, NPO; 40/10 for RMU). `forgetter-ga-lr1e-6-ent0.1` had already started
with 60/10 and its YAML is unchanged, so it is not on the same budget as the other 16. The learner is unchanged.
This was decided after seeing that run's first ~20 epochs, so it is not blind to results.
The shorter budget may cut off runs that would still be improving (the first GA run's target drop was still growing at epoch 20).

## Run note: `forgetter-ga-lr1e-6-ent0.1` was stopped by hand

This run used the Phase 3 budget (60 epochs, patience 10). It was stopped by the user at epoch 34
of 60, while still improving every epoch (the early-stopping counter was 0), so the stop was a
result-dependent choice, not a configured one. It has no final model, no AFC verdict, and its
`experiments` row is still `running`; treat it as incomplete, not as a Phase 4 result on the same
footing as the other 16 runs (15 epochs, patience 5).

Scores of its best checkpoint (epoch 34), computed afterwards with the project's own scoring code
(alias-aware, English probes, eval split):

| | Learner | Epoch-34 checkpoint |
|---|---|---|
| Target P (`full_0` Santiago) | 0.863 | 1.4e-18 (drop 40.98 nats) |
| Neighbour retention (geo-mean) | 1.000 | 0.946 |
| Weakest neighbours | | `full_80` Jordan 0.849, `full_13` chef 0.892 |

The target probability is far below chance for this vocabulary, so this looks like suppression, not
removal; that is an interpretation, not a tested result. Weights are in
`.factverify_internal/train/phase4-llama3.2-3b-alias-ga-lr1e-6-ent0.1/stopped_snapshot/`
(`best_model.safetensors`, `meta.json`, `scores.json`).

Open points, not decided here:
- Hyperparameters other than RMU `steering_coeff` (learning rates, `retain_coeff`, entropy target 11 bits)
  were tuned or chosen for Pythia-410M. They are copied as-is; Llama-3.2-3B has 28 layers, so
  RMU layers 7 and 11 are valid but sit at different relative depths than in Pythia-410M (24 layers).
- Llama-3.2-3B is a gated repo: accept the licence and set `HF_TOKEN` before prefetch.
- Llama has a larger vocabulary than Pythia, so the entropy target (11 bits) may mean something
  different; check before reading GA results.

Everything below is Phase 3's README, kept for reference; read "Phase 3" as "Phase 4" and
Pythia as Llama where it applies.

---

# Phase 3: Pythia-410M forgetter sweep with the updated neighbourhood

The Phase 2 grid (17 forgetter runs, same parameters) re-run after the target fact's
neighbourhood changed. This is a new, separately named sweep. Phase 2 configs and
results are unchanged.

Target: `full_0_jaime_vasquez_hails_from_santiago_chile`.

## What changed from Phase 2

| | Phase 2 | Phase 3 |
|---|---|---|
| Neighbours (from the target's JSON `neighbourhoods`) | true_crime_genre, chukwu (Lagos), anara (Baku), jordan_80, jordan_81 | true_crime_genre, chukwu (Lagos), anara (Baku), jordan_80, **full_13 Jaime Vasquez's father → chef** |
| Learner | `block0-pythia410m-alias-learner` (6 facts) | `phase4-llama3.2-3b-alias-learner` (7 facts: the 6 + full_13) |
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
uv run python -m src.main --config config/jobs/phase4/learner.yaml
for f in config/jobs/phase4/forgetter-*.yaml; do
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
