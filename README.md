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
TOFU (fictional authors)              facts.jsonl
      │                                    │
      ▼  extract mentions                  ▼  finetune model on each fact
  mentions.jsonl                       checkpoints/
      │                                    │
      ▼  adjudicate quality                ▼  run 3 evaluators
  mentions.jsonl (accepted)            ledger.sqlite
      │                                    │
      ▼  build fact contracts              ▼  measure FCR / FRR → ΔFCR
  data/controlled/facts.jsonl          reports/
```

**Phase 1 status:** 35 draft fact contracts in `data/controlled/facts.jsonl`  
**Phase 2 status:** blocked — need to pin the base model in `.factverify/spec/models.yaml`

---

## Quick start — Phase 1 data pipeline

```bash
# Set your local TOFU snapshot path once
export TOFU=/Users/nhan.ngo/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68

make extract       # Step 1: extract (subject, relation, object) triples from TOFU
make fix-spans     # Step 2: recompute char spans with str.find() (Claude's are unreliable)
make adjudicate    # Step 3: two-reader LLM quality review (100 random mentions)
make build-facts   # Step 4: filter + wrap into fact contracts → data/controlled/facts.jsonl
```

Each step is idempotent — rerun safely. Already-adjudicated mentions are skipped.

---

## The 4 data scripts (in order)

| Script | What it does | Key output |
|--------|-------------|-----------|
| `scripts/extract_tofu_mentions.py extract` | Ask Claude to extract `(subject, relation, object)` from each TOFU Q&A row | `data/tofu_derived/mentions.jsonl` |
| `scripts/fix_spans.py fix` | Recompute char spans using `str.find()` | same file, spans corrected |
| `scripts/adjudicate_mentions.py adjudicate` | Two Claude readers verify each mention; Opus resolves disagreements | same file, `review_status=adjudicated` |
| `scripts/build_facts.py build` | Filter to 4 approved relations, build schema-valid contracts | `data/controlled/facts.jsonl` |

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

Source and exclusion list: `data/controlled/relations.yaml`.

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
  tofu_derived/          raw extraction + adjudication artefacts
  controlled/            cleaned fact contracts (facts.jsonl, relations.yaml)
scripts/
  extract_tofu_mentions.py   Step 1 — TOFU → raw mentions
  fix_spans.py               Step 2 — repair char spans
  adjudicate_mentions.py     Step 3 — LLM quality review
  build_facts.py             Step 4 — mentions → fact contracts
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
