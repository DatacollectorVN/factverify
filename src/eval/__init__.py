"""Evaluate one case under the shared query-budget accountant."""

from __future__ import annotations

from pathlib import Path

from src.eval.budget import Accountant, start_run
from src.eval.errors import FactVerifyEvalError
from src.eval.factverify import Confirmation, decide
from src.eval.gateway import CachePort, Gateway, MetricPort, ModelPort
from src.eval.native import rouge_l, score_native
from src.eval.probes import resolve_probe
from src.eval.semantic import select_equivalence
from src.eval.spec_load import SpecBundle, load_spec
from src.eval.store import RawStore, assert_outside_spec_namespace
from src.eval.thresholds import (
    GitThresholdsSource,
    ThresholdsSource,
    load_frozen_thresholds,
)
from src.eval.types import (
    ARMS,
    Bounds,
    BudgetRecord,
    Case,
    CaseResult,
    ChannelScore,
    Probe,
    VerdictRow,
)

__all__ = ["CaseResult", "FactVerifyEvalError", "evaluate_case"]


def evaluate_case(
    case: Case,
    *,
    spec_root: Path,
    raw_dir: Path,
    model: ModelPort,
    cache: CachePort,
    metrics: MetricPort,
    arm: str | None = None,
    bounds: Bounds | None = None,
    thresholds_path: Path | None = None,
    thresholds_source: ThresholdsSource | None = None,
    replay: bool = False,
) -> CaseResult:
    """Run one or all arms. Final-test loads the frozen thresholds file."""
    assert_outside_spec_namespace(raw_dir)
    bundle = load_spec(spec_root)
    start_run(bundle)
    if case.spec_revision != bundle.revision:
        raise FactVerifyEvalError("spec_revision")
    bound_map, tag = _bounds_for(
        case, bundle, bounds, thresholds_path, thresholds_source
    )
    if arm is not None and arm not in ARMS:
        raise FactVerifyEvalError(arm)
    arms = [arm] if arm is not None else list(ARMS)
    store = RawStore(raw_dir)
    verdicts: list[VerdictRow] = []
    records: list[BudgetRecord] = []
    for arm_id in arms:
        verdict, record = _run_arm(
            bundle,
            case,
            arm_id,
            model,
            cache,
            metrics,
            store,
            bound_map,
            tag,
            replay,
        )
        verdicts.append(verdict)
        records.append(record)
    raw_count = sum(store.count(case.case_id, item) for item in arms)
    return CaseResult(
        status="finished",
        verdicts=verdicts,
        budget_records=records,
        raw_count=raw_count,
    )


def _bounds_for(
    case: Case,
    bundle: SpecBundle,
    bounds: Bounds | None,
    thresholds_path: Path | None,
    thresholds_source: ThresholdsSource | None,
) -> tuple[dict[str, float], str | None]:
    del bundle
    if case.split == "final_test":
        if bounds is not None:
            raise FactVerifyEvalError("bounds")
        if thresholds_path is None:
            raise FactVerifyEvalError(thresholds_path)
        if thresholds_source is not None:
            source = thresholds_source
        else:
            source = GitThresholdsSource()
        frozen = load_frozen_thresholds(thresholds_path, source=source)
        return frozen.by_channel, frozen.tag
    if bounds is None:
        raise FactVerifyEvalError("bounds")
    if bounds.split != case.split:
        raise FactVerifyEvalError(f"bounds split {bounds.split}")
    return dict(bounds.by_channel), None


def _run_arm(
    bundle: SpecBundle,
    case: Case,
    arm_id: str,
    model: ModelPort,
    cache: CachePort,
    metrics: MetricPort,
    store: RawStore,
    bound_map: dict[str, float],
    tag: str | None,
    replay: bool,
) -> tuple[VerdictRow, BudgetRecord]:
    accountant = Accountant(bundle, arm_id)
    lines = store.read(case.case_id, arm_id) if replay else None
    gateway = Gateway(
        accountant,
        model,
        cache,
        identity_hash=case.checkpoint_ledger_id,
        replay_lines=lines,
    )
    if case.identifiability == "structurally_indistinguishable":
        verdict = decide(bundle, case, arm_id, [], None, [], tag)
        gateway.finish_measurements()
        return verdict, accountant.budget_record()
    inference_ids: list[str] = []
    confirmation: Confirmation | None = None
    if arm_id == "native":
        scores = _score_native_arm(
            bundle, case, gateway, metrics, store, arm_id, bound_map, replay
        )
    else:
        scores, inference_ids, confirmation = _score_semantic_arm(
            bundle, case, gateway, store, arm_id, bound_map, replay
        )
    gateway.finish_measurements()
    verdict = decide(bundle, case, arm_id, scores, confirmation, inference_ids, tag)
    record = accountant.budget_record()
    if not replay and store.count(case.case_id, arm_id) != record.generated_trials:
        raise FactVerifyEvalError(
            "raw "
            f"{store.count(case.case_id, arm_id)} != "
            f"charged {record.generated_trials}"
        )
    return verdict, record


def _score_native_arm(
    bundle: SpecBundle,
    case: Case,
    gateway: Gateway,
    metrics: MetricPort,
    store: RawStore,
    arm_id: str,
    bound_map: dict[str, float],
    replay: bool,
) -> list[ChannelScore]:
    scores: list[ChannelScore] = []
    for probe in case.probes:
        if resolve_probe(bundle, case, probe) != "native":
            continue
        scores.extend(score_native(bundle, case, probe, gateway, metrics, bound_map))
        _commit(store, case, arm_id, gateway, replay)
    return scores


def _score_semantic_arm(
    bundle: SpecBundle,
    case: Case,
    gateway: Gateway,
    store: RawStore,
    arm_id: str,
    bound_map: dict[str, float],
    replay: bool,
) -> tuple[list[ChannelScore], list[str], Confirmation | None]:
    primary, inference = select_equivalence(bundle, case, case.probes)
    inference_ids = [probe.template_id for probe in inference if probe.template_id]
    measured: list[tuple[Probe, float, float]] = []
    bound = bound_map.get("prompt_variation", 1.0)
    for probe in primary:
        completion = gateway.complete(
            probe, "prompt_variation", seed=case.seed, sample_index=1
        )
        value = rouge_l(completion, case.answers[0])
        gateway.note_scores({"prompt_variation": value})
        _commit(store, case, arm_id, gateway, replay)
        measured.append((probe, value, bound))
    scores: list[ChannelScore] = []
    if measured:
        best = max(item[1] for item in measured)
        scores.append(ChannelScore("prompt_variation", best, bound))
    confirmation: Confirmation | None = None
    families = {probe.family_id for probe, _, _ in measured if probe.family_id}
    crossings = [item for item in measured if item[1] > item[2]]
    if crossings and len(families) >= 2:
        first_family = measured[0][0].family_id
        other = next(
            probe for probe, _, _ in measured if probe.family_id != first_family
        )
        completion = gateway.complete(
            other, "confirmation", seed=case.seed, sample_index=1
        )
        value = rouge_l(completion, case.answers[0])
        gateway.note_scores({"confirmation": value})
        _commit(store, case, arm_id, gateway, replay)
        if value > bound and bundle.route_enabled.get("A", False):
            confirmation = Confirmation(True, "A")
    return scores, inference_ids, confirmation


def _commit(
    store: RawStore,
    case: Case,
    arm_id: str,
    gateway: Gateway,
    replay: bool,
) -> None:
    if replay or gateway.pending is None:
        gateway.pending = None
        return
    store.append(case, arm_id, gateway.pending)
    gateway.pending = None
