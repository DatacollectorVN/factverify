# Research: Readable Decision Identifiers

**Feature**: `20260929-110152-readable-decision-identifiers`
**Date**: 2026-09-29

## Existing Architecture (findings from codebase exploration)

### Decision loading — current pattern

Every module that depends on study decisions has a local `decisions.py` that:

1. Loads a YAML file via `yaml.safe_load`.
2. Scans the `decisions:` list for an entry whose `decision_id` matches the
   target literal string (e.g., `"D-65"`).
3. Validates status (`"open"` / `"closed"`) and required fields.
4. Raises the module's own error class with the legacy ID as the sole message:
   `DataError("D-65")`, `StatsError("D-08")`, `LedgerError("D-56")`.

The error message is therefore always a bare legacy ID. There is no shared
formatter and no enrichment.

### Module inventory

| Module | Error class | Decisions loaded |
|--------|-------------|-----------------|
| `src/data/` | `DataError` | D-65, D-68 (dedicated loaders); D-62 referenced in `tofu.py` |
| `src/stats/` | `StatsError` | D-03, D-05, D-06, D-07, D-08, D-10, D-57 |
| `src/controls/` | `ControlError` | D-53, D-54, D-55, D-58, D-59, D-61 |
| `src/cache/` | `CacheError` | D-60 |
| `src/ledger/` | `LedgerError` | D-56 |
| `src/eval/` | `FactVerifyEvalError` | D-14, D-17–D-26 (via `spec_load.py`) |

### Existing registry

`.factverify/decisions/register.yaml` is a flat mapping of D-* IDs to owner,
status, notes, and `blocked_specs`. It uses a different format from the
per-module YAML files (dict of dicts, not list of dicts). It has no semantic
keys and no `consumers` or `required_fields` fields. It is NOT the same as the
catalog proposed in the ticket.

### Collision evidence in the register

The register contains D-08 (`notes: "uncertainty — seed_types"`) but
`src/stats/multiplicity.py` uses D-08 to mean "multiplicity procedure (holm /
bh / by)". These are different concepts in the same ID. This confirms the
collision report in the ticket.

D-17 in the register means "deviation categories completeness" but is used in
`src/eval/budget.py` as the total evaluator trial cap. Second confirmed
collision.

D-22 in the register means "amendment protocol fields" but is used in
`src/eval/budget.py` as "equal caps versus equal realized usage". Third
confirmed collision.

D-09 does not appear in the module code surveyed; only in the register as an
open decision. D-42 appears in the register as "milestone staged rule
completeness" but the ticket notes it also governs "closure-template
group/split assignment in P0-2 and P1 data preparation".

### Absence of `config/decisions/`

No `config/decisions/catalog.yaml` exists. The new catalog is a net-new file.

---

## Design Decisions

### D1 — New module location: `src/decisions/`

**Decision**: Create a new `src/decisions/` package to house the shared
catalog loader, resolver, and diagnostic formatter.

**Rationale**: Each existing module (`data`, `stats`, `controls`, etc.) has its
own `decisions.py`. A cross-cutting shared layer must not live inside any of
them. A top-level `src/decisions/` package is symmetrical with the other
top-level modules and clearly signals "this is the single source of truth".

**Alternatives considered**:
- Put the catalog loader in `tools/` — rejected because `tools/` is for CLI
  scripts, not importable library code.
- Add to `src/eval/` — rejected because other modules (`data`, `stats`) must
  not import from `eval`.

### D2 — Catalog format: YAML list with dotted keys

**Decision**: `config/decisions/catalog.yaml` is a YAML list where each entry
has `legacy_id`, `key`, `title`, `description`, `domain`, `owner`,
`consumers`, `required_fields`, `status`, and `legacy_aliases`.

**Rationale**: This matches the proposed format in the ticket exactly. YAML is
already the project's config language. A list (rather than a dict keyed by ID)
allows entries to be loaded and sorted without key conflicts during migration
when some IDs are still unresolved or split.

**Alternatives considered**:
- JSON — rejected because the project uses YAML everywhere for human-edited
  config.
- Dict keyed by legacy ID — rejected because it creates a structural dependency
  on the legacy ID being the natural key, which conflicts with the goal of
  making semantic keys primary.

