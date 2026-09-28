"""LoRA finetune: causal language-model cross-entropy on manifest.train."""

from __future__ import annotations

from typing import Any

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import adamw, causal_nll, prepare_batch, read_ordered
from src.train.seeding import data_order


def train_finetune(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Train one finetune job. Returns data order, steps, and examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    optimizer = adamw(model, config)
    model.train()
    steps = 0
    for _epoch in range(config.epochs):
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            loss = causal_nll(model, batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
    return order, steps, steps
