"""TrainingMethod protocol and supporting types (FV-ARCH-017).

Every training method (finetune, GA, GradDiff, NPO, RMU) implements
:class:`TrainingMethod`. The shared engine calls ``compute_loss`` once per
micro-batch and handles all gradient accumulation, clipping, and optimizer
stepping externally.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

import torch

from src.services.training.types import TrainingConfig


@dataclass
class LossOutput:
    """Result of one ``compute_loss`` call."""

    loss: torch.Tensor  # scalar loss to backpropagate
    log_values: dict[str, float] = field(default_factory=dict)  # e.g. "forget_nll"


@dataclass(frozen=True)
class StepContext:
    """Per-step context passed to ``compute_loss``."""

    epoch: int
    step_in_epoch: int
    global_step: int
    accumulation_steps: int
    # Pair identity — allows methods (NPO, GradDiff, RMU) to look up
    # pre-computed data keyed by the current training example.
    fact_id: str = ""
    question: str = ""
    answer: str = ""


class TrainingMethod(Protocol):
    """Protocol for training methods.

    Implementations must be stateless with respect to the optimizer: they
    compute a loss and return it. The engine manages the backward pass,
    gradient accumulation, clipping, and optimizer stepping.
    """

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """One-time setup before training (e.g., pre-compute reference NLLs)."""
        ...

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute loss for one micro-batch. Must not call ``optimizer.step()``."""
        ...

    def finalize(self, model: Any) -> None:
        """Clean-up after training (optional)."""
        ...
