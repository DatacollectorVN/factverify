"""Calibration-only threshold bounds. A final-test row raises before D-03."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from src.stats.bounds import one_sided_exact
from src.stats.decisions import load_decision
from src.stats.errors import StatsError
from src.stats.io import (
    StatsLedgerPort,
    VerdictRow,
    gamma_of,
    load_verdicts,
    read_margins,
)


@dataclass(frozen=True)
class ThresholdBound:
    """One false-rejection upper bound for a genuine reference."""

    threshold_id: str
    point: Decimal
    upper: Decimal
    n: int


def select_thresholds(
    rows: Sequence[VerdictRow],
    *,
    spec_root: Path,
    decisions: Path,
    ledger: StatsLedgerPort,
) -> tuple[ThresholdBound, ...]:
    """One FRR upper bound per threshold_id. Any final-test row raises."""
    loaded = load_verdicts(rows, spec_root=spec_root, ledger=ledger)
    if any(row.split in {"final_test", "final-test"} for row in loaded):
        raise StatsError("final_test")
    d03 = load_decision(decisions, "D-03")
    d05 = load_decision(decisions, "D-05")
    if d03.status != "closed" or d03.fields.get("procedure") != "one_sided_exact":
        raise StatsError("D-03")
    if d05.status != "closed" or d05.fields.get("procedure") != "one_sided_exact":
        raise StatsError("selection_uncertainty_procedure")
    margins = read_margins(spec_root)
    gamma = Decimal(gamma_of(margins))
    grouped: dict[str, list[VerdictRow]] = {}
    for row in loaded:
        if row.oracle_label != "genuine_reference":
            continue
        grouped.setdefault(row.threshold_id, []).append(row)
    bounds: list[ThresholdBound] = []
    for threshold_id in sorted(grouped):
        group = grouped[threshold_id]
        errors = sum(1 for row in group if row.rejected)
        count = len(group)
        point = Decimal(errors) / Decimal(count)
        upper = one_sided_exact(
            errors, count, gamma, procedure=str(d03.fields.get("procedure"))
        )
        bounds.append(ThresholdBound(threshold_id, point, upper, count))
    return tuple(bounds)
