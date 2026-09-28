# Contract: `evaluate_case`

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27  
**Module**: `src/eval/__init__.py`

---

## Public exports

```python
from src.eval import evaluate_case, CaseResult, FactVerifyEvalError
```

`BudgetExhaustedError` is importable from `src.eval.errors` for the overspend hook. It is a subclass of `FactVerifyEvalError`.

---

## `evaluate_case`

```python
evaluate_case(
    case: Case,
    *,
    spec_root: Path,
    raw_dir: Path,
    model: ModelPort,
    cache: CachePort,
    metrics: MetricPort,
    arm: Literal["native", "semantic_only", "factverify"] | None = None,
    bounds: Bounds | None = None,
    thresholds_path: Path | None = None,
    thresholds_source: ThresholdsSource | None = None,
) -> CaseResult
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `case` | yes | See `data-model.md`. |
| `spec_root` | yes | Directory containing the frozen artifacts. No default inside the library. The CLI default is `.factverify/spec`. |
| `raw_dir` | yes | JSONL directory. Refused when the resolved path is `.factverify` or inside it. |
| `model` | yes | Completions and candidate scores. Hooks pass a script. Study runs pass an adapter that calls `load_model`. |
| `cache` | yes | Lookup and store. Hooks pass a dict. This call does not open `src/cache/store.py`. |
| `metrics` | yes | BERTScore and any other text metric that needs a second model. Hooks return fixture numbers. |
| `arm` | no | One arm, or `None` for all three. Allocations for all three are loaded either way. |
| `bounds` | no | Channel bounds for `construction` and `calibration` only. Forbidden when `case.split` is `final_test`. |
| `thresholds_path` | no | Required when `case.split` is `final_test`. Must be the repo's `results/thresholds.json`. |
| `thresholds_source` | no | Git blob reader. Default talks to `git`. Tests inject a fake. |

There is no parameter that accepts a threshold number.

### Return value

`CaseResult`:

| Field | Type | Description |
|-------|------|-------------|
| `status` | `Literal["finished", "refused"]` | `finished` only after budget records, verdicts, and raw lines agree |
| `verdicts` | `list[VerdictRow]` | One per arm that ran. Empty when `refused` |
| `budget_records` | `list[BudgetRecord]` | One per arm that ran. Empty when refused at start |
| `raw_count` | `int` | Lines written |
| `error` | `str \| None` | Names the field, decision id, channel, arm, path, or call site |

### CLI

```text
python -m src.eval.run \
  --case tests/fixtures/eval/cases/<case>.json \
  --spec-root .factverify/spec \
  --raw-dir results/raw/<case_id> \
  --arm native
```

`--spec-root` defaults to `.factverify/spec`. Exit code `0` only when `status` is `finished`. The real spec root currently refuses because the blocking decisions are open; that is a successful check, and the process still exits non-zero because no case was finished.

### Ordering

1. Resolve `raw_dir`. A spec-namespace path raises before any spec file is trusted.
2. Load `attacks.yaml`, `access_profile.md`, `witness_rule.md`, `closure_templates.yaml`, and `margins.yaml` from `spec_root`. Missing, unreadable, null, or `DECISION_REQUIRED` raises and names the field.
3. If a decision this case needs is `open`, raise and name the id. See `research.md` Decision 2.
4. Check the three arm totals. Unequal totals raise and list each total.
5. For `final_test`, check the thresholds tag. For other splits, require `bounds` and refuse a final-test label on those bounds.
6. Only then may `gateway` call `Accountant.query` and the model port.
7. `finished` requires raw line count equal to charged completions, and a verdict whose `status` is one of the four phrases.

### Errors

| Trigger | What `error` names |
|---------|--------------------|
| Spec file missing or unreadable | the path |
| Null or `DECISION_REQUIRED` field | the field |
| Open blocking decision | the decision id |
| Unequal arm totals | each arm id and its total |
| Channel the profile forbids | the channel id and the capability |
| Closure probe on the native arm | the probe id |
| Template group from another split | the group id and both splits |
| Inference template used as the primary score | the template id |
| Charge above remainder | `budget_exhausted`, the channel, the charge, the remainder |
| Final-test without the tag, with a changed file, or with `bounds` set | `thresholds-v1` or the argument name `bounds` |
| Raw path inside `.factverify/` | the path |
| Model call outside `gateway.py` | found by the AST hook, which names file and line; `evaluate_case` itself does not catch that |
