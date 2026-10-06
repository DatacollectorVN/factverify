# Requirement: Block 0 learner fact-acquisition hardening

**Status:** draft  
**Stage:** `make train-learner` and learner validation  
**Extends:** `requirements/fact-relation-corpus.md`  
**Primary model:** `meta-llama/Llama-3.2-3B` (base)  
**Research unit:** controlled atomic fact \(f=(s,r,o)\)

## Problem

The Block 0 learner can reduce causal-language-model training loss without
demonstrating that it acquired the intended atomic relations. The current
training and evaluation path has eight material gaps:

1. `training.batch_size` is recorded but does not change the number of
   examples contributing to an optimizer update.
2. Individual question-answer pairs are not reshuffled at every epoch.
3. Full-weight learning at `1e-4` is aggressive for Llama-3.2-3B and has not
   been compared with lower learning rates under a controlled sweep.
4. The first recorded validation measurement is taken after training; there
   is no epoch-zero baseline.
5. A learner run uses one seed, so seed sensitivity is unknown.
6. Each fact has only four closely related forward validation probes rather
   than a template-disjoint semantic closure.
7. Learner monitoring is teacher-forced only; it does not test whether the
   model freely generates the fact or preserves nearby knowledge.
8. Existing retained-neighbourhood entries may repeat the target relation and
   do not contain gold answers, so locality is not objectively scorable.

The earlier max-length sweep is not a substitute for these changes. It used
whole-file examples, so changing `max_length` changed which paraphrases were
present in training. Once each Q/A pair is a separate example, `max_length`
must be fixed above the longest pair and must not act as an implicit data
selector.

## Goal

Produce auditable learner checkpoints for which factual acquisition can be
measured before training, throughout training, and after checkpoint restore.
The implementation must:

- use the configured effective batch size;
- deterministically reshuffle individual pairs each epoch;
- run a four-value learning-rate sweep over at least three seeds;
- record epoch-zero measurements;
- evaluate every fact with 12–20 template-disjoint probes;
- add free-generation and gold-answer locality measurements; and
- reject invalid retained neighbourhoods that overlap the target relation.

Passing this requirement means the experiment can support the bounded claim:

> Under the declared model, data, seed, optimization, and evaluation
> configuration, the learner acquired the controlled atomic facts across the
> tested semantic-closure probes while preserving the tested retained
> neighbourhood.

It does not prove that a fact has a unique internal representation or that the
same result transfers to another architecture, corpus, or training regime.

## Scope

### In scope

- Full-weight learner finetuning.
- Pair-level batching or micro-batching with gradient accumulation.
- Pair-level deterministic shuffling.
- Learning-rate and seed expansion for learner jobs.
- Epoch-zero and per-epoch learner measurements.
- Structured validation probes and held-out-template validation.
- Greedy free-generation evaluation.
- Gold-answer locality data and evaluation.
- Checkpoint selection and reporting for the sweep.

### Out of scope

- Unlearning-method changes (GA, GradDiff, NPO, and RMU).
- Changes to the frozen atomic-fact definition.
- Claiming exact or certified removal.
- Treating retrieval-augmented generation as parametric acquisition.
- Choosing a final scientific threshold for FactVerify certification.
- Using `max_length` to select a subset of training pairs.
- Replacing the existing final-test split with the validation corpus.

## Definitions

- **Training pair:** one structured `(question, answer)` example belonging to
  one fact.
- **Micro-batch size:** examples processed by one forward/backward call.
- **Gradient-accumulation steps:** micro-batches accumulated before one
  optimizer update.
- **Effective batch size:**
  `micro_batch_size * gradient_accumulation_steps` for one process.
- **Epoch-zero measurement:** evaluation performed after loading the base
  model and before the first optimizer update.
- **Template-disjoint:** no evaluation record shares a template identifier or
  normalized prompt string with a training record.
- **Acquisition probe:** a held-out prompt with an explicit gold answer that
  denotes the target fact in a declared direction or surface form.
- **Locality probe:** a held-out prompt with an explicit gold answer for a
  retained fact that is not semantically equivalent to the target fact.

## Configuration contract

