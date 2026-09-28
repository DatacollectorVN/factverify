"""Negative preference optimization against the frozen parent adapter."""

from __future__ import annotations

from typing import Any

import torch

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import adamw, causal_nll, prepare_batch, read_ordered
from src.train.seeding import data_order


def train_npo(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """NPO on manifest.forget. `beta` is taken from the job."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    beta = float(config.raw["beta"])
    optimizer = adamw(model, config)
    model.train()
    steps = 0
    for _epoch in range(config.epochs):
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            nll_theta = causal_nll(model, batch)
            with torch.no_grad(), model.disable_adapter():
                nll_ref = causal_nll(model, batch)
            log_ratio = nll_ref.detach() - nll_theta
            loss = -(2.0 / beta) * torch.nn.functional.logsigmoid(-beta * log_ratio)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
    return order, steps, steps
