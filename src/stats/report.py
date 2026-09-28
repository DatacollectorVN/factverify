"""Final-report intervals. A row resample is refused."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from src.stats.bootstrap import draw_blocks, quantile
from src.stats.bounds import one_sided_exact
from src.stats.decisions import load_decision
from src.stats.delta import case_id, require_shared_cases
from src.stats.errors import StatsError
from src.stats.io import (
    StatsLedgerPort,
    VerdictRow,
    gamma_of,
    load_verdicts,
    read_margins,
)
from src.stats.multiplicity import adjust
from src.stats.thresholds import ThresholdBound, select_thresholds


@dataclass(frozen=True)
class FamilyRow:
    """One family or the overall row. `point` is absent when `n` is 0."""

    name: str
    n: int
    point: Decimal | None


@dataclass(frozen=True)
class EstimateTable:
    """Block intervals for one closed design."""

    purpose: str
    seed: int
    replicate_count: int
    design: str
    spec_version: str
    input_digest: str
    rows: tuple[FamilyRow, ...]
    estimates: dict[str, dict[str, Decimal]]
    interval: dict[str, dict[str, Decimal]]


def family_rows(
    rows: Sequence[VerdictRow],
    *,
    decisions: Path,
    families: Sequence[str] | None = None,
) -> tuple[FamilyRow, ...]:
    """One row per family and one overall row when D-10 is closed as mean."""
    decision = load_decision(decisions, "D-10")
    if decision.status != "closed":
        raise StatsError("D-10")
    if (
        decision.fields.get("per_family") != "mean"
        or decision.fields.get("overall") != "mean"
    ):
        raise StatsError("D-10")
    names = (
        list(families)
        if families is not None
        else sorted({row.control_family for row in rows})
    )
    built = [
        _family(name, [row for row in rows if row.control_family == name])
        for name in names
    ]
    built.append(_family("overall", list(rows)))
    return tuple(built)


def estimate(
    verdicts: Sequence[VerdictRow],
    *,
    spec_root: Path,
    decisions: Path,
    ledger: StatsLedgerPort,
    seed: int,
    purpose: str,
    unit: str | None = None,
    families: Sequence[str] | None = None,
) -> EstimateTable | tuple[ThresholdBound, ...]:
    """Block intervals for a final report, or raise on an open decision."""
    if purpose not in {"threshold_selection", "final_report"}:
        raise StatsError("purpose")
    if purpose == "threshold_selection":
        return select_thresholds(
            verdicts, spec_root=spec_root, decisions=decisions, ledger=ledger
        )
    loaded = load_verdicts(verdicts, spec_root=spec_root, ledger=ledger)
    design_row = load_decision(decisions, "D-07")
    interval_row = load_decision(decisions, "D-57")
    if design_row.status != "closed":
        raise StatsError("D-07")
    if interval_row.status != "closed":
        raise StatsError("D-57")
    if unit == "row":
        raise StatsError("rows")
    if design_row.fields.get("resampling_contract") != "paired_block_bootstrap":
        raise StatsError("D-07")
    design = design_row.fields.get("design")
    if design not in {"nested", "crossed"}:
        raise StatsError("D-07")
    if interval_row.fields.get("interval_type") != "percentile":
        raise StatsError("D-57")
    replicate_count = interval_row.fields.get("replicate_count")
    if not isinstance(replicate_count, int) or replicate_count < 1:
        raise StatsError("D-57")
    weight_row = load_decision(decisions, "D-06")
    require_shared_cases(loaded, decision=weight_row)
    margins = read_margins(spec_root)
    gamma = Decimal(gamma_of(margins))
    version = margins.get("version")
    if not isinstance(version, str):
        raise StatsError("version")
    replicates = [
        _replicate_rate(loaded, str(design), seed + index)
        for index in range(replicate_count)
    ]
    lower = quantile(sorted(replicates), gamma / 2)
    upper = quantile(sorted(replicates), Decimal(1) - (gamma / 2))
    errors = sum(1 for row in loaded if row.rejected)
    cases = len({case_id(row) for row in loaded}) or len(loaded)
    point = Decimal(0) if errors == 0 else Decimal(errors) / Decimal(len(loaded) or 1)
    if errors == 0:
        d03 = load_decision(decisions, "D-03")
        if d03.status != "closed":
            raise StatsError("D-03")
        upper = one_sided_exact(
            0, cases, gamma, procedure=str(d03.fields.get("procedure"))
        )
        lower = Decimal(0)
        point = Decimal(0)
    d08 = load_decision(decisions, "D-08")
    if d08.status == "closed":
        probability = _bootstrap_p(replicates)
        adjust((probability,), decisions=decisions)
    rows = family_rows(loaded, decisions=decisions, families=families)
    digest = hashlib.sha256(
        json.dumps([row.row_id for row in loaded], separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return EstimateTable(
        purpose=purpose,
        seed=seed,
        replicate_count=replicate_count,
        design=str(design),
        spec_version=version,
        input_digest=digest,
        rows=rows,
        estimates={"fcr": {"point": point}},
        interval={"fcr": {"lower": lower, "upper": upper}},
    )


def _family(name: str, rows: list[VerdictRow]) -> FamilyRow:
    cases = {case_id(row) for row in rows}
    if not cases:
        return FamilyRow(name, 0, None)
    errors = sum(1 for row in rows if row.rejected)
    return FamilyRow(name, len(cases), Decimal(errors) / Decimal(len(rows)))


def _replicate_rate(rows: Sequence[VerdictRow], design: str, seed: int) -> Decimal:
    drawn = draw_blocks(rows, design=design, seed=seed)
    if not drawn:
        return Decimal(0)
    errors = sum(1 for row in drawn if row.rejected)
    return Decimal(errors) / Decimal(len(drawn))


def _bootstrap_p(replicates: list[Decimal]) -> float:
    if not replicates:
        return 1.0
    below = sum(1 for item in replicates if item <= 0)
    above = sum(1 for item in replicates if item >= 0)
    probability = 2 * min(below, above) / len(replicates)
    return min(probability, 1.0)