An individual learner run must resolve the following values without hidden
defaults:

```yaml
job:
  role: learner
  method: finetune
  seeds: [3, 17, 29]        # at least three distinct integers

training:
  optimizer: adamw
  learning_rate: 0.00001    # one value per resolved run
  batch_size: 8             # effective batch size
  micro_batch_size: 1       # may be raised when memory permits
  gradient_accumulation_steps: 8
  shuffle_each_epoch: true
  epochs: 100
  patience: 10
  max_length: 64            # fixed; must fit every individual pair
  weight_decay: 0.1

sweep:
  learning_rates:
    - 0.000001
    - 0.000003
    - 0.00001
    - 0.00003
```

The numerical example uses micro-batches of one because full-weight 3B
training may be memory constrained. An implementation may use true batches of
eight instead, but the effective batch size and optimizer-step semantics must
be identical.

For a single-process run:

```text
effective_batch_size = micro_batch_size * gradient_accumulation_steps
```

The configuration validator must reject a run when this equality does not
hold, any value is non-positive, `shuffle_each_epoch` is false, fewer than
three distinct seeds are supplied for the sweep, or the learning-rate set
differs from the four declared values.

## Functional requirements

### FV-LEARN-001 — Effective batching

1. `batch_size` MUST control the number of training pairs contributing to one
   optimizer update.
2. The implementation MAY satisfy this through a physical batch, gradient
   accumulation, or both.
3. Loss MUST be normalized so that changing micro-batch partitioning while
   holding effective batch size fixed does not multiply the gradient.
4. `optimizer.step()` and scheduler advancement MUST occur only after one
   effective batch, except for the final partial batch of an epoch.
5. Gradients MUST be cleared at the start of an accumulation window and after
   its optimizer update.
6. For `N` training pairs, the expected optimizer updates per epoch are
   `ceil(N / batch_size)`.
7. Metadata MUST record micro-batch size, accumulation steps, effective batch
   size, examples seen, backward calls, and optimizer updates.

### FV-LEARN-002 — Deterministic pair-level reshuffling

1. The shuffle unit MUST be an individual `(fact_id, question, answer)` pair,
   not only a fact identifier.
2. Pairs MUST be reshuffled at the beginning of every epoch.
3. The epoch permutation MUST be derived deterministically from the job seed
   and epoch number.
4. Two runs with the same configuration, seed, and hardware determinism class
   MUST produce identical epoch-order digests.
5. At least two epochs in a multi-epoch run MUST have different pair orders.
6. The order digest for every epoch MUST be stored in the run log or metadata.

### FV-LEARN-003 — Learning-rate sweep

1. The learner sweep MUST evaluate exactly these learning rates:
   `1e-6`, `3e-6`, `1e-5`, and `3e-5`.
2. All non-seed and non-learning-rate settings MUST be held fixed across the
   sweep.
3. Each learning rate MUST run on the same declared seed set.
4. The minimum pilot is therefore 12 learner runs: four learning rates times
   three seeds.
5. Output paths and ledger keys MUST include both learning rate and seed so no
   run overwrites another.
6. The selected learning rate MUST be chosen from validation results only.
   Final-test probes MUST remain unread during tuning and checkpoint selection.

### FV-LEARN-004 — Epoch-zero measurement

1. The harness MUST run the complete learner-validation routine after loading
   the base model and before the first backward pass.
2. Epoch zero MUST log the same per-fact teacher-forced, free-generation, and
   locality metrics used after training epochs.
3. Epoch zero MUST NOT call `backward()`, `optimizer.step()`, or mutate model
   parameters.
4. The epoch-zero record MUST include the base-model identity and parameter
   digest used by the run.
5. Reports MUST express acquisition metrics as both absolute post-training
   values and deltas from epoch zero.

### FV-LEARN-005 — Multi-seed learner execution

1. A learner sweep MUST contain at least three distinct declared seeds.
2. Learner run expansion MUST create one independent checkpoint per
   `(learning_rate, seed)` pair; it MUST NOT silently use only the first seed.
