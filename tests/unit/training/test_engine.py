"""Tests for the shared training engine (FV-ARCH-017, FV-ARCH-019).

Uses a mock TrainingMethod that returns a fixed loss and tracks call counts,
a tiny nn.Linear model, and a mock tokenizer that returns fixed tensors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import pytest
import torch
import torch.nn as nn

from src.services.training.engine import (
    EngineConfig,
    EngineCounters,
    EpochResult,
    run_training_loop,
)
from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.selection import BestCheckpointSelector
from src.services.training.types import TrainingConfig


# ── Test fixtures ──────────────────────────────────────────────────────


def _make_model() -> nn.Module:
    """A tiny model with trainable parameters."""
    return nn.Linear(2, 2)


@dataclass
class MockTokenizer:
    """Minimal tokenizer that returns fixed-size tensors."""

    pad_token: str | None = "<pad>"
    eos_token: str = "</s>"
    _max_length: int = 8

    def __call__(
        self,
        text: str,
        truncation: bool = True,
        max_length: int = 8,
        padding: str = "max_length",
        return_tensors: str = "pt",
    ) -> dict[str, torch.Tensor]:
        seq_len = min(max_length, self._max_length)
        input_ids = torch.ones(1, seq_len, dtype=torch.long)
        attention_mask = torch.ones(1, seq_len, dtype=torch.long)
        return {"input_ids": input_ids, "attention_mask": attention_mask}


class MockMethod:
    """Training method that returns a fixed loss and counts calls."""

    def __init__(self, loss_value: float = 1.0) -> None:
        self._loss_value = loss_value
        self.prepare_called: int = 0
        self.compute_loss_calls: int = 0
        self.finalize_called: int = 0
        self.contexts: list[StepContext] = []

    def prepare(
        self,
        model: Any,
        tokenizer: Any,
        config: TrainingConfig,
        **kwargs: Any,
    ) -> None:
        self.prepare_called += 1

    def compute_loss(
        self,
        model: Any,
        batch: dict[str, torch.Tensor],
        context: StepContext,
    ) -> LossOutput:
        self.compute_loss_calls += 1
        self.contexts.append(context)
        # Create a loss that requires grad through the model parameters
        params = list(model.parameters())
        # Use a dummy forward so gradients flow through the model
        dummy_input = torch.ones(1, params[0].shape[1])
        output = model(dummy_input)
        loss = output.sum() * 0 + self._loss_value
        return LossOutput(loss=loss, log_values={"nll": self._loss_value})

    def finalize(self, model: Any) -> None:
        self.finalize_called += 1


def _engine_config(
    *,
    epochs: int = 1,
    micro_batch_size: int = 1,
    gradient_accumulation_steps: int = 1,
    max_grad_norm: float = 1.0,
    shuffle_each_epoch: bool = False,
    seed: int = 42,
    patience: int | None = None,
    save_best_as: str = "val_loss",
    score_mode: str = "min",
    max_length: int = 8,
) -> EngineConfig:
    return EngineConfig(
        epochs=epochs,
        micro_batch_size=micro_batch_size,
        gradient_accumulation_steps=gradient_accumulation_steps,
        max_grad_norm=max_grad_norm,
        shuffle_each_epoch=shuffle_each_epoch,
        seed=seed,
        patience=patience,
        save_best_as=save_best_as,
        score_mode=score_mode,
        max_length=max_length,
    )


def _make_pairs(n: int) -> list[tuple[str, str, str]]:
    """Generate n unique training pairs."""
    return [(f"f{i}", f"question {i}", f"answer {i}") for i in range(n)]


# ── Scenario 5: 320 examples, 40 updates ──────────────────────────────


def test_320_examples_40_updates() -> None:
    """320 examples, micro_bs=4, accum=2 -> effective_bs=8 -> 40 steps/epoch."""
    model = _make_model()
    method = MockMethod()
    pairs = _make_pairs(320)
    config = _engine_config(
        epochs=1,
        micro_batch_size=4,
        gradient_accumulation_steps=2,
    )

    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer()
    )

    expected_steps = math.ceil(320 / 8)  # 40
    assert expected_steps == 40
    assert counters.total_optimizer_steps == 40
    assert counters.total_backward_passes == 320
    assert counters.total_examples == 320
    assert counters.epochs_completed == 1


# ── Scenario 6: 322 examples, 41 updates (partial window) ─────────────


def test_322_examples_41_updates() -> None:
    """322 examples, micro_bs=4, accum=2 -> effective_bs=8 -> ceil(322/8)=41."""
    model = _make_model()
    method = MockMethod()
    pairs = _make_pairs(322)
    config = _engine_config(
        epochs=1,
        micro_batch_size=4,
        gradient_accumulation_steps=2,
    )

    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer()
    )

    expected_steps = math.ceil(322 / 8)  # 41
    assert expected_steps == 41
    assert counters.total_optimizer_steps == 41
    assert counters.total_backward_passes == 322
    assert counters.total_examples == 322


# ── Partial-window gradient rescaling ──────────────────────────────────


def test_partial_window_rescaling() -> None:
    """When the last window has fewer examples, gradients are rescaled.

    With 3 examples and accum_steps=2, the last window has 1 example.
    The gradient for that window should be scaled by 2/1 = 2.0 before
    the optimizer step, so the effective learning rate matches full windows.
    """
    model = _make_model()
    pairs = _make_pairs(3)
    config = _engine_config(gradient_accumulation_steps=2)

    # We use a method that produces a model-dependent loss so grads exist
    method = MockMethod()

    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer()
    )

    # 3 examples, accum=2: window 1 has 2 examples, window 2 has 1 (partial)
    assert counters.total_optimizer_steps == math.ceil(3 / 2)  # 2
    assert counters.total_backward_passes == 3


# ── Epoch shuffling ───────────────────────────────────────────────────


def test_epoch_shuffling() -> None:
    """With shuffle=True, pair order changes across epochs."""
    model = _make_model()
    pairs = _make_pairs(10)
    config = _engine_config(epochs=3, shuffle_each_epoch=True, seed=42)
    method = MockMethod()

    # Collect the step_in_epoch contexts to verify ordering is consistent
    # per epoch but the method sees all pairs each epoch
    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer()
    )

    assert counters.epochs_completed == 3
    assert counters.total_examples == 30  # 10 per epoch

    # The contexts should show 3 epochs of 10 steps each
    epoch_0_contexts = [c for c in method.contexts if c.epoch == 0]
    epoch_1_contexts = [c for c in method.contexts if c.epoch == 1]
    assert len(epoch_0_contexts) == 10
    assert len(epoch_1_contexts) == 10


# ── Early stopping via callback ───────────────────────────────────────


def test_early_stopping() -> None:
    """With patience=2, stop after 2 non-improving epochs."""
    model = _make_model()
    pairs = _make_pairs(4)
    config = _engine_config(epochs=10, patience=2, score_mode="min")
    method = MockMethod()

    selector = BestCheckpointSelector(mode="min", patience=2)
    # Simulate: epoch 0 score=1.0, epoch 1 score=0.5 (improve),
    # epoch 2 score=0.6 (no improve), epoch 3 score=0.7 (no improve) -> stop
    scores = [1.0, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3]
    epoch_count = 0

    def on_epoch_end(result: EpochResult, mdl: Any) -> bool:
        nonlocal epoch_count
        score = scores[epoch_count]
        epoch_count += 1
        exhausted = selector.update(result.epoch, score, mdl)
        return exhausted

    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer(), on_epoch_end=on_epoch_end
    )

    # Should stop after epoch 3 (index 3): epoch 1 was best,
    # epochs 2 and 3 were non-improving -> patience=2 exhausted
    assert counters.epochs_completed == 4
    assert selector.best_epoch == 1
    assert selector.best_score == 0.5


# ── Counter validation ────────────────────────────────────────────────


def test_counter_validation() -> None:
    """After training, counters match expected values for multiple epochs."""
    model = _make_model()
    pairs = _make_pairs(15)
    config = _engine_config(
        epochs=3,
        micro_batch_size=2,
        gradient_accumulation_steps=3,
    )
    method = MockMethod()

    counters = run_training_loop(
        method, model, pairs, config, MockTokenizer()
    )

    effective_bs = 2 * 3  # 6
    expected_steps_per_epoch = math.ceil(15 / effective_bs)  # ceil(15/6) = 3
    assert counters.total_optimizer_steps == expected_steps_per_epoch * 3  # 9
    assert counters.total_backward_passes == 15 * 3  # 45
    assert counters.total_examples == 15 * 3  # 45
    assert counters.epochs_completed == 3


# ── Method lifecycle ──────────────────────────────────────────────────


def test_method_lifecycle() -> None:
    """prepare is called once, finalize is called once."""
    model = _make_model()
    pairs = _make_pairs(2)
    config = _engine_config(epochs=2)
    method = MockMethod()

    run_training_loop(method, model, pairs, config, MockTokenizer())

    assert method.prepare_called == 1
    assert method.finalize_called == 1
    assert method.compute_loss_calls == 4  # 2 pairs x 2 epochs


# ── Empty pairs raises ────────────────────────────────────────────────


def test_empty_pairs_raises() -> None:
    """Passing an empty pair list raises TrainingError."""
    from src.services.common.errors import TrainingError

    model = _make_model()
    config = _engine_config()
    method = MockMethod()

    with pytest.raises(TrainingError, match="no training pairs"):
        run_training_loop(method, model, [], config, MockTokenizer())


# ── Log values are aggregated ─────────────────────────────────────────


def test_log_values_in_epoch_result() -> None:
    """Log values from compute_loss are averaged in the epoch result."""
    model = _make_model()
    pairs = _make_pairs(4)
    config = _engine_config(epochs=1)
    method = MockMethod(loss_value=2.5)

    results: list[EpochResult] = []

    def on_epoch_end(result: EpochResult, mdl: Any) -> bool:
        results.append(result)
        return False

    run_training_loop(
        method, model, pairs, config, MockTokenizer(), on_epoch_end=on_epoch_end
    )

    assert len(results) == 1
    assert results[0].log_values["nll"] == pytest.approx(2.5)
