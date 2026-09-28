# Quickstart: FV-CTRL — P2-3 Fake-Unlearning Controls

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27

One configuration builds one labelled negative control on the finetuned parent for that fact. Study counts and tolerances are still open decisions, so certification and the retention check refuse until the decision record closes them.

## What you need first

1. A spec root. The frozen one is `.factverify/spec`. Hooks use `tests/fixtures/controls/` when they need a numeric locality margin.
2. A decision record. The study record keeps D-53, D-54, D-55, and D-61 `open`. A hook closes only the row it asserts.
3. A parent ledger row with role `finetuned` for the same fact. Tests use an in-memory port. A SQLite path is refused until P2-5.
4. A fact-contract JSON file. Output filtering and logit masking use `triple.object.label` and `aliases.object[].text`.
5. For suppression and destruction, a behavior port. For destruction, a trainer port. Hooks script both. This package does not download weights.

Do not put an evaluator verdict, a budget record, or a target accuracy in the config. Severity is recorded as given. Tuning it is P2-4.

## Build

```text
python -m src.controls.run \
  --config tests/fixtures/controls/configs/<control>.yaml \
  --spec-root tests/fixtures/controls/spec \
  --ledger /tmp/fv-ledger.sqlite
```

The SQLite ledger path exits non-zero and names P2-5. That refusal is expected. Hooks call `build_control` with an in-memory ledger instead.

An accepted build writes `control.json` with `oracle_label` `negative`, one mechanism layer, and the config hash, seed, split, and spec revision. It also commits a ledger row with role `control`, the family, the parent id, wall-clock, GPU-hours, and peak memory.

## What refuses

| Attempt | Result |
|---------|--------|
| Family token not in the catalog | Raises and names the family |
| `certify_coverage` while D-55 is open | Raises and names D-55 |
| `untouched` while D-61 is open | Raises and names D-61 |
| Parent role other than `finetuned`, or a different fact | Raises before commit |
| Implementation already on the other of calibration and final test | Raises |
| Config key `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, or `frr` | Raises |
| Suppression acceptance while D-54 is open | Ledger `unchecked`, no negative label |
| Destruction acceptance while the locality margin is null | Ledger `unchecked`, no negative label |
| Disabled accuracy outside the closed gap, or locality short of the margin | `rejection.json`, ledger `rejected` |
| `compare_builds` while D-53 is open | Raises and names D-53. The two builds stay ledgered |
| `underlying()` on a wrapper | Raises |

An output-filter label built against Profile A includes `expected_identifiability: structurally_indistinguishable`. Other families omit that field.

## Serve a wrapper

Evaluator code calls `serve(artifact, gateway, probe)`. The gateway's model port is the control. One call is one accountant charge, the same as a plain model call. The parent model is not returned.

## Out of scope

Behaviour matching (`src/controls/match.py`, P2-4), weight-update implementations (`src/train/`), evaluator verdicts (`src/eval/` beyond the gateway), and SQLite (`P2-5`).
