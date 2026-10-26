"""Tests for NPOMethod (FV-ARCH-017)."""

from __future__ import annotations

from dataclasses import replace

import pytest

torch = pytest.importorskip("torch")

from src.services.training.methods.npo import NPOMethod  # noqa: E402
from src.services.training.types import TrainingConfig  # noqa: E402


class TestNPOMethod:
    """NPO computes -(2/beta) * logsigmoid(-beta * log_ratio)."""

    def test_loss_positive(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """NPO loss is non-negative (logsigmoid is always <= 0, so negated >= 0)."""
        config = replace(default_config, beta=0.1)
        pairs = [("f1", "What is X?", "Y")]
        method = NPOMethod()
        method.prepare(tiny_model, mock_tokenizer, config, pairs=pairs)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() >= 0.0, "NPO loss must be non-negative"

    def test_prepare_computes_ref_nlls(
        self, tiny_model, mock_tokenizer, default_config
    ):
        """After prepare(), the reference NLL map is populated."""
        config = replace(default_config, beta=0.1)
        pairs = [("f1", "What is X?", "Y"), ("f2", "What is Z?", "W")]
        method = NPOMethod()
        method.prepare(tiny_model, mock_tokenizer, config, pairs=pairs)
        assert len(method._ref_nll) == 2
        assert ("What is X?", "Y") in method._ref_nll
        assert ("What is Z?", "W") in method._ref_nll
        # Reference NLLs should be positive (they are cross-entropy losses)
        for val in method._ref_nll.values():
            assert val > 0.0

    def test_pre_supplied_ref_nll_map(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        """Pre-computed ref_nll_map is accepted directly."""
        config = replace(default_config, beta=0.5)
        ref_map = {("What is X?", "Y"): 2.5}
        method = NPOMethod()
        method.prepare(
            tiny_model, mock_tokenizer, config, ref_nll_map=ref_map
        )
        assert method._ref_nll == ref_map
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert output.loss.item() >= 0.0

    def test_missing_ref_nll_raises(
        self, tiny_model, mock_tokenizer, default_config, sample_batch
    ):
        """KeyError if ref NLL not found for the current pair."""
        config = replace(default_config, beta=0.1)
        method = NPOMethod()
        method.prepare(tiny_model, mock_tokenizer, config)

        from src.services.training.methods.base import StepContext

        ctx = StepContext(
            epoch=0,
            step_in_epoch=0,
            global_step=0,
            accumulation_steps=1,
            fact_id="f1",
            question="unknown question",
            answer="unknown answer",
        )
        with pytest.raises(KeyError, match="no reference NLL"):
            method.compute_loss(tiny_model, sample_batch, ctx)

    def test_log_values(
        self, tiny_model, mock_tokenizer, default_config, sample_batch, default_context
    ):
        config = replace(default_config, beta=0.1)
        pairs = [("f1", "What is X?", "Y")]
        method = NPOMethod()
        method.prepare(tiny_model, mock_tokenizer, config, pairs=pairs)
        output = method.compute_loss(tiny_model, sample_batch, default_context)
        assert "nll" in output.log_values
        assert "ref_nll" in output.log_values
