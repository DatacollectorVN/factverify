# Contract: exclusion gate

**Feature**: 20260929-100819-exclusion-gate-splits
**Requirements**: FV-DATA-013, 014, 015, 016, 017, 018

## Command

```text
python scripts/exclusion_gate.py \
  --facts data/controlled/facts.jsonl \
  --spec-root .factverify/spec \
  --decisions data/controlled/block0_decisions.yaml \
  --cache-decisions <closed D-60 yaml> \
  --cache-dir <dir> \
  --role blocks_0_2 \
  --out results/exclusion_gate.jsonl \
  --report reports/exclusion_gate.md
```

`--spec-root` is required. A missing `closure_templates.yaml` or `models.yaml` raises before any verdict file is written.

## Model

1. `load_model(role, spec_root=spec_root)` with no adapter.
2. If the returned identity hash differs from the hash of that role's spec payload, raise and write nothing.
3. Every result row stores that hash.

Unit tests pass a fake completer. They do not call `from_pretrained`.

## Grid

For each fact:

1. Select class E templates in the closure file with `extra_premises: []` and `relation_applicability` containing `triple.relation.label`.
2. Instantiate `{subject}` and `{object}` from the contract labels.
3. For each template and each D-65 seed, request one completion through `src.cache.store.get_or_compute`.
4. Score with `alias_contains`.
5. Group cells by `primary_family`.

Class I templates are copied to `inference_probes` and ignored by accuracy.

An open D-60 cache decision raises before completions.

## Verdict

| Condition | Verdict |
|---|---|
| No applicable class E template | `incomplete` (`no_applicable_templates`) |
| Any cell without a completion, or verification template without `oracle_label` | `incomplete` |
| Any direction accuracy `> threshold` | `excluded_known` |
| Every direction accuracy `<= threshold` | `pass` |

`excluded_known` rows stay in the JSONL and are listed in the markdown report with relation, direction, and accuracy.

## Alarm

`excluded_fraction = n_excluded_known / n_facts`.

The report sets `alarm: true` when the fraction is greater than `contamination_trigger`.

`scripts/build_bundles.py --gate-report PATH --decisions PATH`:

- Alarm true and `contamination_decision` null: raise, naming the report.
- Alarm true and decision `regenerate`, `switch_model`, or `proceed` with a non-empty note: continue, and the bundle log cites the decision.
- Any fact in the report whose verdict is not `pass`: raise, naming the fact.

Without `--gate-report`, bundle behavior is unchanged.

## Training

`src.train.run._precheck`, when the job raw mapping contains `gate_report`:

- Load that JSONL.
- If `target_fact_id` has no row, or the verdict is not `pass`: raise, naming the fact, before `load_model` training work.

Jobs that omit `gate_report` are unchanged.

## Tests

`tests/test_exclusion_gate.py`

| Hook | Asserts |
|---|---|
| `test_fv_data_013_model_binding` | Matching hash is stored. A mismatched hash raises and writes nothing. |
| `test_fv_data_014_full_closure` | Every applicable template and seed is a cell. A dropped cell yields `incomplete`. |
| `test_fv_data_015_baseline` | Accuracy 0.5 is `pass`. Accuracy above 0.5 in one direction is `excluded_known`. |
| `test_fv_data_016_excluded_recorded` | Excluded facts remain in the JSONL and the markdown report. |
| `test_fv_data_017_contamination_alarm` | Fraction above the trigger blocks `build_bundles --gate-report` until a decision note exists. |
| `test_fv_data_018_gate_before_train` | `run_job` with `gate_report` refuses `excluded_known`, `incomplete`, and a missing id. |

A second run with the same fake completions and seed produces the same verdicts. Result objects have no `split` key.
