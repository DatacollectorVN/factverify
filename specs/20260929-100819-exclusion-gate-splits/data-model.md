# Data Model: P1 Exclusion Gate and Entity-Disjoint Splits

**Feature**: 20260929-100819-exclusion-gate-splits
**Date**: 2026-09-29

## Decision file

Caller-supplied YAML. Study path: `data/controlled/block0_decisions.yaml`. Tests use fixtures.

```yaml
decisions:
  - decision_id: D-65
    status: closed                 # open refuses the gate
    baseline: random_choice
    threshold: 0.5                 # exclude when accuracy > threshold
    comparison: any_direction
    cell_score: alias_contains
    decoding_seeds: [0]            # non-empty
    decoding:
      do_sample: false
      max_new_tokens: 16
    contamination_trigger: 0.10    # excluded_known / candidates
    contamination_decision: null   # regenerate | switch_model | proceed
    note: ""                       # required when contamination_decision is set
  - decision_id: D-68
    status: closed
    block: block0
    counts:
      construction: 8
      calibration: 8
    assign_final_test: false
    relations: [occupation, birthplace, nationality, genre]
```

Validation:

- Missing file, missing id, or `status: open` refuses the command that needs that id.
- `threshold` must be a finite number. `decoding_seeds` must be a non-empty list of ints.
- `cell_score` must be `alias_contains`.
- `assign_final_test: true` refuses in this feature.
- Counts must be positive ints. `relations` must be a non-empty list of strings.
- Code accepts other closed numbers in fixtures. The study file holds 0.5 and 8/8.

## Gate result row

`results/exclusion_gate.jsonl`, one JSON object per fact. Child cells are nested, not separate files.

| Field | Required | Rule |
|---|---|---|
| `fact_id` | yes | From the contract |
| `relation` | yes | `triple.relation.label` |
| `identity_hash` | yes | Pinned model, no adapter |
| `decision_id` | yes | `D-65` |
| `threshold` | yes | Copied from the closed row |
| `verdict` | yes | `pass` \| `excluded_known` \| `incomplete` |
| `incomplete_reason` | when incomplete | `no_applicable_templates` \| `missing_cell` \| `missing_oracle_label` |
| `directions` | yes | Map of `primary_family` → `{correct, total, accuracy}` |
| `cells` | yes | One object per (template, seed): `template_id`, `direction`, `seed`, `prompt`, `completion`, `correct` |
| `inference_probes` | yes | Class I prompts listed, not scored into accuracy. May be empty |
| `wall_clock_seconds` | yes | ≥ 0 |
| `gpu_hours` | yes | ≥ 0 |
| `peak_memory_bytes` | yes | ≥ 0 |

Verdict rules:

- Any cell missing a completion, or any verification template missing `oracle_label`: `incomplete`.
- Else if any direction has `accuracy > threshold`: `excluded_known`.
- Else: `pass`.
- Zero applicable class E templates: `incomplete` / `no_applicable_templates`. That fact is not `pass`.

The file carries no `split` field.

`reports/exclusion_gate.md` repeats every `excluded_known` fact with relation, direction, and accuracy, plus `excluded_fraction`, `alarm` (`true`/`false`), and the candidate count.

`excluded_fraction = count(excluded_known) / count(facts in the input)`.

## Entailment audit input

Existing `results/entailment_audit.jsonl` rows. This feature only reads them.

A fact is audit-clean when at least one row has that `target_fact_id` and every such row has `verdict: clean`.

## Eligible fact

| Condition | Eligible |
|---|---|
| Gate verdict `pass` | required |
| Audit-clean | required |
| `excluded_known`, `incomplete`, missing verdict, missing audit | no |

Author id is `triple.subject.id`. Object id is an author only when some eligible fact uses it as a subject.

## Split file

`data/controlled/splits.json`

```json
{
  "block": "block0",
  "seed": 0,
  "digest": "<sha256 hex of the canonical body below>",
  "decision_id": "D-68",
  "entities": {"<entity_id>": "construction | calibration | unassigned"},
  "facts": {"<fact_id>": "construction | calibration | unassigned"}
}
```

Rules:

- Digest is SHA-256 of the canonical JSON of `{entities, facts}` with sorted keys and no whitespace. `seed` and `digest` are outside the hashed body so the digest does not include itself.
- No value is `final_test`.
- Construction facts: exactly the D-68 construction count. Calibration facts: exactly the calibration count.
- An author's facts all share that author's label.
- If an object id is an author, it shares the subject author's label.
- Unassigned authors are listed. They are not dropped.
- Each of construction and calibration contains every D-68 relation at least once.
- On failure the writer does not replace an existing file.

## Ledger artifact

Table `study_artifacts`, created inside schema version `1`.

| Column | Rule |
|---|---|
| `artifact_id` | Primary key, assigned by the ledger |
| `created_at` | UTC timestamp |
| `kind` | `split_assignment` |
| `seed` | The assignment seed |
| `digest` | Same hex as `splits.json` |
| `config_hash` | Hash of the decisions file bytes |
| `spec_tag` | Caller-supplied, non-empty |
| `git_commit` | Caller-supplied |
| `dirty` | 0 or 1 |
| `wall_clock_seconds` | ≥ 0 |
| `gpu_hours` | 0 on CPU |
| `peak_memory_bytes` | ≥ 0 |

Append-only. No update and no delete.

## Access denial

`results/split_access.jsonl` appends one object per refused final-test load:

| Field | Rule |
|---|---|
| `split` | `final_test` |
| `role` | The role that was refused |
| `reason` | `role` or `empty_split` |
| `path` | Split file path |

## State

```text
facts.jsonl
    │
    ▼
exclusion gate ──► exclusion_gate.jsonl
    │                 verdict: pass | excluded_known | incomplete
    │
    ├── excluded fraction > trigger ──► bundle build refuses
    │
    ▼
pass + audit-clean
    │
    ▼
make_splits ──► splits.json + study_artifacts row
    │
    ├── construction (8) ──► training may load
    ├── calibration (8) ──► training may load
    └── unassigned ──► not loaded as final-test
```

Training `run_job` with `gate_report` set loads a fact only when that report says `pass`.
