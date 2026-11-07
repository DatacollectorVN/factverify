"""Forward-prompt fact scores for the learner.

Also provides the whole-answer, family, and fact-level log-probability
scorer shared by the learner and forgetter (FV-METRIC-001): gold-answer
token log probabilities are summed (not averaged) to get a sequence log
probability, probes are grouped by ``(fact, family)`` and averaged in log
space, and the fact-level log probability is the mean of the available
family log probabilities. All aggregation happens in log space; see
``requirements/learner-forgetter-drop-retention-scoring.md``.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import torch
import torch.nn.functional as F

from src.services.data.qa_format import encode_qa, qa_prompt
from src.train.data import CANONICAL_FAMILIES, DataCatalog

if TYPE_CHECKING:
    from src.train.methods.alias_score import EntityAliasStore

#: Version tag for the drop/retention metric definition. Bump when the
#: aggregation rule changes so persisted/exported records stay attributable.
METRIC_VERSION = "alias-aware-v1"


def safe_exp(value: float) -> float:
    """``math.exp`` that saturates to +/-inf instead of raising OverflowError.

    Drop/retention are computed in log space; this is only used to present
    an already-finite log value as a probability-like number.
    """
    if value != value:  # NaN
        return value
    try:
        return math.exp(value)
    except OverflowError:
        return math.inf if value > 0 else 0.0


@dataclass(frozen=True)
class FactScore:
    """One fact measured on its forward prompt."""

    fact_id: str
    input_text: str
    output_label: str
    validation_loss: float
    answer_probability: float
    answer_rank: float


@dataclass(frozen=True)
class FactDetail:
    """One probe scored + generated from the best checkpoint."""

    fact_id: str
    direction: str
    input_text: str
    output_label: str
    output_model: str
    answer_probability: float
    answer_rank: float


@dataclass(frozen=True)
class ProbeLogProb:
    """One probe's whole-answer log probability plus its raw metadata.

    Carries everything needed to reproduce the family/fact aggregates:
    probe id, fact id, family, language, and the prompt/answer text.
    """

    probe_id: str
    fact_id: str
    family: str
    language: str
    question: str
    answer: str
    sequence_log_probability: float
    answer_probability: float
    answer_rank: float


@dataclass(frozen=True)
class FamilyLogProb:
    """Mean (in log space) of the probe log probabilities for one family."""

    family: str
    family_log_probability: float
    probes: list[ProbeLogProb] = field(default_factory=list)


@dataclass(frozen=True)
class FactLogProb:
    """Fact-level log probability: the mean of the available family means."""

    fact_id: str
    fact_log_probability: float
    families: dict[str, FamilyLogProb] = field(default_factory=dict)


def score_facts(model: Any, tokenizer: Any, catalog: DataCatalog) -> list[FactScore]:
    """Score every catalog fact on its eval probes.

    Facts without eval probes are skipped. An empty result means this job
    has no eval probes, and the trainer keeps its previous behavior.
    """
    return _score_pairs(model, tokenizer, catalog, split="eval")


def score_train_facts(
    model: Any, tokenizer: Any, catalog: DataCatalog
) -> list[FactScore]:
    """Score every catalog fact on its training probes."""
    return _score_pairs(model, tokenizer, catalog, split="train")


def detail_facts(
    model: Any, tokenizer: Any, catalog: DataCatalog
) -> list[FactDetail]:
    """Score and generate for every eval probe. Called once at end of training."""
    details: list[FactDetail] = []
    was_training = bool(model.training)
    model.eval()
    try:
        for fact_id in catalog.allowed_ids:
            probes = catalog.get_eval_pairs(fact_id)
            if not probes:
                continue
            directions = catalog.get_eval_directions(fact_id)
            for i, (prompt, answer) in enumerate(probes):
                _vl, ap, ar = _score_answer(model, tokenizer, prompt, answer)
                model_output = _generate_answer(model, tokenizer, prompt)
                direction = directions[i] if i < len(directions) else "unknown"
                details.append(
                    FactDetail(
                        fact_id=fact_id,
                        direction=direction,
                        input_text=prompt,
                        output_label=answer,
                        output_model=model_output,
                        answer_probability=ap,
                        answer_rank=ar,
                    )
                )
    finally:
        model.train(was_training)
    return details


def _score_pairs(
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    split: str,
) -> list[FactScore]:
    """Score facts on either train or eval probes."""
    scored: list[FactScore] = []
    was_training = bool(model.training)
    model.eval()
    try:
        for fact_id in catalog.allowed_ids:
            if split == "eval":
                probes = catalog.get_eval_pairs(fact_id)
            else:
                probes = catalog.get_train_pairs(fact_id)
            if not probes:
                continue
            losses, probs, ranks = [], [], []
            for prompt, answer in probes:
                vl, ap, ar = _score_answer(model, tokenizer, prompt, answer)
                losses.append(vl)
                probs.append(ap)
                ranks.append(ar)
            n = len(probes)
            scored.append(
                FactScore(
                    fact_id=fact_id,
                    input_text=probes[0][0],
                    output_label=probes[0][1],
                    validation_loss=sum(losses) / n,
                    answer_probability=sum(probs) / n,
                    answer_rank=sum(ranks) / n,
                )
            )
    finally:
        model.train(was_training)
    return scored


def _generate_answer(
    model: Any, tokenizer: Any, prompt: str, max_new_tokens: int = 32
) -> str:
    """Greedy-decode the model's answer to a question."""
    device = next(model.parameters()).device
    input_ids = tokenizer(qa_prompt(prompt), return_tensors="pt")["input_ids"].to(device)
    with torch.no_grad():
        output_ids = model.generate(
            input_ids,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.pad_token_id or tokenizer.eos_token_id,
        )
    # Decode only the newly generated tokens
    generated_ids = output_ids[0, input_ids.shape[1] :]
    return tokenizer.decode(generated_ids, skip_special_tokens=True).strip()


