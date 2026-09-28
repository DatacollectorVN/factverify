"""Access-profile gate. Charging stays in the accountant."""

from __future__ import annotations

from src.eval.errors import FactVerifyEvalError
from src.eval.spec_load import SpecBundle


def permit(bundle: SpecBundle, channel_id: str, kind: str) -> None:
    """Allow a channel the profile grants. Refuse logit, score, or activation calls."""
    channel = bundle.channels.get(channel_id)
    if channel is None or channel.get("enabled") is not True:
        raise FactVerifyEvalError(f"{channel_id} disabled")
    requirements = channel.get("capability_requirements", {})
    if not isinstance(requirements, dict):
        raise FactVerifyEvalError(channel_id)
    capabilities = bundle.capabilities
    scores_ok = capabilities.get("scores") == "verified"
    if requirements.get("raw_scores") is True and not scores_ok:
        raise FactVerifyEvalError(f"{channel_id} raw_scores")
    internals_ok = capabilities.get("internals") == "verified"
    if requirements.get("weight_update") is True and not internals_ok:
        raise FactVerifyEvalError(f"{channel_id} internals")
    scoring_ok = capabilities.get("candidate_scoring") == "verified"
    if kind == "candidate_score" and not scoring_ok:
        raise FactVerifyEvalError(f"{channel_id} candidate_scoring")
    if kind == "candidate_score" and not scores_ok:
        raise FactVerifyEvalError(f"{channel_id} scores")
