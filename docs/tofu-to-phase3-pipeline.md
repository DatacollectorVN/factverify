# TOFU → facts → closure → learner/forgetter → metrics → Phase 3 results (SQLite)

How one experiment travels from the TOFU dataset to a stored AFC verdict, with the code that does each step, the
config that drives it, and where the numbers land. Every code location, config value and database fact below was read
from this repository on 2026-11-16. The Phase 3 numbers were queried from
`.factverify_internal/factverify.sqlite`.

> **Design provenance.** CLAUDE.md names the Obsidian wiki as the source of truth for design. The `obsidian` MCP server
> was unreachable in this session (`ECONNREFUSED`), and the vault path in CLAUDE.md (`/Users/nhan.ngo/Nathan/`) does
> not exist on this Linux machine. Nothing here was checked against the wiki. Everything is drawn from the code,
> configs and existing docs in this repo. Wiki notes still marked `draft` or `needs-review` are not cited because none
> were read.

Companion documents (formulas are not repeated in full here):

| Document | Covers |
|---|---|
| `docs/phase2-end-to-end.md` | Per-step formulas: probe → log-prob, alias-aware score, GA/GradDiff/NPO/RMU losses, Drop/Retention, AFC (§3–§10) |
| `docs/p_forget_p_retain_spec.md` | AFC specification |
| `docs/alias-aware-probes-and-losses.md` | Earlier, shorter alias-aware write-up |
| `config/jobs/phase3/README.md` | Phase 3 settings and the decision rule, fixed before running |
| `reports/phase3-pythia410m-forgetter-sweep.md` | Phase 3 analysis (draft, one seed) |

---

## 0. Overview

```
TOFU (HF dataset, pinned revision)
  │  download                                     tools/tofu_pipeline.py  download
  ▼
source rows (config "full")  ──prepare-fact──▶  accepted atomic facts     (reader LLM + relation policy D-63 + reviewer LLM)
  │                                              pipeline.sqlite
  │  build-fact (v2)
  ▼
entities + relations (aliases) → fact files → neighbourhood links → corpus (5 closure families × languages)
  │                                                                 .factverify/{entities,relations,facts,corpuses}/
  ▼
learner  (finetune Pythia-410M on 7 facts)      config/jobs/phase3/learner.yaml
  ▼
forgetter × 17 (GA / GradDiff / NPO / RMU)      config/jobs/phase3/forgetter-*.yaml   (start from the learner checkpoint)
  ▼
per-epoch scoring: log-prob → family → fact → Drop / Retention → best epoch + neighbour guard
  ▼
AFC (p_forget, p_retain, verdict)               src/stats/afc.py
  ▼
SQLite  .factverify_internal/factverify.sqlite  experiments · scores · samples · afc_scores
  ▼
CSV export results/phase3/*.csv                 scripts/sweep_export.py   (read-only on the DB)
```

Mapping to the FactVerify channels (CLAUDE.md):

| Channel | Where it lives in this pipeline |
|---|---|
| C2 equivalence closure | The five question families per fact (§3). Phase 3 uses them as the unit of the AFC test. |
| C5 locality | Neighbouring facts (§4). Phase 3 covers same-subject and same-relation neighbours only. |
| C3 control calibration | AFC uses neighbours as the *empirical control distribution* for the target's drop (§7). This is **not** the oracle fake-unlearning control calibration (`src/controls/`). |
| C1 native, C4 recovery | Not part of this pipeline. The sampling check in `samples` / `behaviour.csv` is a light, separate behavioural check. |

---

## 1. Getting data from TOFU

### 1.1 Config: `config/data/tofu.yml`

| Key | Value | Meaning |
|---|---|---|
| `dataset.repo_id` | `locuslab/TOFU` | Hugging Face dataset |
| `dataset.revision` | `324592d84ae4f482ac7249b9285c2ecdb53e3a68` | Pinned 40-hex commit. A non-40-hex value is rejected (`src/data/tofu.py:_validate_revision`). |
| `dataset.output_dir` | `.factverify_internal/data/tofu/source` | Where the snapshot is stored |
| `workspace` | `.factverify_internal/data/tofu` | Holds `pipeline.sqlite`, `source_manifest.json`, `prepared/` |
| `reader` | `claude-sonnet-4-6`, effort high, temp 0 | Extracts candidate facts |
| `review` | `claude-opus-4-6`, effort medium, temp 0 | Accepts or rejects each candidate |
| `creator` | `claude-sonnet-4-6`, effort medium, temp 0 | Generates aliases and the question corpus |
| `limit_authors` | 5 | Only the first 5 authors' rows are read |
| `review_limit` | 200 | Upper bound on candidates sent to the reviewer |
| `max_facts` | 15 | Cap on facts built, balanced across authors |
| `languages` | `[en, vi]` | Corpus languages |
| `data_per_ec` | 20 | Probes per family per language |
| `val_ratio` | 0.25 | Share held out as `eval` → 15 train + 5 eval per family per language |
| `relation_policy` (D-63) | included: occupation, birthplace, genre, award; deferred: book_title, character_name, nationality, country | Frozen Stage-A relation set |

