"""Lookup a decision by semantic key or legacy ID."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.decisions.catalog import load_catalog
from src.decisions.errors import DecisionError
from src.decisions.types import DecisionCatalogEntry


@dataclass
class _CatalogIndex:
    by_legacy_id: dict[str, DecisionCatalogEntry]
    by_key: dict[str, DecisionCatalogEntry]


# Module-level cache keyed on resolved catalog path.
_cache: dict[Path, _CatalogIndex] = {}


def _index(catalog_path: Path) -> _CatalogIndex:
    resolved = catalog_path.resolve()
    if resolved in _cache:
        return _cache[resolved]
    entries = load_catalog(resolved)
    by_legacy_id: dict[str, DecisionCatalogEntry] = {}
    by_key: dict[str, DecisionCatalogEntry] = {}
    for entry in entries:
        by_legacy_id[entry.legacy_id] = entry
        for alias in entry.legacy_aliases:
            by_legacy_id[alias] = entry
        if entry.key is not None:
            by_key[entry.key] = entry
    idx = _CatalogIndex(by_legacy_id=by_legacy_id, by_key=by_key)
    _cache[resolved] = idx
    return idx


def resolve(identifier: str, catalog_path: Path) -> DecisionCatalogEntry:
    """Return the entry matching identifier (legacy ID or semantic key).

    Raises DecisionError if the identifier is not found.
    """
    idx = _index(catalog_path)
    entry = idx.by_legacy_id.get(identifier) or idx.by_key.get(identifier)
    if entry is None:
        raise DecisionError(
            f"decision not found in catalog: {identifier!r} (catalog: {catalog_path})"
        )
    return entry


def resolve_or_none(identifier: str, catalog_path: Path) -> DecisionCatalogEntry | None:
    """Return the entry or None if not found. Never raises."""
    try:
        return resolve(identifier, catalog_path)
    except DecisionError:
        return None
