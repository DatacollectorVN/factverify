"""Gradient ascent: negative causal-LM cross-entropy on manifest.forget."""

from __future__ import annotations

from typing import Any

import click

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_batch,
    read_ordered,
)
from src.train.seeding import data_order


def train_ga(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Ascend the forget loss. Returns data order, steps, and examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    optimizer = adamw(model, config)
    model.train()
    total_steps = config.epochs * len(order)
    steps = 0
    tracker = BestEpochTracker(mode="max", patience=config.patience)
    click.echo(
        f"    GA: {config.epochs} epochs × {len(order)} items = "
        f"{total_steps} steps, lr={config.learning_rate}"
    )
    for epoch in range(config.epochs):
        epoch_loss = 0.0
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            nll = causal_nll(model, batch)
            loss = -nll
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
            epoch_loss += nll.item()
        avg = epoch_loss / len(order)
        finished = epoch + 1
        stop = tracker.update(finished, avg, model)
        click.echo(
            f"    epoch {finished}/{config.epochs}  nll={avg:.4f}"
            f"{tracker.status()}  step={steps}/{total_steps}"
        )
        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, nll={tracker.best_score:.4f})"
            )
            break
    tracker.restore(model)
    tracker.remember(model)
    return order, steps, steps
