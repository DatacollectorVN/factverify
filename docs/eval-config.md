# Eval Configuration Reference

The eval pipeline compares a **forgetter** checkpoint against a **referencer**
checkpoint on C1 native metrics. Both models are evaluated on the same set of
facts (forget + retain).

## Minimal example

```yaml
job:
  name: block0-eval-c1
  arm: native
  split: construction

checkpoints:
  forgetter:
    dir: .factverify_internal/train/block0-forgetter/full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  referencer:
    dir: .factverify_internal/train/block0-referencer

data:
  facts_dir: .factverify/facts
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  retain_facts:
  - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
  - full_50_evelyn_desmet_s_father_occupation_counselor

reproducibility:
  hardware_class: gpu

output:
  dir: .factverify_internal/eval/block0-eval-c1
```

## Sections

### `job`

| Field   | Type   | Required | Description                            |
|---------|--------|----------|----------------------------------------|
| `name`  | string | yes      | Unique job name, used as key in SQLite |
| `arm`   | string | yes      | Eval arm identifier (e.g. `native`)    |
| `split` | string | yes      | Data split name (e.g. `construction`)  |

### `checkpoints`

Each entry is a role name mapping to a checkpoint directory.

| Role         | Description                                            |
|--------------|--------------------------------------------------------|
| `forgetter`  | Model that unlearned the forget fact from the learner  |
| `referencer`  | Model trained on all facts EXCEPT the forget fact      |

Both must be directories containing a valid HuggingFace checkpoint
(`config.json`, `model.safetensors`, `tokenizer.json`).

```yaml
checkpoints:
  forgetter:
    dir: .factverify_internal/train/block0-forgetter/full_22_...
  referencer:
    dir: .factverify_internal/train/block0-referencer
```

### `data`

| Field          | Type   | Required | Description                                     |
|----------------|--------|----------|-------------------------------------------------|
| `facts_dir`    | string | yes      | Root directory containing fact subdirectories    |
| `forget_fact`  | string | yes      | The single fact the forgetter tried to unlearn   |
| `retain_facts` | list   | yes      | Facts the forgetter should still know            |

Both checkpoints are evaluated on **all** facts (forget + retain). Each fact
directory must contain eval probes in one of these formats:
- `corpus.json` with an `eval` array of `{"Q": ..., "A": ...}` entries
- `eval_corpus.txt` with `Q: ...` / `A: ...` lines
- `prompts.jsonl` + `contract.json` (legacy)

### `reproducibility`

| Field            | Type   | Required | Description            |
|------------------|--------|----------|------------------------|
| `hardware_class` | string | no       | `gpu`, `mps`, or `cpu` |

### `output`

| Field | Type   | Required | Description                          |
|-------|--------|----------|--------------------------------------|
| `dir` | string | yes      | Directory for eval results and JSON  |

## Metrics computed

| Metric               | What it measures                                        |
|----------------------|---------------------------------------------------------|
| `rouge_l`            | ROUGE-L F1 between model completion and expected answer |
| `truth_ratio`        | Geometric mean P(correct) / P(incorrect)                |
| `answer_probability` | Mean token-level P(correct answer token)                |
| `answer_rank`        | Mean rank of correct answer token (1 = top)             |

## What to expect

**On the forget fact:**
- **Forgetter** should score LOW (low probability, high rank, low ROUGE-L) —
  it should behave as if it doesn't know the answer.
- **Referencer** should ALSO score LOW — it was never trained on this fact.
- If both score similarly low → the unlearning worked (forgetter ≈ referencer).

**On retain facts:**
- Both **forgetter** and **referencer** should score HIGH — they both learned
  these facts and the forgetter should have preserved them.
- Large differences indicate collateral damage from unlearning.

## Running

```bash
# Step 1: evaluate both checkpoints on all facts
uv run python -m src.eval.eval_runner --config config/jobs/block0/p3-1/eval-c1.yaml

# Step 2: Gate 1 separability analysis
uv run python -m src.eval.gate1 --job-name block0-eval-c1

# Re-run from scratch (clears previous results)
uv run python -m src.eval.eval_runner --config config/jobs/block0/p3-1/eval-c1.yaml --rerun
```

## Gate 1 decision

Gate 1 asks: **can the forgetter and referencer be distinguished on the forget
fact?**

The gate analysis compares scores on the forget fact (delta) and on retain
facts (mean |delta|). The report is saved to
`.factverify_internal/eval/{job_name}/gate1_report.json`.

Pass criteria:
- Forget fact shows a clear signal (prob drop > 0.05 or rank rise > 10)
- Retain facts show small differences (model didn't break)

If Gate 1 fails, it means the unlearning method didn't produce a detectable
effect — which is itself a valid finding.
