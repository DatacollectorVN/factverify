# Contract: `src/decisions` Public API

**Feature**: `20260929-110152-readable-decision-identifiers`
**Date**: 2026-09-29

This document defines the public interface that all callers (`src/data/`,
`src/stats/`, `src/controls/`, `src/cache/`, `src/ledger/`, `src/eval/`)
MUST use when interacting with the decision catalog. Internal helpers inside
`src/decisions/` are not part of this contract.

---

## Types (`src/decisions/types.py`)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class DecisionCatalogEntry:
    legacy_id: str
    key: str | None          # None when status is "collision" or "unresolved"
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
    key: str | None
    legacy_id: str
    title: str
    status: str
    missing_field: str | None = None
    consuming_op: str | None = None
    owner: str | None = None
```

---

## Resolver (`src/decisions/resolver.py`)

### `resolve(identifier: str, catalog_path: Path) -> DecisionCatalogEntry`

Look up a decision by either its semantic key or its legacy ID.

**Parameters**:
- `identifier` — semantic key (e.g. `"data.exclusion_gate.policy"`) or legacy
  ID (e.g. `"D-65"`). Both formats are accepted.
- `catalog_path` — path to `catalog.yaml`. The resolved index is cached per
  path so repeated calls do not re-read the file.

**Returns**: The matching `DecisionCatalogEntry`.

**Raises**:
- `DecisionError` — if the identifier is not found in the catalog.

---

### `resolve_or_none(identifier: str, catalog_path: Path) -> DecisionCatalogEntry | None`

Same as `resolve` but returns `None` instead of raising when the identifier
is not found. Use this during the migration period when some legacy IDs have
not yet been added to the catalog.

---

## Diagnostic formatter (`src/decisions/diagnostic.py`)

### `format_diagnostic(entry: DecisionCatalogEntry, missing_field: str | None = None, consuming_op: str | None = None) -> str`

Produce the multi-line diagnostic string to embed in an exception message.

**Output format** (all lines present when arguments provided):
```
Decision required: data.exclusion_gate.policy (legacy D-65)
Knowledge-exclusion gate policy is open or incomplete.
Missing field: threshold. Required by: exclusion gate.
```

For collision entries (`key is None`):
```
Decision required: (legacy D-08) [COLLISION — owner resolution required]
Uncertainty seed types / multiplicity procedure has conflicting meanings.
See docs/tickets/readable-decision-identifiers.md.
```

**Parameters**:
- `entry` — a `DecisionCatalogEntry` as returned by the resolver.
- `missing_field` — the specific field name that is absent or invalid.
- `consuming_op` — short label for the calling operation (e.g.
  `"exclusion gate"`, `"bootstrap interval"`, `"ledger row"`).

**Returns**: Multi-line string. Never raises.

---

### `format_diagnostic_by_id(legacy_id: str, catalog_path: Path, missing_field: str | None = None, consuming_op: str | None = None) -> str`

Convenience wrapper: resolve `legacy_id` and then format. Falls back to a
minimal message containing only the legacy ID if the catalog cannot resolve it
(to preserve compatibility during migration).

---

## Catalog loader (`src/decisions/catalog.py`)

### `load_catalog(catalog_path: Path) -> list[DecisionCatalogEntry]`

Read and parse `catalog.yaml`. Validates:
- All required fields present per entry.
- `status` is one of the allowed values.
- Does NOT validate uniqueness (that is `validate_catalog`'s job).

**Raises**: `DecisionError` if the file is missing, malformed, or contains an
entry with an unknown status value.

---

### `validate_catalog(entries: list[DecisionCatalogEntry]) -> list[str]`

Run uniqueness checks. Returns a list of human-readable error strings (empty
list means valid).

**Checks performed**:
1. No two entries share the same `legacy_id`.
2. No two non-null `key` values are duplicated.
3. No `legacy_id` from `legacy_aliases` collides with a primary `legacy_id`
   in another entry.
4. Every entry with `status == "closed"` has a non-null `key`.

---

## Errors (`src/decisions/errors.py`)

### `DecisionError(message: str)`

Base error for all failures in `src/decisions/`. Sub-classes the built-in
`Exception`. NOT a subclass of any module-specific error
(`DataError`, `StatsError`, etc.) — callers catch module-specific errors;
`DecisionError` is only raised by `src/decisions/` internals.

---

## Calling conventions for per-module updates

Each per-module `decisions.py` SHOULD update its `_require_closed` (or
equivalent) helper to call `format_diagnostic_by_id` when raising its
module-specific error. The module-specific error class is preserved; only the
message string changes.

**Before** (`src/data/decisions.py`):
```python
def _require_closed(item: dict[str, object], decision_id: str) -> None:
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise DataError(decision_id)
    if status == "open":
        raise DataError(decision_id)
```

**After**:
```python
from src.decisions.diagnostic import format_diagnostic_by_id

_CATALOG = Path(__file__).parents[2] / "config" / "decisions" / "catalog.yaml"

def _require_closed(item: dict[str, object], decision_id: str, consuming_op: str) -> None:
    status = item.get("status")
    if status not in {"open", "closed"}:
        raise DataError(format_diagnostic_by_id(decision_id, _CATALOG, consuming_op=consuming_op))
    if status == "open":
        raise DataError(format_diagnostic_by_id(decision_id, _CATALOG, consuming_op=consuming_op))
```

The consuming_op argument is a short label specific to the call site (e.g.
`"exclusion gate"`, `"split construction"`, `"bootstrap interval"`).
