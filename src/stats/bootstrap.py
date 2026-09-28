"""Block and row resamples. `estimate` does not call `draw_rows`."""

from __future__ import annotations

import random
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml

from src.stats.decisions import load_decision
from src.stats.errors import StatsError
from src.stats.io import VerdictRow, gamma_of, read_margins


@dataclass(frozen=True)
class CoverageReport:
    """Empirical coverage of the block resample and the row resample."""

    block_coverage: float
    row_coverage: float


def draw_blocks(
    rows: Sequence[VerdictRow],
    *,
    design: str,
    seed: int,
) -> tuple[VerdictRow, ...]:
    """Resample checkpoint-fact blocks. Nested refuses a fact on two checkpoints."""
    if design not in {"nested", "crossed"}:
        raise StatsError("design")
    _refuse_nested_crossing(rows, design)
    rng = random.Random(seed)
    if design == "nested":
        return _nested(rows, rng)
    return _crossed(rows, rng)


def draw_rows(rows: Sequence[VerdictRow], *, seed: int) -> tuple[VerdictRow, ...]:
    """Resample prompt rows. Used by the coverage check only."""
    if not rows:
        return ()
    rng = random.Random(seed)
    pool = list(rows)
    return tuple(rng.choice(pool) for _ in pool)


def coverage_simulation(
    simulation: Path,
    *,
    spec_root: Path,
    decisions: Path,
) -> CoverageReport:
    """Block coverage against a row-level resample. Raises while D-57 is open."""
    row = load_decision(decisions, "D-57")
    if row.status != "closed":
        raise StatsError("D-57")
    if row.fields.get("interval_type") != "percentile":
        raise StatsError("D-57")
    tolerance = row.fields.get("coverage_tolerance")
    replicate_count = row.fields.get("replicate_count")
    if not isinstance(tolerance, str) or not isinstance(replicate_count, int):
        raise StatsError("D-57")
    document = _simulation(simulation)
    margins = read_margins(spec_root)
    gamma = Decimal(gamma_of(margins))
    block_hits = 0
    row_hits = 0
    rng = random.Random(_as_int(document, "seed"))
    for _ in range(_as_int(document, "n_simulations")):
        table = _population(document, rng)
        true_fcr = Decimal(str(document["true_fcr"]))
        inner = rng.randrange(2**31)
        block_interval = _mean_interval(
            table, "block", inner, int(replicate_count), gamma
        )
        row_interval = _mean_interval(table, "row", inner, int(replicate_count), gamma)
        if block_interval[0] <= true_fcr <= block_interval[1]:
            block_hits += 1
        if row_interval[0] <= true_fcr <= row_interval[1]:
            row_hits += 1
    total = _as_int(document, "n_simulations")
    return CoverageReport(block_hits / total, row_hits / total)


def _refuse_nested_crossing(rows: Sequence[VerdictRow], design: str) -> None:
    if design != "nested":
        return
    homes: dict[str, set[str]] = {}
    for row in rows:
        homes.setdefault(row.fact_id, set()).add(row.checkpoint_ledger_id)
    if any(len(checkpoints) > 1 for checkpoints in homes.values()):
        raise StatsError("design")


def _nested(rows: Sequence[VerdictRow], rng: random.Random) -> tuple[VerdictRow, ...]:
    blocks: dict[tuple[str, str], list[VerdictRow]] = {}
    for row in rows:
        blocks.setdefault((row.checkpoint_ledger_id, row.fact_id), []).append(row)
    keys = list(blocks)
    if not keys:
        return ()
    drawn = [rng.choice(keys) for _ in keys]
    selected: list[VerdictRow] = []
    for key in drawn:
        selected.extend(blocks[key])
    return tuple(selected)


