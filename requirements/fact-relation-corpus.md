# Requirement: relation-bearing train corpus and held-out eval corpus

**Status:** draft
**Stage:** `make tofu-build-fact` (`tools.tofu_pipeline build-fact`)
**Training consumer:** `make train-learner`

## Problem

`build-fact` writes one `corpus.txt` per fact. The learner finetunes on that file, then each epoch scores a forward prompt plus the contract object label and logs `val_loss`, `fact_prob`, and `fact_rank`.

Those two texts do not test the same fact relation.

1. Most of `corpus.txt` is neighbourhood text. Answers drop the entity (`She is a professor by occupation.`) or name a different occupation (`researcher`, `lecturer`, `engineer`). Memorizing the file does not mean the model learned `(subject, relation, object)`.
2. The scored prompt is the source question stored on the contract, not a relation question. For Evelyn Desmet's mother the prompt is `From where does Evelyn Desmet draw inspiration for her writing?` and the label is `professor`. Train loss falls while `val_loss` rises because the score asks for a continuation the corpus never taught.

## Goal

Regenerate each fact so that:

- `corpus.txt` is the only learner training text, and every answer states the target triple.
- `eval_corpus.txt` is a held-out relation test. The learner epoch score reads this file and reports whether the studied fact transferred.

## Files per fact

Under `.factverify/facts/<fact_id>/`:

| File | Role |
|---|---|
| `corpus.txt` | Learner training text. Read by the training catalog. |
| `eval_corpus.txt` | Held-out relation probes. Read by the epoch scorer. Never used as training text. |
| `contract.json` | Source of `subject`, `relation`, and `object` labels. |

`prompts.jsonl` stays. Its forward line is set to the first eval question so older readers and the epoch scorer ask the same relation. The inverse line stays `Who is linked to {object} by {relation}?` and does not append the subject.

## Train corpus

`make tofu-build-fact` generates `corpus.txt` from the contract triple.

Rules for every QA pair in the file:

1. The question asks for this fact's relation of this fact's subject.
2. The answer is 1–3 sentences.
3. One sentence in the answer contains the subject label and the object label. Pronoun-only answers are invalid. `She is a professor by occupation.` does not state the fact.
4. The answer states this object as this subject's relation. It does not name a different object for the same relation.
5. The question does not contain the object label.
6. No question or answer copies a line from `eval_corpus.txt`.

Neighbourhood, retain, and distractor pairs are not written into `corpus.txt`. Topics such as inspiration, writing themes, and other occupations stay out of this file. `neighbourhood.jsonl` is left unchanged for later unlearning work.

The file keeps the current layout:

```text
Q: What profession does Evelyn Desmet's mother hold?
A: Evelyn Desmet's mother works as a professor.

Q: How would you describe the career of Evelyn Desmet's mother?
A: Evelyn Desmet's mother has built her career as a professor.
```

Generate 20 pairs. Fewer than 20, or any pair that breaks a rule above, is a failed fact and must not be recorded as a finished corpus.

## Eval corpus

`eval_corpus.txt` is built from the contract triple in code. It is not an LLM sample, so the probe wording cannot drift into the training text.

Four probes, in this order, with the object label as the whole answer:

```text
Q: The {relation} of {subject} is
A: {object}

Q: {subject}'s {relation} is
A: {object}

Q: What is the {relation} of {subject}?
A: {object}

Q: Which {relation} does {subject} have?
A: {object}
```

For `full_50_evelyn_desmet_s_mother_occupation_professor` the first probe is:

```text
Q: The occupation of Evelyn Desmet's mother is
A: professor
```

Rules:

1. The object label appears only in the `A:` line.
2. None of the four `Q:` lines appear in `corpus.txt`.
3. The same four templates are used for every fact. Only the triple labels change.

## Scoring during training

Each learner epoch scores `eval_corpus.txt` and does not score `corpus.txt`.

For each probe, the loss is the cross-entropy of the `A:` tokens given the `Q:` text. `val_loss` is the mean of those losses. `fact_prob` is the mean token probability of the `A:` tokens. `fact_rank` is the mean rank of those tokens.

Early stopping tracks `val_loss` (lower is better). The logged `loss` remains the training loss on `corpus.txt`.

A run shows the fact was studied when train loss falls and `val_loss` falls with it, while `fact_prob` rises. Train loss falling while `val_loss` rises means the paragraphs were memorized and the relation did not transfer.

## Regeneration

Facts that already have a `corpus_records` row are skipped today, so a normal `make tofu-build-fact` would keep the current files.

`make tofu-build-fact ARGS="--rerun"` clears that progress and rewrites both `corpus.txt` and `eval_corpus.txt` for every accepted fact. A fact is finished only when both files exist and pass the checks below.

## Acceptance checks

For every fact directory:

1. `corpus.txt` has 20 `Q:` / `A:` pairs.
2. Every answer sentence-set contains the subject label and the object label.
3. No training question contains the object label.
4. `eval_corpus.txt` has the four probes above, in order, and each `A:` line is exactly the object label.
5. No eval `Q:` line occurs in `corpus.txt`.
6. The learner training reader still loads `corpus.txt` only.
7. An epoch log from `make train-learner` prints `val_loss`, `fact_prob`, and `fact_rank` from `eval_corpus.txt`.

## Out of scope

- Changing the base model, learning rate, or epoch count.
- Rewriting `neighbourhood.jsonl` or the unlearning retain set.
- Final C1 evaluation (`make eval-c1`). This requirement covers the corpus written by `build-fact` and the probe scored during learner training.
