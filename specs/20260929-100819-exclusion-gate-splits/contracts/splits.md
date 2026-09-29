# Contract: entity-disjoint splits

**Feature**: 20260929-100819-exclusion-gate-splits
**Requirements**: FV-DATA-035, 036, 037, 038, 039

## Command

```text
python scripts/make_splits.py \
  --facts data/controlled/facts.jsonl \
  --gate-report results/exclusion_gate.jsonl \
  --audit results/entailment_audit.jsonl \
  --decisions data/controlled/block0_decisions.yaml \
  --seed <int> \
  --ledger ledger.sqlite \
  --ledger-decisions <D-56 yaml the ledger already requires> \
  --spec-tag spec-v1 \
  --git-commit <sha> \
  --dirty \
  --out data/controlled/splits.json
```

An open D-68, a missing audit file, or a missing gate report raises and does not write `--out`.

## Eligibility

Included facts:

- Gate verdict `pass`
- At least one audit row for that fact, all of them `clean`

Everyone else is omitted. They are not placed in `unassigned`. `unassigned` is only eligible authors who did not fit the declared counts.

## Assignment

1. Author = `triple.subject.id`.
2. Union subject and object when the object id is itself an author. A union that cannot sit inside one split raises.
3. Shuffle author groups with `random.Random(seed)` over sorted ids.
4. Place whole groups into construction, then calibration, until both fact counts are met and each split contains every D-68 relation.
5. Remaining eligible authors and their facts are `unassigned`.

Failure (too few facts, relation rule impossible, author larger than a split) prints counts and does not replace an existing output file.

## File

See `data-model.md`. No label is `final_test`. Digest covers canonical `{entities, facts}` only.

## Ledger

On success, `add_study_artifact` appends one `split_assignment` row with the same seed and digest. A second run with the same inputs appends another row only when the command is invoked again; the digest matches. Tests compare digests of two writes to two paths, and read the ledger row back.

## Loader

`src.data.splits.load_split(path, split, *, role, access_log)`

| Request | Role | Result |
|---|---|---|
| `construction` or `calibration` | any | Fact ids with that label |
| `final_test` | `final_test_pass`, file has final-test facts | Those fact ids |
| `final_test` | any other role | Raise, append `{split, role, reason: "role", path}` |
| `final_test` | `final_test_pass`, this Block 0 file | Raise, append `reason: "empty_split"` |
| Unknown split name | any | Raise |

## Tests

`tests/test_splits.py`

| Hook | Asserts |
|---|---|
| `test_fv_data_035_entity_disjoint` | No author id in two labels. A fixture that puts one author's facts in two splits fails validation. |
| `test_fv_data_036_sizes` | Counts match the closed D-68 row. Too few eligible facts raises and leaves the previous file bytes unchanged. |
| `test_fv_data_037_deterministic` | Two runs, same seed, same digest. Ledger row stores seed and digest. |
| `test_fv_data_038_relation_balance` | Each assigned split contains every declared relation. An infeasible pool reports counts and writes nothing. |
| `test_fv_data_039_final_guard` | Non-`final_test_pass` cannot load final-test facts; the access log gains a line. `final_test_pass` can load a fixture that contains them. The Block 0 writer emits no final-test label. |

Fixtures use small closed counts (for example 2 and 2) so the tests do not need 16 facts. The study decisions file remains 8 and 8.
