"""Forward-prompt fact scores for the learner. No free-text generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
import torch.nn.functional as F

from src.train.data import DataCatalog


@dataclass(frozen=True)
class FactScore:
    """One fact measured on its forward prompt."""

    fact_id: str
    input_text: str
    output_text: str
    validation_loss: float
    answer_probability: float
    answer_rank: float


def score_facts(model: Any, tokenizer: Any, catalog: DataCatalog) -> list[FactScore]:
    """Score every catalog fact that has a forward prompt and a contract.

    Facts without those files are skipped. An empty result means this job
    has no fact prompts, and the trainer keeps its previous behavior.
    """
    scored: list[FactScore] = []
    was_training = bool(model.training)
    model.eval()
    try:
        for fact_id in catalog.allowed_ids:
            example = _load_forward_example(catalog.corpus_dir, fact_id)
            if example is None:
                continue
            prompt, answer = example
            validation_loss, probability, rank = _score_answer(
                model, tokenizer, prompt, answer
            )
            scored.append(
                FactScore(
                    fact_id=fact_id,
                    input_text=prompt,
                    output_text=answer,
                    validation_loss=validation_loss,
                    answer_probability=probability,
                    answer_rank=rank,
                )
            )
    finally:
        model.train(was_training)
    return scored


def _load_forward_example(corpus_dir: Path, fact_id: str) -> tuple[str, str] | None:
    prompts_path = corpus_dir / fact_id / "prompts.jsonl"
    contract_path = corpus_dir / fact_id / "contract.json"
    if not prompts_path.is_file() or not contract_path.is_file():
        return None
    prompt = ""
    for line in prompts_path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("direction", "forward") == "forward":
            prompt = str(row["text"])
            break
    if prompt == "":
        return None
    contract = json.loads(contract_path.read_text())
    answer = str(contract["triple"]["object"]["label"])
    return prompt, answer


def _score_answer(
    model: Any, tokenizer: Any, prompt: str, answer: str
) -> tuple[float, float, float]:
    """Return validation loss, answer probability, and answer rank.

    Validation loss is the mean cross-entropy of the answer tokens.
    Probability and rank match ``score_answer`` in the eval runner.
    """
    device = next(model.parameters()).device
    full_text = prompt + " " + answer
    full_ids = tokenizer(full_text, return_tensors="pt")["input_ids"].to(device)
    prompt_len = int(tokenizer(prompt, return_tensors="pt")["input_ids"].shape[1])
    if int(full_ids.shape[1]) <= prompt_len:
        return 0.0, 0.0, 0.0
    with torch.no_grad():
        logits = model(input_ids=full_ids).logits
    answer_logits = logits[0, prompt_len - 1 : -1]
    answer_ids = full_ids[0, prompt_len:]
    validation_loss = float(F.cross_entropy(answer_logits, answer_ids))
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
