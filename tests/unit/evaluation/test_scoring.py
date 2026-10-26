"""Tests for evaluation scoring functions."""

from __future__ import annotations

import pytest

from src.services.evaluation.scoring import rouge_l


class TestRougeL:
    def test_exact_match(self) -> None:
        assert rouge_l("the cat sat", "the cat sat") == pytest.approx(1.0)

    def test_no_overlap(self) -> None:
        assert rouge_l("the cat sat", "big dog ran") == pytest.approx(0.0)

    def test_partial_overlap(self) -> None:
        score = rouge_l("the cat sat on the mat", "the cat on mat")
        assert 0.0 < score < 1.0

    def test_empty_hypothesis(self) -> None:
        assert rouge_l("", "some reference") == pytest.approx(0.0)

    def test_empty_reference(self) -> None:
        assert rouge_l("some hypothesis", "") == pytest.approx(0.0)

    def test_both_empty(self) -> None:
        assert rouge_l("", "") == pytest.approx(0.0)

    def test_single_token_match(self) -> None:
        assert rouge_l("hello", "hello") == pytest.approx(1.0)

    def test_subsequence(self) -> None:
        # "a c" is a subsequence of "a b c" → LCS=2
        score = rouge_l("a c", "a b c")
        # precision=2/2=1.0, recall=2/3=0.667, F=0.8
        assert score == pytest.approx(0.8)
