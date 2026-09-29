# Quickstart: Readable Decision Identifiers

**Feature**: `20260929-110152-readable-decision-identifiers`
**Date**: 2026-09-29

This guide shows how to use the new decision catalog and diagnostic system
after it is implemented.

---

## 1. Look up any decision

```python
from pathlib import Path
from src.decisions.resolver import resolve

CATALOG = Path("config/decisions/catalog.yaml")

entry = resolve("D-65", CATALOG)
print(entry.key)     # "data.exclusion_gate.policy"
print(entry.title)   # "Knowledge-exclusion gate policy"
print(entry.status)  # "open"

# Same result by semantic key:
entry2 = resolve("data.exclusion_gate.policy", CATALOG)
assert entry == entry2
```

---

## 2. Produce an actionable diagnostic

```python
from src.decisions.diagnostic import format_diagnostic_by_id

CATALOG = Path("config/decisions/catalog.yaml")

msg = format_diagnostic_by_id(
    "D-65",
    CATALOG,
    missing_field="threshold",
    consuming_op="exclusion gate",
)
print(msg)
# Decision required: data.exclusion_gate.policy (legacy D-65)
# Knowledge-exclusion gate policy is open or incomplete.
# Missing field: threshold. Required by: exclusion gate.
```

---

## 3. Raise a module error with the enriched message

```python
from src.data.errors import DataError
from src.decisions.diagnostic import format_diagnostic_by_id

CATALOG = Path("config/decisions/catalog.yaml")

raise DataError(
    format_diagnostic_by_id("D-65", CATALOG, missing_field="threshold", consuming_op="exclusion gate")
)
```

The existing `DataError` is preserved. Only the message string becomes rich.

---

## 4. Validate the catalog for uniqueness

```python
from pathlib import Path
from src.decisions.catalog import load_catalog, validate_catalog

entries = load_catalog(Path("config/decisions/catalog.yaml"))
errors = validate_catalog(entries)
if errors:
    for e in errors:
        print(e)
```

Run this check with `uv run python -m src.decisions.catalog` (or via CI) to
confirm no collisions have been introduced.

---

## 5. Regenerate the decision reference document

```bash
uv run python tools/generate_decision_ref.py \
    --catalog config/decisions/catalog.yaml \
    --output docs/decision_reference.md
```

CI runs this and diffs the output against the committed file. Any divergence
causes the build to fail. After editing `catalog.yaml`, regenerate and commit
both files.

---

## 6. Add a new decision to the catalog

1. Open `config/decisions/catalog.yaml`.
2. Add a new entry following the schema in `specs/.../data-model.md`.
3. Set `status: "open"` initially; `key` is required and must be unique.
4. Run the uniqueness validator (step 4 above) to confirm no collision.
5. Regenerate the reference document (step 5 above).
6. Commit `catalog.yaml` and `docs/decision_reference.md` together.

**New entries that omit `key` will be rejected by the validator.**

---

## 7. Handle a collision entry

If you encounter a diagnostic like:

```
Decision required: (legacy D-08) [COLLISION — owner resolution required]
Uncertainty seed types / multiplicity procedure has conflicting meanings.
See docs/tickets/readable-decision-identifiers.md.
```

This means `D-08` has a confirmed meaning conflict that has not been resolved.
Do not attempt to use this decision until the study owner has assigned a unique
semantic key and split the conflicting usages into separate catalog entries.

---

## Running the tests

```bash
# All new decision tests
uv run pytest tests/unit/test_decisions_catalog.py \
               tests/unit/test_decisions_diagnostic.py \
               tests/unit/test_decisions_resolver.py \
               tests/integration/test_data_decisions.py \
               tests/integration/test_generate_decision_ref.py -v
```
