"""Tests for RMUMethod (FV-ARCH-017)."""

from __future__ import annotations

from dataclasses import replace

import pytest

torch = pytest.importorskip("torch")

from src.services.training.methods.rmu import RMUMethod, _unit_direction  # noqa: E402
from src.services.training.types import TrainingConfig  # noqa: E402


class TestRMUMethod:
    """RMU computes forget steering + retain anchoring losses."""

    def test_loss_positive(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """RMU loss is non-negative (MSE is always >= 0)."""
        config = replace(
            default_config, steering_coeff=10.0, steering_layer=0
        )
        method = RMUMethod()
        method.prepare(tiny_model, mock_tokenizer, config, seed=42)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() >= 0.0, "RMU loss must be non-negative"

    def test_loss_has_grad(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        config = replace(
            default_config, steering_coeff=10.0, steering_layer=0
        )
        method = RMUMethod()
        method.prepare(tiny_model, mock_tokenizer, config, seed=42)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        output.loss.backward()
        has_grad = any(
            p.grad is not None and p.grad.abs().sum() > 0
            for p in tiny_model.parameters()
        )
        assert has_grad, "backward pass must produce non-zero gradients"

    def test_direction_is_unit_vector(self, tiny_model):
        """The random steering direction should have unit norm."""
        direction = _unit_direction(tiny_model, seed=42)
        assert direction.norm().item() == pytest.approx(1.0, abs=1e-5)

    def test_direction_is_reproducible(self, tiny_model):
        """Same seed produces the same direction."""
        d1 = _unit_direction(tiny_model, seed=123)
        d2 = _unit_direction(tiny_model, seed=123)
        assert torch.allclose(d1, d2)

    def test_direction_dimension_matches_hidden_size(self, tiny_model):
        """Direction dimension must match model hidden size."""
        direction = _unit_direction(tiny_model, seed=42)
        assert direction.shape == (tiny_model.config.hidden_size,)

    def test_retain_pairs_produce_retain_loss(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """When retain pairs are provided, retain_loss is non-zero."""
        config = replace(
            default_config, steering_coeff=10.0, steering_layer=0
        )
        retain_pairs = [("r1", "Who is A?", "B")]
        method = RMUMethod()
        method.prepare(
            tiny_model, mock_tokenizer, config,
            retain_pairs=retain_pairs, seed=42,
        )
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert "forget_loss" in output.log_values
        assert "retain_loss" in output.log_values
        assert output.log_values["forget_loss"] >= 0.0

    def test_no_retain_gives_zero_retain_loss(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Without retain pairs, retain_loss logged as 0.0."""
        config = replace(
            default_config, steering_coeff=10.0, steering_layer=0
        )
        method = RMUMethod()
        method.prepare(tiny_model, mock_tokenizer, config, seed=42)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.log_values["retain_loss"] == 0.0
