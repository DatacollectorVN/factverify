"""Four public statuses. Spec codes sit underneath and are not a fifth status."""

from __future__ import annotations

from src.eval.errors import FactVerifyEvalError
from src.eval.types import (
    STATUS_CODES,
    STATUS_PHRASES,
    ChannelScore,
    Diagnostics,
    VerdictRow,
)

_FORBIDDEN = ("average", "combined_score", "mean_score")


def reject_combined_average(payload: dict[str, object]) -> None:
    """Refuse a payload that averages channel scores."""
    for key in _FORBIDDEN:
        if key in payload:
            raise FactVerifyEvalError(key)
    scores = payload.get("scores")
    if isinstance(scores, dict):
        for key in _FORBIDDEN:
            if key in scores:
                raise FactVerifyEvalError(key)


def build_verdict(
    *,
    status: str,
    access_label: str,
    arm_id: str,
    checkpoint_ledger_id: str,
    fact_id: str,
    split: str,
    spec_revision: str,
    scores: list[ChannelScore],
    raw_maximum: float | None = None,
    confirmation_route: str | None = None,
    inference_output: list[str] | None = None,
    thresholds_tag: str | None = None,
) -> VerdictRow:
    """Return one verdict row. Combined-average keys are rejected."""
    if status not in STATUS_PHRASES:
        raise FactVerifyEvalError(status)
    reject_combined_average({"status": status, "scores": scores})
    if status == "confirmed recovery witness" and not confirmation_route:
        raise FactVerifyEvalError("confirmation_route")
    if status != "confirmed recovery witness":
        confirmation_route = None
    return VerdictRow(
        status=status,
        status_code=STATUS_CODES[status],
        access_label=access_label,
        arm_id=arm_id,
        checkpoint_ledger_id=checkpoint_ledger_id,
        fact_id=fact_id,
        split=split,
        spec_revision=spec_revision,
        thresholds_tag=thresholds_tag,
        scores=list(scores),
        diagnostics=Diagnostics(raw_maximum=raw_maximum),
        confirmation_route=confirmation_route,
        inference_output=list(inference_output or []),
    )
