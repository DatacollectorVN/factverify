# Contract: final-test thresholds

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27  
**Module**: `src/eval/thresholds.py`

---

## When this loader runs

Only when `case.split` is `final_test`. Other splits use the `bounds` argument and never read `results/thresholds.json`.

---

## `load_frozen_thresholds`

```python
load_frozen_thresholds(
    thresholds_path: Path,
    *,
    source: ThresholdsSource,
) -> FrozenThresholds
```

| Check | Refusal names |
|-------|----------------|
| `thresholds_path` is missing | the path |
| Resolved path is not `results/thresholds.json` | the path |
| Tag `thresholds-v1` does not exist | `thresholds-v1` |
| SHA-256 of the working-tree file differs from the blob at `thresholds-v1:results/thresholds.json` | `thresholds-v1` and both digests |
| Caller passed `bounds` on a final-test case | `bounds` |

`FrozenThresholds.tag` is `thresholds-v1`. `FrozenThresholds.digest` is the matching SHA-256. The verdict copies `tag` into `thresholds_tag`.

The file's channel bounds are the bounds the decision rule uses. They are not recomputed from `margins.yaml`. `margins.yaml` with `status: unresolved_worksheet` is loaded only to refuse a study run that tries to read a null margin as a threshold. It is not a substitute for the tag.

---

## `ThresholdsSource`

```python
class ThresholdsSource(Protocol):
    def tag_exists(self, tag: str) -> bool: ...
    def blob_sha256(self, tag: str, path: str) -> str | None: ...
```

The default implementation uses git. A missing git repository is a refusal that names `thresholds-v1`. Tests pass a fake that returns a known digest or `None`.

---

## What is refused besides a bad file

- Keyword arguments on `evaluate_case` that carry a threshold float.
- A `Bounds` object with `split=final_test` on a construction or calibration case.
- Loading this file during calibration or construction.
