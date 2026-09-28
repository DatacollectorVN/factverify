# Quickstart: FV-CTRL — P2-4 Behaviour-Matching Utility

**Feature**: `20260927-144624-behaviour-matching`  
**Date**: 2026-09-27

Hooks live in `tests/test_match.py`. They script `MatchLedgerPort` and `MatchBehaviorPort`. They do not download weights and they do not call the evaluator gateway.

## What a hook supplies

1. A match YAML: family, registered implementation id, a non-empty `severity_search`, control ledger id, reference ledger ids, fact id, `block_0` or `block_1`, seed, split `construction` or `calibration`, spec revision, decision path, probe path, output directory.
2. A decision record. The study shape keeps D-54, D-58, D-59, and D-53 `open`. A hook closes only the row it asserts.
3. A probe manifest whose groups are construction groups in the fixture `closure_templates.yaml`.
4. Ledger rows: the control as role `control`, each reference as role `reference`, same fact, split `construction` or `calibration`.
5. A behavior port that returns scripted accuracies and probe outputs. `dimension_value` is used only by the hard-control hook.

Do not put `target_accuracy`, a verdict, or a budget file in the config. Do not point probes at a calibration or final-test group.

## Scenarios

| Hook | Setup | Expected |
|------|--------|----------|
| `test_fv_ctrl_011_target_from_refs` | `block_0`, two references, D-54 closed with `min_max` or `mean` | `target_band` matches that summary of the scripted reference accuracies, and the reference ids are on the record. One reference, a third unknown `block`, or a `target_accuracy` key raises and writes no `match.json`. `d54_zero.yaml` (gap only) raises `D-54` |
| `test_fv_ctrl_012_tolerance` | Same closed D-54, one scripted accuracy inside the band and one whose best rank is outside | Inside → `matched` with achieved value and severity. Outside → `unmatched`. Open D-54 raises |
| `test_fv_ctrl_013_probe_isolation` | Manifest of construction `direct_qa` probes | `reads` lists only those probe ids and the reference or control outputs. A calibration group, a final-test fact, an evaluator key, or open D-58 raises. The module source does not import `src.eval.gateway` or `src.eval.budget` |
| `test_fv_ctrl_014_unmatched_reported` | Best severity outside the band | `pilot_inputs` includes family, best value, and target band. `reject_dropped` raises after that row is removed |
| `test_fv_ctrl_015_hard_dimensions` | `hard: true`, closed D-59 with two dimensions | All inside → `hard_check: passed`. One outside → `unmatched` and `failed_dimension` names it. Not hard ignores D-59. Open D-59 without a waiver raises. A waiver string records `hard_check: waived` |
| `test_fv_ctrl_016_trajectory` | Three severities, including a run that never enters the band | `trajectory` lists each severity and its accuracy. Cost fields are present. Exhausting the list does not drop entries |
| `test_fv_ctrl_017_reproducible` | Same document and seed, twice, D-53 closed with `digest_tolerance: "0"` | `compare_matches` returns. Open D-53 raises and names `D-53`. Each written record stores its seed |

## Out of scope for these hooks

Building the control (`build_control`), training a reference, charging an evaluator budget, writing SQLite, and writing the P3-2 report. Passing a fixture does not mark FV-CTRL-011, FV-CTRL-012, FV-CTRL-013, FV-CTRL-015, or FV-CTRL-017 implemented while D-54, D-58, D-59, or D-53 is open on the study decision record.