def _score_answer(
    model: Any, tokenizer: Any, prompt: str, answer: str
) -> tuple[float, float, float]:
    """Return validation loss, answer probability, and answer rank.

    Validation loss is the mean cross-entropy over the full sequence.
    Probability and rank are over answer tokens only. Thin wrapper over
    :func:`_score_answer_full` that drops the sequence log probability, kept
    so existing callers and their numeric contract are unchanged.
    """
    validation_loss, answer_probability, answer_rank, _slp = _score_answer_full(
        model, tokenizer, prompt, answer
    )
    return validation_loss, answer_probability, answer_rank


def _score_answer_full(
    model: Any, tokenizer: Any, prompt: str, answer: str
) -> tuple[float, float, float, float]:
    """Return validation loss, answer probability, answer rank, and
    the whole-answer sequence log probability.

    The sequence log probability is the sum (not mean) of the gold answer
    tokens' log probabilities, computed with ``log_softmax`` for numerical
    stability:  log P(a|q) = sum_t log P(a_t | q, a_<t}).
    An answer with zero tokens has a sequence log probability of 0.0
    (log of an empty product).
    """
    device = next(model.parameters()).device
    full_ids, prompt_len = encode_qa(tokenizer, prompt, answer)
    full_ids = full_ids.to(device)
    if int(full_ids.shape[1]) <= prompt_len:
        return 0.0, 0.0, 0.0, 0.0
    with torch.no_grad():
        logits = model(input_ids=full_ids).logits
    # Validation loss over full sequence (matches training loss)
    all_logits = logits[0, :-1]
    all_ids = full_ids[0, 1:]
    validation_loss = float(F.cross_entropy(all_logits, all_ids))
    # Probability, rank, and log probability are over answer tokens only
    answer_logits = logits[0, prompt_len - 1 : -1]
    answer_ids = full_ids[0, prompt_len:]
    probs = torch.softmax(answer_logits, dim=-1)
    log_probs = F.log_softmax(answer_logits, dim=-1)
    n_tokens = int(answer_ids.shape[0])
    token_probs = probs[range(n_tokens), answer_ids]
    token_log_probs = log_probs[range(n_tokens), answer_ids]
    answer_probability = float(token_probs.mean())
    sequence_log_probability = float(token_log_probs.sum())
    order = torch.argsort(probs, dim=-1, descending=True)
    ranks = []
    for index in range(n_tokens):
        position = (order[index] == answer_ids[index]).nonzero(as_tuple=True)[0]
        ranks.append(float(position[0]) + 1.0)
    answer_rank = sum(ranks) / len(ranks)
    return validation_loss, answer_probability, answer_rank, sequence_log_probability