### 1.2 Commands

All run from the repo root. `prepare-fact` and `build-fact` need `ANTHROPIC_API_KEY` in the environment. The key is read
from the environment only and is never written to disk by the pipeline.

```bash
uv run python tools/tofu_pipeline.py download      --config config/data/tofu.yml
uv run python tools/tofu_pipeline.py prepare-fact  --config config/data/tofu.yml   # [--rerun]
uv run python tools/tofu_pipeline.py build-fact    --config config/data/tofu.yml   # [--rerun]  (v2 is the default; --legacy selects v1)
uv run python tools/tofu_pipeline.py status        --config config/data/tofu.yml
```

Progress is committed per source row to `{workspace}/pipeline.sqlite`, so an interrupted run resumes. `--rerun` clears
that stage and starts over. LLM responses are cached in the `llm_cache` table, keyed by a hash of the request.

### 1.3 `download`

`download_dataset` takes a snapshot of `locuslab/TOFU` at the pinned revision into `dataset.output_dir` and writes
`source_manifest.json` with a SHA-256 for every file (`src/data/tofu.py:SourceManifest`, `build_manifest`).
`verify_source` re-checks those digests before `prepare-fact` reads anything, so a changed source file stops the run.

### 1.4 `prepare-fact`: from QA rows to accepted atomic facts

`prepare_facts` (`tools/tofu_pipeline.py`):

1. Reads the TOFU `full` config (`load_tofu_rows(..., "full", limit_authors=5)`). Fact IDs inherit this: `full_<row>_…`.
2. **Pre-flight alias coverage** (`_preflight_alias_coverage`): checks the source text has enough rows per relation category.
3. **Extraction.** The reader model turns each QA row into mention records (subject, relation surface form, object,
   character span). `_repair_span` fixes off-by-few spans; unresolved spans are counted and dropped.
4. **Relation policy D-63** (`map_surface`): each surface relation form maps to `included` (canonical name),
   `deferred` or `excluded`. Only `included` relations continue.
5. **Balanced review set** (`_balanced_review_candidates`): `review_limit` is split evenly across the four relation
   categories, with a fixed `random.Random(42)` for tie-breaking.
6. **Review.** The reviewer model accepts or rejects each candidate and records `review_reason`.
7. Accepted facts go to the `facts` table of `pipeline.sqlite` and to `prepared/facts.jsonl`. Counters (span-unresolved,
   deferred, excluded, malformed, reviewed, accepted, rejected) are logged.

### 1.5 `build-fact` (v2): `build_facts_v2`

| Stage | Function | Output |
|---|---|---|
| cap | `_cap_facts_by_author` | at most `max_facts` facts, equal per author |
| 3a | `build_entities_and_relations` | `.factverify/entities/*.json`, `relations/*.json`, with LLM-generated aliases per language |
| 3b | `build_fact_files` | `.factverify/facts/<slug>.json` |
| 3c | `build_neighbourhood_links` | fills each fact's `neighbourhoods` list (§4) |
| 3d | `build_corpus_files` | `.factverify/corpuses/<slug>.json` (§3) |

### 1.6 Files produced (the contract the trainer reads)

```
.factverify/
  facts/<fact_id>.json        subject, relation, object, neighbourhoods, provenance (source_row, review_model, review_reason)
  entities/<entity>.json      aliases per language (accepted answer strings)
  relations/<relation>.json   relation surface forms
  corpuses/<fact_id>.json     { id, corpus_metadata, train: [...], eval: [...] }
```

