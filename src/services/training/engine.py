"""Shared training loop for all training methods (FV-ARCH-017).

Extracted from the five duplicated epoch loops in ``src/train/methods/``.
The engine owns gradient accumulation (with partial-window rescaling),
gradient clipping, optimizer stepping, deterministic shuffling, early
stopping, and counter validation. It delegates loss computation to the
:class:`TrainingMethod` protocol.

Counter validation (FV-ARCH-019): after every epoch the engine asserts
that the observed optimizer step count matches
``ceil(N / effective_batch_size)`` (or the sum over all epochs at the
end). A mismatch raises :class:`TrainingError`.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import torch

from src.services.common.errors import TrainingError
from src.services.common.reproducibility import epoch_pair_order
from src.services.data.collator import prepare_qa_batch
from src.services.training.methods.base import LossOutput, StepContext, TrainingMethod
from src.services.training.optimizer import build_optimizer
from src.services.training.types import TrainingConfig


@dataclass(frozen=True)
class EngineConfig:
    """Configuration for the shared training loop."""

    epochs: int
    micro_batch_size: int
    gradient_accumulation_steps: int
    max_grad_norm: float
    shuffle_each_epoch: bool
    seed: int
    patience: int | None
    save_best_as: str  # metric name for best-checkpoint selection
    score_mode: str  # "min" or "max"
    max_length: int = 128

    @property
    def effective_batch_size(self) -> int:
        return self.micro_batch_size * self.gradient_accumulation_steps


@dataclass
class EngineCounters:
    """Accumulated counters validated at the end of training (FV-ARCH-019)."""

    total_examples: int = 0
    total_backward_passes: int = 0
    total_optimizer_steps: int = 0
    epochs_completed: int = 0


@dataclass
class EpochResult:
    """Summary of one completed epoch, passed to ``on_epoch_end``."""

    epoch: int
    avg_loss: float
    optimizer_steps: int
    backward_passes: int
    examples: int
    log_values: dict[str, float] = field(default_factory=dict)


def run_training_loop(
    method: TrainingMethod,
    model: Any,
    pairs: list[tuple[str, str, str]],  # (fact_id, question, answer)
    engine_config: EngineConfig,
    tokenizer: Any,
    *,
    training_config: TrainingConfig | None = None,
    on_epoch_end: Callable[[EpochResult, Any], bool | None] | None = None,
    logger: logging.Logger | None = None,
) -> EngineCounters:
    """Run the training loop. Returns accumulated counters.

    Parameters
    ----------
    method:
        A :class:`TrainingMethod` implementation (finetune, GA, etc.).
    model:
        The model to train. Must have ``parameters()`` and ``state_dict()``.
    pairs:
        Flat list of ``(fact_id, question, answer)`` training examples.
    engine_config:
        Loop hyperparameters (epochs, accumulation, clipping, etc.).
    tokenizer:
        HuggingFace-compatible tokenizer.
    training_config:
        Full :class:`TrainingConfig` passed to ``method.prepare()``.
        When ``None``, a default is synthesised from ``engine_config``.
    on_epoch_end:
        Optional callback ``(epoch_result, model) -> should_stop``.
        Return ``True`` to request early stopping for this epoch.
    logger:
        Python logger; falls back to ``logging.getLogger(__name__)``.
    """
    log = logger or logging.getLogger(__name__)

    if not pairs:
        raise TrainingError("no training pairs provided")

    n_pairs = len(pairs)
    accum_steps = engine_config.gradient_accumulation_steps
    effective_bs = engine_config.effective_batch_size
    expected_steps_per_epoch = math.ceil(n_pairs / effective_bs)

    # ── Build optimizer and prepare method ──────────────────────────────
    if training_config is None:
        training_config = TrainingConfig(
            method="engine",
            optimizer="adamw",
            learning_rate=1e-4,
            weight_decay=0.0,
            epochs=engine_config.epochs,
            max_length=engine_config.max_length,
            micro_batch_size=engine_config.micro_batch_size,
            gradient_accumulation_steps=accum_steps,
            patience=engine_config.patience,
            max_grad_norm=engine_config.max_grad_norm,
            shuffle_each_epoch=engine_config.shuffle_each_epoch,
            save_best_as=engine_config.save_best_as,
        )

    optimizer = build_optimizer(model, training_config)
    method.prepare(model, tokenizer, training_config)

    counters = EngineCounters()
    global_step = 0

    log.debug(
        "engine: %d epochs x %d pairs, accum=%d, effective_bs=%d, "
        "expected_steps/epoch=%d",
        engine_config.epochs,
        n_pairs,
        accum_steps,
        effective_bs,
        expected_steps_per_epoch,
    )

    micro_bs = engine_config.micro_batch_size

    # ── Epoch loop ─────────────────────────────────────────────────────
    for epoch in range(engine_config.epochs):
        # Deterministic per-epoch shuffling
        if engine_config.shuffle_each_epoch:
            epoch_pairs = epoch_pair_order(pairs, engine_config.seed, epoch)
        else:
            epoch_pairs = pairs

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_optimizer_steps = 0
        epoch_backward = 0
        epoch_log_values: dict[str, list[float]] = {}

        # Group examples into micro-batches of size micro_batch_size.
        # Each micro-batch is one accumulation step; after
        # gradient_accumulation_steps micro-batches the optimizer steps.
        n_micro_batches = math.ceil(n_pairs / micro_bs)

        optimizer.zero_grad()
        accum_count = 0

        for mb_idx in range(n_micro_batches):
            mb_start = mb_idx * micro_bs
            mb_end = min(mb_start + micro_bs, n_pairs)
            mb_pairs = epoch_pairs[mb_start:mb_end]
            mb_size = len(mb_pairs)

            # Forward + backward for every example in this micro-batch
            for ex_offset, (fact_id, question, answer) in enumerate(mb_pairs):
                batch = prepare_qa_batch(
                    tokenizer, question, answer, engine_config.max_length
                )

                context = StepContext(
                    epoch=epoch,
                    step_in_epoch=mb_start + ex_offset,
                    global_step=global_step,
                    accumulation_steps=accum_steps,
                    fact_id=fact_id,
                    question=question,
                    answer=answer,
                )

                loss_output: LossOutput = method.compute_loss(
                    model, batch, context
                )

                # Scale: divide by (accum_steps × mb_size) so that the
                # mean gradient over the full effective batch is correct.
                scaled_loss = loss_output.loss / (accum_steps * mb_size)
                scaled_loss.backward()
                epoch_backward += 1
                epoch_loss += loss_output.loss.item()
                epoch_examples += 1
                global_step += 1

                for key, val in loss_output.log_values.items():
                    epoch_log_values.setdefault(key, []).append(val)

            accum_count += 1

            # ── Optimizer step at accumulation boundary or end ──────
            if accum_count == accum_steps or mb_idx == n_micro_batches - 1:
                # Partial-window rescaling: if the last accumulation
                # window has fewer micro-batches, re-scale so the
                # effective learning rate matches full windows.
                if accum_count < accum_steps:
                    scale = accum_steps / accum_count
                    for param in model.parameters():
                        if param.grad is not None:
                            param.grad.mul_(scale)

                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), engine_config.max_grad_norm
                )
                optimizer.step()
                optimizer.zero_grad()
                epoch_optimizer_steps += 1
                accum_count = 0

        # ── Counter validation (FV-ARCH-019) ───────────────────────────
        if epoch_optimizer_steps != expected_steps_per_epoch:
            raise TrainingError(
                f"counter validation failed: epoch {epoch} had "
                f"{epoch_optimizer_steps} optimizer steps, expected "
                f"{expected_steps_per_epoch} (n_pairs={n_pairs}, "
                f"effective_bs={effective_bs})"
            )

        counters.total_examples += epoch_examples
        counters.total_backward_passes += epoch_backward
        counters.total_optimizer_steps += epoch_optimizer_steps
        counters.epochs_completed += 1

        avg_loss = epoch_loss / n_pairs if n_pairs > 0 else 0.0

        # Average the per-step log values
        avg_log_values = {
            key: sum(vals) / len(vals) for key, vals in epoch_log_values.items()
        }

        epoch_result = EpochResult(
            epoch=epoch,
            avg_loss=avg_loss,
            optimizer_steps=epoch_optimizer_steps,
            backward_passes=epoch_backward,
            examples=epoch_examples,
            log_values=avg_log_values,
        )

        log.debug(
            "epoch %d: loss=%.4f, steps=%d, bwd=%d, examples=%d",
            epoch,
            avg_loss,
            epoch_optimizer_steps,
            epoch_backward,
            epoch_examples,
        )

        # ── Epoch-end callback (eval / early stopping) ─────────────
        if on_epoch_end is not None:
            should_stop = on_epoch_end(epoch_result, model)
            if should_stop:
                log.debug("early stop requested at epoch %d", epoch)
                break

    # ── Method finalization ─────────────────────────────────────────────
    method.finalize(model)

    return counters
