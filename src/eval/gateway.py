"""The only module under src/eval that calls a model or cache port."""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import torch

from src.cache.errors import CacheError
from src.cache.key import CacheBody, CacheEntry, CacheEvent, CacheRequest
from src.eval.budget import Accountant
from src.eval.errors import TransportError
from src.eval.types import Probe, QueryRequest


class ModelPort(Protocol):
    def complete(self, probe: Probe) -> str: ...

    def score_candidate(self, probe: Probe) -> dict[str, float]: ...


class CachePort(Protocol):
    def get_or_compute(
        self,
        request: CacheRequest,
        compute: Callable[[], CacheBody],
    ) -> tuple[CacheEntry, CacheEvent]: ...


class MetricPort(Protocol):
    def bertscore(self, hypothesis: str, reference: str) -> float: ...


def _is_model_call(line: str) -> bool:
    if "from_pretrained" in line or ".generate(" in line or "ModelPort." in line:
        return True
    return False


def illegal_calls_in_source(source: str, filename: str) -> list[tuple[str, int]]:
    """Return file/line pairs for model calls outside gateway.py."""
    if filename.endswith("gateway.py"):
        return []
    hits: list[tuple[str, int]] = []
    for number, line in enumerate(source.splitlines(), start=1):
        if _is_model_call(line):
            hits.append((filename, number))
    return hits


def illegal_model_calls(root: Path) -> list[tuple[str, int]]:
    found: list[tuple[str, int]] = []
    for path in sorted(root.rglob("*.py")):
        text = path.read_text(encoding="utf-8")
        found.extend(illegal_calls_in_source(text, path.name))
    return found


def gpu_hours(elapsed_seconds: float) -> float:
    """Elapsed seconds times visible CUDA devices, divided by 3600. Else 0."""
    if not torch.cuda.is_available():
        return 0.0
    return elapsed_seconds * torch.cuda.device_count() / 3600


def peak_memory_bytes() -> int:
    try:
        import resource
    except ImportError:
        return 0
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


class Gateway:
    """Check capacity, call the model, then charge. Replay never calls the model."""

    def __init__(
        self,
        accountant: Accountant,
        model: ModelPort,
        cache: CachePort,
        *,
        identity_hash: str,
        replay_lines: list[dict[str, object]] | None = None,
    ) -> None:
        self.accountant = accountant
        self.model = model
        self.cache = cache
        self.identity_hash = identity_hash
        self.replay_lines = replay_lines
        self.pending: dict[str, object] | None = None
        self._started = time.perf_counter()

    def complete(
        self,
        probe: Probe,
        channel_id: str,
        *,
        seed: int = 0,
        sample_index: int = 1,
    ) -> str:
        if self.replay_lines is not None:
            return str(self._replay(probe.probe_id, channel_id)["completion"])
        request = self._cache_request(probe, seed, sample_index, "generate")

        def compute() -> CacheBody:
            charged = self._request(probe, channel_id, "generation", seed)
            self.accountant.ensure_capacity(channel_id, probe_trials(charged), charged)
            try:
                text = self.model.complete(probe)
            except TransportError:
                failure = self._request(probe, channel_id, "transport_failure", seed)
                self.accountant.query(channel_id, failure)
                raise
            return CacheBody(body=text, token_count=0)

        entry, event = self._cached(
            channel_id, probe, seed, request, compute, "generation"
        )
        if event.kind in {"miss", "corrupt"}:
            self.pending = self._line(probe, channel_id, str(entry.body), seed)
        return str(entry.body)

    def score(self, probe: Probe, channel_id: str) -> dict[str, float]:
        if self.replay_lines is not None:
            stored = self._replay(probe.probe_id, channel_id).get("metric_scores", {})
            if not isinstance(stored, dict):
                return {}
            return {str(key): float(value) for key, value in stored.items()}
        request = self._cache_request(probe, 0, 1, "score")

        def compute() -> CacheBody:
            raw = self.model.score_candidate(probe)
            body: dict[str, object] = {key: value for key, value in raw.items()}
            return CacheBody(body=body, token_count=0)

        entry, _event = self._cached(
            channel_id, probe, 0, request, compute, "candidate_score"
        )
        raw = entry.body
        if not isinstance(raw, dict):
            return {}
        scores: dict[str, float] = {}
        for key, value in raw.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                return {}
            scores[str(key)] = float(value)
        if self.pending is not None:
            bucket = self.pending.setdefault("metric_scores", {})
            if isinstance(bucket, dict):
                bucket.update(scores)
        return scores

    def note_scores(self, scores: dict[str, float]) -> None:
        if self.pending is None:
            return
        bucket = self.pending.setdefault("metric_scores", {})
        if isinstance(bucket, dict):
            bucket.update(scores)

    def finish_measurements(self) -> None:
        elapsed = time.perf_counter() - self._started
        self.accountant.wall_clock_seconds = elapsed
        self.accountant.gpu_hours = gpu_hours(elapsed)
        self.accountant.peak_memory_bytes = peak_memory_bytes()

    def _cache_request(
        self, probe: Probe, seed: int, sample_index: int, request_kind: str
    ) -> CacheRequest:
        return CacheRequest(
            identity_hash=self.identity_hash,
            model_input=probe.prompt,
            decoding={"probe_id": probe.probe_id, "seed": seed},
            seed=seed,
            sample_index=sample_index,
            request_kind=request_kind,
            producer_run_id=self.accountant.arm_id,
        )

    def _cached(
        self,
        channel_id: str,
        probe: Probe,
        seed: int,
        request: CacheRequest,
        compute: Callable[[], CacheBody],
        miss_kind: str,
    ) -> tuple[CacheEntry, CacheEvent]:
        try:
            entry, event = self.cache.get_or_compute(request, compute)
        except CacheError as exc:
            if exc.message != "conflict":
                raise
            charged = self._request(probe, channel_id, "generation", seed)
            self.accountant.query(channel_id, charged)
            if exc.event is not None:
                self.accountant.note_cache_event(exc.event)
            raise
        kind = "cache_hit" if event.kind == "hit" else miss_kind
        charged = self._request(probe, channel_id, kind, seed)
        self.accountant.query(channel_id, charged)
        self.accountant.note_cache_event(event)
        return entry, event

    def _replay(self, probe_id: str, channel_id: str) -> dict[str, object]:
        assert self.replay_lines is not None
        for line in self.replay_lines:
            same_probe = line.get("probe_id") == probe_id
            same_channel = line.get("channel_id") == channel_id
            if same_probe and same_channel:
                return line
        for line in self.replay_lines:
            if line.get("probe_id") == probe_id:
                return line
        from src.eval.errors import FactVerifyEvalError

        raise FactVerifyEvalError(probe_id)

    def _request(
        self, probe: Probe, channel_id: str, kind: str, seed: int
    ) -> QueryRequest:
        return QueryRequest(
            channel_id=channel_id,
            kind=kind,
            probe_id=probe.probe_id,
            prompt_count=1,
            sample_count=1,
            decoding={"seed": seed},
            seed=seed,
        )

    def _line(
        self,
        probe: Probe,
        channel_id: str,
        completion: str,
        seed: int,
    ) -> dict[str, object]:
        return {
            "probe_id": probe.probe_id,
            "channel_id": channel_id,
            "prompt": probe.prompt,
            "completion": completion,
            "decoding": {"seed": seed},
            "seed": seed,
            "metric_scores": {},
        }


def probe_trials(request: QueryRequest) -> int:
    return request.prompt_count * request.sample_count