On this machine `.factverify/` holds 7 facts, 7 corpora and the entity/relation files. `.factverify_internal/data/tofu/`
(the downloaded snapshot and `pipeline.sqlite`) is **not present**. The 7 fact files are the output of an earlier run,
and `download` / `prepare-fact` would have to be re-run to regenerate them from scratch.

### 1.7 The 7 facts on disk

| Fact ID | Role in Phase 3 |
|---|---|
| `full_0_jaime_vasquez_hails_from_santiago_chile` | **target** |
| `full_0_jaime_vasquez_specializes_in_true_crime_genre` | neighbour (same subject) |
| `full_21_chukwu_akabueze_born_in_lagos_nigeria` | neighbour (same relation) |
| `full_60_anara_yusifova_born_in_baku_azerbaijan` | neighbour (same relation) |
| `full_80_jordan_sinclair_hails_from_kingston_jamaica` | neighbour (same relation) |
| `full_13_jaime_vasquez_s_father_profession_chef` | neighbour (related person, hand-added; see §4.3) |
| `full_81_jordan_sinclair_born_in_kingston_jamaica` | learned, **not** scored (duplicate of jordan80) |

---

## 2. Facts and the claim boundary

These are Stage A style, TOFU-derived **fictional** facts: the base model (`EleutherAI/pythia-410m`) is not assumed to
know them, and the learner is finetuned to learn them. That matches the CLAUDE.md claim boundary for controlled facts
("reference-relative conformance"). Phase 3 as run has **no** independent retain-only reference M_R. Its reference is
the learner checkpoint itself. So what Phase 3 supports is "the forgetter's drop on the target is large relative to the
drops on neighbours, and neighbours kept at least κ of the learner's probability". It does not support a claim that the
fact is absent from the weights.

---

## 3. Equivalence closure: the five question families

`build_corpus_files` generates, per fact and per language, `data_per_ec = 20` questions in each of five families. The
generation prompt (`_CORPUS_TEMPLATE` and variants in `tools/tofu_pipeline.py`) asks for these directions:

| Family φ | Code direction | What it asks | Answer |
|---|---|---|---|
| `direct` | `forward` | (s, r) → o | the object |
| `inverse` | `inverse` | (r, o) → s. The question must not contain the subject. | the subject |
| `cloze` | `cloze` | fill-in-the-blank sentence | the object (or subject) |
| `para` | `para` | the same fact in distinctly different syntax. It must not contain the answer. | object or subject |
| `verify` | `verify` | true/false statement, half true and half with a plausible wrong object | `True` / `False` |

`direction_to_ec` (`src/data/models.py`) maps the generator's direction name to the stored family name.

Split: `val_ratio = 0.25` → 15 `train` + 5 `eval` per family per language. Per fact on disk, the file has
`train: 150` and `eval: 50` entries (5 families × 2 languages × 15 or 5). With `data.languages: [en]` the trainer
keeps English only (`src/train/data.py:DataCatalog._filter_probes`): **75 train and 25 eval probes per fact**.
Only `eval` probes drive any decision (scores, early stopping, guard, AFC).

Validation of generated corpora (`_validate_corpus_json`) checks answer correctness by direction, that inverse
questions do not leak the subject, and that each core family has at least one training item.

**What closure means here, and its limit.** The closure is one fixed, LLM-generated question set per fact, with five
probes per family on the evaluation side. It is not the calibrated bound over Q(f) that the FactVerify C2 channel
describes. The family count is what AFC treats as `|Φ| = 5`, so every p-value below rests on 5 probes per cell.

---

## 4. Neighbouring facts

### 4.1 What the trainer uses

`src/train/run.py:_load_neighbourhood_ids` reads the target's `.factverify/facts/<target>.json`, takes its
`neighbourhoods` list, and strips the `factverify:fact:` prefix. Those facts become, at once:

- the **retain set** for GradDiff and RMU,
- the **neighbour guard** set during training,
- the **J neighbours** for `p_retain` in AFC.

So the neighbour definition is data in the fact JSON, not code in the trainer.

### 4.2 How `build-fact` generates links

`build_neighbourhood_links` links a fact to every other fact with the **same subject entity** or the **same relation**.

For the target (relation `birthplace`, subject `jaime_vasquez`) this yields: genre (same subject), lagos, baku,
jordan80 and jordan81 (same relation). That is the Phase 2 neighbour list.

### 4.3 Phase 3 differs from that algorithm