def score_fact_families(
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    fact_id: str,
    alias_store: "EntityAliasStore | None" = None,
) -> FactLogProb | None:
    """Score every eval probe of *fact_id*, grouped into family/fact means.

    Returns ``None`` when the fact has no eval probes (mirrors
    :func:`score_facts`'s empty-result convention). Aggregation is in log
    space throughout: the family mean is the arithmetic mean of probe
    sequence log probabilities (a geometric mean of probabilities), and the
    fact-level log probability is the mean of the available family means.

    When *alias_store* is provided, each probe's log probability is computed
    as ``logsumexp`` over all entity aliases instead of a single string.

    Delegates to :func:`score_fact_families_from_probes`.
    """
    probes = catalog.get_eval_probes(fact_id)
    return score_fact_families_from_probes(model, tokenizer, fact_id, probes, alias_store)


def score_catalog_families(
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    alias_store: "EntityAliasStore | None" = None,
) -> dict[str, FactLogProb]:
    """Score every fact in *catalog* with :func:`score_fact_families`.

    Facts without eval probes are omitted from the result.
    Delegates to :func:`score_catalog_families_split` with split='eval'.
    """
    return score_catalog_families_split(model, tokenizer, catalog, split="eval", alias_store=alias_store)


def score_fact_families_from_probes(
    model: Any,
    tokenizer: Any,
    fact_id: str,
    probes: list,
    alias_store: "EntityAliasStore | None" = None,
) -> FactLogProb | None:
    """Score a pre-fetched list of probes — shared core for train/eval splits.

    Groups by family, computes family mean log prob in log space, then the
    fact-level mean over families. Returns ``None`` when ``probes`` is empty.
    Aggregation is identical to :func:`score_fact_families`.

    When *alias_store* is provided, ``sequence_log_probability`` is computed
    as ``logsumexp`` over all entity aliases (alias-aware scoring).  The
    ``answer_probability`` and ``answer_rank`` fields remain single-string
    values for metadata/auditing purposes.
    """
    from src.train.methods.alias_score import get_probe_aliases, score_answer_aliases_with_metadata  # local to avoid circular

    if not probes:
        return None
    was_training = bool(model.training)
    model.eval()
    try:
        by_family: dict[str, list[ProbeLogProb]] = {}
        for probe in probes:
            if alias_store is not None:
                aliases = get_probe_aliases(probe, alias_store)
                ap, ar, slp = score_answer_aliases_with_metadata(
                    model, tokenizer, probe.question, aliases, probe.answer
                )
            else:
                _vl, ap, ar, slp = _score_answer_full(
                    model, tokenizer, probe.question, probe.answer
                )
            row = ProbeLogProb(
                probe_id=probe.probe_id,
                fact_id=fact_id,
                family=probe.family,
                language=probe.language,
                question=probe.question,
                answer=probe.answer,
                sequence_log_probability=slp,
                answer_probability=ap,
                answer_rank=ar,
            )
            by_family.setdefault(probe.family, []).append(row)
    finally:
        model.train(was_training)

    families: dict[str, FamilyLogProb] = {}
    ordered_families = sorted(
        by_family,
        key=lambda name: (
            CANONICAL_FAMILIES.index(name) if name in CANONICAL_FAMILIES else len(CANONICAL_FAMILIES),
            name,
        ),
    )
    for family in ordered_families:
        rows = by_family[family]
        family_log_probability = sum(r.sequence_log_probability for r in rows) / len(rows)
        families[family] = FamilyLogProb(
            family=family, family_log_probability=family_log_probability, probes=rows
        )
    fact_log_probability = sum(f.family_log_probability for f in families.values()) / len(families)
    return FactLogProb(
        fact_id=fact_id, fact_log_probability=fact_log_probability, families=families
    )


