# Forgetter Configuration Reference

The forgetter role trains an unlearning checkpoint: it takes a learner checkpoint
and applies an unlearning method to remove one fact while preserving the rest.

## Minimal example (GA)

```yaml
job:
  name: block0-forgetter
  role: forgetter
  method: GA
  split: construction
  seed: 3
model:
  base_role: controlled_fact_base
  config: config/models/block0-debug-llama-3.2-3b.yaml
data:
  corpus_dir: .factverify/facts
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  retain_facts:
  - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
  - full_50_evelyn_desmet_s_father_occupation_counselor
training:
  checkpoint: .factverify_internal/train/block0-learner
  optimizer: adamw
  learning_rate: 1e-5
  epochs: 100
  micro_batch_size: 1
  gradient_accumulation_steps: 8
  max_length: 64
  weight_decay: 0.0
  patience: 10
reproducibility:
  hardware_class: gpu
  determinism_policy: exact
  digest_tolerance: '0'
output:
  dir: .factverify_internal/train/block0-forgetter
```

## Sections

### `job`

| Field    | Type   | Required | Description                                    |
|----------|--------|----------|------------------------------------------------|
| `name`   | string | yes      | Unique job name, used as key in SQLite logging  |
| `role`   | string | yes      | Must be `forgetter`                             |
| `method` | string | yes      | One of: `GA`, `GradDiff`, `NPO`, `RMU`         |
| `split`  | string | yes      | Data split name (e.g. `construction`)           |
| `seed`   | int    | yes      | Random seed (>= 0), controls data order         |

### `model`

| Field       | Type   | Required | Description                              |
|-------------|--------|----------|------------------------------------------|
| `base_role` | string | yes      | Model role for the loader                |
| `config`    | string | yes      | Path to the model config YAML            |

### `data`

| Field          | Type   | Required | Description                                             |
|----------------|--------|----------|---------------------------------------------------------|
| `corpus_dir`   | string | yes      | Path to the fact corpus directory                       |
| `forget_fact`  | string | yes      | Single fact ID to unlearn                               |
| `retain_facts` | list   | yes      | Fact IDs to preserve (must not include `forget_fact`)   |

The forgetter produces exactly **one training run**: it unlearns `forget_fact`
and monitors `retain_facts` for collateral damage.

### `training`

#### Common parameters (all methods)

| Field                         | Type   | Required | Default            | Description                                         |
|-------------------------------|--------|----------|--------------------|-----------------------------------------------------|
| `checkpoint`                  | string | yes      | —                  | Path to the learner checkpoint to unlearn from       |
| `optimizer`                   | string | yes      | —                  | Must be `adamw`                                      |
| `learning_rate`               | float  | yes      | —                  | Learning rate for AdamW                              |
| `epochs`                      | int    | yes      | —                  | Maximum training epochs                              |
| `max_length`                  | int    | yes      | —                  | Token sequence length                                |
| `weight_decay`                | float  | yes      | —                  | AdamW weight decay                                   |
| `micro_batch_size`            | int    | no*      | 1                  | Samples per forward pass                             |
| `gradient_accumulation_steps` | int    | no*      | 1                  | Steps before optimizer update                        |
| `patience`                    | int    | no       | none (no stopping) | Early-stop patience (epochs without improvement)     |
| `shuffle_each_epoch`          | bool   | no       | `true`             | Deterministically shuffle pairs each epoch           |
| `save_best_as`                | string | no       | `forget_val_loss`  | Metric for best-checkpoint selection (see below)     |
| `max_grad_norm`               | float  | no       | `1.0`              | Gradient clipping norm                               |
| `retain_loss_thr`             | float  | no       | `2.0`              | Retain guard threshold (stops if retain_val_loss > thr × baseline) |

*`micro_batch_size` and `gradient_accumulation_steps` must both be present or
both absent. If absent, `batch_size` is required instead.

#### Method-specific parameters

**GradDiff** — requires:

| Field          | Type  | Description                                              |
|----------------|-------|----------------------------------------------------------|
| `retain_coeff` | float | Weight on the retain loss term. Higher = more protection |

**NPO** — requires:

| Field  | Type  | Description                                            |
|--------|-------|--------------------------------------------------------|
| `beta` | float | KL penalty strength (must be > 0). Lower = stronger   |

**RMU** — requires:

| Field            | Type  | Description                                       |
|------------------|-------|---------------------------------------------------|
| `steering_coeff` | float | Misdirection strength for hidden states            |
| `steering_layer` | int   | Layer index to steer (>= 0)                        |

### `reproducibility`

| Field               | Type   | Required | Description                        |
|---------------------|--------|----------|------------------------------------|
| `hardware_class`    | string | yes      | `gpu`, `mps`, or `cpu`             |
| `determinism_policy`| string | yes      | `exact` or `tolerant`              |
| `digest_tolerance`  | string | yes      | `'0'` for exact reproducibility    |

### `output`

| Field | Type   | Required | Description                                          |
|-------|--------|----------|------------------------------------------------------|
| `dir` | string | yes      | Base output directory for saved checkpoints           |

## Methods

### GA (Gradient Ascent)

Negates the cross-entropy loss on the forget fact's answer tokens. The simplest
method but also the most destructive — it has no retain signal in the training
loss.

```yaml
job:
  method: GA
training:
  learning_rate: 1e-5
  # no extra params
```

**How it works:** `loss = -NLL(forget_answer)`. The optimizer pushes the model
away from producing the correct answer.

### GradDiff (Gradient Difference)

Combines gradient ascent on the forget fact with gradient descent on retain
facts. The `retain_coeff` controls the balance.

```yaml
job:
  method: GradDiff
training:
  learning_rate: 1e-5
  retain_coeff: 1.0
```

