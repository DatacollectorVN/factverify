"""Negative Preference Optimisation (NPO) unlearning method (FV-ARCH-017).

Implements :class:`TrainingMethod` for NPO:

    log_ratio = ref_nll - nll_theta
    loss = -(2 / beta) * logsigmoid(-beta * log_ratio)

Reference NLLs are pre-computed from the model's initial state during
``prepare()`` and looked up per step via the ``(question, answer)``
pair identity carried in :class:`StepContext`.
"""

from __future__ import annotations

import logging
from typing import Any

import torch
import torch.nn.functional as F

from src.services.data.collator import causal_nll, prepare_qa_batch
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig

logger = logging.getLogger(__name__)


class NPOMethod:
    """Negative preference optimisation for unlearning."""

    def __init__(self) -> None:
        self._beta: float = 0.1
        self._ref_nll: dict[tuple[str, str], float] = {}

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """Pre-compute reference NLLs from the model's current state.

        Parameters
        ----------
        kwargs["pairs"]:
            List of ``(fact_id, question, answer)`` tuples.
            Reference NLLs are computed for each unique ``(question, answer)``.
        kwargs["ref_nll_map"]:
            Optional pre-computed map; if provided, ``pairs`` is ignored.
        """
        self._beta = config.beta if config.beta is not None else 0.1

        # Accept pre-computed map or build from pairs
        ref_nll_map: dict[tuple[str, str], float] | None = kwargs.get("ref_nll_map")
        if ref_nll_map is not None:
            self._ref_nll = dict(ref_nll_map)
            logger.debug("NPO: received %d pre-computed reference NLLs", len(self._ref_nll))
            return

        pairs: list[tuple[str, str, str]] = kwargs.get("pairs", [])
        if not pairs:
            logger.warning("NPO: no pairs provided — reference NLLs will be empty")
            return

        model.eval()
        with torch.no_grad():
            for _fid, q, a in pairs:
                key = (q, a)
                if key not in self._ref_nll:
                    batch = prepare_qa_batch(tokenizer, q, a, config.max_length)
                    self._ref_nll[key] = causal_nll(model, batch).item()
        model.train()
        logger.debug("NPO: pre-computed %d reference NLLs, beta=%.4f", len(self._ref_nll), self._beta)

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute NPO loss using pre-computed reference NLL."""
        nll_theta = causal_nll(model, batch)

        key = (context.question, context.answer)
        if key not in self._ref_nll:
            raise KeyError(
                f"NPO: no reference NLL for pair ({context.question!r}, "
                f"{context.answer!r}). Did you pass pairs to prepare()?"
            )

        ref_nll = torch.tensor(self._ref_nll[key], device=nll_theta.device)
        log_ratio = ref_nll - nll_theta
        loss = -(2.0 / self._beta) * F.logsigmoid(-self._beta * log_ratio)

        return LossOutput(
            loss=loss,
            log_values={"nll": nll_theta.item(), "ref_nll": ref_nll.item()},
        )

    def finalize(self, model: Any) -> None:
        """No cleanup needed."""