### D3 — Resolver: load catalog once per process, cache in module scope

**Decision**: The resolver module loads and validates the catalog on first use
and stores the result in a module-level cache keyed on the resolved `Path`.
No process-global singleton; tests can pass different paths.

**Rationale**: Decision resolution happens at config-load time for a single run.
Performance is not a concern; but thread safety is, because pytest runs tests
concurrently. Using a `dict[Path, CatalogIndex]` cache avoids re-reading the
file on every lookup while keeping the cache key stable across test cases.

**Alternatives considered**:
- Global singleton loaded at import time — rejected because it would require
  the catalog to exist at import time, breaking tests that do not use the
  catalog.
- Re-read on every call — simple but wastes I/O; rejected.

### D4 — Diagnostic message format: multi-line, semantic key first

**Decision**: The diagnostic formatter returns a multi-line string:

```
Decision required: <key> (legacy <legacy_id>)
<title> is open or incomplete.
[Missing field: <field>. ][Required by: <consuming_op>.]
```

Lines 3+ are omitted when the corresponding argument is `None`.

**Rationale**: The format matches the example in both the ticket and Principle 14
of the constitution. Multi-line is fine for error strings because these are
surfaced to humans at the terminal, not machine-parsed.

**Alternatives considered**:
- Structured object raised instead of string — considered for future
  programmatic use, but the existing error classes all carry a string message.
  The diagnostic formatter produces a string; if a structured form is needed
  later, it can be added as a second function.

### D5 — Compatibility: legacy-only YAML files accepted without change

**Decision**: The per-module `_item()` / `_rows()` functions are not changed.
They continue to read `decision_id` fields from YAML. The shared diagnostic
formatter is called with the legacy ID as a lookup key. If the catalog has an
entry for that ID, the enriched message is returned; if not (during the
transition), the formatter falls back to the legacy ID alone.

**Rationale**: FR-006 requires legacy-only historical inputs to be accepted in
compatibility mode. Changing the YAML parsing rules would break existing test
fixtures and operator-written decision files.

### D6 — Dual-ID in ledger rows: add `decision_key` column

**Decision**: When `src/ledger/api.py` writes a row that references a decision,
it also writes the semantic key resolved from the catalog. If the catalog
cannot resolve the legacy ID (pre-migration period), `decision_key` is `null`.

**Rationale**: FR-005 requires both IDs in newly generated records. A nullable
column means the ledger schema does not break before the catalog is fully
populated.

### D7 — Collision entries: mark status as `collision`, no semantic key

**Decision**: The five confirmed collisions (D-08, D-09, D-17, D-22, D-42) are
entered in the catalog with `status: collision` and `key: null`. The resolver
returns a special `CollisionEntry` that the diagnostic formatter renders as:

```
Decision required: (legacy D-08)
D-08 has confirmed conflicting meanings — owner resolution required before
this ID can be migrated. See docs/tickets/readable-decision-identifiers.md.
```

**Rationale**: The catalog must cover every D-* ID (SC-001) including
unresolved ones. Marking them `collision` makes them visible to the uniqueness
checker and produces a useful diagnostic instead of a silent omission.

### D8 — Reference document: Markdown generated from catalog by `tools/generate_decision_ref.py`

**Decision**: The reference document is a Markdown file output by
`tools/generate_decision_ref.py` to `docs/decision_reference.md`. It is
generated deterministically (sorted by `legacy_id`). CI runs the generator and
diffs against the committed file; any divergence is a build failure.

**Rationale**: SC-005 requires a deterministic, CI-verified document. The
generator is a simple script that reads the catalog and writes sorted Markdown
tables, making the output fully reproducible.

---

## Migration Phase Mapping to User Stories

| Phase (ticket) | User Story | Deliverable |
|----------------|------------|-------------|
| Phase 1: Reconcile | Pre-condition (owner action, not code) | D-08/D-09/D-17/D-22/D-42 collision records in catalog with `status: collision` |
| Phase 2: Aliases + diagnostics | US1 + US2 | `src/decisions/`, catalog, resolver, formatter; per-module error updates |
| Phase 3: Migrate callers | US3 | Dual-ID in ledger/verdict outputs |
| Phase 4: Deprecate | US4 | Validator rejects new definitions without `key`; reference doc in CI |
