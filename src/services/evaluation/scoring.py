"""Scoring functions: ROUGE-L and teacher-forced likelihood metrics."""

from __future__ import annotations


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
    """Length of the longest common subsequence."""
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
