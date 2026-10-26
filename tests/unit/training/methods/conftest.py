"""Shared fixtures for training method tests.

Provides a tiny causal-LM-like model and a mock tokenizer that produce
correctly shaped tensors without needing real HuggingFace weights.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest
import torch
import torch.nn as nn

from src.services.training.methods.base import StepContext
from src.services.training.types import TrainingConfig


# ── Tiny model ───────────────────────────────────────────────────────


class TinyModel(nn.Module):
    """Minimal model with ``output.hidden_states`` support for RMU testing.

    - Forward with ``labels`` returns a cross-entropy ``.loss``.
    - Forward with ``output_hidden_states=True`` returns 10 identical
      hidden layers (enough to test steering layers 0..8).
    - Has a ``.config`` with ``hidden_size`` for ``_unit_direction``.
    """

    VOCAB: int = 100
    HIDDEN: int = 16

    def __init__(self) -> None:
        super().__init__()
        self.embed = nn.Embedding(self.VOCAB, self.HIDDEN)
        self.linear = nn.Linear(self.HIDDEN, self.VOCAB)
        # Expose a config object with hidden_size for RMU helpers
        self.config = SimpleNamespace(hidden_size=self.HIDDEN)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        labels: torch.Tensor | None = None,
        output_hidden_states: bool = False,
        **kwargs: Any,
    ) -> SimpleNamespace:
        h = self.embed(input_ids)
        logits = self.linear(h)
        loss = None
        if labels is not None:
            loss = nn.functional.cross_entropy(
                logits.view(-1, self.VOCAB),
                labels.view(-1),
                ignore_index=-100,
            )
        result = SimpleNamespace(loss=loss, logits=logits)
        if output_hidden_states:
            # 10 layers of identical hidden states (layer 0 = embed output)
            result.hidden_states = [h] * 10
        return result


# ── Mock tokenizer ───────────────────────────────────────────────────


@dataclass
class MockTokenizer:
    """Minimal tokenizer returning fixed-size tensors.

    Every call returns ``input_ids`` in ``[1, VOCAB)`` so they are valid
    embedding indices for :class:`TinyModel`.
    """

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
        return {
            "input_ids": torch.randint(1, TinyModel.VOCAB, (1, seq_len)),
            "attention_mask": torch.ones(1, seq_len, dtype=torch.long),
        }


# ── Pytest fixtures ──────────────────────────────────────────────────


@pytest.fixture()
def tiny_model() -> TinyModel:
    """Fresh tiny model in train mode."""
    m = TinyModel()
    m.train()
    return m


@pytest.fixture()
def mock_tokenizer() -> MockTokenizer:
    return MockTokenizer()


@pytest.fixture()
def default_config() -> TrainingConfig:
    """TrainingConfig with sensible defaults for unit tests."""
    return TrainingConfig(
        method="test",
        optimizer="adamw",
        learning_rate=1e-4,
        weight_decay=0.0,
        epochs=1,
        max_length=8,
        micro_batch_size=1,
        gradient_accumulation_steps=1,
    )


@pytest.fixture()
def sample_batch(mock_tokenizer: MockTokenizer) -> dict[str, torch.Tensor]:
    """A tokenized QA batch from the mock tokenizer, with labels."""
    from src.services.data.collator import prepare_qa_batch

    return prepare_qa_batch(mock_tokenizer, "What is X?", "Y", max_length=8)


@pytest.fixture()
def default_context() -> StepContext:
    """A StepContext with pair identity set."""
    return StepContext(
        epoch=0,
        step_in_epoch=0,
        global_step=0,
        accumulation_steps=1,
        fact_id="f1",
        question="What is X?",
        answer="Y",
    )
