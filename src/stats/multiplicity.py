"""Holm, Benjamini-Hochberg, and Benjamini-Yekutieli. No other procedure."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from src.stats.decisions import load_decision
from src.stats.errors import StatsError


def adjust(p_values: Sequence[float], *, decisions: Path) -> tuple[float, ...]:
    """Multiplicity adjustment for a closed D-08 procedure."""
    row = load_decision(decisions, "D-08")
    if row.status != "closed":
        raise StatsError("D-08")
    procedure = row.fields.get("procedure")
    values = [float(item) for item in p_values]
    if procedure == "holm":
        return _holm(values)
    if procedure == "bh":
        return _step_up(values, harmonic=False)
    if procedure == "by":
        return _step_up(values, harmonic=True)
    raise StatsError("D-08")


def _holm(values: list[float]) -> tuple[float, ...]:
    count = len(values)
    order = sorted(range(count), key=lambda index: values[index])
    adjusted = [0.0] * count
    running = 0.0
    for rank, index in enumerate(order):
        raw = (count - rank) * values[index]
        running = max(running, raw)
        adjusted[index] = min(running, 1.0)
    return tuple(adjusted)


def _step_up(values: list[float], *, harmonic: bool) -> tuple[float, ...]:
    count = len(values)
    if count == 0:
        return ()
    factor = _harmonic(count) if harmonic else 1.0
    order = sorted(range(count), key=lambda index: values[index])
    adjusted = [0.0] * count
    running = 1.0
    for rank in range(count, 0, -1):
        index = order[rank - 1]
        raw = factor * (count / rank) * values[index]
        running = min(running, raw)
        adjusted[index] = min(running, 1.0)
    return tuple(adjusted)


def _harmonic(count: int) -> float:
    total = 0.0
    for number in range(1, count + 1):
        total += 1.0 / number
    return total
