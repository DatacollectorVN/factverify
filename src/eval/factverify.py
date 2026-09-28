"""FactVerify decision: a confirmed witness needs an enabled route."""

from __future__ import annotations

from dataclasses import dataclass

from src.eval.errors import FactVerifyEvalError
from src.eval.spec_load import SpecBundle, require_closed
from src.eval.types import Case, ChannelScore, VerdictRow
from src.eval.verdict import build_verdict


@dataclass
class Confirmation:
    succeeded: bool
    route: str


def decide(
    bundle: SpecBundle,
    case: Case,
    arm_id: str,
    scores: list[ChannelScore],
    confirmation: Confirmation | None,
    inference_output: list[str] | None = None,
    thresholds_tag: str | None = None,
) -> VerdictRow:
    """Apply the witness-rule order. A raw maximum is never the status."""
    require_closed(bundle, ["D-14"])
    if bundle.raw_maximum_role != "diagnostic_only":
        raise FactVerifyEvalError("raw_maximum_role")
    _inference = inference_output or []
    if case.identifiability == "structurally_indistinguishable":
        return build_verdict(
            status="non-identifiable under this profile",
            access_label=case.access_label,
            arm_id=arm_id,
            checkpoint_ledger_id=case.checkpoint_ledger_id,
            fact_id=case.fact_id,
            split=case.split,
            spec_revision=case.spec_revision,
            scores=scores,
            inference_output=_inference,
            thresholds_tag=thresholds_tag,
        )
    if case.identifiability != "identifiable":
        raise FactVerifyEvalError("identifiability")
    crossings = [item for item in scores if item.score > item.bound]
    raw_maximum = max((item.score for item in crossings), default=None)
    route_ok = (
        confirmation is not None
        and confirmation.succeeded
        and bundle.route_enabled.get(confirmation.route, False)
    )
    if route_ok and confirmation is not None:
        return build_verdict(
            status="confirmed recovery witness",
            access_label=case.access_label,
            arm_id=arm_id,
            checkpoint_ledger_id=case.checkpoint_ledger_id,
            fact_id=case.fact_id,
            split=case.split,
            spec_revision=case.spec_revision,
            scores=scores,
            raw_maximum=raw_maximum,
            confirmation_route=confirmation.route,
            inference_output=_inference,
            thresholds_tag=thresholds_tag,
        )
    if crossings or not bundle.no_witness_is_not_accept:
        return build_verdict(
            status="insufficient evidence/incomplete",
            access_label=case.access_label,
            arm_id=arm_id,
            checkpoint_ledger_id=case.checkpoint_ledger_id,
            fact_id=case.fact_id,
            split=case.split,
            spec_revision=case.spec_revision,
            scores=scores,
            raw_maximum=raw_maximum,
            inference_output=_inference,
            thresholds_tag=thresholds_tag,
        )
    return build_verdict(
        status="conformant under the declared test",
        access_label=case.access_label,
        arm_id=arm_id,
        checkpoint_ledger_id=case.checkpoint_ledger_id,
        fact_id=case.fact_id,
        split=case.split,
        spec_revision=case.spec_revision,
        scores=scores,
        raw_maximum=None,
        inference_output=_inference,
        thresholds_tag=thresholds_tag,
    )
