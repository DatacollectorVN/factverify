"""Scripted model, cache, and metric ports for evaluator tests."""

from __future__ import annotations

from src.eval.types import Probe


class ScriptedModel:
    """Returns fixed text and scores. Does not load weights."""

    def __init__(
        self,
        completion: str = "Zephyr",
        scores: dict[str, float] | None = None,
        *,
        fail: bool = False,
    ) -> None:
        self.completion = completion
        self.scores = scores or {
            "truth_ratio": 0.2,
            "answer_probability": 0.2,
            "answer_rank": 1.0,
        }
        self.fail = fail
        self.calls = 0

    def complete(self, probe: Probe) -> str:
        del probe
        self.calls += 1
        if self.fail:
            raise AssertionError("model called")
        return self.completion

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        del probe
        self.calls += 1
        if self.fail:
            raise AssertionError("model called")
        return dict(self.scores)


class DictCache:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], str] = {}

    def get(self, key: tuple[str, str]) -> str | None:
        return self.data.get(key)

    def put(self, key: tuple[str, str], value: str) -> None:
        self.data[key] = value


class FixedMetrics:
    def bertscore(self, hypothesis: str, reference: str) -> float:
        del hypothesis, reference
        return 0.5