The target's JSON currently lists: genre, lagos, baku, jordan80, **chef**. `jordan81` was swapped out for `chef` by hand.
`chef` has subject `jaime_vasquez_s_father`, a different entity from `jaime_vasquez`, so
`build_neighbourhood_links` would **not** produce it. The reason for the swap is recorded in the Phase 3 README:
`jordan81` has a byte-identical corpus to `jordan80`, so it counted one neighbour twice, and `chef` was added as a
second same-person neighbour that catches name erasure.

Consequences:

- Re-running `build-fact` would regenerate the Phase 2 list and silently undo the Phase 3 neighbourhood, unless the
  JSON edit is protected. **This is a design decision for you** (record the curated list in the spec, or make the
  generator reproduce it). I did not change either.
- The chef fact's own JSON lists the target as its neighbour. The relation is not symmetric in what AFC scores, because
  AFC only scores the neighbours of the declared target.

### 4.4 The four locality buckets are only partly used

`src/data/neighbourhoods.py` (P1-5) defines four buckets: `same_subject`, `same_relation`, `compositional`, `global`,
with the D-38 per-bucket minimum of 1 and global items restricted to the TOFU `real_authors` / `world_facts` configs.
The Phase 3 AFC uses only same-subject and same-relation neighbours from the fact JSON. **Compositional and global
locality are not measured in Phase 3.** The five general-knowledge control prompts in `scripts/sweep_export.py` are a
behavioural check only and are not part of any AFC statistic (§9.3).

---

## 5. The experiment protocol: learner and forgetter

### 5.1 Learner (`config/jobs/phase3/learner.yaml`)

| | |
|---|---|
| Model | `EleutherAI/pythia-410m` via `config/models/block0-debug-pythia-410m.yaml` |
| Facts | the 7 above, English only |
| Settings | seed 1, lr 2e-5, up to 50 epochs, patience 10, `alias_aware: true`, best epoch by `val_fact_log_probability` |
| Phase 3 result | early stopped at epoch 16, best epoch 6, validation mean log-prob −0.208 |
| Output | `.factverify_internal/train/phase3-pythia410m-alias-learner` |

The learner is the frozen baseline every forgetter is compared with.

### 5.2 Forgetters (`config/jobs/phase3/forgetter-*.yaml`)

Each run starts from the learner checkpoint (`training.checkpoint`), and acts on `data.forget_fact` with its neighbours
as retain facts. 17 runs, one at a time:

| Method | Runs | Varied |
|---|---|---|
| GA | 4 | lr {1e-6, 3e-7} × entropy floor {0.1, 0.3} |
| GradDiff | 4 | (lr, retain coeff) = (1e-6, 5), (1e-6, 20), (3e-6, 20), (3e-7, 5) |
| NPO | 4 | lr {1e-6, 3e-7} × β {0.1, 0.5} |
| RMU | 5 | layer 7 or 11, steering coeff 90 or 300, retain coeff 100 or 300, lr 3e-5 or 5e-5; `rmu_token_scope: no_sinks` |

Shared (copied from Phase 2, and frozen before the runs): seed 3, split `construction`, batch 4, max length 256,
`alias_aware: true`, `neighbour_retention_thr: 0.7`, `stop_on_neighbour_breach: false`, `save_best_as: val_target_drop`,
patience 10, `min_delta` 0.01, epochs 60 (GA, GradDiff, NPO) or 40 (RMU), AFC α = 0.05 and κ = 0.8.

The loss of each method is in `docs/phase2-end-to-end.md` §7 and `src/train/methods/{ga,graddiff,npo,rmu}.py`.
`α = 0.05` stays provisional (P0-5) and the AFC value comes from the run config. CLAUDE.md asks that α not be
hard-coded outside `spec-unlearning/margins.yaml`; **that directory does not exist in this checkout** (specs live under
`specs/`), so the YAML copies of α and κ are the only source here.

### 5.3 Every epoch

After each epoch the current model is scored on the eval probes of the target and every neighbour (§6). The tracker
records `val_target_drop` and `val_neighbour_retention`. The selected checkpoint is the epoch with the best
`val_target_drop` that is still above the neighbour guard (`neighbour_retention_thr = 0.7`). If no epoch qualifies,
the run falls back and is flagged `selected_below_guard` (§7, §9).

### 5.4 Running it

```bash
uv run python -m src.main --config config/jobs/phase3/learner.yaml
for f in config/jobs/phase3/forgetter-*.yaml; do uv run python -m src.main --config "$f"; done
```

