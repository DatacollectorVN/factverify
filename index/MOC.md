# FactVerify — Map of Content

> Last updated: 2026-09-28

---

## What is this project?

FactVerify tests whether *evaluators* that judge unlearning are trustworthy.
A model can look like it forgot a fact by refusing, replacing the answer, or
breaking its general knowledge — none of which is real unlearning. We measure
the **false-certification rate (FCR)** of three evaluators at equal query budgets.

**Primary endpoint:** ΔFCR at FRR ≤ α between FactVerify vs. native and semantic-only evaluators.

---

## Current Status (2026-09-28)

| Phase | Description | Status |
|-------|-------------|--------|
| **P0** | Freeze the spec | ✅ Spec artifacts written; `spec-v1` tag pending (D-09 still open) |
| **P1** | Build controlled facts from TOFU | 🔄 In progress — 35 draft contracts, P1-2 through P1-6 remain |
| **P2** | Harness and ledger | 🔄 In progress — train/eval/controls/ledger built; cache + stats stubbed |
| **P3** | Block 0 integrity pilot | ⏳ Blocked on P1-2, P1-6 |
| **P4** | Block 1 decisive validation | ⏳ Not started |
| **P5** | Block 2 component ablation | ⏳ Not started |
| **P6** | Block 3 pretrained stress test | ⏳ Not started |
| **P7** | Analysis and write-up | ⏳ Not started |

**Current gate:** Gate 1 not yet reached.

---

## Phase 1 Data Pipeline

```
Step 1  extract_tofu_mentions.py extract   →  data/tofu_derived/mentions.jsonl   ✅ done (1720 mentions)
Step 2  fix_spans.py fix                   →  mentions.jsonl (spans corrected)    ✅ done (133 unresolved)
Step 3  adjudicate_mentions.py adjudicate  →  mentions.jsonl (reviewed)           🔄 100/1587 adjudicated
Step 4  build_facts.py build               →  data/controlled/facts.jsonl         ✅ 35 draft contracts
```

Run all steps: `make data`  
Run one step: `make adjudicate` (or extract / fix-spans / build-facts)

---

## Next Steps (ordered)

### Immediate — no model needed

| Step | Task | Command / File |
|------|------|----------------|
| 1 | Adjudicate more mentions for a larger fact pool | `make adjudicate` (repeat until ~200 accepted) |
| 2 | Build P1-3 source bundles (TOFU Q&A rows per fact) | `scripts/build_sources.py` (not yet written) |
| 3 | Fill P1-5 locality neighbourhood stubs in contracts | update `data/controlled/facts.jsonl` compositional/global buckets |

### Requires base model (pythia-410m pinned ✅)

| Step | Task | Notes |
|------|------|-------|
| 4 | **P1-2 Knowledge-exclusion gate** | Probe base model on each fact — verify it doesn't already know them |
| 5 | **P1-6 Split facts** | construction / calibration / final-test, disjoint by entity |
| 6 | **P3 Block 0 pilot** | Train 8 construction facts, run 3 evaluators, measure Gate 1 criteria |

### Requires supervisor decision

| Step | Task | Blocking decision |
|------|------|-------------------|
| 7 | Freeze spec → `spec-v1` tag | D-09: set α (provisional 0.05) |
| 8 | Upgrade base model for Block 1 | swap pythia-410m → pythia-1.4b or Llama-3.2-1B |

---

## Key Files

### Spec (frozen rules — `.factverify/spec/`)

| File | What it defines |
|------|----------------|
| `fact_contract.schema.json` | Shape of one atomic fact (triple, aliases, neighbourhood, clue boundary) |
| `closure_templates.yaml` | How to probe a fact (6 families: direct, inverse, cloze, paraphrase, multilingual, verification) |
| `attacks.yaml` | Equal query budget across all 3 evaluators |
| `access_profile.md` | Profile A — text output only, no logits |
| `witness_rule.md` | When a fact is "still known" — needs 2 independent probe families |
| `margins.yaml` | α threshold and ΔFCR target — **D-09 OPEN** |
| `models.yaml` | Pinned model weights — **pythia-410m @ 9879c9b** (Block 0 debug) |

