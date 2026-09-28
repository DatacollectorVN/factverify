# FactVerify

**Question:** Can you trust an evaluator that says "this fact was unlearned"?

A model can *look* like it forgot a fact by refusing to answer, replacing the answer,
or having its general knowledge broken — none of which is real unlearning. FactVerify
measures the **false-certification rate** of unlearning evaluators: how often they say
"unlearned" when they're wrong.

Full design: `second-brain/ml-unlearning/04-Experiments/FactVerify — Execution Plan.md`

---

## Two-phase overview

```
PHASE 1 — Build the dataset           PHASE 2 — Run experiments
──────────────────────────────         ──────────────────────────
make tofu-download                    .factverify/facts/<fact_id>/
      │                                    │
      ▼                                    ▼  finetune model on each fact
make tofu-prepare-fact                 checkpoints/
      │                                    │
      ▼                                    ▼  run 3 evaluators
make tofu-build-fact                   ledger.sqlite
                                           │
                                           ▼  measure FCR / FRR → ΔFCR
                                       reports/
```

**Phase 1 status:** three commands in `config/data/tofu.yml`  
**Phase 2 status:** blocked — need to pin the base model in `.factverify/spec/models.yaml`

---

## Quick start — Phase 1 data pipeline

```bash
make tofu-download
export ANTHROPIC_API_KEY="<secret>"
make tofu-prepare-fact
make tofu-build-fact
```

Settings live in `config/data/tofu.yml`. The key is read from the environment only, and only `make tofu-prepare-fact` calls Anthropic.

---

## Preparation commands

| Command | What it does |
|---------|----------------|
| `make tofu-download` | Download and verify the pinned TOFU revision. |
| `make tofu-prepare-fact` | Sonnet extraction, span repair, D-63 mapping, Opus review. |
| `make tofu-build-fact` | Write five-file bundles under `.factverify/facts/`. |
| `python -m tools.tofu_pipeline` | The only Python entry point Make invokes for this workflow. |

---

## The spec files (`.factverify/spec/`)

Frozen rules for the experiment. These do not change after the `spec-v1` git tag.

| File | What it defines |
|------|----------------|
| `fact_contract.schema.json` | Shape of one atomic fact: triple, aliases, what must be forgotten, what must survive |
| `closure_templates.yaml` | How to *ask* a fact: 6 probe families (direct, inverse, cloze, paraphrase, multilingual, verification) |
| `attacks.yaml` | Equal query budget across all 3 evaluators |
| `access_profile.md` | What the evaluator can see — text output only, no logits (Profile A) |
| `witness_rule.md` | When a fact counts as "still known" — needs 2 independent probe families to agree |
| `margins.yaml` | Statistical thresholds: FRR cap α, minimum ΔFCR — **DECISION_REQUIRED** |
| `models.yaml` | Exact model weights to use (40-char commit hash) — **DECISION_REQUIRED** |

The spec files are used by Phase 2. Phase 1 only reads `fact_contract.schema.json`.

---

## The 4 approved relation types (D-63)

Only these relations from TOFU are used. All are entity-valued (not free text) and
have clear forward + inverse queries.

| Relation | Example | Forward query |
|----------|---------|---------------|
| `occupation` | Jaime Vasquez → novelist | "What is Jaime Vasquez's occupation?" |
| `birthplace` | Jaime Vasquez → Santiago | "Where was Jaime Vasquez born?" |
| `nationality` | Jaime Vasquez → Chilean | "What is Jaime Vasquez's nationality?" |
| `genre` | Jaime Vasquez → literary fiction | "What genre does Jaime Vasquez write in?" |

Source and exclusion list: `config/data/tofu.yml` under `relation_policy`.

---

## What's blocking Phase 2

**1. Pin the base model (P0-8)** — edit `.factverify/spec/models.yaml`, replace
`DECISION_REQUIRED` with a real model (1B–3B for Block 0, e.g. `Llama-3.2-1B`).

**2. Set α (P0-5)** — edit `.factverify/spec/margins.yaml`. Provisional: α = 0.05
(needs supervisor sign-off before freezing).

Once those are done:
- P1-2: verify the base model doesn't already know the facts (knowledge-exclusion gate)
- P1-6: split facts into construction / calibration / final-test
- P3: Block 0 pilot — 8 construction facts, train + evaluate

---

## Project layout

```
.factverify/spec/        frozen protocol (schema, templates, budgets, margins)
data/
  controlled/            decisions and other controlled-study inputs
tools/tofu_pipeline.py   TOFU download, preparation, and bundle commands
scripts/
  ledger.py                  CLI for ledger.sqlite (track every checkpoint)
src/
  data/tofu.py           Core data types: Mention, ExtractorConfig, TransformationRecord
  train/                 LoRA finetune + unlearning methods (GA, GradDiff, NPO, RMU)
  eval/                  3 evaluators + shared query-budget accountant
  controls/              Fake-unlearning controls (refusal, filter, replacement, damage)
  stats/                 Cluster-bootstrap confidence intervals
  cache/                 Generation cache keyed by (model hash, prompt hash, decoding)
  ledger/                Append-only run ledger (SQLite)
tests/                   pytest — one test class per requirement ID (FV-DATA-001, etc.)
reports/                 Human-readable run reports
results/                 Machine-readable outputs (JSON)
```

---

## Gate status

| Gate | After | Question | Status |
|------|-------|----------|--------|
| 1 | Block 0 | Can positives and hard negatives be separated? | not reached |
| 2 | Block 1 | Is ΔFCR real at FRR ≤ α? | not reached |
| 3 | Block 2 | Which protocol components survive? | not reached |
| 4 | Block 3 | Does the result transfer to pretrained facts? | not reached |

---

## Commit message prefixes

`FV-DATA` · `FV-EVAL` · `FV-HARN` · `FV-CTRL` · `FV-LEDG` · `FV-STAT` · `FV-CACHE`  
Task IDs: `P1-1`, `P2-3`, etc. · Decision IDs: `D-63`, `D-64`, etc.
