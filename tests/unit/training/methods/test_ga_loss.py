"""Tests for GradientAscentMethod (FV-ARCH-017)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from src.services.training.methods.finetune import FinetuneMethod  # noqa: E402
from src.services.training.methods.gradient_ascent import GradientAscentMethod  # noqa: E402


class TestGradientAscentMethod:
    """GradientAscentMethod returns negative NLL."""

    def test_loss_is_negative(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        method = GradientAscentMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() < 0.0, "GA loss must be negative (= -NLL)"

    def test_loss_magnitude_matches_finetune(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Absolute value of GA loss equals finetune (positive) NLL."""
        ft = FinetuneMethod()
        ft.prepare(tiny_model, mock_tokenizer, default_config)
        ft_output = ft.compute_loss(tiny_model, sample_batch, default_context)

        ga = GradientAscentMethod()
        ga.prepare(tiny_model, mock_tokenizer, default_config)
        ga_output = ga.compute_loss(tiny_model, sample_batch, default_context)

        assert abs(ga_output.loss.item()) == pytest.approx(
            ft_output.loss.item(), rel=1e-5
        ), "|GA loss| must equal finetune NLL"

    def test_log_values_has_nll(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        method = GradientAscentMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert "nll" in output.log_values
        # log_values["nll"] is the positive NLL, not the negated loss
        assert output.log_values["nll"] > 0.0
