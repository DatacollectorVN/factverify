"""Tests for GradientDifferenceMethod (FV-ARCH-017)."""

from __future__ import annotations

from dataclasses import replace

import pytest

torch = pytest.importorskip("torch")

from src.services.training.methods.gradient_difference import GradientDifferenceMethod  # noqa: E402
from src.services.training.types import TrainingConfig  # noqa: E402


class TestGradientDifferenceMethod:
    """GradDiff computes -forget_nll + retain_coeff * retain_nll."""

    def test_loss_has_forget_and_retain_components(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        config = replace(default_config, retain_coeff=1.0)
        retain_pairs = [("r1", "Who is A?", "B")]
        method = GradientDifferenceMethod()
        method.prepare(
            tiny_model, mock_tokenizer, config, retain_pairs=retain_pairs
        )
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert "forget_nll" in output.log_values
        assert "retain_nll" in output.log_values
        assert output.log_values["forget_nll"] > 0.0
        assert output.log_values["retain_nll"] > 0.0

    def test_retain_coeff_scales(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Higher retain_coeff shifts the loss toward the retain term."""
        retain_pairs = [("r1", "Who is A?", "B")]

        config_low = replace(default_config, retain_coeff=0.1)
        method_low = GradientDifferenceMethod()
        method_low.prepare(
            tiny_model, mock_tokenizer, config_low, retain_pairs=retain_pairs
        )
        out_low = method_low.compute_loss(tiny_model, sample_batch, default_context)

        config_high = replace(default_config, retain_coeff=10.0)
        method_high = GradientDifferenceMethod()
        method_high.prepare(
            tiny_model, mock_tokenizer, config_high, retain_pairs=retain_pairs
        )
        out_high = method_high.compute_loss(tiny_model, sample_batch, default_context)

        # With higher retain_coeff, the total loss should be more positive
        # because the positive retain term dominates more.
        assert out_high.loss.item() > out_low.loss.item(), (
            "higher retain_coeff should increase loss (retain term dominates)"
        )

    def test_no_retain_pairs_gives_pure_ascent(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Without retain pairs, loss is pure -NLL (gradient ascent)."""
        method = GradientDifferenceMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() < 0.0, "without retain, loss = -forget_nll < 0"
        assert output.log_values["retain_nll"] == 0.0

    def test_retain_cycling(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Retain pairs cycle when more steps than pairs."""
        retain_pairs = [("r1", "Q1?", "A1"), ("r2", "Q2?", "A2")]
        method = GradientDifferenceMethod()
        method.prepare(
            tiny_model, mock_tokenizer, default_config, retain_pairs=retain_pairs
        )
        # Call 3 times — should cycle: r1, r2, r1
        for _ in range(3):
            out = method.compute_loss(tiny_model, sample_batch, default_context)
            out.loss.backward()
            tiny_model.zero_grad()
        assert method._retain_idx == 3
