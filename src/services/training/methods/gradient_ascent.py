"""Gradient ascent unlearning method (FV-ARCH-017).

Implements :class:`TrainingMethod` for gradient ascent.
The loss is the *negative* mean token cross-entropy: maximising NLL
pushes the model away from producing the target answer.
"""

from __future__ import annotations

from typing import Any

import torch

from src.services.data.collator import causal_nll
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig


class GradientAscentMethod:
    """Negative NLL for gradient ascent unlearning."""

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """No setup needed for gradient ascent."""

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute negative NLL — gradient ascent on the answer tokens."""
        nll = causal_nll(model, batch)
        loss = -nll  # Ascent: maximise NLL
        return LossOutput(loss=loss, log_values={"nll": nll.item()})

    def finalize(self, model: Any) -> None:
        """No cleanup needed."""
