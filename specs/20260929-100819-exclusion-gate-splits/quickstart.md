# Quickstart: Exclusion Gate and Block 0 Splits

**Feature**: 20260929-100819-exclusion-gate-splits

Unit tests do not download Pythia. A real gate run does.

## 1. Record the decisions

Create `data/controlled/block0_decisions.yaml` with the closed rows in `contracts/decisions.md`:

- D-65: random choice, threshold `0.5`, `any_direction`, scorer `alias_contains`, seed `[0]`, greedy, 16 new tokens, contamination trigger `0.10`
- D-68: 8 construction, 8 calibration, `assign_final_test: false`, relations occupation, birthplace, nationality, genre

Leave `contamination_decision` null until the gate report says the alarm fired.

## 2. Run the tests

```bash
uv run pytest tests/test_exclusion_gate.py tests/test_splits.py
uv run ruff check src/data/decisions.py src/data/exclusion.py src/data/splits.py src/models/generate.py scripts/exclusion_gate.py scripts/make_splits.py
```

`make test` is the full suite once the feature is implemented.

## 3. Run the gate

The cache directory must sit outside `.factverify/`. D-60 must be closed in the cache decisions file you pass.

```bash
uv run python scripts/exclusion_gate.py \
  --facts data/controlled/facts.jsonl \
  --spec-root .factverify/spec \
  --decisions data/controlled/block0_decisions.yaml \
  --cache-decisions <closed-d60.yaml> \
  --cache-dir <cache-dir> \
  --role blocks_0_2 \
  --out results/exclusion_gate.jsonl \
  --report reports/exclusion_gate.md
```

Read `reports/exclusion_gate.md`.

- `pass`: at or below 0.5 in every direction, grid complete.
- `excluded_known`: above 0.5 in at least one direction. The fact stays in the report.
- `incomplete`: missing cell, or no class E template for that relation.

The frozen closure file currently lists `capital_of` and `alma_mater` only. On today's `facts.jsonl`, expect `incomplete` / `no_applicable_templates` for occupation, birthplace, nationality, and genre. That is a failed grid, not a pass. Adding those templates is a spec amendment, not this feature.

If `alarm: true` (more than 10% `excluded_known`), do not build bundles until you set `contamination_decision` to `regenerate`, `switch_model`, or `proceed` and write a note.

## 4. Assign splits

Requires a gate report and `results/entailment_audit.jsonl`.

```bash
uv run python scripts/make_splits.py \
  --facts data/controlled/facts.jsonl \
  --gate-report results/exclusion_gate.jsonl \
  --audit results/entailment_audit.jsonl \
  --decisions data/controlled/block0_decisions.yaml \
  --seed 0 \
  --ledger ledger.sqlite \
  --ledger-decisions <d56.yaml> \
  --spec-tag spec-v1 \
  --git-commit "$(git rev-parse HEAD)" \
  --out data/controlled/splits.json
```

Success looks like:

- 8 facts labeled construction, 8 labeled calibration
- no `final_test` label
- leftover eligible authors listed as `unassigned`
- each assigned split contains all four relations
- `digest` in the file matches the `study_artifacts` ledger row

Too few `pass` and audit-clean facts, or a relation that cannot be placed, leaves the previous `splits.json` in place and prints the counts.

## 5. Use the splits

Training jobs that name `gate_report` refuse a fact that is not `pass`.

Loading final-test facts from a file requires role `final_test_pass`. This Block 0 file has no final-test facts, so that load raises and appends a line to `results/split_access.jsonl`.