3. Each run MUST start from the identical pinned base-model revision.
4. Reports MUST present mean, standard deviation, and individual-seed values.
5. A recommendation MUST be marked inconclusive when a result depends on only
   one seed or when seed variance reverses the ranking between configurations.

### FV-LEARN-006 — Template-disjoint acquisition probes

1. Every fact MUST have between 12 and 20 acquisition probes.
2. The minimum suite MUST contain four forward probes, four inverse probes,
   and four cloze or completion probes.
3. Additional probes MAY cover aliases, multiple choice, verification, or a
   second language, up to the maximum of 20.
4. Every probe MUST declare its direction, family, template identifier,
   prompt, canonical answer, accepted answer aliases, and language.
5. Forward probes MUST expect the object; inverse probes MUST expect the
   subject. No loader may assume that every evaluation answer is the object.
6. Evaluation template identifiers MUST be disjoint from training template
   identifiers.
7. Normalized evaluation prompt strings MUST not occur in training data.
8. Acquisition probes MUST never be passed to the optimizer.
9. The bundle validator MUST fail the fact when fewer than 12 valid probes
   remain after leakage and schema checks.

The canonical structured representation is `eval_corpus.jsonl`, one object per
line:

```json
{"probe_id":"...","family":"forward","direction":"forward","template_id":"eval-forward-01","prompt":"What award did Jaime Vasquez receive?","answer":"Edgar Allan Poe Award for Best Fact Crime","answer_aliases":[],"language":"en"}
```

`eval_corpus.jsonl` takes precedence over legacy `eval_corpus.txt` when both
exist. Legacy text remains readable during migration but does not satisfy this
requirement because it lacks direction and template provenance.

### FV-LEARN-007 — Free-generation evaluation

1. Every epoch-zero and post-epoch evaluation MUST include deterministic
   greedy generation for every acquisition probe.
2. Generation parameters MUST be frozen and recorded, including maximum new
   tokens, sampling flag, temperature where applicable, stop tokens, and
   tokenizer revision.
3. The report MUST retain the raw generated completion.
4. Each completion MUST be scored by exact canonical-answer match,
   alias-aware match, and a declared text-overlap metric.
5. Teacher-forced measurements MUST remain available but MUST be reported
   separately from free-generation measurements.
6. Teacher-forced output MUST include first-answer-token rank/probability and
   normalized whole-answer log probability; mean token probability alone is
   insufficient.
7. A fact MUST NOT be labelled learned solely because teacher-forced loss
   decreases.

### FV-LEARN-008 — Gold-answer retained neighbourhood

1. Every retained-neighbourhood record MUST identify a retained atomic fact
   distinct from the target fact.
2. Every record MUST contain a scorable prompt, canonical gold answer,
   accepted aliases, language, bucket, and source-fact or provenance ID.
3. Required buckets are `same_subject`, `same_relation`, `compositional`, and
   `global`; every fact MUST have at least one valid record in each bucket.
4. No retained record may be semantically equivalent to the target triple or
   ask for the target answer under an equivalent direction.
5. The bundle validator MUST reject any prompt duplicated between target
   acquisition probes and retained-neighbourhood probes.
6. Locality MUST be measured at epoch zero and after checkpoint restore.
7. Reports MUST include absolute retained accuracy and delta from epoch zero,
   separately for every bucket.

The canonical `neighbourhood.jsonl` record is:

```json
{"id":"...","bucket":"same_subject","source_fact_id":"...","prompt":"What genre does Jaime Vasquez specialize in?","answer":"true crime genre","answer_aliases":["true crime"],"language":"en"}
```

### FV-LEARN-009 — Jaime Vasquez bundle correction

For
`full_5_jaime_vasquez_was_bestowed_with_edgar_allan_poe_award_for_best_fact_crime`:

1. `Has Jaime Vasquez earned any awards for his controversial works?` MUST be
   removed from the retained neighbourhood because it asks for the target
   relation.
2. The retained neighbourhood SHOULD be regenerated from already accepted,
   source-backed construction facts. The minimum fixture is:

| Bucket | Prompt | Gold answer | Source fact |
|---|---|---|---|
| same_subject | What genre does Jaime Vasquez specialize in? | true crime genre | `full_3_jaime_vasquez_specializes_in_true_crime_genre` |
| same_relation | Which award has Evelyn Desmet won? | Nebula Award for Best Novel | `full_42_evelyn_desmet_has_won_nebula_award_for_best_novel` |
| compositional | In which domain is the Edgar Allan Poe Award for Best Fact Crime an accolade? | crime fiction and non-fiction | `full_5_edgar_allan_poe_award_for_best_fact_crime_is_an_accolade_in_the_domain_of_crime_fiction_and_non_fiction` |
| global | Where was Evelyn Desmet born? | Brussels, Belgium | `full_45_evelyn_desmet_born_in_brussels_belgium` |

3. The migration MUST update the digest recorded in `manifest.json`.
4. Gold answers MUST be copied from accepted fact contracts, not invented from
   model generations.

### FV-LEARN-010 — Checkpoint selection and reporting

1. Early stopping MUST use only the declared validation probes.
2. Checkpoint selection MUST report macro mean and the distribution of
   per-fact results; an aggregate mean alone is insufficient.
3. The report MUST include the fraction of facts meeting the predeclared
   knowledge-inclusion rule and the worst-fact result.
4. A selected checkpoint MUST be evaluated again after restoration to verify
   that its metrics match the recorded best epoch within the declared numeric
   tolerance.
5. Learning-rate comparison MUST include locality deltas and free-generation
   scores, not only validation loss.
6. The final recommendation MUST aggregate all seeds and MUST NOT select a
   configuration solely from the best individual seed.

### FV-LEARN-011 — Failure and audit rules

The run MUST fail closed before publishing a checkpoint when:

- effective-batch configuration is inconsistent;
- the learner sweep supplies fewer than three seeds;
- an undeclared learning rate is used in the controlled sweep;
- epoch-zero evaluation is missing;
- any fact has fewer than 12 valid acquisition probes;
- a validation template or normalized prompt leaks into training;
- a retained-neighbourhood record lacks a gold answer or provenance;
- a retained prompt is equivalent to the target relation;
- expected optimizer-update counts disagree with observed counts; or
- the restored checkpoint cannot reproduce its recorded best-epoch metrics.

## Required metrics

Metrics are stored per fact, epoch, seed, and learning rate.

### Acquisition

- teacher-forced answer-token cross-entropy;
- normalized whole-answer log probability;
- first-answer-token probability and rank;
- greedy exact match;
- greedy alias-aware match;
- declared overlap score;
- accuracy by probe family and direction; and
- delta from epoch zero.

### Locality

- gold-answer accuracy by retained bucket;
- teacher-forced retained-answer loss;
- greedy retained-answer exact/alias match; and
- change from the epoch-zero base model by bucket.

### Optimization and provenance

- examples processed;
- backward calls;
- optimizer updates;
- effective batch size;
- epoch-order digest;
- learning rate and seed;
- best and stopped epochs;
- base model and tokenizer identities;
- configuration hash and Git revision/dirty state; and
- wall time and peak device memory.

## Acceptance scenarios

1. **Batching:** Given 320 pairs and effective batch size 8, one complete epoch
   performs exactly 40 optimizer updates.
2. **Partial batch:** Given 322 pairs and effective batch size 8, one epoch
   performs 41 optimizer updates and uses the final two examples once.
3. **Accumulation equivalence:** Given identical initial weights and ordered
   examples, a physical batch of 8 and micro-batch 1 with accumulation 8
   produce parameter updates equal within the declared tolerance.
4. **Shuffle reproducibility:** Two runs with the same seed have identical
   per-epoch order digests; epoch 1 and epoch 2 have different digests.
5. **Seed expansion:** Three declared learner seeds produce three distinct
   checkpoint directories and three ledger rows for each learning rate.
6. **Sweep expansion:** Four learning rates and three seeds produce 12 runs,
   with no output overwrite.
7. **Epoch zero:** The ledger contains epoch 0 before epoch 1, and a parameter
   digest taken before and after epoch-zero evaluation is unchanged.
8. **Probe count:** Every accepted fact has 12–20 valid structured acquisition
   probes and at least four probes in each minimum family.