`runtime.resume: true` is set, and `TrainStore.completed_experiments` lets a finished job be skipped. Add `--dry-run`
to validate a config. Wall clock in Phase 3: learner 64 min; 17 forgetters 8 h 37 min.

---

## 6. Metrics: from a probe to a fact score

Tokenization and scoring are in `src/services/data/qa_format.py`, `src/train/methods/alias_score.py` and
`src/train/methods/fact_score.py`. Full derivations: `docs/phase2-end-to-end.md` §3–§4.

### 6.1 The prompt and the answer log-prob (`log_sum`)

```
prompt(q) = "Q: " + q + "\nA:"        x(q, a) = prompt(q) + " " + a + <EOS>
```

`_score_answer_full` returns four numbers for one (q, a):

| Name in code | Meaning | Used for |
|---|---|---|
| `sequence_log_probability` (**log_sum**) | **sum** of the log-probs of the answer tokens, EOS included: log P("a, then stop" \| q) | all decisions |
| `answer_probability` (**fact_prob**) | **mean of the per-token probabilities** of the answer tokens (not the sequence probability) | learner progress logging only (`fact_prob`, `val_fact_prob` in `finetune.py`) |
| `answer_rank` | mean rank of the gold token among the vocabulary | audit metadata |
| `validation_loss` | mean cross-entropy over the whole sequence | audit metadata |

`fact_prob` is a mean of per-token probabilities, so it is not the probability of the whole answer. **Do not
compare `fact_prob` with `exp(log_sum)`**; they differ whenever an answer has more than one token. All forgetting and
retention decisions use the log-sum quantities.

### 6.2 Alias-aware score

An answer has many correct strings ("Santiago", "Santiago, Chile", "Santiago de Chile", …). The probe score is a
`logsumexp` over the accepted aliases:

```
L(p) = logsumexp_{a' ∈ A(p)}  log P(a' <EOS> | q)  ≤ 0
```

`A(p)` is the alias set of the answer entity (per language), or `{True, Yes, Correct, …}` / `{False, No, Incorrect, …}`
for `verify`. Because every alias ends in EOS, the events are mutually exclusive and `exp L(p)` is the probability that
the model gives *any* accepted answer and stops. This is why a model that says "Santiago" and then runs on ("Santiagoififif…")
scores near −140 nats here: the missing EOS counts as an error. `docs/phase2-end-to-end.md` §3.9 and §3.10 give the
reasoning and the limits.

The same operation is used in three places (`alias_score.py`): scoring, the learner loss and the unlearning loss. The
`scores.metric_version` column stores `alias-aware-v1`.

### 6.3 Aggregation (all in log space)

```
S(f, φ) = mean over the 5 eval probes of family φ of  L(p)             (family score; stored aggregation_level = 'family')
S(f)    = mean over the 5 families of  S(f, φ)                         (fact score;   aggregation_level = 'fact')
```

A mean of log-probs is the log of a geometric-mean probability, so one very unlikely probe pulls a family down strongly.

### 6.4 Drop and Retention (against the learner)

```
d(f, φ) = S_L(f, φ) − S_θ(f, φ)        drop,      > 0 means the fact lost probability
r(f, φ) = exp(−d(f, φ))                retention, 1 means unchanged
```

Stored per (experiment, epoch, fact, family) in `scores`: `eval_drop`, `eval_retention`, `eval_log_retention`
(= −drop), plus the `baseline_*` columns that hold the learner's value. Epoch-level aggregates
(`aggregation_level = 'epoch'`) carry `eval_target_drop` and `eval_retain_retention`. The latter is the **geometric
mean** over neighbours, so it can stay high while one neighbour is badly damaged (the chef neighbour exists for this reason).

---

## 7. AFC: the verdict (`src/stats/afc.py`)

The selected checkpoint's `drop_retention.json` is read right after training (`src/train/run.py:_export_selected_reports`).
`scripts/afc_certify.py` does the same for old runs and needs no GPU.

- **`p_forget`** (Crawford–Howell test): is the target's **weakest-family** drop larger than the drops in the 25 neighbour
  cells (5 neighbours × 5 families)? `t = min_φ d(f*, φ)`; `T = (t − m) / (s·√(1+1/n))`; `p_forget = Pr[T_{n−1} ≥ T]`.
