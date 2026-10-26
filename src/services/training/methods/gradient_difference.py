"""Gradient difference (GradDiff) unlearning method (FV-ARCH-017).

Implements :class:`TrainingMethod` for GradDiff:

    loss = -NLL(forget) + retain_coeff * NLL(retain)

The forget term pushes the model away from the target answer while
the retain term preserves performance on retained knowledge.
Retain pairs are cycled through in order.
"""

from __future__ import annotations

import logging
from typing import Any

import torch

from src.services.data.collator import causal_nll, prepare_qa_batch
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig

logger = logging.getLogger(__name__)


class GradientDifferenceMethod:
    """GradDiff: -NLL(forget) + retain_coeff * NLL(retain)."""

    def __init__(self) -> None:
        self._retain_coeff: float = 1.0
        self._tokenizer: Any = None
        self._max_length: int = 128
        self._retain_pairs: list[tuple[str, str, str]] = []
        self._retain_idx: int = 0

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """Store retain coefficient and retain pairs for cycling.

        Parameters
        ----------
        kwargs["retain_pairs"]:
            List of ``(fact_id, question, answer)`` tuples for the retain
            set.  Cycled through during ``compute_loss``.
        """
        self._retain_coeff = config.retain_coeff if config.retain_coeff is not None else 1.0
        self._tokenizer = tokenizer
        self._max_length = config.max_length
        self._retain_pairs = kwargs.get("retain_pairs", [])
        self._retain_idx = 0
        logger.debug(
            "GradDiff: retain_coeff=%.4f, %d retain pairs",
            self._retain_coeff,
            len(self._retain_pairs),
        )

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute GradDiff loss: -forget_nll + retain_coeff * retain_nll."""
        # Forget loss (ascent)
        forget_nll = causal_nll(model, batch)

        # Retain loss (descent) — cycle through retain pairs
        retain_nll_val: float = 0.0
        if self._retain_pairs:
            _rid, rq, ra = self._retain_pairs[self._retain_idx % len(self._retain_pairs)]
            self._retain_idx += 1
            retain_batch = prepare_qa_batch(
                self._tokenizer, rq, ra, self._max_length
            )
            retain_nll = causal_nll(model, retain_batch)
            retain_nll_val = retain_nll.item()
        else:
            retain_nll = torch.tensor(0.0, device=forget_nll.device)

        loss = -forget_nll + self._retain_coeff * retain_nll
        return LossOutput(
            loss=loss,
            log_values={
                "forget_nll": forget_nll.item(),
                "retain_nll": retain_nll_val,
            },
        )

    def finalize(self, model: Any) -> None:
        """No cleanup needed."""
