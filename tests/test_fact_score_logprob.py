"""Whole-answer, family, and fact-level log-probability scoring.

Covers requirement test items 1, 2, and 8 of
``requirements/learner-forgetter-drop-retention-scoring.md``:

  1. whole-answer probability with deterministic multi-token logits
  2. family and fact geometric means against hand-calculated fixtures
  8. very small probabilities remain finite in log space
"""

from __future__ import annotations

import math
from pathlib import Path

from src.train.data import DataCatalog
from src.train.methods.fact_score import (
    _score_answer_full,
    score_catalog_families,
    score_fact_families,
)
from tests.support_logprob import CharTokenizer, FixedLogitsLM, write_eval_corpus

# Fixed 5-class logit row shared by every position (the fake model ignores
# the actual input entirely). Index 4 has an extremely low logit so its
# softmax probability underflows toward zero while its log probability
# must stay finite.
_LOGITS = [0.0, 1.0, 2.0, -5.0, -60.0]


def _reference_log_softmax(logits: list[float]) -> list[float]:
    """Independent reference: log p_i = x_i - log(sum_j exp(x_j))."""
    denom = math.log(sum(math.exp(x) for x in logits))
    return [x - denom for x in logits]


class _WordTokenizer:
    """Maps whitespace-separated words to caller-provided token ids."""

    pad_token_id: int | None = 0
    eos_token_id: int = 0

    def __init__(self, vocab: dict[str, int]) -> None:
        self.vocab = vocab

    def __call__(self, text: str, return_tensors: str = "pt"):
        import torch

        ids = [self.vocab[word] for word in text.split()]
        if not ids:
            ids = [0]
        return {"input_ids": torch.tensor([ids])}

    def decode(self, ids, skip_special_tokens: bool = True) -> str:
        return "model output"


def test_sequence_log_probability_is_sum_not_mean_of_token_log_probs() -> None:
    """Item 1: deterministic multi-token logits, hand-computed sequence log prob."""
    vocab = {"Q:": 0, "q1": 0, "A:": 0, "ans1": 2, "ans2": 4}
    tokenizer = _WordTokenizer(vocab)
    model = FixedLogitsLM(_LOGITS)

    _vl, _ap, _ar, slp = _score_answer_full(model, tokenizer, "q1", "ans1 ans2")

    ls = _reference_log_softmax(_LOGITS)
    expected_sum = ls[2] + ls[4]
    expected_mean = (ls[2] + ls[4]) / 2

    assert slp == _approx(expected_sum)
    # The whole-answer log probability must be the *sum*, not the mean —
    # the two differ by a large, unmistakable margin here.
    assert abs(slp - expected_mean) > 10


def test_very_small_probability_remains_finite_in_log_space() -> None:
    """Item 8: an (almost) zero-probability token stays finite, never -inf/NaN."""
    vocab = {"Q:": 0, "q1": 0, "A:": 0, "ans_rare": 4}
    tokenizer = _WordTokenizer(vocab)
    model = FixedLogitsLM(_LOGITS)

    _vl, ap, _ar, slp = _score_answer_full(model, tokenizer, "q1", "ans_rare")

    ls = _reference_log_softmax(_LOGITS)
    assert slp == _approx(ls[4])
    assert math.isfinite(slp)
    assert not math.isnan(slp)
    # The mean-token probability (legacy metric) correspondingly underflows
    # toward zero but must not raise or produce NaN either.
    assert 0.0 <= ap < 1e-6


def test_family_and_fact_log_probability_against_handcalculated_fixture(
    tmp_path: Path,
) -> None:
    """Item 2: family log prob = mean of probe log probs; fact = mean of families."""
    vocab = {
        "Q:": 0, "A:": 0,
        "q1": 0, "q2": 0, "q3": 0,
        "w0": 0, "w1": 1, "w2": 2,
    }
    tokenizer = _WordTokenizer(vocab)
    model = FixedLogitsLM(_LOGITS)

    probes = [
        {"_id": 1, "Q": "q1", "A": "w0", "ec": "direct", "language": "en"},
        {"_id": 2, "Q": "q2", "A": "w1", "ec": "direct", "language": "en"},
        {"_id": 3, "Q": "q3", "A": "w2", "ec": "cloze", "language": "en"},
    ]
    write_eval_corpus(tmp_path / "fact-x.json", probes)
    catalog = DataCatalog(tmp_path, ["fact-x"])

    result = score_fact_families(model, tokenizer, catalog, "fact-x")
    assert result is not None

    ls = _reference_log_softmax(_LOGITS)
    expected_direct = (ls[0] + ls[1]) / 2
    expected_cloze = ls[2]
    expected_fact = (expected_direct + expected_cloze) / 2

    assert result.families["direct"].family_log_probability == _approx(expected_direct)
    assert result.families["cloze"].family_log_probability == _approx(expected_cloze)
    assert result.fact_log_probability == _approx(expected_fact)

    # Raw probe rows reproduce the aggregate and carry id/family/language.
    direct_probes = result.families["direct"].probes
    assert {p.probe_id for p in direct_probes} == {"fact-x:1", "fact-x:2"}
    assert all(p.family == "direct" for p in direct_probes)
    assert all(p.language == "en" for p in direct_probes)
    assert sum(p.sequence_log_probability for p in direct_probes) / 2 == _approx(
        expected_direct
    )


def test_score_catalog_families_covers_every_fact(tmp_path: Path) -> None:
    """score_catalog_families scores every fact in the catalog, skipping none."""
    vocab = {"Q:": 0, "A:": 0, "q": 0, "w0": 0}
    tokenizer = _WordTokenizer(vocab)
    model = FixedLogitsLM(_LOGITS)

    probes = [{"_id": 1, "Q": "q", "A": "w0", "ec": "direct", "language": "en"}]
    write_eval_corpus(tmp_path / "fact-a.json", probes)
    write_eval_corpus(tmp_path / "fact-b.json", probes)
    catalog = DataCatalog(tmp_path, ["fact-a", "fact-b"])

    scored = score_catalog_families(model, tokenizer, catalog)
    assert set(scored) == {"fact-a", "fact-b"}


def _approx(value: float, rel: float = 1e-6):
    import pytest

    return pytest.approx(value, rel=rel, abs=1e-9)
