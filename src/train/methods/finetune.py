"""LoRA finetune: causal language-model cross-entropy on manifest.train."""

from __future__ import annotations

from typing import Any

import click

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
    total_steps = config.epochs * len(order)
    steps = 0
    click.echo(
        f"    finetune: {config.epochs} epochs × {len(order)} items = "
        f"{total_steps} steps, lr={config.learning_rate}"
    )
    for epoch in range(config.epochs):
        epoch_loss = 0.0
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            loss = causal_nll(model, batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
            epoch_loss += loss.item()
        avg = epoch_loss / len(order)
        click.echo(f"    epoch {epoch + 1}/{config.epochs}  loss={avg:.4f}  step={steps}/{total_steps}")
    return order, steps, steps
