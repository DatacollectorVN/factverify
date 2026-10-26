"""Tests for FinetuneMethod (FV-ARCH-017)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")

from src.services.training.methods.finetune import FinetuneMethod  # noqa: E402
from src.services.training.methods.base import StepContext  # noqa: E402


class TestFinetuneMethod:
    """FinetuneMethod returns positive NLL with gradient."""

    def test_loss_is_positive(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        method = FinetuneMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() > 0.0, "finetune NLL must be positive"

    def test_loss_has_grad(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        method = FinetuneMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        output.loss.backward()
        has_grad = any(
            p.grad is not None and p.grad.abs().sum() > 0
            for p in tiny_model.parameters()
        )
        assert has_grad, "backward pass must produce non-zero gradients"

    def test_log_values_has_nll(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        method = FinetuneMethod()
        method.prepare(tiny_model, mock_tokenizer, default_config)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert "nll" in output.log_values
        assert output.log_values["nll"] == pytest.approx(output.loss.item())
