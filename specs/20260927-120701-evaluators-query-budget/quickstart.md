# Quickstart: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27

Three arms score one case. Every model call is charged by one accountant. Study caps and policies are still open decisions, so a run against the frozen spec root refuses until those fields are closed in the spec.

## What you need first

1. A spec root. The frozen one is `.factverify/spec`. Hooks use `tests/fixtures/eval/` instead, with the decisions that hook closes.
2. A case file: checkpoint ledger id, fact id, split, probes, answers, and `identifiability`.
3. A raw directory that is not inside `.factverify/`.
4. A model port. Hooks use a script. A study run uses `load_model` from inside the port, not from an evaluator.

Do not pass threshold numbers on the command line. Final-test reads `results/thresholds.json` only after the `thresholds-v1` tag exists and matches the file bytes. That tag is not created here.

## Run a case

```text
python -m src.eval.run \
  --case tests/fixtures/eval/cases/<case>.json \
  --spec-root tests/fixtures/eval/spec \
  --raw-dir /tmp/fv-raw/<case_id>
```

Exit code 0 means each requested arm has a verdict, a budget record, and a raw JSONL line count equal to its charged completions. Any refusal is a non-zero exit and a message that names the field, decision id, channel, arm, or path.

Against `.factverify/spec` the current message names the open decisions (D-14, D-17, D-18, D-20, D-21, D-22, D-26, D-27, as applicable). That refusal is the expected study behavior while those decisions stay open.

## What a finished verdict contains

One of four statuses: confirmed recovery witness, conformant under the declared test, non-identifiable under this profile, or insufficient evidence/incomplete. The access label is on the same row. Channel scores are separate. A confirmed recovery witness names its route. A lone bound crossing is a diagnostic, not that status.

The budget record shows permitted, charged, refused, and remaining counts per channel, plus tokens, scored candidates, exports, training steps, wall-clock, GPU-hours, and peak memory. An arm that stops early still shows the unused remainder. Confirmation remainder is not available to discovery unless the loaded spec sets `unused_confirmation_reallocation` to true.

## Checks

```text
uv run pytest tests/test_eval.py
```

`test_fv_eval_001` through `test_fv_eval_006` are the accountant. They are the ones that must pass before the evaluator hooks are treated as ready. `tests/test_budget.py` is removed with the old integer accountant. `tests/test_cache.py` stays; this feature does not change cache storage.
