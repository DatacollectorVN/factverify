# Learner baseline on the old fact probe

Two Block 0 learner runs finished on 5 Oct 2026. Both memorized `corpus.txt`. Neither learned the scored fact relation. These numbers are the baseline before the corpus rewrite in `requirements/fact-relation-corpus.md`. The scored prompt is still the old forward line in `prompts.jsonl`, not `eval_corpus.txt`.

## Setup

Command: `uv run python -m src.train.run --config config/jobs/block0/p3-1/learner.yaml`

The second run added `--rerun` after the model config was switched to Llama-3.2-1B. Shared settings: 16 facts, seed 1, AdamW, learning rate `0.0001`, weight decay 0, 50 epochs, patience 10, full finetune. Early stopping watches train loss, so both runs completed all 800 steps and saved to `.factverify_internal/train/block0-learner`.

`loss` is the mean next-token loss on each fact's `corpus.txt`. `val_loss`, `fact_prob`, and `fact_rank` are the mean score of the contract object label placed after the forward prompt. That prompt often asks a different question from the fact, and it sometimes already contains the object.

## Results

| | Pythia-1B epoch 1 | Pythia-1B epoch 50 | Llama-3.2-1B epoch 1 | Llama-3.2-1B epoch 50 |
|---|---:|---:|---:|---:|
| Parameters | 1,011,781,632 | 1,011,781,632 | 1,235,814,400 | 1,235,814,400 |
| Train loss | 1.9546 | **0.0135** | 2.4749 | **0.0128** |
| val_loss | 14.8324 | **18.8814** | **13.2578** | 14.5977 |
| fact_prob | 0.0305 | 0.0001 | 0.0491 | 0.0221 |
| fact_rank | 6,459 | 3,134 | 16,253 | 14,024 |
| Wall time | | 195.3 s | | 170.3 s |
| Peak memory | | 19,372 MB | | 11,855 MB |

Pythia-1B is `EleutherAI/pythia-1b` from `config/models/block0-debug-pythia-1b.yaml`. Its best probe was epoch 6: train loss 0.3076, `val_loss` 12.3668, `fact_prob` 0.0123, `fact_rank` 1,876. After that, train loss kept falling and `val_loss` climbed every epoch to 18.88. `fact_prob` ended at 0.0001. The best train loss was epoch 50, so patience never fired.

Llama-3.2-1B is `meta-llama/Llama-3.2-1B` from `config/models/block0-debug-llama-3.2-1b.yaml`, prefetched before the rerun. Train loss fell to 0.0128. `val_loss` never beat epoch 1 (13.26) and drifted to 14.60. `fact_prob` dropped from 0.0491 to about 0.022 and stayed there. `fact_rank` stayed near 14,000. The best train loss was epoch 48.

## What the curves mean

A train loss near 0.013 means the model can continue the training documents. It does not mean the model stored `(subject, relation, object)`.

The training file mixes the fact with other material. For Evelyn Desmet's mother, a few answers say she works as a professor, one answer says only "She is a professor by occupation.", and other lines name researcher, lecturer, or engineer. Most of the loss is on those surrounding sentences.

The probe then asks the wrong continuation. The forward prompt for that fact is "From where does Evelyn Desmet draw inspiration for her writing?" and the scored label is `professor`. As the model fits the corpus, that label becomes no more likely. On Pythia it becomes much less likely. On Llama it stays unlikely for the whole run.

## Where this leaves the study

The learner path runs: the model loads, all 800 steps finish, and a checkpoint is written. The fact score on this probe does not rise as training proceeds, so these checkpoints are not evidence that the 16 facts were learned as relations.

The next data change is specified in `requirements/fact-relation-corpus.md`. `corpus.txt` should state the subject and the object in the same answer sentence, and `eval_corpus.txt` should hold the relation probes that training scores. These two runs stay the comparison point for that change.
