"""Optimizer construction for the shared training engine.

Ported from ``src/train/methods/common.py:adamw``.
"""

from __future__ import annotations

from typing import Any

import torch

from src.services.training.types import TrainingConfig


def build_optimizer(model: Any, config: TrainingConfig) -> torch.optim.Optimizer:
    """AdamW over trainable parameters. Coefficients come only from the config."""
    parameters = [p for p in model.parameters() if p.requires_grad]
    return torch.optim.AdamW(
        parameters,
        lr=config.learning_rate,
        weight_decay=config.weight_decay,
    )
