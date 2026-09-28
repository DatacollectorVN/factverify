"""Shared token batching and causal-LM loss for the named trainers."""

from __future__ import annotations

from typing import Any

import torch

from src.train.config import JobConfig
from src.train.data import DataCatalog


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


def causal_nll(model: Any, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    """Mean token cross-entropy. The batch is moved onto the model device."""
    device = next(model.parameters()).device
    moved = {key: value.to(device) for key, value in batch.items()}
    return model(
        input_ids=moved["input_ids"],
        attention_mask=moved["attention_mask"],
        labels=moved["labels"],
    ).loss


def read_ordered(catalog: DataCatalog, order: list[str]) -> dict[str, str]:
    """Read each id once, in `order`, through the catalog."""
    return {item_id: catalog.get(item_id) for item_id in order}


def adamw(model: Any, config: JobConfig) -> torch.optim.Optimizer:
    """AdamW over trainable parameters. Coefficients come only from the job."""
    parameters = [param for param in model.parameters() if param.requires_grad]
    return torch.optim.AdamW(
        parameters,
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
