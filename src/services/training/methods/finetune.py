"""Standard causal NLL finetuning method (FV-ARCH-017).

Implements :class:`TrainingMethod` for supervised finetuning.
The loss is the mean token cross-entropy on the answer portion of
each QA pair.
"""

from __future__ import annotations

from typing import Any

import torch  # noqa: F401 — used by LossOutput.loss type

from src.services.data.collator import causal_nll
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig


class FinetuneMethod:
    """Standard causal NLL finetuning."""

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """No setup needed for finetune."""

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute mean token NLL on the answer tokens."""
        loss = causal_nll(model, batch)
        return LossOutput(loss=loss, log_values={"nll": loss.item()})

    def finalize(self, model: Any) -> None:
        """No cleanup needed."""