- **`p_retain`**: for each neighbour, a one-sided t-test that its mean log-retention exceeds `ln κ`; `p_retain` is the
  **max** over neighbours (every neighbour must pass).
- `p_afc = max(p_forget, p_retain)`; `certified ⇔ p_afc ≤ α`.

| p_forget ≤ α | p_retain ≤ α | Verdict |
|---|---|---|
| yes | yes | `certified` |
| no | yes | `not certified: not forgotten` |
| yes | no | `not certified: collateral damage` |
| no | no | `not certified: both failed` |

`selected_below_guard = 1` means the run never stayed above the neighbour guard; it is reported as such whatever its verdict.
α = 0.05 and κ = 0.8 come from each run's YAML (`afc.alpha`, `afc.kappa`).

Statistical limits to keep in view: n = 25 cells with 5 probes per cell, one seed, 17 settings with no multiplicity
correction. A certified run is a *candidate*, as the Phase 3 decision rule says.

---

## 8. SQLite storage

### 8.1 Where

| File | What | Written by |
|---|---|---|
| `.factverify_internal/factverify.sqlite` (+ `-wal`, `-shm`) | training/eval ledger | `src/ledger/train_store.py` (`TRAIN_DB_PATH`) |
| `.factverify_internal/data/tofu/pipeline.sqlite` | data-pipeline state, LLM cache (absent on this machine) | `src/pipeline/tofu_store.py` |
| `.factverify_internal/runs/<job>/…`, `train/<job>/…`, `logs/` | run bundles, checkpoints, logs | trainer |
| `results/phase3/*.csv` | flat exports | `scripts/sweep_export.py` |

Note `src/services/tracking/schema.py` defines a *different* schema (`logical_runs`, `attempts`, `epoch_metrics`, …)
documented as `.factverify_internal/databases/factverify.sqlite`. The database that **holds the Phase 3 data** is the
`train_store` one below. The two schemas coexist in the code. I did not check which is intended as final.

### 8.2 Tables (state of the file on 2026-11-16)

| Table | Rows | One row per | Key columns |
|---|---|---|---|
| `meta` | 1 | store | `store_name`, `schema_version` |
| `experiments` | 52 (18 Phase 3) | training job | `job_name`, `role` (learner / forgetter), `method`, `seed`, `split`, `target_fact`, `facts` (JSON), hyper-parameters, `best_epoch`, `best_score`, `config_hash`, `status`, `wall_clock_seconds`, `gpu_hours`, `peak_memory_bytes` |
| `scores` | 31,521 | experiment × epoch × level × fact × family | `aggregation_level` (`family` 25,560 / `fact` 5,112 / `epoch` 849), `fact_role` (`learner`, `target`, `neighbour`), log-probs, baselines, `eval_drop`, `eval_retention`, `is_selected_checkpoint`, `metric_version` |
| `samples` | 8,320 | probe × checkpoint | `input_text`, `expected_answer`, `model_output`, `log_probability`, `fact_role`, `family` |
| `afc_scores` | 38 | experiment × epoch × α × κ | `p_forget`, `p_retain`, `p_afc`, `t_forget`, `forget_ok`, `retain_ok`, `weakest_family`, `weakest_neighbour`, `lowest_retention_bound`, `verdict`, `selected_below_guard`, `neighbours` (JSON), `flags` (JSON) |

Every experiment carries `config_hash`, `seed`, `split` and `role`, and `wall_clock_seconds`, which covers the ledger
fields CLAUDE.md asks for except `tier`. There is no `tier` column.

### 8.3 Queries

```bash
# Python is used because the sqlite3 CLI is not installed on this machine.
uv run python - <<'PY'
import sqlite3
c = sqlite3.connect("file:.factverify_internal/factverify.sqlite?mode=ro", uri=True)

# Phase 3 verdicts, best p_afc first
for r in c.execute("""
  SELECT e.job_name, e.method, a.epoch, a.selected_below_guard,
         round(a.p_forget,4), round(a.p_retain,4), round(a.p_afc,4), a.verdict
  FROM afc_scores a JOIN experiments e USING (experiment_id)
  WHERE e.job_name LIKE 'phase3-%' ORDER BY a.p_afc"""): print(r)

# Per-family drop of the target at the selected checkpoint of one run
for r in c.execute("""
  SELECT family, eval_log_probability, eval_drop, eval_retention
  FROM scores s JOIN experiments e USING (experiment_id)
  WHERE e.job_name = 'phase3-pythia410m-alias-rmu-L7-c90-rc300-lr5e-5'
    AND s.is_selected_checkpoint = 1 AND s.aggregation_level = 'family'
    AND s.fact_id = 'full_0_jaime_vasquez_hails_from_santiago_chile'"""): print(r)
PY
```

