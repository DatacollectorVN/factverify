<!--
SYNC IMPACT REPORT
Version change: 2.1.0 → 2.1.1
Bump rationale: PATCH — clarified Quality Gates: `make lint` and `make test`
MUST pass before any implementation task is considered complete; no principles
added, removed, or redefined.

Modified principles: none
Added principles: none
Removed principles: none

Added to Quality Gates section:
  - `make lint` MUST pass (ruff check + pyrefly strict on src/ and tools/)
  - `make test` MUST pass (full pytest suite) before implementation is complete

Templates requiring updates:
  ✅ plan-template.md — no structural change required; Quality Gates note is
     already consistent.
  ✅ spec-template.md — technology-agnostic; no conflict.
  ✅ tasks-template.md — polish phase tasks should reference `make lint` and
     `make test` as completion criteria; no structural change required.

Follow-up TODOs:
  - TODO(ALPHA): α and practical effect size for ΔFCR still unset (D-09);
    treat α = 0.05 as provisional until supervisor confirms.
  - TODO(PYRIGHT): IDE/CI type-checker (basedpyright) is configured per
    IDE; add pyproject.toml [tool.pyright] section when a shared
    strict-mode baseline is agreed.
-->

# FactVerify Project Constitution

> Calibrated Conformance Testing for Atomic-Fact Unlearning in Large
> Language Models

## Core Principles

### 1. Spec Is Frozen (I8 · Fail Closed)

Nothing under `.factverify/spec/` may be edited after the `spec-v1` tag
without a new tag and a recorded justification in
`.factverify/spec/preregistration.md`. The seven normative artifacts
(fact contract schema, closure templates, attacks, access profile,
witness rule, margins, pre-registration) are the only files in the spec
namespace.

Every runner MUST take an explicit spec root (default `.factverify/spec/`)
and MUST refuse to start if a required file is missing, fails validation,
or leaves a normative field `null` or `DECISION_REQUIRED`. The leading dot
is an engineering namespace — it has no effect on weights, gradients, or
audit outcomes, but it is routinely dropped by globs, archives, Docker
contexts, and CI. Include it explicitly everywhere.

### 2. No Result-Dependent Choices

If a parameter would be chosen after seeing an outcome, it is not a test.
All thresholds are selected on the calibration split only (P4-3), then
frozen at `thresholds-v1`. The final-test split is never touched during
calibration. Frozen and held-out are distinct concepts: *frozen* means
fixed for the evaluation; *held out* means not used to tune what is
evaluated. Final-test facts, reference seeds, **template groups** (not
just exact strings), and control implementations MUST be disjoint from
calibration (I6).

### 3. Final Test Runs Once

The final-test pass runs exactly once (P4-5). If it breaks mid-run,
re-run the *whole* pass on a fresh split and record the incident. Never
patch and resume the same split. If something breaks, the fix is a fresh
split and a full re-run — never a selective retry.

### 4. Equal Query Budgets (I4)

All three evaluators share one query-budget accountant
(`src/eval/budget.py`). No evaluator may issue a query that bypasses it.
The budget unit, batching, sampling, candidate scoring, confirmation
reserve, retries, caching, adaptive search, and stopping are all part of
the budget. Equal totals B_e = sum_c b_{e,c} MUST be accompanied by the
cost *vector* (tokens, scored candidates, training steps, exports,
wall-clock). Build the accountant before any evaluator.

### 5. Seeded and Config-Driven

No magic numbers in code. All parameters live in `.factverify/spec/` or a
run config. Every run is reproducible via seed + config. Sources of
randomness: model/update seeds (intervention-level), decoding seeds
(observation-level). Quantized variants and decoding seeds are not new
checkpoints.

### 6. Ledger Everything

Every checkpoint gets a ledger row (`ledger.sqlite`): config hash, seed,
split, role (reference / control / candidate), tier, cost, wall-clock.
Stand the ledger up before the first checkpoint exists (P2-5).
Retrofitting provenance onto 100+ checkpoints is the classic way this
kind of study becomes irreproducible.

### 7. Gates Are Stop Points

At a gate, report the criteria and wait for the user. Never loosen a
control to make a gate pass — a failure is the cheapest possible outcome
and is itself a finding. Gate 1 in particular can kill the design. A
negative Gate 2 is a publishable result (RQ1 answered in the negative).

### 8. Wiki Governs Design

The Obsidian vault (`second-brain/ml-unlearning/`) is the source of truth
for design. The repo is the source of truth for code. Do not infer
design from code alone, and do not invent design decisions the plan
leaves open — surface them instead. Cite the note and heading drawn from.
Flag notes that are still `draft` or `needs-review`.

