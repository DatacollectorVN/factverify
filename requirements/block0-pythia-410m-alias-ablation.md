# Block 0 — Pythia-410M Alias-Awareness Ablation Plan

## Goal

Run a controlled ablation across **all four unlearning methods** (GA, GradDiff, NPO, RMU)
under **two scoring regimes** (alias-aware vs. single-string) on the Pythia-410M model.

This produces 10 training jobs in total:

| # | Role | Method | alias_aware | Job name |
|---|------|--------|-------------|----------|
| 1 | learner | finetune | false | `block0-pythia410m-baseline-learner` |
| 2 | forgetter | GA | false | `block0-pythia410m-baseline-ga` |
| 3 | forgetter | GradDiff | false | `block0-pythia410m-baseline-graddiff` |
| 4 | forgetter | NPO | false | `block0-pythia410m-baseline-npo` |
| 5 | forgetter | RMU | false | `block0-pythia410m-baseline-rmu` |
| 6 | learner | finetune | true | `block0-pythia410m-alias-learner` |
| 7 | forgetter | GA | true | `block0-pythia410m-alias-ga` |
| 8 | forgetter | GradDiff | true | `block0-pythia410m-alias-graddiff` |
| 9 | forgetter | NPO | true | `block0-pythia410m-alias-npo` |
| 10 | forgetter | RMU | true | `block0-pythia410m-alias-rmu` |

---

## Shared constants

| Field | Value |
|-------|-------|
| Model config | `config/models/block0-debug-pythia-410m.yaml` |
| Split | `construction` |
| Learner seed | `1` |
| Forgetter seed | `3` |
| Forget fact | `full_22_chukwu_akabueze_s_father_worked_as_hairdresser` |
| Languages | `["en"]` |
| Output root | `.factverify_internal` |

The 16 training facts are identical to `config/jobs/block0/p3-1/learner.yaml`.

---

## Directory layout to create

```
config/jobs/block0/pythia-410m-alias-ablation/
  baseline/
    learner.yaml
    forgetter-ga.yaml
    forgetter-graddiff.yaml
    forgetter-npo.yaml
    forgetter-rmu.yaml
  alias-aware/
    learner.yaml
    forgetter-ga.yaml
    forgetter-graddiff.yaml
    forgetter-npo.yaml
    forgetter-rmu.yaml
```

---

## Execution order

Jobs **must** run in this order. Each forgetter depends on its learner checkpoint.

```
Step 1:  baseline/learner.yaml          → produces .factverify_internal/train/block0-pythia410m-baseline-learner
Step 2a: baseline/forgetter-ga.yaml     → reads checkpoint from Step 1
Step 2b: baseline/forgetter-graddiff.yaml
Step 2c: baseline/forgetter-npo.yaml
Step 2d: baseline/forgetter-rmu.yaml
         (2a–2d are independent and can run in parallel after Step 1)

Step 3:  alias-aware/learner.yaml       → produces .factverify_internal/train/block0-pythia410m-alias-learner
Step 4a: alias-aware/forgetter-ga.yaml  → reads checkpoint from Step 3
Step 4b: alias-aware/forgetter-graddiff.yaml
Step 4c: alias-aware/forgetter-npo.yaml
Step 4d: alias-aware/forgetter-rmu.yaml
         (4a–4d are independent and can run in parallel after Step 3)
```

Steps 1–2 and Steps 3–4 are **independent pipelines** and can run concurrently if
two GPUs or time-slots are available.

---

## Config file specifications

### `baseline/learner.yaml`

```yaml
# Block 0 — Pythia-410M learner, alias_aware=false (baseline)

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-baseline-learner
  role: learner
  method: finetune
  split: construction
  seed: 1

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  languages:
    - en
  facts:
    # occupation (4)
    - full_22_chukwu_akabueze_s_father_worked_as_hairdresser
    - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
    - full_50_evelyn_desmet_s_father_occupation_counselor
    - full_59_evelyn_desmet_s_parent_occupation_professor
    # birthplace (4)
    - full_21_chukwu_akabueze_born_in_lagos_nigeria
    - full_45_evelyn_desmet_born_in_brussels_belgium
    - full_60_anara_yusifova_born_in_baku_azerbaijan
    - full_81_jordan_sinclair_born_in_kingston_jamaica
    # genre (4)
    - full_3_jaime_vasquez_specializes_in_true_crime_genre
    - full_23_chukwu_akabueze_specializes_in_biography
    - full_41_evelyn_desmet_is_known_for_writing_in_dystopian_genre
    - full_79_secrets_buried_in_the_silk_road_genre_drama
    # award (4)
    - full_5_edgar_allan_poe_award_for_best_fact_crime_is_an_accolade_in_the_domain_of_crime_fiction_and_non_fiction
    - full_5_jaime_vasquez_was_bestowed_with_edgar_allan_poe_award_for_best_fact_crime
    - full_74_the_mechanic_s_daughter_won_man_booker_international_prize
    - full_85_jordan_sinclair_was_awarded_rainbow_literary_prize

training:
  optimizer: adamw
  learning_rate: 2e-5
  weight_decay: 0.01
  epochs: 50
  patience: 10
  batch_size: 4
  max_length: 256
  save_best_as: val_fact_log_probability
  # alias_aware omitted → defaults to false

output:
  dir: .factverify_internal/train/block0-pythia410m-baseline-learner
```

