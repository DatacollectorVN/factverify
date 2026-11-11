# RMU tuning sweep (separate from the declared grid)

Why: the declared per-token RMU grid (lr 5e-6) barely moved layer-7 states
(forget MSE 1.70 → 1.57 over 5 epochs, target drop 0.0000 at c30 rc100).
Adam moves each weight ≈ lr per update, so 5e-6 is ~10× below the RMU
paper's step (5e-5). This sweep is a **tuning** search on the construction
split, recorded separately; its results are reported as tuned RMU, not as the
pre-declared grid.

Shared: per-token RMU, `rmu_token_scope: content`, seed 3, batch 4,
epochs ≤ 40, patience 5, `min_delta: 0.01`, neighbour guard 0.7,
`save_best_as: val_target_drop`. RMU logs `retain_mse` per epoch.

## Stage 1 — step size × retain weight (layer 7)

| tag | c | rc | lr | question |
|---|---|---|---|---|
| L7-c90-rc1-lr5e-5 | 90 | 1 | 5e-5 | does a paper-scale step move the target? |
| L7-c90-rc100-lr5e-5 | 90 | 100 | 5e-5 | same, does rc=100 act as the brake? |
| L7-c90-rc1-lr2e-5 | 90 | 1 | 2e-5 | how much step is needed? |
| L7-c300-rc100-lr5e-5 | 300 | 100 | 5e-5 | does stronger steering overcome the anchor? |

Stage 2 (layer 5 / 7 / 11 at the best stage-1 setting) is defined after
stage 1 and recorded here before it runs.

## Stage 1 results (recorded 2026-11-07)

| tag | outcome | selected epoch | target drop | neighbour ret. |
|---|---|---|---|---|
| L7-c90-rc1-lr5e-5 | guard_stopped | — | (28.0) | 0.004 |
| L7-c90-rc100-lr5e-5 | succeeded | 8 | 28.3 | 0.78 (true-crime 0.30) |
| L7-c90-rc1-lr2e-5 | guard_stopped | — | (20.8) | 0.0003 |
| L7-c300-rc100-lr5e-5 | succeeded | 2 | 22.2 | 0.995 (all ≥ 0.91) |

160-question greedy check of L7-c300-rc100-lr5e-5 (vs learner): neighbours 0 new
errors; target forward questions still start with "Santiago" in 17/21 (prefix
P ≈ 80–100 %), reverse questions forgotten (0/5), verify broken (True to false
claims). Diagnosis: with `rmu_token_scope: content` the final `:` of `A:` — the
position that predicts the first answer token — is never steered.

## Stage 1b — token scope (defined before running)

| tag | change from L7-c300-rc100-lr5e-5 | question |
|---|---|---|
| L7-c300-rc100-lr5e-5-nosinks | `rmu_token_scope: no_sinks` (all tokens except first token, template `\n`, `<EOS>`) | does steering the answer-predicting `:` remove the "Santiago" leak while neighbours stay intact? |

Evaluated with the same 160-question greedy check.