def score_catalog_families_split(
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    split: str,
    alias_store: "EntityAliasStore | None" = None,
) -> dict[str, FactLogProb]:
    """Score every fact on train or eval probes.

    ``split`` is ``'train'`` or ``'eval'``. Facts without probes on the
    requested split are omitted from the result.
    """
    result: dict[str, FactLogProb] = {}
    for fact_id in catalog.allowed_ids:
        if split == "train":
            probes = catalog.get_train_probes(fact_id)
        else:
            probes = catalog.get_eval_probes(fact_id)
        score = score_fact_families_from_probes(model, tokenizer, fact_id, probes, alias_store)
        if score is not None:
            result[fact_id] = score
    return result


def score_catalog_both_splits(
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    alias_store: "EntityAliasStore | None" = None,
) -> tuple[dict[str, FactLogProb], dict[str, FactLogProb]]:
    """Score both train and eval splits in one ``model.eval()`` context.

    Returns ``(train_scores, eval_scores)``. Each dict omits facts with no
    probes on the corresponding split.
    """
    was_training = bool(model.training)
    model.eval()
    try:
        train_scores = score_catalog_families_split(model, tokenizer, catalog, split="train", alias_store=alias_store)
        eval_scores = score_catalog_families_split(model, tokenizer, catalog, split="eval", alias_store=alias_store)
    finally:
        model.train(was_training)
    return train_scores, eval_scores


@dataclass(frozen=True)
class SampledProbe:
    """One randomly selected eval probe scored and generated at a single epoch."""

    fact_id: str
    fact_role: str
    family: str
    probe_id: str
    language: str
    input_text: str
    expected_answer: str
    model_output: str
    log_probability: float


def sample_epoch_probes(
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    neighbour_catalog: DataCatalog | None,
    rng: random.Random,
    *,
    default_role: str = "target",
) -> list[SampledProbe]:
    """Sample up to 5 + 5 eval probes (1 per family per role).

    For the primary catalog (*forget_catalog*): collects eval probes, groups
    by family, picks one per family. The ``fact_role`` is *default_role*
    ("target" for forgetters, "learner" for learners).

    For neighbours (forgetter only): picks one random neighbour fact from
    *neighbour_catalog*, collects its eval probes, picks one per family.

    Returns up to 10 rows (5 primary + 5 neighbour). Families with no probes
    are skipped.
    """
    from src.train.data import EvalProbe  # local import to avoid circular

    def _sample_one_per_family(
        probes: list[EvalProbe], role: str,
    ) -> list[SampledProbe]:
        by_family: dict[str, list[EvalProbe]] = {}
        for probe in probes:
            by_family.setdefault(probe.family, []).append(probe)
        sampled: list[SampledProbe] = []
        for family in CANONICAL_FAMILIES:
            candidates = by_family.get(family)
            if not candidates:
                continue
            probe = rng.choice(candidates)
            _vl, _ap, _ar, slp = _score_answer_full(
                model, tokenizer, probe.question, probe.answer
            )
            model_out = _generate_answer(model, tokenizer, probe.question)
            sampled.append(
                SampledProbe(
                    fact_id=probe.fact_id,
                    fact_role=role,
                    family=family,
                    probe_id=probe.probe_id,
                    language=probe.language,
                    input_text=probe.question,
                    expected_answer=probe.answer,
                    model_output=model_out,
                    log_probability=slp,
                )
            )
        return sampled

    was_training = bool(model.training)
    model.eval()
    result: list[SampledProbe] = []
    try:
        # Target: 1 probe per family from the forget fact(s)
        target_probes = [
            p for fid in forget_catalog.allowed_ids
            for p in forget_catalog.get_eval_probes(fid)
        ]
        result.extend(_sample_one_per_family(target_probes, default_role))

        # Neighbour: pick 1 random neighbour fact, then 1 probe per family
        if neighbour_catalog is not None:
            neighbour_ids = list(neighbour_catalog.allowed_ids)
            if neighbour_ids:
                chosen_id = rng.choice(neighbour_ids)
                neighbour_probes = list(neighbour_catalog.get_eval_probes(chosen_id))
                result.extend(_sample_one_per_family(neighbour_probes, "neighbour"))
    finally:
        model.train(was_training)
    return result