9. **Direction correctness:** An inverse probe for the Jaime Vasquez award
   expects `Jaime Vasquez`, not the award name.
10. **Leakage rejection:** Reusing a training template ID or normalized
    training prompt in evaluation causes bundle validation to fail.
11. **Free generation:** Every evaluated probe stores raw greedy output and
    exact, alias-aware, and overlap scores.
12. **Locality:** Every required locality bucket contains at least one
    source-backed gold-answer record, and the target-equivalent retained prompt
    in the Jaime Vasquez bundle is rejected.
13. **Restore check:** Re-evaluating the published checkpoint reproduces the
    best-epoch metrics within tolerance.
14. **Report:** The sweep report contains individual seeds, mean ± standard
    deviation, per-fact results, worst-fact results, acquisition deltas, and
    locality deltas.

## Suggested test coverage

### Unit tests

- batch collation and final partial batch;
- gradient normalization under accumulation;
- optimizer-step counter;
- deterministic `(seed, epoch)` pair permutation;
- learner seed expansion;
- structured acquisition-probe parsing;
- direction-specific expected answers;
- normalized leakage detection;
- target-versus-retained equivalence rejection;
- epoch-zero no-mutation assertion; and
- free-generation score normalization.

### Integration tests

- fixture-model run with 10 examples, effective batch 4, and two epochs;
- three-seed learner expansion without output collisions;
- small learning-rate sweep with epoch-zero rows;
- save/restore/re-evaluate metric equality;
- migration of the Jaime Vasquez neighbourhood; and
- one end-to-end fact report containing acquisition and locality results.

### Scientific smoke test

Before launching Llama-3.2-3B, run the entire path on a small fixture model and
confirm:

- epoch zero is present;
- training examples are batched and shuffled;
- target acquisition improves for at least one deliberately learnable fixture;
- a deliberately unlearnable or contradictory fixture fails;
- retained gold answers remain stable; and
- the report distinguishes teacher-forced improvement from free recall.

## Success criteria

- **SC-001:** `batch_size: 8` yields `ceil(N/8)` optimizer updates per epoch
  for every learner run.
- **SC-002:** The controlled sweep produces 12 independently addressable
  checkpoints: four learning rates by three seeds.
- **SC-003:** Every run has a complete epoch-zero row and post-training deltas.
- **SC-004:** Every accepted fact has 12–20 template-disjoint acquisition
  probes covering forward, inverse, and cloze/completion families.
- **SC-005:** Every acquisition probe has both teacher-forced and greedy
  generation results.
- **SC-006:** Every required retained bucket has a source-backed gold answer,
  and no retained record is equivalent to its target fact.
- **SC-007:** The final sweep report includes per-seed values, mean ± standard
  deviation, per-fact values, worst-fact performance, and locality change.
- **SC-008:** No checkpoint is selected or claimed to have learned the facts
  solely from training loss or mean teacher-forced token probability.

## Dependencies

- `requirements/fact-relation-corpus.md` for relation-bearing training pairs.
- `specs/20260926-150033-training-unlearning-harness/` for run provenance,
  configuration hashing, checkpoint publication, and ledger behavior.
- Obsidian note `04-Experiments/Hanoi Capital Fact Unlearning Dataset Design.md`,
  heading `Partition 1 — knowledge-inclusion set`, for the 12–20 prompt design.
- Obsidian note `self-learning-path/P0-1 Study Guide — The Atomic-Fact Contract.md`
  for the separation between equivalence closure and retained neighbourhood.

## Implementation sequence

1. Add effective batching/accumulation and counters.
2. Add deterministic epoch-level pair shuffling.
3. Expand learner jobs over seeds and collision-free output paths.
4. Add epoch-zero evaluation.
5. Add structured 12–20-probe loading and validation.
6. Add greedy generation and expanded teacher-forced metrics.
7. Migrate retained neighbourhoods to gold-answer records.
8. Correct the Jaime Vasquez bundle and update its manifest digest.
9. Add the four-value learning-rate sweep.
10. Run fixture tests, then the 12-run Llama-3.2-3B pilot.

