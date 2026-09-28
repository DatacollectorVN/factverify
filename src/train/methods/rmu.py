"""Representation misdirection at a job-specified layer."""

from __future__ import annotations

from typing import Any

import torch

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import adamw, prepare_batch, read_ordered
from src.train.seeding import data_order


def train_rmu(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Steer forget states and keep retain states near the frozen parent.

    `steering_coeff` and `steering_layer` come from the job. The steer direction
    is a unit vector drawn from the job seed.
    """
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    layer = int(config.raw["steering_layer"])
    coeff = float(config.raw["steering_coeff"])
    forget_ids = set(config.manifest["forget"])
    direction = _unit_direction(model, config.seed)
    optimizer = adamw(model, config)
    model.train()
    steps = 0
    for _epoch in range(config.epochs):
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            current = _pooled(model, batch, layer)
            if item_id in forget_ids:
                target = coeff * direction.to(current.device)
                loss = torch.mean((current - target) ** 2)
            else:
                with torch.no_grad(), model.disable_adapter():
                    frozen = _pooled(model, batch, layer)
                loss = torch.mean((current - frozen.detach()) ** 2)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
    return order, steps, steps


def _unit_direction(model: Any, seed: int) -> torch.Tensor:
    base = model.get_base_model() if hasattr(model, "get_base_model") else model
    hidden = int(base.config.n_embd)
    generator = torch.Generator()
    generator.manual_seed(seed)
    vector = torch.randn(hidden, generator=generator)
    return vector / vector.norm()


def _pooled(model: Any, batch: dict[str, torch.Tensor], layer: int) -> torch.Tensor:
    device = next(model.parameters()).device
    moved = {key: value.to(device) for key, value in batch.items()}
    output = model(
        input_ids=moved["input_ids"],
        attention_mask=moved["attention_mask"],
        output_hidden_states=True,
    )
    hidden = output.hidden_states[layer + 1]
    mask = moved["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    denom = mask.sum(dim=1).clamp_min(1.0)
    return (hidden * mask).sum(dim=1) / denom
