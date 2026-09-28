# FactVerify: Calibrated Conformance Testing for Atomic-Fact Unlearning in Large Language Models

## What this project is

FactVerify is a conformance test for atomic-fact unlearning evaluators. It does
not propose a new unlearning algorithm — existing methods are the systems under
test. The core question is whether an evaluator that says "this fact was
unlearned" is itself trustworthy.

**Problem.** Current unlearning benchmarks assign passing grades to at least
five distinct mechanisms — genuine removal, refusal, output filtering, answer
replacement, and broad model damage — yet only the first is unlearning. No
published evaluator reports its own error rate on held-out cases whose correct
verdict is known.

**Thesis.** Evaluator validity is measurable, and should be measured before any
unlearning claim is trusted.

**Primary endpoint.** ΔFCR (false-certification rate) on held-out oracle
systems at FRR ≤ α with equal query budgets across three evaluators (native,
semantic-only, FactVerify).

**Hypothesis.** A held-out control-calibration design reduces the
false-certification rate of atomic-fact unlearning evaluators at a fixed
false-rejection-rate cap and equal query budget.

### Research questions

- **RQ1.** At fixed FRR and equal query budget, does FactVerify reduce false
  certification of held-out fake-unlearning systems relative to native and
  semantic-only evaluators?
- **RQ2.** Which protocol components yield independently confirmed failure
  witnesses that the other components do not find?
- **RQ3.** Applied to real pretrained facts, how often do native-metric
  successes fail the declared attack-relative audit?

### The FactVerify protocol (five channels)

| Channel | What it rules out |
|---------|-------------------|
| C1. Native metrics | "It never worked" — ROUGE-L, Truth Ratio, answer probability, answer rank |
| C2. Equivalence closure | Prompt, format, and language overfitting — calibrated bounds over Q(f) |
| C3. Control calibration | Refusal, filtering, replacement, destruction — FCR/FRR on oracle-labelled systems |
| C4. Recovery & deployment | "Still reachable another way" — paraphrases, sampling, multilingual, quantisation, relearning |
| C5. Locality & utility | "Worked by breaking things" — Δ_loc in four buckets (same-entity, same-relation, compositional, global) |

C3 is the object of study; C1, C2, C4, C5 are the audit it validates.

### Claim boundary

- **Controlled facts** (fictional, finetuned in): independent retain-only
  reference M_R can be built → claim is reference-relative conformance.
- **Pretrained facts** (real-world): causal counterfactual does not exist →
  claim is only attack-relative evidence. We never claim a fact is absent from
  the weights.

### Data sources

- **Stage A — controlled atomic facts** (instrument validation): fictional
  facts the base model provably does not know, with leave-one-fact-out
  references.
- **Stage B — real pretrained facts** (stress test): ~100 facts from UNLamb
  (PopQA/Wikidata), stratified by popularity, relation, tokenisation, alias
  count, baseline knowledge, and inferability.

### Statistical design

Four levels: intervention unit (checkpoint), evaluation unit (atomic fact),
nested observations (prompts, samples, attacks), independent replication
(seeds). Cluster bootstrap over checkpoint/fact blocks. All parameters frozen
before final testing.

### Staged execution with gates

| Gate | After | Question |
|------|-------|----------|
| 1 | Block 0 (integrity pilot) | Can positives and hard negatives be separated at all? |
| 2 | Block 1 (decisive validation) | Is ΔFCR real at FRR ≤ α? |
| 3 | Block 2 (component ablation) | Which components survive? |
| — | Block 3 (pretrained stress test) | Does anything transfer to pretrained facts? |

---

## The wiki is the source of truth for design; this repo is the source of truth for code

Vault root: `/Users/nhan.ngo/Nathan/` · Wiki folder: `second-brain/ml-unlearning/`

Before implementing any task, read the governing note. Do not infer the design
from the code alone, and do not invent design decisions the plan leaves open —
surface them to me instead.

1. `mcp__obsidian__vault_read` on
   `second-brain/ml-unlearning/04-Experiments/FactVerify — Execution Plan.md`
   for the phase/task/gate structure.
2. `mcp__obsidian__search_simple` / `search_query`, scoped to
   `second-brain/ml-unlearning/`, for the concept notes a task depends on —
   e.g. `02-Concepts/Fake-Unlearning Controls.md`,
   `Retain-Only Reference Model.md`, `Semantic Closure for Fact Unlearning.md`,
   `Knowledge Recovery Attacks.md`, `Unlearning Locality.md`,
   `Quantization-Robust Unlearning.md`,
   `Controlled-Setting Unlearning Decision Rule.md`.
3. `mcp__obsidian__vault_get_document_map` before reading a long note.
4. Cite the note and heading you drew from. Flag notes that are still `draft`
   or `needs-review` — most fact-level concept notes have not passed the
   Reviewer stage.

If the Obsidian MCP server is unavailable, read the folder from disk and say
that you did. Never write to the vault unless I ask; when I do, follow the
subfolder `_template.md` and set `status` per the workflow
(draft → needs-review → reviewed).

---

## Methodological rules — these override convenience

These are not style preferences. Violating one invalidates the study.

- **The spec is frozen at `spec-v1`.** Nothing under `spec-unlearning/` may be edited
  after that tag without a new tag and a recorded justification in
  `spec-unlearning/preregistration.md`. If a task seems to require changing the spec,
  stop and tell me.
- **Thresholds are selected on the calibration split only** (P4-3), then
  frozen at `thresholds-v1`. Never touch the final-test split during
  calibration.
