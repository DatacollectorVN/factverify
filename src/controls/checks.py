"""Retention and locality checks. Numbers come from the decision record or the spec."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Protocol

from src.controls.decisions import DecisionRow
from src.controls.errors import ControlError
from src.controls.spec_load import ControlSpec


class BehaviorPort(Protocol):
    """Direct-QA and locality measurements. Tests script this."""

    def direct_qa_accuracy(
        self, system_id: str, fact_id: str, *, mechanism_enabled: bool
    ) -> float:
        """Accuracy on the target fact. `system_id` is `disabled` or `parent`."""

    def delta_loc(self, system_id: str, bucket: str) -> float:
        """Locality change for one bucket."""


@dataclass(frozen=True)
class CheckOutcome:
    """accepted, rejected, or unchecked. Unchecked names the unresolved field."""

    status: str
    reason: str | None
    measured: dict[str, float]
    threshold: str
    error_name: str


def check_retention(
    behavior: BehaviorPort, fact_id: str, decision: DecisionRow
) -> CheckOutcome:
    """Compare the disabled control with the parent. Open D-54 does not measure."""
    if decision.status != "closed" or decision.max_abs_gap is None:
        return CheckOutcome("unchecked", None, {}, "", "D-54")
    gap = _gap(decision.max_abs_gap)
    disabled = behavior.direct_qa_accuracy("disabled", fact_id, mechanism_enabled=False)
    parent = behavior.direct_qa_accuracy("parent", fact_id, mechanism_enabled=False)
    measured = {"disabled": disabled, "parent": parent}
    difference = abs(Decimal(str(disabled)) - Decimal(str(parent)))
    if difference <= gap:
        return CheckOutcome("accepted", None, measured, decision.max_abs_gap, "")
    return CheckOutcome("rejected", "retention_gap", measured, decision.max_abs_gap, "")


def margins_resolved(spec: ControlSpec, family: str) -> tuple[bool, str]:
    """True when every bucket this family requires has a non-null margin.

    Does not call the behavior port — safe to call before training.
    Returns (resolved, error_name).
    """
    if family == "targeted_damage":
        buckets: tuple[str, ...] = ("same_subject", "same_relation")
    elif family == "broad_destruction":
        buckets = ("global",)
    else:
        raise ControlError(family)
    for bucket in buckets:
        margin = spec.margins.get(bucket)
        if margin is None or margin.value is None:
            return False, "margin.value"
    return True, ""


def check_locality(
    behavior: BehaviorPort, family: str, spec: ControlSpec
) -> CheckOutcome:
    """Targeted damage uses a local bucket. Broad destruction uses global only."""
    if family == "targeted_damage":
        buckets = ("same_subject", "same_relation")
    elif family == "broad_destruction":
        buckets = ("global",)
    else:
        raise ControlError(family)
    parsed: list[tuple[str, float, float, str]] = []
    for bucket in buckets:
        margin = spec.margins.get(bucket)
        if margin is None or margin.value is None:
            return CheckOutcome("unchecked", None, {}, "", "margin.value")
        measured = behavior.delta_loc("control", bucket)
        parsed.append((bucket, measured, margin.value, margin.orientation))
    values = {bucket: measured for bucket, measured, _, _ in parsed}
    passed = [
        bucket
        for bucket, measured, value, orientation in parsed
        if _beyond(measured, value, orientation)
    ]
    threshold = str(parsed[0][2])
    if passed:
        return CheckOutcome("accepted", None, values, threshold, "")
    return CheckOutcome("rejected", "locality_margin", values, threshold, "")


def _gap(text: str) -> Decimal:
    try:
        gap = Decimal(text)
    except InvalidOperation as exc:
        raise ControlError("D-54") from exc
    if gap < 0 or gap > 1:
        raise ControlError("D-54")
    return gap


def _beyond(measured: float, value: float, orientation: str) -> bool:
    if orientation == "upper":
        return measured > value
    if orientation == "lower":
        return measured < value
    raise ControlError(orientation)