def _crossed(rows: Sequence[VerdictRow], rng: random.Random) -> tuple[VerdictRow, ...]:
    by_case: dict[tuple[str, str], list[VerdictRow]] = {}
    checkpoints: list[str] = []
    facts: list[str] = []
    for row in rows:
        key = (row.checkpoint_ledger_id, row.fact_id)
        if key not in by_case:
            by_case[key] = []
            if row.checkpoint_ledger_id not in checkpoints:
                checkpoints.append(row.checkpoint_ledger_id)
            if row.fact_id not in facts:
                facts.append(row.fact_id)
        by_case[key].append(row)
    if not checkpoints or not facts:
        return ()
    checkpoint_counts = Counter(rng.choice(checkpoints) for _ in checkpoints)
    fact_counts = Counter(rng.choice(facts) for _ in facts)
    selected: list[VerdictRow] = []
    for (checkpoint_id, fact_id), prompts in by_case.items():
        multiplicity = checkpoint_counts[checkpoint_id] * fact_counts[fact_id]
        for _ in range(multiplicity):
            selected.extend(prompts)
    return tuple(selected)


def _as_int(document: dict[str, object], name: str) -> int:
    value = document[name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise StatsError(name)
    return value


def _simulation(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise StatsError(path.name)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise StatsError(path.name)
    required = (
        "n_checkpoints",
        "n_facts",
        "n_prompts",
        "true_fcr",
        "checkpoint_shift",
        "n_simulations",
        "seed",
    )
    for name in required:
        if name not in loaded:
            raise StatsError(name)
    return loaded


def _population(
    document: dict[str, object], rng: random.Random
) -> list[list[list[int]]]:
    true_fcr = Decimal(str(document["true_fcr"]))
    shift = Decimal(str(document["checkpoint_shift"]))
    n_checkpoints = _as_int(document, "n_checkpoints")
    n_facts = _as_int(document, "n_facts")
    n_prompts = _as_int(document, "n_prompts")
    table: list[list[list[int]]] = []
    for index in range(n_checkpoints):
        sign = Decimal(1) if index % 2 == 0 else Decimal(-1)
        rate = true_fcr + (sign * shift)
        if rate <= 0:
            rate = Decimal("0.000001")
        if rate >= 1:
            rate = Decimal("0.999999")
        checkpoint: list[list[int]] = []
        for _fact in range(n_facts):
            prompts = [1 if rng.random() < float(rate) else 0 for _ in range(n_prompts)]
            checkpoint.append(prompts)
        table.append(checkpoint)
    return table


def _mean_interval(
    table: list[list[list[int]]],
    unit: str,
    seed: int,
    replicate_count: int,
    gamma: Decimal,
) -> tuple[Decimal, Decimal]:
    rng = random.Random(seed)
    stats: list[Decimal] = []
    for _ in range(replicate_count):
        if unit == "block":
            stats.append(_block_mean(table, rng))
        else:
            stats.append(_row_mean(table, rng))
    return _percentile(stats, gamma)


def _block_mean(table: list[list[list[int]]], rng: random.Random) -> Decimal:
    drawn = [rng.choice(table) for _ in table]
    total = 0
    count = 0
    for checkpoint in drawn:
        for fact in checkpoint:
            total += sum(fact)
            count += len(fact)
    if count == 0:
        return Decimal(0)
    return Decimal(total) / Decimal(count)


def _row_mean(table: list[list[list[int]]], rng: random.Random) -> Decimal:
    flat = [bit for checkpoint in table for fact in checkpoint for bit in fact]
    if not flat:
        return Decimal(0)
    drawn = [rng.choice(flat) for _ in flat]
    return Decimal(sum(drawn)) / Decimal(len(drawn))


def _percentile(stats: list[Decimal], gamma: Decimal) -> tuple[Decimal, Decimal]:
    ordered = sorted(stats)
    return quantile(ordered, gamma / 2), quantile(ordered, Decimal(1) - (gamma / 2))


def quantile(ordered: Sequence[Decimal], probability: Decimal) -> Decimal:
    """Linear quantile. One replicate returns that replicate."""
    if not ordered:
        raise StatsError("replicate_count")
    if len(ordered) == 1:
        return ordered[0]
    position = probability * Decimal(len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - Decimal(lower)
    return ordered[lower] * (Decimal(1) - weight) + ordered[upper] * weight
