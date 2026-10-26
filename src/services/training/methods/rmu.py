"""Representation Misdirection for Unlearning (RMU) method (FV-ARCH-017).

Implements :class:`TrainingMethod` for RMU:

    forget_loss = MSE(hidden - steering_coeff * direction)
    retain_loss = MSE(hidden - frozen_reference)
    loss = forget_loss + retain_loss

Hidden representations are mean-pooled at a specified steering layer.
Frozen retain-pair hidden states and the random steering direction are
pre-computed during ``prepare()``.
"""

from __future__ import annotations

import logging
from typing import Any

import torch

from src.services.data.collator import prepare_qa_batch
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig

logger = logging.getLogger(__name__)


class RMUMethod:
    """Representation misdirection for unlearning."""

    def __init__(self) -> None:
        self._steering_coeff: float = 100.0
        self._steering_layer: int = 7
        self._direction: torch.Tensor | None = None
        self._tokenizer: Any = None
        self._max_length: int = 128
        self._retain_pairs: list[tuple[str, str, str]] = []
        self._retain_idx: int = 0
        self._frozen_states: dict[tuple[str, str], torch.Tensor] = {}

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        """Pre-compute random steering direction and frozen retain states.

        Parameters
        ----------
        kwargs["retain_pairs"]:
            List of ``(fact_id, question, answer)`` tuples for the retain set.
        kwargs["seed"]:
            Seed for the random steering direction.  Falls back to 42.
        """
        self._steering_coeff = (
            config.steering_coeff if config.steering_coeff is not None else 100.0
        )
        self._steering_layer = (
            config.steering_layer if config.steering_layer is not None else 7
        )
        self._tokenizer = tokenizer
        self._max_length = config.max_length
        self._retain_pairs = kwargs.get("retain_pairs", [])
        self._retain_idx = 0

        seed: int = kwargs.get("seed", 42)
        self._direction = _unit_direction(model, seed)

        # Pre-compute frozen hidden states for retain pairs
        if self._retain_pairs:
            model.eval()
            with torch.no_grad():
                for _rid, rq, ra in self._retain_pairs:
                    key = (rq, ra)
                    if key not in self._frozen_states:
                        batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                        self._frozen_states[key] = _pooled(
                            model, batch, self._steering_layer
                        ).cpu()
            model.train()

        logger.debug(
            "RMU: steering_coeff=%.1f, layer=%d, direction dim=%d, "
            "%d frozen states",
            self._steering_coeff,
            self._steering_layer,
            self._direction.shape[0],
            len(self._frozen_states),
        )

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        """Compute RMU loss: forget steering + retain anchoring."""
        assert self._direction is not None, "prepare() must be called before compute_loss()"

        # Forget: steer hidden representation toward random direction
        current_f = _pooled(model, batch, self._steering_layer)
        target = self._steering_coeff * self._direction.to(current_f.device)
        forget_loss = torch.mean((current_f - target) ** 2)

        # Retain: anchor to frozen reference (cycle through retain pairs)
        retain_loss_val: float = 0.0
        if self._retain_pairs:
            _rid, rq, ra = self._retain_pairs[
                self._retain_idx % len(self._retain_pairs)
            ]
            self._retain_idx += 1
            retain_batch = prepare_qa_batch(
                self._tokenizer, rq, ra, self._max_length
            )
            current_r = _pooled(model, retain_batch, self._steering_layer)
            frozen = self._frozen_states[(rq, ra)].to(current_r.device)
            retain_loss = torch.mean((current_r - frozen) ** 2)
            retain_loss_val = retain_loss.item()
        else:
            retain_loss = torch.tensor(0.0, device=current_f.device)

        loss = forget_loss + retain_loss
        return LossOutput(
            loss=loss,
            log_values={
                "forget_loss": forget_loss.item(),
                "retain_loss": retain_loss_val,
            },
        )

    def finalize(self, model: Any) -> None:
        """No cleanup needed."""


# ── Helpers (ported from src/train/methods/rmu.py) ────────────────────


def _unit_direction(model: Any, seed: int) -> torch.Tensor:
    """Random unit vector in hidden-state space, seeded for reproducibility."""
    model_config = getattr(model, "config", None)
    if model_config is None:
        base = model.get_base_model() if hasattr(model, "get_base_model") else model
        model_config = base.config
    hidden = getattr(model_config, "hidden_size", None) or getattr(
        model_config, "n_embd", None
    )
    if hidden is None:
        raise ValueError("Cannot determine hidden size from model config")
    generator = torch.Generator()
    generator.manual_seed(seed)
    vector = torch.randn(int(hidden), generator=generator)
    return vector / vector.norm()


def _pooled(
    model: Any, batch: dict[str, torch.Tensor], layer: int
) -> torch.Tensor:
    """Mean-pooled hidden state at ``layer`` (attention-mask-aware)."""
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
