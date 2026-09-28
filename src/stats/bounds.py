"""One-sided Clopper-Pearson upper bound. Stdlib only."""

from __future__ import annotations

import math
from decimal import Decimal

from src.stats.errors import StatsError

SOLVER_WIDTH = Decimal("1e-12")


def one_sided_exact(errors: int, n: int, gamma: Decimal, *, procedure: str) -> Decimal:
    """Upper bound. Zero errors use `1 - gamma ** (1/n)`."""
    if procedure != "one_sided_exact":
        raise StatsError("D-03")
    if n < 1:
        raise StatsError("n")
    if errors < 0 or errors > n:
        raise StatsError("n")
    if errors == 0:
        return Decimal(1) - (gamma ** (Decimal(1) / Decimal(n)))
    if errors == n:
        return Decimal(1)
    low = Decimal(0)
    high = Decimal(1)
    while high - low > SOLVER_WIDTH:
        mid = (low + high) / 2
        if _lower_tail(n, errors, mid) > gamma:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def _lower_tail(n: int, errors: int, probability: Decimal) -> Decimal:
    total = Decimal(0)
    for count in range(errors + 1):
        total += _pmf(n, count, probability)
    return total


def _pmf(n: int, count: int, probability: Decimal) -> Decimal:
    return (
        Decimal(math.comb(n, count))
        * (probability**count)
        * ((Decimal(1) - probability) ** (n - count))
    )
