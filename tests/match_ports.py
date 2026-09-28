"""Scripted ledger and behaviour ports for matching hooks. No model calls."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LedgerRow:
    """One scripted ledger row."""

    ledger_id: str
    role: str
    fact_id: str
    split: str


@dataclass(frozen=True)
class ProbeRead:
    """One scripted probe output."""

    probe_id: str
    system_id: str
    output: str


@dataclass(frozen=True)
class ScriptedMeasurement:
    """Accuracy plus the outputs the matcher records."""

    accuracy: float
    outputs: tuple[ProbeRead, ...]


class MemoryMatchLedger:
    """In-memory ledger. Unknown ids return None."""

    def __init__(self, rows: dict[str, LedgerRow]) -> None:
        self._rows = rows

    def get(self, ledger_id: str) -> LedgerRow | None:
        return self._rows.get(ledger_id)


class ScriptedMatchBehavior:
    """Returns scripted accuracies. Records every call."""

    def __init__(
        self,
        references: dict[str, float],
        by_severity: dict[str, float],
        dimensions: dict[str, float] | None = None,
    ) -> None:
        self._references = references
        self._by_severity = by_severity
        self._dimensions = dimensions or {}
        self.calls: list[tuple[str, str | None]] = []
        self.dimension_calls: list[tuple[str, str]] = []

    def direct_qa_accuracy(
        self,
        system_id: str,
        fact_id: str,
        probe_ids: tuple[str, ...],
        severity: str | None,
    ) -> ScriptedMeasurement:
        self.calls.append((system_id, severity))
        if severity is None:
            accuracy = self._references[system_id]
        else:
            accuracy = self._by_severity[severity]
        outputs = tuple(
            ProbeRead(probe_id, system_id, f"out-{probe_id}") for probe_id in probe_ids
        )
        return ScriptedMeasurement(accuracy, outputs)

    def dimension_value(
        self, system_id: str, fact_id: str, name: str, severity: str
    ) -> float:
        self.dimension_calls.append((name, severity))
        return self._dimensions[name]
