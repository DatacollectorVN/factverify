# Block 0 — Pythia-410M alias-aware pipeline (learner → forgetter, all methods)

Derived from `requirements/block0-pythia-410m-alias-ablation.md`, adapted to the
data present on this host. Written before any run; nothing here was chosen from
an outcome.

## Deviations from the plan (and why)

| Plan | Here | Reason |
|---|---|---|
| 16 block0 facts, forget `full_22_…hairdresser` | the 6 facts in `.factverify/facts`, forget `full_0_jaime_vasquez_hails_from_santiago_chile` | The 16 facts have no corpus/fact/entity files on this host; Nathan chose the 6 present facts and this target. |
| `save_best_as: val_neighbour_retention` | `val_target_drop` | `val_neighbour_retention` is not an allowed forgetter metric (validation fails); maximising neighbour retention would also select the least-forgotten epoch. The neighbour guard protects retention instead. |
| `neighbour_retention_thr: 0.5` | `0.7` | Stricter collateral-damage stop. |
| `lr 1e-4`, `batch_size 1` | per-method sweep below, `batch_size 4` | 1e-4 full-weight AdamW on 410M collapses the model within one epoch. |
| `entropy_coeff 0.1` on NPO/RMU | omitted | Only GA and GradDiff read `entropy_coeff`. |
| RMU `steering_coeff 100` @ layer 7 only | per-token RMU on content tokens; c = 30 / 90 (≈1× / ≈3× the per-token content norm ≈ 30 on the learner), layers 7 and 11 | Steering target norm should be chosen relative to activation scale; see "RMU revision". |

## Run order

```bash
# 1. learner (≈ one job, must finish first)
uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/learner.yaml
# 2. forgetters — sequential (11 GB GPU fits one job at a time)
for f in config/jobs/block0/pythia-410m-alias-ablation/alias-aware/forgetter-*.yaml; do
  uv run python -m src.main --config "$f"
done
```

## Sweep (pre-declared)

Shared: seed 3, epochs 100, patience 10, batch 4, max_length 256,
`save_best_as: val_target_drop`, `neighbour_retention_thr: 0.7`, `alias_aware: true`.

| Method | Variants |
|---|---|
| GA (entropy 0.1 @ 11 bits) | lr 1e-6 · 3e-6 · 1e-5 |
| GradDiff (entropy 0.1 @ 11 bits) | lr 3e-6 rc 1 · lr 1e-5 rc 1 · lr 1e-5 rc 5 |
| NPO | lr 1e-5 β 0.1 · lr 3e-5 β 0.1 · lr 1e-5 β 0.05 |
| RMU (lr 5e-6, per-token, `rmu_token_scope: content`) | L7 c30 rc100 · L7 c90 rc1 · L7 c90 rc100 · L7 c90 rc1000 · L11 c90 rc100 · L11 c90 rc1000 |

### RMU revision (2026-11-07, before any per-token RMU result existed)

The first RMU implementation mean-pooled the layer-L hidden state over the
whole padded `Q+A` sequence. Only ~18 % of the pooled tokens were answer
tokens and ~30 % were the shared `Q:`/`\nA:` template, so forget and retain
competed on template tokens; the one partial run (old `L7-sc100-rc100`,
stopped after epoch 7) reached drop 0.39 at epoch 3 then fell back to 0.16 at epoch 5 while
neighbour retention slid to 0.76. RMU was changed to the paper's **per-token**
loss on **unpadded** sequences (also removing a wasted forward pass).

Pre-training measurement on the learner checkpoint (layer 7 / 11):
first token `Q` ‖h‖ ≈ 943 / 1007; `\n` before `A:` and `<EOS>` > 200;
question/answer content tokens median ≈ 30 / 29 (answer ≈ 35). The three
template tokens are Pythia attention sinks shared by every fact, so the loss
uses **content tokens only** (`rmu_token_scope: content`), a documented
deviation from paper RMU. Steering coefficients keep the declared rule
(≈1× and ≈3× the activation norm) re-based on the per-token norm:
c = 30 and 90 (configs renamed sc30 / sc90). `retain_coeff` grid unchanged.
Both choices were fixed from the measurement, not from any RMU outcome.

## Selection rule (fixed before running)

Per method, the reported variant is the one whose **selected checkpoint** has the
highest `val_target_drop` among variants whose selected checkpoint has
`val_neighbour_retention ≥ 0.7`. Ties → the smaller learning rate. If no variant
qualifies, the method is reported as "no usable forget/retain trade-off" — the
grid is not extended after seeing results without recording it as a new,
separately named sweep.
