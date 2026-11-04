"""Tests for alias-aware scoring and loss utilities.

Covers EntityAliasStore, get_probe_aliases, score_answer_aliases,
alias_log_prob, compute_entropy_loss, and the METRIC_VERSION bump.

Uses FixedLogitsLM and WordTokenizer from support_logprob.py so all
expected values are hand-computable against fixed logit rows.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest
import torch

from tests.support_logprob import FixedLogitsLM, WordTokenizer


# ── Helpers ──────────────────────────────────────────────────────────────────

def _approx(value: float, rel: float = 1e-5) -> pytest.ApproxBase:
    return pytest.approx(value, rel=rel)


def _log_softmax_manual(logits: list[float]) -> list[float]:
    """Hand-compute log_softmax for reference."""
    denom = math.log(sum(math.exp(x) for x in logits))
    return [x - denom for x in logits]


def _logsumexp_manual(*values: float) -> float:
    m = max(values)
    return m + math.log(sum(math.exp(v - m) for v in values))


# ── EntityAliasStore tests ────────────────────────────────────────────────────

def test_entity_alias_store_returns_language_filtered_aliases(tmp_path: Path) -> None:
    """EntityAliasStore.get_aliases returns only aliases for the requested language."""
    from src.train.methods.alias_score import EntityAliasStore

    entity_data = {
        "id": "factverify:entity:test_city",
        "label": "Test City",
        "alias": [
            {"value": "City A", "language": "en"},
            {"value": "City B", "language": "en"},
            {"value": "Thành phố A", "language": "vi"},
        ],
    }
    (tmp_path / "test_city.json").write_text(json.dumps(entity_data), encoding="utf-8")

    store = EntityAliasStore(tmp_path)
    en_aliases = store.get_aliases("factverify:entity:test_city", "en")
    vi_aliases = store.get_aliases("factverify:entity:test_city", "vi")

    assert en_aliases == ["City A", "City B"]
    assert vi_aliases == ["Thành phố A"]


def test_entity_alias_store_returns_empty_for_missing_entity(tmp_path: Path) -> None:
    """EntityAliasStore.get_aliases returns [] when the entity file does not exist."""
    from src.train.methods.alias_score import EntityAliasStore

    store = EntityAliasStore(tmp_path)
    result = store.get_aliases("factverify:entity:no_such_entity", "en")
    assert result == []


def test_entity_alias_store_returns_empty_for_missing_directory() -> None:
    """EntityAliasStore.get_aliases returns [] when the entities dir does not exist."""
    from src.train.methods.alias_score import EntityAliasStore

    store = EntityAliasStore(Path("/nonexistent/entities"))
    result = store.get_aliases("factverify:entity:anything", "en")
    assert result == []


# ── get_probe_aliases tests ───────────────────────────────────────────────────

def _make_probe(family: str, answer: str, entity_id: str = "", language: str = "en"):
    from src.train.data import EvalProbe
    return EvalProbe(
        probe_id="p1",
        fact_id="f1",
        family=family,
        language=language,
        question="What is the capital of Chile?",
        answer=answer,
        answer_entity_id=entity_id,
    )


def test_get_probe_aliases_verify_positive_returns_boolean_positives() -> None:
    from src.train.methods.alias_score import BOOLEAN_ALIASES, get_probe_aliases

    probe = _make_probe("verify", "True")
    result = get_probe_aliases(probe, alias_store=None)
    assert result == BOOLEAN_ALIASES["positive"]


def test_get_probe_aliases_verify_negative_returns_boolean_negatives() -> None:
    from src.train.methods.alias_score import BOOLEAN_ALIASES, get_probe_aliases

    probe = _make_probe("verify", "False")
    result = get_probe_aliases(probe, alias_store=None)
    assert result == BOOLEAN_ALIASES["negative"]


def test_get_probe_aliases_entity_family_with_store_returns_entity_aliases(tmp_path: Path) -> None:
    from src.train.methods.alias_score import EntityAliasStore, get_probe_aliases

    entity_data = {
        "id": "factverify:entity:santiago_chile",
        "label": "Santiago",
        "alias": [
            {"value": "Santiago", "language": "en"},
            {"value": "Santiago city", "language": "en"},
        ],
    }
    (tmp_path / "santiago_chile.json").write_text(json.dumps(entity_data), encoding="utf-8")
    store = EntityAliasStore(tmp_path)

    probe = _make_probe("direct", "Santiago city", entity_id="factverify:entity:santiago_chile")
    result = get_probe_aliases(probe, alias_store=store)
    assert result == ["Santiago", "Santiago city"]


def test_get_probe_aliases_no_store_returns_single_answer() -> None:
    from src.train.methods.alias_score import get_probe_aliases

    probe = _make_probe("direct", "Santiago city", entity_id="factverify:entity:santiago_chile")
    result = get_probe_aliases(probe, alias_store=None)
    assert result == ["Santiago city"]


def test_get_probe_aliases_empty_entity_aliases_falls_back_to_answer(tmp_path: Path) -> None:
    """When entity file has no aliases for the language, fall back to probe.answer."""
    from src.train.methods.alias_score import EntityAliasStore, get_probe_aliases

    entity_data = {"id": "factverify:entity:test", "label": "Test", "alias": []}
    (tmp_path / "test.json").write_text(json.dumps(entity_data), encoding="utf-8")
    store = EntityAliasStore(tmp_path)

    probe = _make_probe("direct", "Test value", entity_id="factverify:entity:test")
    result = get_probe_aliases(probe, alias_store=store)
    assert result == ["Test value"]


# ── score_answer_aliases tests ────────────────────────────────────────────────

def _build_model_tokenizer():
    """Build a FixedLogitsLM and WordTokenizer for hand-computable tests."""
    # Vocab: Q: → 0, A: → 0 (same id, doesn't matter), w0 → 0, w1 → 1, w2 → 2
    # Logits: [2.0, 1.0, 0.5, -1.0, -2.0] for a 5-word vocabulary
    logits = [2.0, 1.0, 0.5, -1.0, -2.0]
    vocab = {"Q:": 0, "What": 0, "is": 0, "this": 0, "A:": 0, "w0": 0, "w1": 1, "w2": 2}
    model = FixedLogitsLM(logits)
    tokenizer = WordTokenizer(vocab)
    return model, tokenizer, logits


def test_score_answer_aliases_single_alias_equals_score_answer_full() -> None:
    """score_answer_aliases with one alias equals _score_answer_full slp."""
    from src.train.methods.alias_score import score_answer_aliases
    from src.train.methods.fact_score import _score_answer_full

    model, tokenizer, _ = _build_model_tokenizer()
    model.eval()

    _, _, _, slp_full = _score_answer_full(model, tokenizer, "What is this", "w1")
    result = score_answer_aliases(model, tokenizer, "What is this", ["w1"])

    assert result == _approx(slp_full)


def test_score_answer_aliases_two_aliases_equals_logsumexp() -> None:
    """score_answer_aliases with two aliases equals logsumexp of their log probs."""
    from src.train.methods.alias_score import score_answer_aliases
    from src.train.methods.fact_score import _score_answer_full

    model, tokenizer, _ = _build_model_tokenizer()
    model.eval()

    _, _, _, slp1 = _score_answer_full(model, tokenizer, "What is this", "w1")
    _, _, _, slp2 = _score_answer_full(model, tokenizer, "What is this", "w2")
    expected = _logsumexp_manual(slp1, slp2)

    result = score_answer_aliases(model, tokenizer, "What is this", ["w1", "w2"])
    assert result == _approx(expected)


def test_score_answer_aliases_logsumexp_ge_single() -> None:
    """logsumexp over aliases is always ≥ any single-alias log prob."""
    from src.train.methods.alias_score import score_answer_aliases
    from src.train.methods.fact_score import _score_answer_full

    model, tokenizer, _ = _build_model_tokenizer()
    model.eval()

    _, _, _, slp1 = _score_answer_full(model, tokenizer, "What is this", "w1")
    result = score_answer_aliases(model, tokenizer, "What is this", ["w0", "w1", "w2"])

    assert result >= slp1


# ── alias_log_prob tests ──────────────────────────────────────────────────────

def test_alias_log_prob_returns_scalar_tensor() -> None:
    """alias_log_prob returns a scalar Tensor (shape ())."""
    from src.train.methods.alias_score import alias_log_prob

    model, tokenizer, _ = _build_model_tokenizer()
    model.train()

    result = alias_log_prob(model, tokenizer, "What is this", ["w1"], max_length=64)
    assert isinstance(result, torch.Tensor)
    assert result.shape == ()


def test_alias_log_prob_grad_flows_through_parameters() -> None:
    """alias_log_prob grad_fn exists when logits are connected to model parameters."""
    import torch.nn as nn
    from src.train.methods.alias_score import alias_log_prob

    # Minimal differentiable model: logits come from a Parameter directly.
    class ParamLM(nn.Module):
        def __init__(self, vocab_size: int) -> None:
            super().__init__()
            self.weight = nn.Parameter(torch.zeros(vocab_size))

        def forward(self, input_ids: torch.Tensor, **_kwargs: object) -> object:
            seq_len = input_ids.shape[1]
            logits = self.weight.view(1, 1, -1).expand(1, seq_len, -1).clone()
            return type("Out", (), {"logits": logits})()

    vocab = {"Q:": 0, "What": 0, "is": 0, "this": 0, "A:": 0, "w1": 1}
    tokenizer = WordTokenizer(vocab)
    model = ParamLM(vocab_size=5)
    model.train()

    result = alias_log_prob(model, tokenizer, "What is this", ["w1"], max_length=64)
    assert result.grad_fn is not None, "alias_log_prob must retain grad_fn for .backward()"


def test_alias_log_prob_single_alias_matches_score_answer_aliases() -> None:
    """alias_log_prob with one alias numerically matches score_answer_aliases."""
    from src.train.methods.alias_score import alias_log_prob, score_answer_aliases

    model, tokenizer, _ = _build_model_tokenizer()
    model.eval()

    with torch.no_grad():
        result_tensor = alias_log_prob(model, tokenizer, "What is this", ["w1"], max_length=64)
    result_float = score_answer_aliases(model, tokenizer, "What is this", ["w1"])

    assert float(result_tensor.item()) == _approx(result_float)


def test_alias_log_prob_two_aliases_equals_logsumexp() -> None:
    """alias_log_prob with two aliases equals logsumexp of their individual log probs."""
    from src.train.methods.alias_score import alias_log_prob, score_answer_aliases
    from src.train.methods.fact_score import _score_answer_full

    model, tokenizer, _ = _build_model_tokenizer()
    model.eval()

    _, _, _, slp1 = _score_answer_full(model, tokenizer, "What is this", "w1")
    _, _, _, slp2 = _score_answer_full(model, tokenizer, "What is this", "w2")
    expected = _logsumexp_manual(slp1, slp2)

    with torch.no_grad():
        result = alias_log_prob(model, tokenizer, "What is this", ["w1", "w2"], max_length=64)
    assert float(result.item()) == _approx(expected)


# ── compute_entropy_loss tests ────────────────────────────────────────────────

def test_compute_entropy_loss_uniform_logits_returns_zero() -> None:
    """When model already has very high entropy, entropy_loss = 0."""
    from src.train.methods.alias_score import compute_entropy_loss

    # Uniform logits → maximum entropy for 5 tokens: H = log(5) ≈ 1.609 nats
    logits = [0.0, 0.0, 0.0, 0.0, 0.0]
    vocab = {"Q:": 0, "What": 0, "A:": 0}
    model = FixedLogitsLM(logits)
    tokenizer = WordTokenizer(vocab)

    # Set target well below natural entropy (H_max = log(5) ≈ 1.609 nats)
    h_target = 0.5  # nats
    result = compute_entropy_loss(model, tokenizer, "What", max_length=64, entropy_target_nats=h_target)
    assert float(result.item()) == _approx(0.0, rel=1e-4)


def test_compute_entropy_loss_peaked_logits_returns_positive() -> None:
    """When model has low entropy, entropy_loss > 0 to push toward uncertainty."""
    from src.train.methods.alias_score import compute_entropy_loss

    # Strongly peaked at token 0: logits = [10, -10, -10, -10, -10]
    # H is very small (near 0 nats)
    logits = [10.0, -10.0, -10.0, -10.0, -10.0]
    vocab = {"Q:": 0, "What": 0, "A:": 0}
    model = FixedLogitsLM(logits)
    tokenizer = WordTokenizer(vocab)

    # Target entropy is 11 bits = 11 * ln(2) ≈ 7.62 nats
    h_target = 11.0 * math.log(2)
    result = compute_entropy_loss(model, tokenizer, "What", max_length=64, entropy_target_nats=h_target)
    assert float(result.item()) > 0.0


def test_compute_entropy_loss_returns_tensor() -> None:
    """compute_entropy_loss returns a scalar Tensor (not a float)."""
    from src.train.methods.alias_score import compute_entropy_loss

    logits = [0.0, 0.0, 0.0, 0.0, 0.0]
    vocab = {"Q:": 0, "What": 0, "A:": 0}
    model = FixedLogitsLM(logits)
    tokenizer = WordTokenizer(vocab)

    result = compute_entropy_loss(model, tokenizer, "What", max_length=64, entropy_target_nats=5.0)
    assert isinstance(result, torch.Tensor)
    assert result.shape == ()


# ── METRIC_VERSION tests ──────────────────────────────────────────────────────

def test_metric_version_is_alias_aware() -> None:
    """METRIC_VERSION must be 'alias-aware-v1' after the alias-aware refactor."""
    from src.train.methods.fact_score import METRIC_VERSION

    assert METRIC_VERSION == "alias-aware-v1"