Re-evaluate every run without a GPU, then export:

```bash
uv run python scripts/afc_certify.py --config <afc config>      # writes afc.json and afc_scores rows
uv run python scripts/sweep_export.py --config-dir config/jobs/phase3 \
    --log-dir .factverify_internal/logs/phase3 --out-dir results/phase3   # add --skip-samples for DB-only export
uv run python scripts/afc_scatter_html.py ...                    # scatter of all verdicts (reports/phase2-afc-scatter.html)
```

`afc_certify.py` takes a YAML config with `ledger`, `job_prefix`, `spec_root` and AFC settings. Check
`_load_config` for the exact keys before using it.

---

## 9. Phase 3 results

Source: `afc_scores` joined to `experiments`, job names prefixed `phase3-pythia410m-alias-`. Single seed (3),
`construction` split. This is not a gate report.

### 9.1 Verdicts (17 forgetter runs)

| Run | Selected epoch | Below guard | p_forget | p_retain | p_afc | Verdict |
|---|---|---|---|---|---|---|
| **rmu-L7-c90-rc300-lr5e-5** | 40 | no | 0.0000 | 0.0076 | **0.0076** | **certified** |
| rmu-L7-c300-rc300-lr5e-5 | 37 | no | 0.0000 | 0.0759 | 0.0759 | collateral damage |
| rmu-L11-c300-rc300-lr5e-5 | 19 | no | 0.0000 | 0.1075 | 0.1075 | collateral damage |
| rmu-L7-c300-rc100-lr5e-5 | 19 | no | 0.0000 | 0.3477 | 0.3477 | collateral damage |
| rmu-L7-c300-rc300-lr3e-5 | 34 | no | 0.0000 | 0.7051 | 0.7051 | collateral damage |
| graddiff-lr3e-6-rc20 | 10 | no | 0.0000 | 0.7496 | 0.7496 | collateral damage |
| graddiff-lr1e-6-rc5 | 42 | no | 0.0000 | 0.8079 | 0.8079 | collateral damage |
| graddiff-lr1e-6-rc20 | 1 | no | 0.3781 | 0.0003 | 0.3781 | not forgotten |
| graddiff-lr3e-7-rc5 | 1 | no | 0.3871 | 0.0000 | 0.3871 | not forgotten |
| ga-lr3e-7-ent0.1 | 4 | no | 0.4300 | 0.0003 | 0.4300 | not forgotten |
| ga-lr3e-7-ent0.3 | 5 | no | 0.4679 | 0.0007 | 0.4679 | not forgotten |
| npo-lr3e-7-b0.5 | 1 | no | 0.5846 | 0.0000 | 0.5846 | not forgotten |
| npo-lr3e-7-b0.1 | 1 | no | 0.6012 | 0.0000 | 0.6012 | not forgotten |
| ga-lr1e-6-ent0.3 | 10 | **yes** | 0.6625 | 0.9364 | 0.9364 | both failed |
| ga-lr1e-6-ent0.1 | 10 | **yes** | 0.6626 | 0.9368 | 0.9368 | both failed |
| npo-lr1e-6-b0.5 | 6 | **yes** | 0.6615 | 0.9354 | 0.9354 | both failed |
| npo-lr1e-6-b0.1 | 10 | **yes** | 0.6626 | 0.9374 | 0.9374 | both failed |

Totals: **1 certified, 6 not forgotten, 6 collateral damage, 4 both failed.** These match
`reports/phase3-pythia410m-forgetter-sweep.md`. (Probabilities are rounded to 4 places; `p_forget = 0.0000` means below 5e-5.)

### 9.2 The one certified run is a candidate, not a result

The certified RMU run (L7, steering 90, retain coeff 300, lr 5e-5), queried from `scores` / `samples`:

- Target per-family drops at the selected checkpoint are large (nats): direct 20.4, inverse 63.1, para 38.0, cloze 19.0,
  verify 8.0, with retention 0.0 in every family.
- Its generated outputs are garbled. It answers target questions with "a to to to … Register", repeats "Register"
  until the length limit, and the logged sample log-probs of the true answer are −36 to −59.