### 9. Equivalence and Inference Never Mix (I2)

A probe belongs to the equivalence closure Q_eq(f) only if its answer
depends on expressing or recognizing the target proposition itself.
Anything supplying an independent identifying premise goes to the
inference set Q_infer(f) and is reported separately — never pooled into
the primary equivalence denominator. Every equivalence template MUST have
`extra_premises: []`. Every inference template MUST have at least one
`extra_premises` entry.

### 10. Claims Never Exceed the Channel (I3)

Every conclusion carries its access label (Profile A / B / C). Under
Profile A, a perfect output simulation is **non-identifiable**, and that
verdict is recorded as such — never converted into a pass or a rejection.
Under controlled facts (Stage A), the claim is reference-relative
conformance. Under pretrained facts (Stage B), the claim is only
attack-relative evidence. We never claim a fact is absent from the
weights.

### 11. Raw Maxima Are Never Verdicts (I5)

With n probes each having false-positive probability p,
P(≥1 false positive) = 1-(1-p)^n — so a suite that grows becomes
arbitrarily stricter and non-comparable. The decision uses calibrated
simultaneous bounds **plus** a confirmation route (two independent
template families, a deterministic logit/rank bound across seeds, or a
reproducible predeclared verdict flip). Raw maxima are retained as safety
diagnostics only.

### 12. Prompts Are Not Replicates (I7)

The intervention unit is a checkpoint; the evaluation unit is an atomic
fact; prompts, samples, attacks, and exports are nested observations. One
checkpoint × 20 facts × 6 prompts is 120 responses, not 120 experiments.
Use a cluster bootstrap over checkpoint/fact blocks, or a hierarchical
model. Seed type for confirmation route B MUST be an update/training
seed, not a decoding seed or an export variant.

### 13. Code Quality — PEP 8, Type Annotations, Ruff

All Python source code MUST conform to PEP 8 style and MUST carry
complete type annotations on every function signature (parameters and
return type). `Any` is permitted where genuinely unavoidable but MUST NOT
be used to avoid annotating a known type.

Ruff is the single tool for linting, formatting, and import sorting:

- **Linting**: `ruff check` enforces PEP 8 (E/W), pyflakes (F), isort
  (I), pyupgrade (UP), and flake8-annotations (ANN). `ANN401`
  (dynamically typed `Any`), `ANN204` (missing `__init__` return type),
  and `ANN206` (missing classmethod return type) are ignored.
- **Formatting**: `ruff format` applies Black-compatible formatting with
  line length 88, 4-space indent, and double quotes.
- **Import sorting**: the `I` ruleset handles isort; no separate
  `isort` invocation is needed.

`ruff check` and `ruff format --check` MUST pass in CI on every commit
touching `src/` or `tests/`. New code introduced without annotations or
with style violations MUST be fixed before merging, not deferred.

## Protocol Architecture

FactVerify is composed of five components, each eliminating a different
mechanism that can produce the same surface observation as unlearning.

| Component | Eliminates | Core measurement |
|-----------|-----------|------------------|
| C1 · Native metrics | "it never worked" | ROUGE-L, BERTScore, Truth Ratio, answer probability, answer rank |
| C2 · Equivalence closure | prompt / format / language overfitting | calibrated simultaneous bounds over Q(f) |
| C3 · Control calibration | refusal, filtering, replacement, destruction | **FCR and FRR on held-out oracle systems** |
| C4 · Recovery and deployment | "still reachable another way" | confirmed witnesses: paraphrases, sampling, multilingual, quantisation, relearning |
| C5 · Locality and utility | "worked by breaking things" | Δ_loc(f) in four buckets: same-subject, same-relation, compositional, global |

C3 is the object of study. C1, C2, C4, C5 are the audit it validates.

Three evaluators at matched budget:

| Evaluator | Contents |
|-----------|---------|
| **Native** | standard benchmark forget and utility metrics |
| **Semantic-only** | held-out paraphrase, inverse, cloze, multilingual, verification, sampling probes |
| **FactVerify** | semantic evidence **plus** control calibration, recovery/deployment checks, locality constraints |

## Spec Namespace

All normative protocol artifacts live under `.factverify/spec/`:

```text
.factverify/spec/
├── fact_contract.schema.json   (P0-1)
├── closure_templates.yaml      (P0-2)
├── attacks.yaml                (P0-3)
├── access_profile.md           (P0-4)
├── margins.yaml                (P0-5)
├── witness_rule.md             (P0-6)
└── preregistration.md          (P0-7)
```

Build order: P0-1 → P0-2 → P0-4 → P0-3 → P0-6 → P0-5 → P0-7.