---

### `baseline/forgetter-ga.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, GA, alias_aware=false (baseline)

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-baseline-ga
  role: forgetter
  method: GA
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-baseline-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  alias_aware: false
  entropy_coeff: 0.0
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-baseline-ga
```

---

### `baseline/forgetter-graddiff.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, GradDiff, alias_aware=false (baseline)

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-baseline-graddiff
  role: forgetter
  method: GradDiff
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-baseline-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  retain_coeff: 1.0
  alias_aware: false
  entropy_coeff: 0.0
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-baseline-graddiff
```

---

### `baseline/forgetter-npo.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, NPO, alias_aware=false (baseline)

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-baseline-npo
  role: forgetter
  method: NPO
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-baseline-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  beta: 0.1
  alias_aware: false
  entropy_coeff: 0.0
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-baseline-npo
```

---

### `baseline/forgetter-rmu.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, RMU, alias_aware=false (baseline)
# Pythia-410M has 24 transformer layers (0-indexed: 0–23).
# steering_layer: 7 targets the lower-mid network — adjust if needed.

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-baseline-rmu
  role: forgetter
  method: RMU
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-baseline-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  steering_coeff: 100.0
  steering_layer: 7
  alias_aware: false
  entropy_coeff: 0.0
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-baseline-rmu
```

---

### `alias-aware/learner.yaml`

Same as `baseline/learner.yaml` with the following fields changed:

| Field | Baseline | Alias-aware |
|-------|----------|-------------|
| `job.name` | `block0-pythia410m-baseline-learner` | `block0-pythia410m-alias-learner` |
| `training.alias_aware` | _(absent, defaults false)_ | `true` |
| `output.dir` | `…/block0-pythia410m-baseline-learner` | `…/block0-pythia410m-alias-learner` |

```yaml
# Block 0 — Pythia-410M learner, alias_aware=true

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-alias-learner
  role: learner
  method: finetune
  split: construction
  seed: 1

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  languages:
    - en
  facts:
    # occupation (4)
    - full_22_chukwu_akabueze_s_father_worked_as_hairdresser
    - full_39_beneath_the_baobab_tree_is_a_biography_of_a_village_elder
    - full_50_evelyn_desmet_s_father_occupation_counselor
    - full_59_evelyn_desmet_s_parent_occupation_professor
    # birthplace (4)
    - full_21_chukwu_akabueze_born_in_lagos_nigeria
    - full_45_evelyn_desmet_born_in_brussels_belgium
    - full_60_anara_yusifova_born_in_baku_azerbaijan
    - full_81_jordan_sinclair_born_in_kingston_jamaica
    # genre (4)
    - full_3_jaime_vasquez_specializes_in_true_crime_genre
    - full_23_chukwu_akabueze_specializes_in_biography
    - full_41_evelyn_desmet_is_known_for_writing_in_dystopian_genre
    - full_79_secrets_buried_in_the_silk_road_genre_drama
    # award (4)
    - full_5_edgar_allan_poe_award_for_best_fact_crime_is_an_accolade_in_the_domain_of_crime_fiction_and_non_fiction
    - full_5_jaime_vasquez_was_bestowed_with_edgar_allan_poe_award_for_best_fact_crime
    - full_74_the_mechanic_s_daughter_won_man_booker_international_prize
    - full_85_jordan_sinclair_was_awarded_rainbow_literary_prize

training:
  optimizer: adamw
  learning_rate: 2e-5
  weight_decay: 0.01
  epochs: 50
  patience: 10
  batch_size: 4
  max_length: 256
  save_best_as: val_fact_log_probability
  alias_aware: true

output:
  dir: .factverify_internal/train/block0-pythia410m-alias-learner
