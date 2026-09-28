"""Native-arm scores. Closure-template probes are refused."""

from __future__ import annotations

from src.eval.channels import permit
from src.eval.errors import FactVerifyEvalError
from src.eval.gateway import Gateway, MetricPort
from src.eval.probes import resolve_probe
from src.eval.spec_load import SpecBundle
from src.eval.types import Case, ChannelScore, Probe


def rouge_l(hypothesis: str, reference: str) -> float:
    """LCS F-measure over whitespace tokens."""
    hyp = hypothesis.split()
    ref = reference.split()
    if not hyp or not ref:
        return 0.0
    length = _lcs(hyp, ref)
    precision = length / len(hyp)
    recall = length / len(ref)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def _lcs(left: list[str], right: list[str]) -> int:
    previous = [0] * (len(right) + 1)
    for token in left:
        current = [0]
        for index, other in enumerate(right, start=1):
            if token == other:
                current.append(previous[index - 1] + 1)
            else:
                current.append(max(current[-1], previous[index]))
        previous = current
    return previous[-1]


def score_native(
    bundle: SpecBundle,
    case: Case,
    probe: Probe,
    gateway: Gateway,
    metrics: MetricPort,
    bounds: dict[str, float],
) -> list[ChannelScore]:
    """Five native metrics when scores are allowed. Text metrics otherwise."""
    if resolve_probe(bundle, case, probe) != "native":
        raise FactVerifyEvalError(probe.template_id or probe.probe_id)
    if not case.answers:
        raise FactVerifyEvalError("answers")
    completion = gateway.complete(
        probe, "prompt_variation", seed=case.seed, sample_index=1
    )
    answer = case.answers[0]
    text_scores = {
        "rouge_l": rouge_l(completion, answer),
        "bertscore": metrics.bertscore(completion, answer),
    }
    gateway.note_scores(text_scores)
    scores = [
        ChannelScore(name, value, bounds.get(name, 1.0))
        for name, value in text_scores.items()
    ]
    try:
        permit(bundle, "raw_likelihood", "candidate_score")
    except FactVerifyEvalError:
        return scores
    raw = gateway.score(probe, "prompt_variation")
    for name in ("truth_ratio", "answer_probability", "answer_rank"):
        if name not in raw:
            raise FactVerifyEvalError(name)
        value = float(raw[name])
        scores.append(ChannelScore(name, value, bounds.get(name, 1.0)))
    return scores
