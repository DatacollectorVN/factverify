"""Loss-level characterization tests for all five TrainingMethod implementations.

Each test uses a tiny model (nn.Linear or custom) and mock tokenizer
to verify the sign and properties of the computed loss.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

torch = pytest.importorskip("torch")
nn = torch.nn

from src.services.training.methods.base import LossOutput, StepContext
from src.services.training.types import TrainingConfig


# ── Shared fixtures ──────────────────────────────────────────────────────


class TinyModel(nn.Module):
    """Tiny model that produces loss from labels and hidden_states for RMU."""

    def __init__(self, vocab: int = 100, hidden: int = 16) -> None:
        super().__init__()
        self.embed = nn.Embedding(vocab, hidden)
        self.head = nn.Linear(hidden, vocab)
        self.config = SimpleNamespace(hidden_size=hidden)

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor | None = None,
        labels: torch.Tensor | None = None,
        output_hidden_states: bool = False,
        **kwargs: Any,
    ) -> SimpleNamespace:
        h = self.embed(input_ids)
        logits = self.head(h)
        loss = None
        if labels is not None:
            loss = nn.functional.cross_entropy(
                logits.view(-1, logits.size(-1)),
                labels.view(-1),
                ignore_index=-100,
            )
        result = SimpleNamespace(loss=loss, logits=logits)
        if output_hidden_states:
            # Return enough layers for RMU (layer+1 indexing)
            result.hidden_states = [h] * 12
        return result


class MockTokenizer:
    pad_token: str | None = "<pad>"
    eos_token: str = "</s>"

    def __call__(
        self,
        text: str,
        truncation: bool = True,
        max_length: int = 8,
        padding: str = "max_length",
        return_tensors: str = "pt",
    ) -> dict[str, torch.Tensor]:
        seq_len = min(max_length, 8)
        return {
            "input_ids": torch.randint(1, 50, (1, seq_len)),
            "attention_mask": torch.ones(1, seq_len, dtype=torch.long),
        }


def _default_config(**overrides: Any) -> TrainingConfig:
    defaults = dict(
        method="test",
        optimizer="adamw",
        learning_rate=1e-4,
        weight_decay=0.0,
        epochs=1,
        max_length=8,
        micro_batch_size=1,
        gradient_accumulation_steps=1,
    )
    defaults.update(overrides)
    return TrainingConfig(**defaults)


def _context() -> StepContext:
    return StepContext(
        epoch=0,
        step_in_epoch=0,
        global_step=0,
        accumulation_steps=1,
        fact_id="f1",
        question="What is X?",
        answer="Y",
    )


def _make_batch(tokenizer: MockTokenizer, model: TinyModel) -> dict[str, torch.Tensor]:
    """Create a batch with labels for causal NLL."""
    encoded = tokenizer("Q: What is X?\nA: Y")
    input_ids = encoded["input_ids"]
    attention_mask = encoded["attention_mask"]
    labels = input_ids.clone()
    labels[attention_mask == 0] = -100
    return {"input_ids": input_ids, "attention_mask": attention_mask, "labels": labels}


# ── Finetune ─────────────────────────────────────────────────────────────


class TestFinetuneMethod:
    def test_loss_is_positive(self) -> None:
        from src.services.training.methods.finetune import FinetuneMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = FinetuneMethod()
        method.prepare(model, tokenizer, _default_config())
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.item() > 0

    def test_loss_has_grad(self) -> None:
        from src.services.training.methods.finetune import FinetuneMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = FinetuneMethod()
        method.prepare(model, tokenizer, _default_config())
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.requires_grad

    def test_log_values(self) -> None:
        from src.services.training.methods.finetune import FinetuneMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = FinetuneMethod()
        method.prepare(model, tokenizer, _default_config())
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert "nll" in output.log_values


# ── Gradient Ascent ──────────────────────────────────────────────────────


class TestGradientAscentMethod:
    def test_loss_is_negative(self) -> None:
        from src.services.training.methods.gradient_ascent import GradientAscentMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = GradientAscentMethod()
        method.prepare(model, tokenizer, _default_config())
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.item() < 0

    def test_magnitude_matches_finetune(self) -> None:
        from src.services.training.methods.finetune import FinetuneMethod
        from src.services.training.methods.gradient_ascent import GradientAscentMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        batch = _make_batch(tokenizer, model)
        ctx = _context()
        cfg = _default_config()

        ft = FinetuneMethod()
        ft.prepare(model, tokenizer, cfg)
        ft_loss = ft.compute_loss(model, batch, ctx).loss.item()

        ga = GradientAscentMethod()
        ga.prepare(model, tokenizer, cfg)
        ga_loss = ga.compute_loss(model, batch, ctx).loss.item()

        assert abs(ga_loss) == pytest.approx(ft_loss)


# ── Gradient Difference ──────────────────────────────────────────────────


class TestGradientDifferenceMethod:
    def test_log_values_have_components(self) -> None:
        from src.services.training.methods.gradient_difference import GradientDifferenceMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        retain_pairs = [("r1", "What is R?", "R answer")]
        method = GradientDifferenceMethod()
        method.prepare(
            model, tokenizer, _default_config(retain_coeff=0.5),
            retain_pairs=retain_pairs,
        )
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert "forget_nll" in output.log_values
        assert "retain_nll" in output.log_values

    def test_loss_has_grad(self) -> None:
        from src.services.training.methods.gradient_difference import GradientDifferenceMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = GradientDifferenceMethod()
        method.prepare(model, tokenizer, _default_config(retain_coeff=1.0))
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.requires_grad


# ── NPO ──────────────────────────────────────────────────────────────────


class TestNPOMethod:
    def test_prepare_computes_ref_nlls(self) -> None:
        from src.services.training.methods.npo import NPOMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        pairs = [("f1", "What is X?", "Y"), ("f2", "What is Z?", "W")]
        method = NPOMethod()
        method.prepare(
            model, tokenizer, _default_config(beta=0.1), pairs=pairs
        )
        assert len(method._ref_nll) >= 1

    def test_loss_has_grad(self) -> None:
        from src.services.training.methods.npo import NPOMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        pairs = [("f1", "What is X?", "Y")]
        method = NPOMethod()
        method.prepare(
            model, tokenizer, _default_config(beta=0.1), pairs=pairs
        )
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.requires_grad


# ── RMU ──────────────────────────────────────────────────────────────────


class TestRMUMethod:
    def test_loss_is_positive(self) -> None:
        from src.services.training.methods.rmu import RMUMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        method = RMUMethod()
        method.prepare(
            model, tokenizer,
            _default_config(steering_coeff=10.0, steering_layer=0),
            seed=42,
        )
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert output.loss.item() >= 0

    def test_direction_is_unit_vector(self) -> None:
        from src.services.training.methods.rmu import RMUMethod, _unit_direction

        model = TinyModel()
        direction = _unit_direction(model, seed=42)
        assert direction.norm().item() == pytest.approx(1.0, abs=1e-5)

    def test_log_values(self) -> None:
        from src.services.training.methods.rmu import RMUMethod

        model = TinyModel()
        tokenizer = MockTokenizer()
        retain_pairs = [("r1", "What is R?", "R answer")]
        method = RMUMethod()
        method.prepare(
            model, tokenizer,
            _default_config(steering_coeff=10.0, steering_layer=0),
            retain_pairs=retain_pairs, seed=42,
        )
        batch = _make_batch(tokenizer, model)
        output = method.compute_loss(model, batch, _context())
        assert "forget_loss" in output.log_values
        assert "retain_loss" in output.log_values