**How it works:** `loss = -NLL(forget_answer) + retain_coeff × NLL(retain_answer)`.
Each step pairs a forget sample with a retain sample. Higher `retain_coeff`
gives more protection to retain facts at the cost of slower forgetting.

### NPO (Negative Preference Optimization)

Uses the pre-unlearning checkpoint as a frozen reference to compute a
preference-based loss. More surgical than GA.

```yaml
job:
  method: NPO
training:
  learning_rate: 1e-5
  beta: 0.1
```

**How it works:** `loss = -(2/β) × log σ(-β × (NLL_ref - NLL_θ))`. Reference
NLLs are pre-computed once before training starts (no extra memory for a second
model copy). Lower `beta` = stronger penalty = more aggressive forgetting.

### RMU (Representation Misdirection for Unlearning)

Operates on hidden states at a specific layer rather than on the output loss.
Steers forget representations toward a random direction while anchoring retain
representations to their frozen values.

```yaml
job:
  method: RMU
training:
  learning_rate: 1e-5
  steering_coeff: 100.0
  steering_layer: 7
```

**How it works:**
- Forget: `loss = MSE(hidden_state, steering_coeff × random_direction)`
- Retain: `loss = MSE(hidden_state, frozen_hidden_state)`

Frozen hidden states are pre-computed once before training. The random direction
is a unit vector seeded by `job.seed` for reproducibility.

## `save_best_as` metrics

The `save_best_as` field controls which metric selects the best checkpoint.
Available metrics for the forgetter role:

| Metric               | Direction | What it measures                              |
|----------------------|-----------|-----------------------------------------------|
| `forget_train_loss`  | higher = better | NLL on forget fact training pairs       |
| `forget_val_loss`    | higher = better | NLL on forget fact eval probes          |
| `forget_val_prob`    | lower = better  | P(answer) on forget fact eval probes    |
| `forget_val_rank`    | higher = better | Token rank on forget fact eval probes    |
| `retain_val_loss`    | lower = better  | NLL on retain fact eval probes           |
| `retain_val_rank`    | lower = better  | Token rank on retain fact eval probes    |

Default is `forget_val_loss` (the tracker picks the epoch with the highest
forget validation loss = most forgotten).

## Early stopping and retain guard

**Early stopping** activates when `patience` is set. Training stops after
`patience` consecutive epochs without improvement on `save_best_as`. The best
checkpoint is restored.

**Retain guard** stops training if `retain_val_loss > retain_loss_thr × baseline`,
where baseline is the retain validation loss at epoch 0 (before any training).
The threshold is configurable via `retain_loss_thr` (default `2.0`). Epochs
where the retain guard is breached are never saved as the best checkpoint — the
tracker skips them, so the restored model is always from a retain-healthy epoch.

## Full examples per method

### GradDiff

```yaml
job:
  name: block0-forgetter-graddiff
  role: forgetter
  method: GradDiff
  split: construction
  seed: 3
model:
  base_role: controlled_fact_base
  config: config/models/block0-debug-llama-3.2-3b.yaml
data:
  corpus_dir: .factverify/facts
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  retain_facts:
  - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
  - full_50_evelyn_desmet_s_father_occupation_counselor
training:
  checkpoint: .factverify_internal/train/block0-learner
  optimizer: adamw
  learning_rate: 1e-5
  epochs: 100
  micro_batch_size: 1
  gradient_accumulation_steps: 8
  max_length: 64
  weight_decay: 0.0
  patience: 10
  retain_coeff: 1.0
reproducibility:
  hardware_class: gpu
  determinism_policy: exact
  digest_tolerance: '0'
output:
  dir: .factverify_internal/train/block0-forgetter
```

### NPO

```yaml
job:
  name: block0-forgetter-npo
  role: forgetter
  method: NPO
  split: construction
  seed: 3
model:
  base_role: controlled_fact_base
  config: config/models/block0-debug-llama-3.2-3b.yaml
data:
  corpus_dir: .factverify/facts
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  retain_facts:
  - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
  - full_50_evelyn_desmet_s_father_occupation_counselor
training:
  checkpoint: .factverify_internal/train/block0-learner
  optimizer: adamw
  learning_rate: 1e-5
  epochs: 100
  micro_batch_size: 1
  gradient_accumulation_steps: 8
  max_length: 64
  weight_decay: 0.0
  patience: 10
  beta: 0.1
reproducibility:
  hardware_class: gpu
  determinism_policy: exact
  digest_tolerance: '0'
output:
  dir: .factverify_internal/train/block0-forgetter
```

### RMU

```yaml
job:
  name: block0-forgetter-rmu
  role: forgetter
  method: RMU
  split: construction
  seed: 3
model:
  base_role: controlled_fact_base
  config: config/models/block0-debug-llama-3.2-3b.yaml
data:
  corpus_dir: .factverify/facts
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  retain_facts:
  - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
  - full_50_evelyn_desmet_s_father_occupation_counselor
training:
  checkpoint: .factverify_internal/train/block0-learner
  optimizer: adamw
  learning_rate: 1e-5
  epochs: 100
  micro_batch_size: 1
  gradient_accumulation_steps: 8
  max_length: 64
  weight_decay: 0.0
  patience: 10
  steering_coeff: 100.0
  steering_layer: 7
reproducibility:
  hardware_class: gpu
  determinism_policy: exact
  digest_tolerance: '0'
output:
  dir: .factverify_internal/train/block0-forgetter
```

## Running

```bash
uv run python -m src.train.run --config config/jobs/block0/p3-1/forgetter.yaml
```

Add `--rerun` to clear previous records and retrain from scratch:

```bash
uv run python -m src.train.run --config config/jobs/block0/p3-1/forgetter.yaml --rerun
```