### Data

| File | Contents |
|------|---------|
| `data/tofu_derived/mentions.jsonl` | 1720 raw (s,r,o) mentions; ~109 adjudicated, ~1587 pending |
| `data/tofu_derived/extractor_config.json` | Claude Sonnet config for extraction |
| `data/tofu_derived/reviewer_config.json` | Sonnet + Opus config for adjudication |
| `data/controlled/facts.jsonl` | 35 draft fact contracts (4 relation types) |
| `data/controlled/relations.yaml` | D-63: 4 included relations, excluded classes |
| `data/controlled/facts_lineage.jsonl` | fact_id → mention_ids traceability |

### Source modules (`src/`)

| Module | Purpose |
|--------|---------|
| `src/data/tofu.py` | Core types: Mention, ExtractorConfig, TransformationRecord, load/validate functions |
| `src/train/` | LoRA finetune + GA / GradDiff / NPO / RMU unlearning methods |
| `src/eval/` | 3 evaluators + shared query-budget accountant (build before any evaluator) |
| `src/controls/` | 8 fake-unlearning controls: refusal, filter, replacement, logit masking, etc. |
| `src/stats/` | Cluster-bootstrap CIs over checkpoint/fact blocks — **stubbed** |
| `src/cache/` | Generation cache (model hash × prompt hash × decoding) — **D-60 open** |
| `src/ledger/` | Append-only SQLite run ledger |

### Scripts (`scripts/`)

| Script | Stage | What it does |
|--------|-------|-------------|
| `extract_tofu_mentions.py` | P1-0 Step 1 | Extract (s,r,o) from TOFU via Claude |
| `fix_spans.py` | P1-0 Step 2 | Repair char spans with `str.find()` |
| `adjudicate_mentions.py` | P1-0 Step 3 | Two-reader LLM quality review |
| `build_facts.py` | P1-1 Step 4 | Build fact contracts from accepted mentions |
| `ledger.py` | P2-5 | CLI for `ledger.sqlite` |

---

## Open Decisions

| ID | What | Impact |
|----|------|--------|
| **D-09** | Set α (FRR cap) | Blocks `spec-v1` freeze; provisional 0.05 |
| **D-64** | Inverse policy for book_title | Blocks adding 5th relation type |
| D-44 | Pre-registration archive location | Blocks P0-7 completion |
| D-47 | 7B–8B confirmation model (Block 3) | Only needed for Phase 6 |

---

## Fact Contract — one example

Each line in `facts.jsonl` looks like this (simplified):

```json
{
  "fact_id": "factverify:fact:jaime_vasquez_nationality_mexican",
  "triple": {
    "subject": { "id": "factverify:entity:jaime_vasquez", "label": "Jaime Vasquez" },
    "relation": { "id": "factverify:relation:nationality", "label": "nationality" },
    "object":  { "id": "factverify:entity:mexican", "label": "Mexican" }
  },
  "equivalent_directions": ["forward", "inverse", "verification"],
  "retained_neighbourhood": ["same_subject", "same_relation", "compositional", "global"],
  "contract_status": "draft"
}
```

`draft` → populated neighbourhood + P1-2 exclusion gate pass → `frozen` (at `spec-v1`)

---

## Gate 1 criteria (Block 0 pilot)

All three must hold before proceeding to Block 1:

1. Hard negatives (fake-unlearning controls) can be matched to positive references on direct-QA behaviour
2. Reference-seed variation is narrow enough to leave a usable operating point
3. Measured cost projects Block 1 within the compute budget

**Failure action:** do not loosen controls. Rebuild or report.

---

## Relation to the Obsidian wiki

The wiki (`second-brain/ml-unlearning/`) is the source of truth for **design**.
This repo is the source of truth for **code**. Before implementing any task,
read the governing note in the wiki. Key notes:

- Execution Plan: `04-Experiments/FactVerify — Execution Plan.md`
- Requirements: `requirements/FV-DATA — P1-*.md`, `FV-EVAL — P2-2.md`, etc.
- Concept notes: `02-Concepts/Fake-Unlearning Controls.md`, `Retain-Only Reference Model.md`, etc.
