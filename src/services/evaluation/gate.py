"""Gate analysis: compare forgetter vs referencer checkpoints (FV-ARCH-023).

Ported from src/eval/gate1.py. Consumes evaluation results (not raw job names)
and produces a structured GateReport.
"""

from __future__ import annotations

import math

from .types import FactComparison, GateReport

_METRICS = ("rouge_l", "truth_ratio", "answer_probability", "answer_rank")


def analyze_gate1(
    job_name: str,
    forget_fact: str,
    forgetter_scores: dict[str, dict[str, float]],
    referencer_scores: dict[str, dict[str, float]],
) -> GateReport:
    """Run Gate 1 separability analysis.

    Parameters
    ----------
    job_name:
        Evaluation job identifier.
    forget_fact:
        The single fact being unlearned.
    forgetter_scores:
        ``{fact_id: {metric: value}}`` for forgetter checkpoint.
    referencer_scores:
        ``{fact_id: {metric: value}}`` for referencer checkpoint.
    """
    common = sorted(set(forgetter_scores) & set(referencer_scores))
    if not common:
        return GateReport(
            job_name=job_name,
            gate="gate1",
            forget_fact=forget_fact,
            total_facts=0,
            retain_count=0,
            decision="NO_DATA",
        )

    comparisons: list[FactComparison] = []
    for fid in common:
        comparisons.append(FactComparison(
            fact_id=fid,
            is_forget=(fid == forget_fact),
            forgetter=forgetter_scores[fid],
            referencer=referencer_scores[fid],
        ))

    # Forget-fact delta
    forget_comp = next((c for c in comparisons if c.is_forget), None)
    forget_delta: dict[str, float] = {}
    if forget_comp:
        for m in _METRICS:
            forget_delta[m] = forget_comp.forgetter.get(m, 0.0) - forget_comp.referencer.get(m, 0.0)

    # Retain-facts mean |delta|
    retain_comps = [c for c in comparisons if not c.is_forget]
    retain_delta: dict[str, float] = {}
    for m in _METRICS:
        if retain_comps:
            diffs = [abs(c.forgetter.get(m, 0.0) - c.referencer.get(m, 0.0)) for c in retain_comps]
            retain_delta[m] = sum(diffs) / len(diffs)
        else:
            retain_delta[m] = 0.0

    # Decision: forgetter shows clear forget signal
    decision = "UNDETERMINED"
    if forget_comp:
        prob_drop = forget_delta.get("answer_probability", 0.0)
        rank_rise = forget_delta.get("answer_rank", 0.0)
        # Forgetter should have LOWER prob (negative delta) and HIGHER rank (positive delta)
        forget_signal = prob_drop < -0.05 or rank_rise > 10.0
        decision = "PASS" if forget_signal else "FAIL"

    return GateReport(
        job_name=job_name,
        gate="gate1",
        forget_fact=forget_fact,
        total_facts=len(common),
        retain_count=len(retain_comps),
        decision=decision,
        forget_delta=forget_delta,
        retain_delta=retain_delta,
        comparisons=comparisons,
    )