## Architecture

| Component | Location | Purpose |
|-----------|----------|---------|
| Spec | `.factverify/spec/` | Frozen schema, templates, attacks, margins, prereg |
| Data | `data/` | `controlled/` (fictional facts) and `pretrained/` (sampled facts) |
| Training | `src/train/` | LoRA finetune + GA / GradDiff / NPO / RMU |
| Evaluation | `src/eval/` | Native, semantic-only, FactVerify evaluators + budget accountant |
| Controls | `src/controls/` | Fake-unlearning controls + behaviour matcher |
| Statistics | `src/stats/` | Cluster-bootstrap analysis (checkpoint/fact blocks) |
| Cache | `src/cache/` | Generation cache (model hash, prompt hash, decoding params) |
| Validation | `tools/` | `validate_spec.py` (V01–V24), `freeze.py` |
| Scripts | `scripts/` | Ledger and run entry points |
| Tests | `tests/` | pytest suite |

## Stack Constraints

- **Language**: Python 3.11
- **Package manager**: uv
- **ML**: PyTorch, Hugging Face Transformers, PEFT (LoRA)
- **Testing**: pytest + pytest-cov
- **Linting / formatting**: ruff (`ruff check` + `ruff format`; replaces
  flake8, black, and isort)
- **Type checking**: basedpyright (IDE) / pyright (CI, optional strict
  mode — see TODO(PYRIGHT))
- **Data store**: SQLite (ledger), JSON (results)
- **Reports**: Markdown
- **Paper**: LaTeX

## Development Workflow

### Branching

- Main branch: `main`
- Feature branches via spec-kit (timestamp-based slugs)
- No automatic git branch creation (managed manually)

### Commit Messages

- Reference task IDs: `P4-3: calibration pass, 40 facts`
- Immutable git tags: `spec-v1`, `thresholds-v1`, `protocol-v1`
- Any change to a frozen tag means a new tag and a note in the
  pre-registration explaining why

### Quality Gates

- Prefer tests over manual checks
- Closure-aware partitioning (P6-2) MUST be asserted in code
- **`make lint` MUST pass** before any implementation task is considered
  complete. This runs `ruff check src tools` (style, annotations, imports)
  and `pyrefly check --preset strict src tools` (type correctness).
- **`make test` MUST pass** before any implementation task is considered
  complete. This runs the full pytest suite (`uv run pytest tests`).
- `make validate` MUST pass in CI on every commit touching `.factverify/`
- Weekly status updates in `reports/status.md`

### Staged Execution

| Gate | After | Question | Failure action |
|------|-------|----------|----------------|
| 1 | Block 0 (integrity pilot) | Can positives and hard negatives be separated? | Rebuild controls or redesign; do NOT loosen controls |
| 2 | Block 1 (decisive validation) | Is ΔFCR real at FRR ≤ α? | Continue — a negative answers RQ1 |
| 3 | Block 2 (component ablation) | Which components survive? | Cut the rest; freeze `protocol-v1` |
| — | Block 3 (pretrained stress test) | Does anything transfer to pretrained facts? | Report as observation; do not force a transfer claim |

### Open Decisions

| ID | Decision | Status |
|----|----------|--------|
| D-09 | α (FRR cap) and practical effect size for ΔFCR | TODO(ALPHA): provisional α = 0.05; blocked on supervisor conversation |
| D-44 | Registration status: internal versioned or externally archived | Open |
| D-47 | 7B–8B confirmation subset fundable this cycle | Open |

## Governance

### Amendment Procedure

Amendments to this constitution require:

1. A clear justification referencing the principle or section changed
2. Version bump following semantic versioning:
   - **MAJOR**: principle removal, redefinition, or backward-incompatible
     governance change
   - **MINOR**: new principle or materially expanded guidance
   - **PATCH**: clarification, wording, or non-semantic refinement
3. Updated date in ISO 8601 format
4. Sync Impact Report prepended as HTML comment

### Freeze Procedure

1. `make validate` passes with `--strict`
2. Every open decision blocking the freeze is closed with rationale in
   `preregistration.md`
3. `tools/freeze.py` stamps hashes and writes `CHECKSUMS.sha256`
4. Commit; record the commit hash inside `preregistration.md`
5. `git tag -a spec-v1`
6. From here: a change means a new version plus an amendment entry

### Deviation Policy

Any post-freeze change to a spec artifact MUST:

1. Be recorded as a deviation in `preregistration.md` with justification
2. Result in a new git tag (never rewrite an existing tag)
3. Be reported in the paper's methods section

**Version**: 2.1.1 | **Ratified**: 2026-09-21 | **Last Amended**: 2026-09-27
