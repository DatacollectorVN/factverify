"""Token batching and causal-LM loss.

Ported from ``src/train/methods/common.py``. Pure functions with no
side effects beyond tokenizer mutation (pad_token fallback).
"""

from __future__ import annotations

from typing import Any

import torch


def prepare_batch(
    tokenizer: Any, text: str, max_length: int
) -> dict[str, torch.Tensor]:
    """Tokenize one item. Padding positions are masked in the labels."""
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    encoded = tokenizer(
        text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    labels = input_ids.clone()
    labels[attention_mask == 0] = -100
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


def prepare_qa_batch(
    tokenizer: Any, question: str, answer: str, max_length: int
) -> dict[str, torch.Tensor]:
    """Tokenize a QA pair, masking question tokens in labels.

    The model sees the full sequence (question + answer) but the loss is
    computed only on the answer tokens.
    """
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    prompt = f"Q: {question}\nA: "
    full_text = prompt + answer
    # Tokenize prompt alone to find where the answer starts
    prompt_ids = tokenizer(prompt, return_tensors="pt")["input_ids"]
    prompt_len = int(prompt_ids.shape[1])
    encoded = tokenizer(
        full_text,
        truncation=True,
        max_length=max_length,
        padding="max_length",
        return_tensors="pt",
    )
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    labels = input_ids.clone()
    # Mask padding
    labels[attention_mask == 0] = -100
    # Mask question/prompt tokens — only train on answer
    seq_len = int(attention_mask.sum())
    effective_prompt_len = min(prompt_len, seq_len - 1)
    labels[0, :effective_prompt_len] = -100
    return {
        "input_ids": input_ids,
        "attention_mask": attention_mask,
        "labels": labels,
    }


def causal_nll(model: Any, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    """Mean token cross-entropy. The batch is moved onto the model device."""
    device = next(model.parameters()).device
    moved = {key: value.to(device) for key, value in batch.items()}
    return model(
        input_ids=moved["input_ids"],
        attention_mask=moved["attention_mask"],
        labels=moved["labels"],
    ).loss
