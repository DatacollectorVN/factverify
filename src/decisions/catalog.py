"""Load and validate docs/decisions/catalog.yaml."""

from __future__ import annotations

from pathlib import Path

import yaml

from src.decisions.errors import DecisionError
from src.decisions.types import DecisionCatalogEntry

_ALLOWED_STATUSES = frozenset(
    {"open", "closed", "pending", "collision", "unresolved", "absent"}
)
_REQUIRED_FIELDS = frozenset(
    {
        "legacy_id",
        "key",
        "title",
        "description",
        "domain",
        "owner",
        "consumers",
        "required_fields",
        "status",
        "legacy_aliases",
    }
)


def load_catalog(catalog_path: Path) -> list[DecisionCatalogEntry]:
    """Read catalog_path and return a list of entries.

    Raises DecisionError if the file is missing, malformed, or contains an
    entry with an unknown status value or missing required fields.
    """
    if not catalog_path.is_file():
        raise DecisionError(f"catalog not found: {catalog_path}")
    try:
        loaded = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise DecisionError(f"catalog YAML parse error: {catalog_path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise DecisionError(f"catalog must be a YAML mapping: {catalog_path}")
    raw_decisions = loaded.get("decisions")
    if not isinstance(raw_decisions, list):
        raise DecisionError(f"catalog missing 'decisions' list: {catalog_path}")
    entries: list[DecisionCatalogEntry] = []
    for i, item in enumerate(raw_decisions):
        if not isinstance(item, dict):
            raise DecisionError(f"catalog entry {i} is not a mapping")
        missing = _REQUIRED_FIELDS - item.keys()
        if missing:
            lid = item.get("legacy_id", f"entry[{i}]")
            raise DecisionError(
                f"catalog entry {lid} missing required fields: {sorted(missing)}"
            )
        status = item["status"]
        if status not in _ALLOWED_STATUSES:
            raise DecisionError(
                f"catalog entry {item['legacy_id']} has unknown status: {status!r}"
            )
        consumers_raw = item["consumers"]
        if not isinstance(consumers_raw, list):
            raise DecisionError(
                f"catalog entry {item['legacy_id']} 'consumers' must be a list"
            )
        required_raw = item["required_fields"]
        if not isinstance(required_raw, list):
            raise DecisionError(
                f"catalog entry {item['legacy_id']} 'required_fields' must be a list"
            )
        aliases_raw = item["legacy_aliases"]
        if not isinstance(aliases_raw, list):
            raise DecisionError(
                f"catalog entry {item['legacy_id']} 'legacy_aliases' must be a list"
            )
        entries.append(
            DecisionCatalogEntry(
                legacy_id=str(item["legacy_id"]),
                key=str(item["key"]) if item["key"] is not None else None,
                title=str(item["title"]),
                description=str(item["description"]),
                domain=str(item["domain"]),
                owner=str(item["owner"]),
                consumers=tuple(str(c) for c in consumers_raw),
                required_fields=tuple(str(f) for f in required_raw),
                status=str(status),
                legacy_aliases=tuple(str(a) for a in aliases_raw),
            )
        )
    return entries


def validate_catalog(entries: list[DecisionCatalogEntry]) -> list[str]:
    """Run uniqueness checks. Returns a list of error strings (empty = valid).

    Checks:
    1. No two entries share the same legacy_id.
    2. No two non-null key values are duplicated.
    3. No legacy_alias collides with a primary legacy_id in another entry.
    4. Every closed entry has a non-null key.
    """
    errors: list[str] = []
    seen_legacy: dict[str, str] = {}  # legacy_id → title
    seen_keys: dict[str, str] = {}  # key → legacy_id

    for entry in entries:
        # Check 1: duplicate legacy_id
        if entry.legacy_id in seen_legacy:
            errors.append(
                f"duplicate legacy_id {entry.legacy_id!r}: "
                f"'{seen_legacy[entry.legacy_id]}' and '{entry.title}'"
            )
        else:
            seen_legacy[entry.legacy_id] = entry.title

        # Check 2: duplicate semantic key
        if entry.key is not None:
            if entry.key in seen_keys:
                errors.append(
                    f"duplicate key {entry.key!r}: "
                    f"{seen_keys[entry.key]} and {entry.legacy_id}"
                )
            else:
                seen_keys[entry.key] = entry.legacy_id

        # Check 4: closed entry without key
        if entry.status == "closed" and entry.key is None:
            errors.append(
                f"closed entry {entry.legacy_id} has null key — "
                "a closed decision must have a semantic key"
            )

    # Check 3: legacy_alias collision
    for entry in entries:
        for alias in entry.legacy_aliases:
            if alias in seen_legacy and seen_legacy[alias] != entry.title:
                errors.append(
                    f"legacy_alias {alias!r} in entry {entry.legacy_id} "
                    f"collides with primary legacy_id of '{seen_legacy[alias]}'"
                )

    return errors
