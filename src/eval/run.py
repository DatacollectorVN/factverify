"""CLI: python -m src.eval.run --case PATH --spec-root PATH --raw-dir PATH."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from src.cache.key import CacheBody, CacheEntry, CacheEvent, CacheRequest
from src.eval import evaluate_case
from src.eval.errors import FactVerifyEvalError
from src.eval.gateway import CachePort, MetricPort, ModelPort
from src.eval.spec_load import case_from_path, load_spec
from src.eval.types import Bounds, Case, Probe


class _MemoryCache:
    def __init__(self) -> None:
        self._data: dict[tuple[object, ...], CacheEntry] = {}

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
        found = self._data.get(key)
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
        self._data[key] = entry
        return entry, CacheEvent("miss")


class _FixedMetrics:
    def bertscore(self, hypothesis: str, reference: str) -> float:
        del hypothesis, reference
        return 0.5


class _FixtureModel:
    """Completions for fixture-eval specs. Study specs never reach this."""

    def complete(self, probe: Probe) -> str:
        del probe
        return "Zephyr"

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        del probe
        return {
            "truth_ratio": 0.2,
            "answer_probability": 0.2,
            "answer_rank": 1.0,
        }


class _MissingModel:
    def complete(self, probe: Probe) -> str:
        del probe
        raise FactVerifyEvalError("model port")

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        del probe
        raise FactVerifyEvalError("model port")


def _ports(spec_root: Path) -> tuple[ModelPort, CachePort, MetricPort, Bounds | None]:
    bundle = load_spec(spec_root)
    model: ModelPort
    if bundle.revision == "fixture-eval":
        model = _FixtureModel()
    else:
        model = _MissingModel()
    return model, _MemoryCache(), _FixedMetrics(), None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m src.eval.run")
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--spec-root", type=Path, default=Path(".factverify"))
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--arm", default=None)
    args = parser.parse_args(argv)
    try:
        case = case_from_path(args.case)
        model, cache, metrics, _unused = _ports(args.spec_root)
        bounds = _fixture_bounds(case, args.spec_root)
        result = evaluate_case(
            case,
            spec_root=args.spec_root,
            raw_dir=args.raw_dir,
            model=model,
            cache=cache,
            metrics=metrics,
            arm=args.arm,
            bounds=bounds,
        )
    except FactVerifyEvalError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if result.status != "finished":
        print(result.error or "refused", file=sys.stderr)
        return 1
    print(result.verdicts[0].status)
    return 0


def _fixture_bounds(case: Case, spec_root: Path) -> Bounds | None:
    bundle = load_spec(spec_root)
    if bundle.revision != "fixture-eval" or case.split == "final_test":
        return None
    return Bounds(
        split=case.split,
        by_channel={
            "rouge_l": 1.0,
            "bertscore": 1.0,
            "truth_ratio": 1.0,
            "answer_probability": 1.0,
            "answer_rank": 1.0,
            "prompt_variation": 1.0,
        },
    )


if __name__ == "__main__":
    raise SystemExit(main())
