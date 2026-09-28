"""Scripted model, cache, and metric ports for evaluator tests."""

from __future__ import annotations

from collections.abc import Callable

from src.cache.key import CacheBody, CacheEntry, CacheEvent, CacheRequest
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
        self.data: dict[tuple[object, ...], CacheEntry] = {}

    def get_or_compute(
        self,
        request: CacheRequest,
        compute: Callable[[], CacheBody],
    ) -> tuple[CacheEntry, CacheEvent]:
        key = (
            request.identity_hash,
            request.model_input,
            tuple(sorted(request.decoding.items())),
            request.seed,
            request.sample_index,
            request.request_kind,
        )
        found = self.data.get(key)
        if found is not None:
            return found, CacheEvent("hit")
        produced = compute()
        entry = CacheEntry(
            body=produced.body,
            token_count=produced.token_count,
            created_at="",
            content_digest="",
            producer_run_id=request.producer_run_id,
        )
        self.data[key] = entry
        return entry, CacheEvent("miss")


class FixedMetrics:
    def bertscore(self, hypothesis: str, reference: str) -> float:
        del hypothesis, reference
        return 0.5
