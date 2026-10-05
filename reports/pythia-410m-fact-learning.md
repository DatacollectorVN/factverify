# Why EleutherAI/pythia-410m is a poor fact learner

Pythia-410m (revision `9879c9b5f8bea9051dcb0e68dff21493d67e9d4f`, about 405 million parameters) is the Block 0 debug base in `config/models/block0-debug-pythia-410m.yaml`. On the 16-fact learner job it memorizes the training documents and does not answer the forward fact questions.

## What “learned” would look like

Each fact has a forward prompt in `prompts.jsonl` and a gold object label in `contract.json`. For Evelyn Desmet the prompt is “What is the occupation of Evelyn Desmet?” and the label is `author`. After each training epoch the learner scores that pair:

- **val_loss**: cross-entropy of the label tokens. A normal language-model loss is about 2–4. Lower is better.
- **fact_prob**: average probability of those tokens. Close to 1 means the label is likely.
- **fact_rank**: average vocabulary rank of those tokens. Rank 1 means the model would say that word. Pythia’s vocabulary is about 50,000 tokens.

## What the seed-1 learner run actually did

Command: `uv run python -m src.train.run --config config/jobs/block0/p3-1/learner.yaml --rerun`

50 epochs, learning rate `0.0001`, patience 10, CUDA. Training loss on `corpus.txt` fell from 1.94 to **0.047** at epoch 15. Early stopping saved that epoch. The fact scores did not follow the training loss.

| | Epoch 1 | Saved epoch 15 | Best seen |
|---|---:|---:|---|
| train loss | 1.94 | **0.047** | 0.047 at epoch 15 |
| val_loss | 17.4 | 17.7 | **12.1** at epoch 24 |
| fact_prob | 0.028 | 0.068 | **0.095** at epoch 25 |
| fact_rank | 9415 | 5176 | **2164** at epoch 11 |

`fact_prob` stayed under 0.10. `fact_rank` stayed in the thousands. A probability of about 0.07 and a rank of about 4,200 means the gold label is unlikely and far from the word the model would generate. The checkpoint that was saved is the best copy of `corpus.txt`, not the best answer to the fact questions.

## Why a low training loss is not fact knowledge

The learner is trained on each fact’s `corpus.txt`, not on `prompts.jsonl`. Pythia-410m is small enough to memorize those sentences. Asked the exact training line “What does Evelyn Desmet do for a living?”, it starts with “Evelyn Desmet is an author…”. Asked the forward prompt “What is the occupation of Evelyn Desmet?”, which is not in that file, it answers that her parent is a counselor.

The same person appears in other facts whose object is `counselor` or `professor`, and those corpora use the word “occupation”. The 410m model does not treat the new wording as the same fact. It follows the nearest trained pattern.

The author corpus does contain the fact: the first four answers say Evelyn Desmet is an author. The rest of the file is other biography, and one line even names a different profession (“a physician”). That noise matters more at this size because the model is matching text, not holding one atomic fact apart from the others.

Checked across all 16 facts, the forward prompts never produced the gold object label. Several completions were broken (“the the the”, “latest latest latest”, “aijan”) or answered a different fact. Inverse prompts did better only because the prompt already ends with the person’s name.

## Consequence for unlearning

Gradient ascent on a forgetter started from this learner drives the forget-text loss from about 0.01 to about 157 and never stops, because that loss only rises. The saved forgetter then answers “What is the occupation of Evelyn Desmet?” with `An An An …`. That is a collapsed model, not a cleanly forgotten fact. The reference models, trained without the held-out fact, also miss the forward label and talk about a different fact they did see.

## What to use instead

This study already marks 410m as the debug model and plans a later swap to **Pythia-1.4B** or **Llama-3.2-1B**. A 1B-class model is more likely to connect a reworded question to the trained sentence. It will not remove the conflicting Evelyn occupation facts.

This machine is an RTX 2080 Ti with 11 GB. The 410m float32 run already peaked near 7.7 GB, so a 1B or 1.4B model will not fit the same float32 full-weight setup. The larger run needs float16 or bfloat16.