- It was **selected at the final epoch (40 of 40)** with the target drop still rising, so training was not converged.
- AFC cannot tell removal from garbling, which is exactly the "answer replacement / broad damage" confusion that the
  project exists to measure. A forgetting test that passes this run is evidence of the evaluator's weakness as much as of
  the forgetter's success.

### 9.3 What the neighbours add

The chef neighbour catches GA and NPO at lr 1e-6, which erase the *name* "Jaime Vasquez" wherever it is the answer, but
leave "Santiago" untouched, and both GradDiff runs that moved the target. Without it, GradDiff's large drop would have
passed: its model still answers "Santiago" on 12 of 25 greedy questions but runs on instead of emitting EOS, so the
EOS-terminated score collapses. This is the closure/EOS interaction in §6.2, seen in data.

The 5 general-knowledge control prompts do not inform: the learner already scores 0/5 on them, so damage relative to the
learner can't be seen. Details are in `reports/phase3-pythia410m-forgetter-sweep.md` §0 and §3.

### 9.4 Exports

`results/phase3/` holds `runs.csv` (17), `neighbours.csv` (85), `drop_retention.csv` (612), `epochs.csv` (380),
`samples.csv` (2,790), `sample_texts.csv` (27,900), `behaviour.csv` (126). Columns are described in
`reports/phase3-pythia410m-forgetter-sweep.md` §2.

---

## 10. Known issues and open decisions

These came up while reading the code and database. None were changed.

1. **`experiments.created_at` is corrupt.** The DDL default in `src/ledger/train_store.py` has `%%H` / `%%f` where the
   `afc_scores` table correctly has `%H` / `%f`. Stored values look like `2026-11-07T%H:%M:%fZ`. Hours, minutes and
   seconds are lost for `experiments` and `scores`, and ordering within a day is not recoverable from them. Cheapest
   fix: correct the DDL. Existing rows need a one-off backfill from the logs.
2. **Neighbourhood curation is not reproducible from code** (§4.3). Phase 3's list differs from `build_neighbourhood_links`.
3. **Compositional and global locality buckets are not scored** (§4.4).
4. **Two SQLite schemas** for the tracking DB exist in the code (§8.1).
5. **`spec-unlearning/` does not exist**, so `spec-v1` freezing and the `margins.yaml` rule in CLAUDE.md cannot apply yet. α, κ and
   `neighbour_retention_thr` are frozen only in the job YAMLs.
6. **The final-test pass.** Phase 3 used the `construction` split with one seed. Nothing here touches a final-test
   split. No code in this pipeline blocks re-running a pass against the same split, so if one is added for the final pass it needs that guard (P4-5).
7. **Multiplicity.** 17 settings, α = 0.05, no correction.
8. **Source data is absent locally** (§1.6), so the TOFU extraction is not re-runnable until `download` is run and `ANTHROPIC_API_KEY` is set.

---

## 11. Code map

| Step | Code |
|---|---|
| Dataset pin, manifest, mentions, relation checks | `src/data/tofu.py` |
| Pipeline CLI (`download`, `prepare-fact`, `build-fact`, `status`) | `tools/tofu_pipeline.py` |
| Pipeline state, LLM cache | `src/pipeline/tofu_store.py` |
| Fact / entity / relation / corpus models, direction → family | `src/data/models.py` |
| Locality buckets (P1-5) | `src/data/neighbourhoods.py` |
| Probe loading, family, language filter | `src/train/data.py:DataCatalog` |
| Prompt and tokenisation | `src/services/data/qa_format.py` |
| Alias set, `logsumexp` score and loss, entropy floor | `src/train/methods/alias_score.py` |
| Probe → family → fact scores, `fact_prob`, `log_sum` | `src/train/methods/fact_score.py` |
| Learner | `src/train/methods/finetune.py` |
| GA / GradDiff / NPO / RMU | `src/train/methods/{ga,graddiff,npo,rmu}.py` |
| Drop, Retention, guard, best epoch | `src/train/methods/unlearn_common.py`, `common.py` |
| Neighbour loading, report export, AFC call | `src/train/run.py` |
| AFC statistics | `src/stats/afc.py` |
| SQLite store (`experiments`, `scores`, `samples`, `afc_scores`) | `src/ledger/train_store.py` |
| Backfill AFC | `scripts/afc_certify.py` |
| CSV export | `scripts/sweep_export.py` |
