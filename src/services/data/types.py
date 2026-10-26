"""Data service domain types."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrainingExample:
    """One QA training pair."""

    fact_id: str
    question: str
    answer: str


@dataclass(frozen=True)
class EvaluationProbe:
    """One eval probe with equivalence-class / direction label."""

    fact_id: str
    question: str
    expected_answer: str
    direction: str


@dataclass(frozen=True)
class ManifestDigest:
    """SHA-256 digest over the sorted fact IDs in a manifest."""

    digest: str


@dataclass(frozen=True)
class ValidationReport:
    """Result of a validation check."""

    valid: bool
    errors: list[str] = field(default_factory=list)
