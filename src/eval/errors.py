"""Fail-closed errors for the evaluators and the query-budget accountant."""

from __future__ import annotations

from dataclasses import dataclass

from typing_extensions import override


class FactVerifyEvalError(ValueError):
    """Names the field, decision id, channel, arm, path, or call site."""


class TransportError(FactVerifyEvalError):
    """The model port failed before a completion existed."""


@dataclass
class BudgetExhaustedError(FactVerifyEvalError):
    """A charge would exceed the channel remainder. The remainder is unchanged."""

    channel_id: str
    charge: int
    remaining: int

    @override
    def __str__(self) -> str:
        return (
            f"budget_exhausted channel={self.channel_id} "
            f"charge={self.charge} remaining={self.remaining}"
        )
