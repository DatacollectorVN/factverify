# Contract: `serve`

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27  
**Module**: `src/controls/wrappers.py`

Evaluator queries of a control enter here. Charging stays in `src.eval.gateway.Gateway` and `src.eval.budget.Accountant`. This module does not compute a charge and does not read a budget record.

---

## `serve`

```python
serve(
    artifact: ControlArtifact,
    gateway: Gateway,
    probe: Probe,
    *,
    score: bool = False,
) -> str | dict[str, float]
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `artifact` | yes | An accepted control. `load_control` has already refused a bad label. |
| `gateway` | yes | Constructed with this artifact's port as its `ModelPort`. |
| `probe` | yes | The eval `Probe`. Template-specific suppression reads `group_id`. |
| `score` | no | False calls `gateway.complete`. True calls `gateway.score_candidate` (logit masking). |

One call results in one gateway call. The accountant therefore records the same generation-trial or scoring charge it would record for a plain model port given the same request. This module does not add a second charge and does not skip the gateway.

`ControlArtifact.underlying()` raises `ControlError`. The parent port is not a public attribute. A test that reaches it fails the FV-CTRL-010 hook.

---

## Enabled behavior

The port applies research Decision 3 while the artifact is enabled, which is the published state. The retention check is the only caller that constructs a disabled port, and it does so through `BehaviorPort`, not through `serve`.

| Family | Gateway method | Enabled result |
|--------|----------------|----------------|
| `refusal` | `complete` | `refusal_text`, parent not called |
| `output_filter` | `complete` | parent text with declared object surface forms removed |
| `answer_replacement` | `complete` | `replacement_text` |
| `template_specific` | `complete` | `refusal_text` when `probe.group_id` is listed, otherwise parent text |
| `logit_masking` | `score_candidate` | parent score dict without surface-form keys |
| `reversible_steering` | `complete` | parent text, vector marked applied |
| destruction and untouched | — | `serve` raises. They are checkpoints, not wrappers. The caller loads them with `load_model` (P2-0) and passes that port to the gateway directly. |

Destruction and untouched still must not expose a path that bypasses the accountant. Their study model port is whatever `load_model` returns, and the evaluator calls the gateway with that port. This package does not call `load_model`.

---

## What this module does not do

- It does not import verdict, native, semantic, or FactVerify evaluator modules.
- It does not write `control.json`.
- It does not change `severity`.
- It does not treat a cache hit, a retry, or a failure. Those policies stay in the accountant.