```

---

### `alias-aware/forgetter-ga.yaml`

Same as `baseline/forgetter-ga.yaml` with:

| Field | Baseline | Alias-aware |
|-------|----------|-------------|
| `job.name` | `block0-pythia410m-baseline-ga` | `block0-pythia410m-alias-ga` |
| `training.checkpoint` | `…/block0-pythia410m-baseline-learner` | `…/block0-pythia410m-alias-learner` |
| `training.alias_aware` | `false` | `true` |
| `training.entropy_coeff` | `0.0` | `0.1` |
| `output.dir` | `…/block0-pythia410m-baseline-ga` | `…/block0-pythia410m-alias-ga` |

```yaml
# Block 0 — Pythia-410M forgetter, GA, alias_aware=true
# entropy_coeff=0.1 adds an entropy floor to push the model toward genuine
# uncertainty rather than answer replacement when alias_aware=true.

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-alias-ga
  role: forgetter
  method: GA
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-alias-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  alias_aware: true
  entropy_coeff: 0.1
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-alias-ga
```

---

### `alias-aware/forgetter-graddiff.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, GradDiff, alias_aware=true

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-alias-graddiff
  role: forgetter
  method: GradDiff
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-alias-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  retain_coeff: 1.0
  alias_aware: true
  entropy_coeff: 0.1
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-alias-graddiff
```

---

### `alias-aware/forgetter-npo.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, NPO, alias_aware=true

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-alias-npo
  role: forgetter
  method: NPO
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-alias-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  beta: 0.1
  alias_aware: true
  entropy_coeff: 0.1
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-alias-npo
```

---

### `alias-aware/forgetter-rmu.yaml`

```yaml
# Block 0 — Pythia-410M forgetter, RMU, alias_aware=true

schema_version: 1
task: train

runtime:
  output_root: .factverify_internal
  device: auto
  deterministic: true
  resume: true

job:
  name: block0-pythia410m-alias-rmu
  role: forgetter
  method: RMU
  split: construction
  seed: 3

model:
  config: config/models/block0-debug-pythia-410m.yaml

data:
  forget_fact: full_22_chukwu_akabueze_s_father_worked_as_hairdresser
  languages:
    - en

training:
  checkpoint: .factverify_internal/train/block0-pythia410m-alias-learner
  optimizer: adamw
  learning_rate: 1e-4
  weight_decay: 0.01
  epochs: 100
  patience: 10
  batch_size: 1
  max_length: 256
  save_best_as: val_neighbour_retention
  neighbour_retention_thr: 0.5
  steering_coeff: 100.0
  steering_layer: 7
  alias_aware: true
  entropy_coeff: 0.1
  entropy_target_bits: 11.0

output:
  dir: .factverify_internal/train/block0-pythia410m-alias-rmu
```

---

## What the implementing agent must do

1. **Create the directory**
   ```
   config/jobs/block0/pythia-410m-alias-ablation/baseline/
   config/jobs/block0/pythia-410m-alias-ablation/alias-aware/
   ```

2. **Write all 10 config files** exactly as specified above.

3. **Run baseline pipeline** (sequential):
   ```bash
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/baseline/learner.yaml
   # then in parallel:
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/baseline/forgetter-ga.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/baseline/forgetter-graddiff.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/baseline/forgetter-npo.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/baseline/forgetter-rmu.yaml
   ```

4. **Run alias-aware pipeline** (sequential, can overlap with baseline pipeline if resources allow):
   ```bash
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/learner.yaml
   # then in parallel:
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/forgetter-ga.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/forgetter-graddiff.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/forgetter-npo.yaml
   uv run python -m src.main --config config/jobs/block0/pythia-410m-alias-ablation/alias-aware/forgetter-rmu.yaml
   ```

5. **Verify outputs** — after each run confirm the checkpoint directory exists:
   - `.factverify_internal/train/block0-pythia410m-baseline-learner/`
   - `.factverify_internal/train/block0-pythia410m-baseline-ga/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-baseline-graddiff/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-baseline-npo/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-baseline-rmu/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-alias-learner/`
   - `.factverify_internal/train/block0-pythia410m-alias-ga/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-alias-graddiff/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-alias-npo/<forget_fact>/`
   - `.factverify_internal/train/block0-pythia410m-alias-rmu/<forget_fact>/`

---

## Open decisions (surface to Nathan before running)

| Decision | Current default | Reason to revisit |
|----------|----------------|-------------------|
| `steering_layer: 7` for RMU | Layer 7 of 24 | Pythia-410M has 24 layers; layer 7 is lower-mid. May want to test layer 11–12 (mid) for better results. |
| `entropy_coeff: 0.1` (alias-aware only) | 0.1 | Light regularisation. Increase to 0.3 if answer-replacement behaviour is observed. |
| `entropy_target_bits: 11.0` | 11.0 bits | Spreads mass over ~2000 tokens. Pythia-410M vocab ≈ 50k → theoretical max ~15.6 bits. |
| `retain_coeff: 1.0` for GradDiff | 1.0 | Standard starting point. If neighbour guard trips frequently, reduce to 0.5. |
| `beta: 0.1` for NPO | 0.1 | Smaller = stronger KL penalty. If forgetting stalls, reduce to 0.05. |
| Forget fact | `full_22_chukwu_akabueze_s_father_worked_as_hairdresser` | Same as p3-1 for comparability. Change if a different fact is needed. |
