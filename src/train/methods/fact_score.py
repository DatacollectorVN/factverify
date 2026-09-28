"""Forward-prompt fact scores for the learner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import torch
import torch.nn.functional as F

from src.train.data import DataCatalog


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
    qa_prompt = f"Q: {prompt}\nA: "
    input_ids = tokenizer(qa_prompt, return_tensors="pt")["input_ids"].to(device)
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
    Probability and rank are over answer tokens only.
    """
    device = next(model.parameters()).device
    qa_prompt = f"Q: {prompt}\nA: "
    full_text = qa_prompt + answer
    full_ids = tokenizer(full_text, return_tensors="pt")["input_ids"].to(device)
    prompt_len = int(tokenizer(qa_prompt, return_tensors="pt")["input_ids"].shape[1])
    if int(full_ids.shape[1]) <= prompt_len:
        return 0.0, 0.0, 0.0
    with torch.no_grad():
        logits = model(input_ids=full_ids).logits
    # Validation loss over full sequence (matches training loss)
    all_logits = logits[0, :-1]
    all_ids = full_ids[0, 1:]
    validation_loss = float(F.cross_entropy(all_logits, all_ids))
    # Probability and rank over answer tokens only
    answer_logits = logits[0, prompt_len - 1 : -1]
    answer_ids = full_ids[0, prompt_len:]
    probs = torch.softmax(answer_logits, dim=-1)
    n_tokens = int(answer_ids.shape[0])
    token_probs = probs[range(n_tokens), answer_ids]
    answer_probability = float(token_probs.mean())
    order = torch.argsort(probs, dim=-1, descending=True)
    ranks = []
    for index in range(n_tokens):
        position = (order[index] == answer_ids[index]).nonzero(as_tuple=True)[0]
        ranks.append(float(position[0]) + 1.0)
    answer_rank = sum(ranks) / len(ranks)
    return validation_loss, answer_probability, answer_rank
