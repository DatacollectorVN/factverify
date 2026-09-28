"""Shared types for the decision catalog and diagnostic formatter."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionCatalogEntry:
    """One entry in docs/decisions/catalog.yaml."""

    legacy_id: str
    key: str | None
    title: str
    description: str
    domain: str
    owner: str
    consumers: tuple[str, ...]
    required_fields: tuple[str, ...]
    status: str
    legacy_aliases: tuple[str, ...]


@dataclass(frozen=True)
class DecisionDiagnostic:
    """Structured representation of a blocked-decision error."""

    key: str | None
    legacy_id: str
    title: str
    status: str
    missing_field: str | None = None
    consuming_op: str | None = None
    owner: str | None = None
