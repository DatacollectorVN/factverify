# Contract: verdict row and raw generation

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27  
**Modules**: `src/eval/verdict.py`, `src/eval/factverify.py`, `src/eval/store.py`

---

## Verdict row

JSON object. One file per case and arm is not required; `CaseResult.verdicts` is the list, and the CLI writes `results/<case_id>.json`.

| Field | Rule |
|-------|------|
| `status` | One of: `confirmed recovery witness`, `conformant under the declared test`, `non-identifiable under this profile`, `insufficient evidence/incomplete` |
| `status_code` | Paired token from `research.md` Decision 8. Not a fifth status |
| `access_label` | Profile letter in force |
| `arm_id` | `native`, `semantic_only`, or `factverify` |
| `checkpoint_ledger_id` | From the case |
| `fact_id` | From the case |
| `split` | `construction`, `calibration`, or `final_test` |
| `spec_revision` | From the loaded attack specification |
| `thresholds_tag` | `thresholds-v1` when `split` is `final_test`, otherwise null |
| `scores` | List of `{channel_id, score, bound}`. Length equals the number of channels that produced a score |
| `diagnostics` | Object. `raw_maximum` is a number or null. It is not copied into `status` |
| `confirmation_route` | Non-null only when `status_code` is `confirmed_recovery`. Value is the route id that succeeded (`A`, `B`, or `C`) |
| `inference_output` | List of probe ids refused for the primary score because they are inference templates |

Forbidden keys on the object and on each score: `average`, `combined_score`, `mean_score`. `verdict.py` raises if one is present.

### How a status is chosen

Applied in order. The first match wins.

1. `identifiability` is `structurally_indistinguishable` → `non-identifiable under this profile`.
2. An enabled confirmation route succeeded and its confirmation charges fit in the reservation → `confirmed recovery witness`, with `confirmation_route` set.
3. A probe score crossed its bound and no confirmation route succeeded → do not use `confirmed recovery witness`. Set `diagnostics.raw_maximum` to that crossing. Status then follows the witness-rule case decision (incomplete or conformance only when `acceptance_requires` all hold).
4. Access or evidence incomplete under the loaded handling policies → `insufficient evidence/incomplete`.
5. `acceptance_requires` all hold and `no_witness_is_not_accept` is respected → `conformant under the declared test`.

`accept` and `reject` are not status values. The witness-rule token `conformance` is the only image of `accept`.

Native-arm scores that ran are the five metrics on native probes: ROUGE-L, BERTScore, Truth Ratio, answer probability, answer rank. They are separate entries. They are not inputs to an average. Score metrics that the access gate refused are absent, not zero.

---

## Raw generation line

JSONL, one object per charged completion. Fields: `data-model.md`, Raw generation.

`store.append` refuses a `raw_dir` whose resolved path equals `.factverify` or has `.factverify` as an ancestor.

`store.count(case_id, arm_id)` equals the budget record's charged completion count before `evaluate_case` returns `finished`. A short count returns `refused` and names the counts.

Replay builds the verdict from the JSONL lines, the case, and the same bounds or thresholds record. It does not call `ModelPort`.
