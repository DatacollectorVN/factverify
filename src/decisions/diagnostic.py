"""Format blocked-decision diagnostics."""

from __future__ import annotations

from pathlib import Path

from src.decisions.resolver import resolve_or_none
from src.decisions.types import DecisionCatalogEntry


def format_diagnostic(
    entry: DecisionCatalogEntry,
    missing_field: str | None = None,
    consuming_op: str | None = None,
) -> str:
    """Return a multi-line diagnostic string for a blocked decision.

    Format (normal entry):
        Decision required: <key> (legacy <legacy_id>)
        <title> is open or incomplete.
        Missing field: <missing_field>. Required by: <consuming_op>.

    Format (collision/unresolved entry):
        Decision required: (legacy <legacy_id>) [COLLISION — owner resolution required]
        <title> has conflicting meanings.
        See docs/tickets/readable-decision-identifiers.md.

    Lines 3+ are omitted when the corresponding argument is None.
    """
    if entry.key is None:
        # Collision or unresolved entry
        lines = [
            f"Decision required: (legacy {entry.legacy_id})"
            " [COLLISION — owner resolution required]",
            f"{entry.title} has conflicting meanings.",
            "See docs/tickets/readable-decision-identifiers.md.",
        ]
        return "\n".join(lines)

    # Normal entry
    first_line = f"Decision required: {entry.key} (legacy {entry.legacy_id})"
    second_line = f"{entry.title} is open or incomplete."
    lines = [first_line, second_line]

    third_parts: list[str] = []
    if missing_field is not None:
        third_parts.append(f"Missing field: {missing_field}.")
    if consuming_op is not None:
        third_parts.append(f"Required by: {consuming_op}.")
    if third_parts:
        lines.append(" ".join(third_parts))

    return "\n".join(lines)


def format_diagnostic_by_id(
    legacy_id: str,
    catalog_path: Path,
    missing_field: str | None = None,
    consuming_op: str | None = None,
) -> str:
    """Resolve legacy_id and format a diagnostic string.

    Falls back to a minimal message containing only the legacy ID if the
    catalog cannot resolve the identifier (compatibility mode during migration).
    """
    entry = resolve_or_none(legacy_id, catalog_path)
    if entry is None:
        # Compatibility fallback — catalog not yet populated for this ID
        parts = [f"Decision required: (legacy {legacy_id})"]
        if missing_field is not None:
            parts.append(f"Missing field: {missing_field}.")
        if consuming_op is not None:
            parts.append(f"Required by: {consuming_op}.")
        return "\n".join(parts)
    return format_diagnostic(
        entry, missing_field=missing_field, consuming_op=consuming_op
    )