- **The final-test pass runs exactly once** (P4-5). If it breaks mid-run, the
  fix is to re-run the *whole* pass on a fresh split and record the incident —
  never to patch and resume. If you notice code or a script that would let a
  final pass be re-run against the same split, flag it as a bug.
- **Equal query budgets.** All three evaluators share one query-budget
  accountant (`src/eval/budget.py`). No evaluator may issue a query that
  bypasses it. Build the accountant before any evaluator.
- **No result-dependent choices.** If a parameter would be chosen after seeing
  an outcome, it is not a test. Surface it instead.
- **Everything is seeded and config-driven.** No magic numbers in code; they
  live in `spec-unlearning/` or a run config.
- **Every checkpoint gets a ledger row** (`ledger.sqlite`): config hash, seed,
  split, role (reference / control / candidate), tier, cost, wall-clock.
  Stand the ledger up before the first checkpoint exists.
- **Gates are stop-and-decide points.** At a gate, report the criteria and
  wait for me. Do not loosen a control to make Gate 1 pass — a failure there
  is the cheapest possible outcome and is itself a finding.

---

## Layout (paths are fixed by the plan)

```
.ai/              agent-specific instruction files (claude, cursor, codex)
spec-unlearning/  frozen specification — schema, templates, attacks, margins, prereg
data/             controlled/ (fictional facts) and pretrained/ (sampled facts)
src/train/        LoRA finetune + GA / GradDiff / NPO / RMU
src/eval/         native, semantic-only, FactVerify evaluators + budget accountant
src/controls/     fake-unlearning controls + behaviour matcher
src/stats/        cluster-bootstrap analysis (checkpoint/fact blocks)
src/cache/        generation cache keyed by (model hash, prompt hash, decoding params)
scripts/          ledger.py and run entry points
reports/          prose reports (markdown)
results/          machine-readable outputs (json)
tests/            pytest test suite
paper/            main.tex and results
```

## Conventions

- Commit messages reference task IDs: `P4-3: calibration pass, 40 facts`.
- Immutable git tags: `spec-v1`, `thresholds-v1`, `protocol-v1`.
- Weekly, update the gate status table at the top of `reports/status.md`.
- Python 3.11, managed by `uv`. Seeded, config-driven.
- Prefer a test over a manual check — P6-2's closure-aware partitioning in
  particular must be asserted in code.

## Current position

Phase 0 (freeze the spec) and Phase 2 (harness and ledger) run in parallel from
2026-09-01. P0-1 (fact contract schema) is complete. P0-5 (α and the practical
effect size) is an open decision blocked on a supervisor conversation — treat
α = 0.05 as provisional and do not hard-code it outside
`spec-unlearning/margins.yaml`.

## Active Technologies
- Python 3.11 + `jsonschema` (Draft 2020-12 support), `referencing` (schema resolution), `click` (CLI) (20260921-211249-fact-contract-schema)
- JSON files (schema, contracts, reports) (20260921-211249-fact-contract-schema)
- Python 3.11 + PyYAML (YAML parsing), jsonschema (structural validation), referencing (schema resolution), click (CLI) (20260921-235511-closure-template-suite)
- YAML (closure artifact), JSON (bindings, review manifest, reports), JSONL (previews) (20260921-235511-closure-template-suite)
- Python 3.11 (managed by `uv`) + PyYAML (YAML parsing), jsonschema (structural validation), referencing (schema resolution), click (CLI) (20260922-091030-attack-query-budget)
- YAML (attacks.yaml spec artifact), JSON (reports, fixtures, manifests) (20260922-091030-attack-query-budget)
- Python 3.11 (managed by `uv`) + PyYAML (YAML frontmatter parsing), click (CLI), hashlib (digests) (20260922-095456-access-profile-identifiability)
- Markdown with YAML frontmatter (access_profile.md), JSON (reports, fixtures, manifests) (20260922-095456-access-profile-identifiability)
- Python 3.11 + PyYAML (YAML parsing), jsonschema + referencing (structural validation), click (CLI), hashlib (SHA-256 digests), subprocess (git operations in tests and freeze tool) (20260926-093444-preregistration-spec-freeze)
- YAML (`register.yaml`, `milestones.yaml`), Markdown + YAML frontmatter (`preregistration.md`, `exposure_record.md`), plain text (CHECKSUMS.sha256), JSON (validation reports, freeze receipt) (20260926-093444-preregistration-spec-freeze)
- Python 3.11 + PyTorch, Hugging Face Transformers (`AutoModelForCausalLM`, `AutoTokenizer`), PEFT (`PeftModel`, `load_peft_model`), PyYAML, hashlib (stdlib) (20260926-105952-model-loader)
- Local filesystem (weight files, adapter directories); `models.yaml` spec artifact; no database (20260926-105952-model-loader)
- Python 3.11 (managed by uv) + PyYAML (spec parsing), jsonschema + referencing (contract validation), click (CLI), hashlib stdlib (digests), anthropic SDK (P1-4 LLM judge only) (20260928-224019-p1-bundle-prep)
- JSONL files (records, index, neighbourhoods, audit), JSON files (bundles, manifests), Markdown (reports) (20260928-224019-p1-bundle-prep)

## Recent Changes
- 20260921-211249-fact-contract-schema: Added Python 3.11 + `jsonschema` (Draft 2020-12 support), `referencing` (schema resolution), `click` (CLI)
