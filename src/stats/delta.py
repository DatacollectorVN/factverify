"""Paired case differences. Open D-06 still checks that the case ids match."""

from __future__ import annotations

from collections.abc import Sequence

from src.stats.decisions import StatsDecision
from src.stats.errors import StatsError
from src.stats.io import VerdictRow


def case_id(row: VerdictRow) -> tuple[str, str]:
    """The resample case is the checkpoint and the fact."""
    return (row.checkpoint_ledger_id, row.fact_id)


def require_shared_cases(
    rows: Sequence[VerdictRow],
    *,
    decision: StatsDecision,
) -> None:
    """Both arms must list the same cases. A supplied weight raises `D-06`."""
    if any(row.weight is not None for row in rows):
        raise StatsError("D-06")
    if decision.status == "closed" and decision.fields.get("case_weights") != "uniform":
        raise StatsError("D-06")
    arms = sorted({row.arm for row in rows})
    if len(arms) < 2:
        return
    first = {case_id(row) for row in rows if row.arm == arms[0]}
    for arm in arms[1:]:
        other = {case_id(row) for row in rows if row.arm == arm}
        missing = sorted(first.symmetric_difference(other))
        if missing:
            rendered = ", ".join(f"{checkpoint}:{fact}" for checkpoint, fact in missing)
            raise StatsError(rendered)
