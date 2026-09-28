# Data Model: Readable Decision Identifiers

**Feature**: `20260929-110152-readable-decision-identifiers`
**Date**: 2026-09-29

## Entities

### DecisionCatalogEntry

The canonical record for one study decision. Lives in
`config/decisions/catalog.yaml` as a YAML list item.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `legacy_id` | `str` | Yes | Immutable audit handle (e.g. `"D-65"`). Unique across the catalog. |
| `key` | `str \| None` | Yes | Dotted semantic key (e.g. `"data.exclusion_gate.policy"`). `null` when status is `collision` or `unresolved`. Unique across non-null entries. |
| `title` | `str` | Yes | Short human-readable name (e.g. `"Knowledge-exclusion gate policy"`). |
| `description` | `str` | Yes | One-paragraph explanation of what the decision controls. |
| `domain` | `str` | Yes | Top-level grouping. Allowed values: `stats`, `eval`, `data`, `model`, `controls`, `ledger`, `cache`, `preregistration`, `training`, `facts`, `witness`, `closure`, `access`, `reporting`. |
| `owner` | `str` | Yes | Person or role responsible for closing the decision. |
| `consumers` | `list[str]` | Yes | Dotted module paths that read this decision (e.g. `"src.data.decisions.load_d65"`). May be empty list for fully resolved historical decisions. |
| `required_fields` | `list[str]` | Yes | Field names that must be present and non-null when `status == "closed"`. May be empty. |
| `status` | `str` | Yes | `"open"` \| `"closed"` \| `"pending"` \| `"collision"` \| `"unresolved"` \| `"absent"` |
| `legacy_aliases` | `list[str]` | Yes | Additional legacy IDs that map to this entry (for decisions that appeared under multiple IDs in historical files). Usually empty. |

**Validation invariants**:

- `legacy_id` is unique across all entries (including `legacy_aliases` of other entries).
- `key` is unique across all entries where `key is not None`.
- When `status == "collision"`, `key` MUST be `null`.
- When `status == "closed"`, `key` MUST be non-null.

---

### DecisionDiagnostic

The structured representation of a blocked-decision error. Produced by the
diagnostic formatter and embedded in exception messages.

| Field | Type | Nullable | Description |
|-------|------|----------|-------------|
| `key` | `str \| None` | Yes | Semantic key, if assigned. `None` for collision/unresolved entries. |
| `legacy_id` | `str` | No | Legacy audit ID. |
| `title` | `str` | No | Human-readable name from the catalog. |
| `status` | `str` | No | Status field from the catalog entry. |
| `missing_field` | `str \| None` | Yes | Specific field that is absent or invalid. |
| `consuming_op` | `str \| None` | Yes | Short label for the operation that needs this decision. |
| `owner` | `str \| None` | Yes | Owner from the catalog entry, when available. |

**Rendered format** (the string placed inside exception messages):

```
Decision required: <key> (legacy <legacy_id>)
<title> is open or incomplete.
Missing field: <missing_field>. Required by: <consuming_op>.
```

Lines 3 and onwards are omitted when the corresponding field is `None`.
For collision entries where `key` is `None`, the first line reads:
`Decision required: (legacy <legacy_id>) [COLLISION — owner resolution required]`

---

### CatalogIndex

An in-memory index built from the catalog file. Not persisted; rebuilt on
first use per process (or per test invocation, keyed by resolved path).

| Attribute | Type | Description |
|-----------|------|-------------|
| `by_legacy_id` | `dict[str, DecisionCatalogEntry]` | Primary lookup by legacy ID. |
| `by_key` | `dict[str, DecisionCatalogEntry]` | Lookup by semantic key (non-null keys only). |
| `path` | `Path` | Resolved path from which the index was loaded. |

---

### LegacyDecisionFile (existing — unchanged structure)

The YAML format already in use by per-module decision loaders. The catalog
adds metadata around these; the file format itself does not change.

```yaml
decisions:
  - decision_id: D-65       # legacy ID — existing field, unchanged
    decision_key: data.exclusion_gate.policy   # NEW optional field (Phase 4)
    status: closed
    baseline: random_choice
    threshold: 0.5
    # … other fields
```

The new `decision_key` field is optional and ignored by existing loaders. It
provides a human-readable hint inside the file and is written by new authoring
tools. It does not change how the loader resolves the entry.

---

## State Transitions for a Decision

```
                   owner assigns meaning
   collision ──────────────────────────► open
   unresolved ─────────────────────────► open
   absent ──────────────────────────────► open
   open ───── owner approves value ─────► closed
   pending ── supervisor sign-off ─────► closed
   closed ─── reopen (amendment) ──────► open
```

---

## Catalog YAML Schema (abbreviated)

```yaml
# config/decisions/catalog.yaml
- legacy_id: "D-65"
  key: "data.exclusion_gate.policy"
  title: "Knowledge-exclusion gate policy"
  description: >-
    Defines how the pinned base model is judged as already knowing a fact.
    Controls baseline construction, threshold, scoring, decoding, and the
    contamination trigger.
  domain: "data"
  owner: "study_owner"
  consumers:
    - "src.data.decisions.load_d65"
    - "src.data.exclusion.run_gate"
  required_fields:
    - "baseline"
    - "threshold"
    - "comparison"
    - "cell_score"
    - "decoding_seeds"
    - "generation"
    - "contamination_trigger"
  status: "open"
  legacy_aliases: []

- legacy_id: "D-08"
  key: null
  title: "Uncertainty seed types / multiplicity procedure"
  description: >-
    Collision: used to mean uncertainty seed types in the decision register
    and multiplicity procedure (holm/bh/by) in stats code. Owner resolution
    required before migration.
  domain: "stats"
  owner: "study_owner"
  consumers:
    - "src.stats.decisions.load_decision"
    - "src.stats.multiplicity"
  required_fields: []
  status: "collision"
  legacy_aliases: []
```
