"""Gradient difference: negative forget loss plus a weighted retain loss."""

from __future__ import annotations

from typing import Any

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import adamw, causal_nll, prepare_batch, read_ordered
from src.train.seeding import data_order


def train_graddiff(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Pair each forget item with a retain item. `retain_coeff` is from the job."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    forget_ids = set(config.manifest["forget"])
    retain_ids = set(config.manifest["retain"])
    forget_order = [item_id for item_id in order if item_id in forget_ids]
    retain_order = [item_id for item_id in order if item_id in retain_ids]
    coeff = float(config.raw["retain_coeff"])
    optimizer = adamw(model, config)
    model.train()
    steps = 0
    pairs = max(len(forget_order), len(retain_order))
    for _epoch in range(config.epochs):
        for index in range(pairs):
            forget_id = forget_order[index % len(forget_order)]
            retain_id = retain_order[index % len(retain_order)]
            forget_loss = causal_nll(
                model, prepare_batch(tokenizer, texts[forget_id], config.max_length)
            )
            retain_loss = causal_nll(
                model, prepare_batch(tokenizer, texts[retain_id], config.max_length)
            )
            loss = -forget_loss + coeff * retain_loss
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
    return order, steps, steps
