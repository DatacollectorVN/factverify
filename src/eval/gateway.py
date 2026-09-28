"""The only module under src/eval that calls a model or cache port."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Protocol

from src.eval.budget import Accountant
from src.eval.errors import TransportError
from src.eval.types import Probe, QueryRequest


class ModelPort(Protocol):
    def complete(self, probe: Probe) -> str: ...

    def score_candidate(self, probe: Probe) -> dict[str, float]: ...


class CachePort(Protocol):
    def get(self, key: tuple[str, str]) -> str | None: ...

    def put(self, key: tuple[str, str], value: str) -> None: ...


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
    try:
        import torch
    except ImportError:
        return 0.0
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
        replay_lines: list[dict[str, object]] | None = None,
    ) -> None:
        self.accountant = accountant
        self.model = model
        self.cache = cache
        self.replay_lines = replay_lines
        self.pending: dict[str, object] | None = None
        self._started = time.perf_counter()

    def complete(self, probe: Probe, channel_id: str, *, seed: int = 0) -> str:
        if self.replay_lines is not None:
            return str(self._replay(probe.probe_id, channel_id)["completion"])
        key = (probe.probe_id, channel_id)
        cached = self.cache.get(key)
        if cached is not None:
            request = self._request(probe, channel_id, "cache_hit", seed)
            self.accountant.query(channel_id, request)
            return cached
        request = self._request(probe, channel_id, "generation", seed)
        self.accountant.ensure_capacity(channel_id, probe_trials(request), request)
        try:
            completion = self.model.complete(probe)
        except TransportError:
            failure = self._request(probe, channel_id, "transport_failure", seed)
            self.accountant.query(channel_id, failure)
            raise
        self.accountant.query(channel_id, request)
        self.cache.put(key, completion)
        self.pending = self._line(probe, channel_id, completion, seed)
        return completion

    def score(self, probe: Probe, channel_id: str) -> dict[str, float]:
        if self.replay_lines is not None:
            stored = self._replay(probe.probe_id, channel_id).get("metric_scores", {})
            if not isinstance(stored, dict):
                return {}
            return {str(key): float(value) for key, value in stored.items()}
        request = self._request(probe, channel_id, "candidate_score", 0)
        self.accountant.query(channel_id, request)
        raw = self.model.score_candidate(probe)
        if self.pending is not None:
            scores = self.pending.setdefault("metric_scores", {})
            if isinstance(scores, dict):
                scores.update(raw)
        return raw

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
