# Feature Specification: Readable Decision Identifiers

**Feature Branch**: `20260929-110152-readable-decision-identifiers`
**Created**: 2026-09-29
**Status**: Draft
**Input**: User description: docs/tickets/readable-decision-identifiers.md

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Actionable Decision Diagnostics (Priority: P1)

A researcher or developer runs a validation step and it fails because a study
decision is open or incomplete. Instead of seeing an opaque code like `D-65`,
they receive a message that names the decision's purpose, which specific
setting is missing, who owns the decision, and what operation needs it — so
they can act immediately without searching the repository.

**Why this priority**: This is the core user value of the entire feature. All
other work (catalog, lookup, migration) is invisible to the operator unless
error messages change. An operator who still sees only `D-65` cannot benefit
from anything else delivered.

**Independent Test**: Trigger a validation run against a decision file that is
missing a required field. Confirm the output names the decision's human title,
the missing field, and the owner or resolution location. No search of any
source file should be needed to understand the message.

**Acceptance Scenarios**:

1. **Given** a study decision whose required field `threshold` has not been
   set, **When** the exclusion gate runs, **Then** the diagnostic reads
   `data.exclusion_gate.policy (legacy D-65) — Knowledge-exclusion gate
   policy is open or incomplete. Missing field: threshold. Required by:
   exclusion gate.`

2. **Given** a decision that is present but marked open (status: open),
   **When** any consumer requests its value, **Then** the diagnostic names
   the semantic key first, the legacy ID second, the title, the status, and
   the consuming operation.

3. **Given** a decision diagnostic produced before this feature was
   implemented (containing only `D-65`), **When** a developer reads it,
   **Then** they can look it up in the authoritative catalog by that legacy ID
   and retrieve the same information a new diagnostic would show.

---

### User Story 2 — Single-Source Decision Lookup (Priority: P2)

A developer cross-referencing a historical artifact (which uses a legacy ID
like `D-08`) with current code (which uses a semantic key) needs to confirm
they are referring to the same decision. They consult one authoritative
catalog and find the entry by either identifier — the catalog is the single
source of truth.

**Why this priority**: The catalog is the structural foundation on which
diagnostics, migration, and integrity checks all depend. Without it, semantic
keys and legacy IDs are just two unconnected naming schemes.

**Independent Test**: Given the catalog in place with at least ten entries,
query by legacy ID `D-46` and confirm the result matches the entry retrieved
by key `model.blocks_0_2.identity`. Then query by an ID that does not exist
and confirm a clear not-found response.

**Acceptance Scenarios**:

1. **Given** the catalog is populated, **When** a developer looks up `D-65`,
   **Then** they receive the entry with key `data.exclusion_gate.policy`,
   title, description, owner, consumers, required fields, and status.

2. **Given** the catalog is populated, **When** a developer looks up
   `data.exclusion_gate.policy`, **Then** they receive the same entry as
   above.

3. **Given** two catalog entries that accidentally share the same legacy ID,
   **When** the catalog is validated, **Then** validation fails and reports
   the collision before any consumer runs.

4. **Given** two catalog entries that accidentally share the same semantic
   key, **When** the catalog is validated, **Then** validation fails and
   reports the duplicate before any consumer runs.

---

### User Story 3 — Dual-ID Traceability in Outputs (Priority: P3)

A study auditor reviews a ledger row, a verdict record, or a validation
report generated after migration. The record contains both the semantic key
and the legacy ID for every referenced decision, so the auditor can trace it
forward to current catalog definitions and backward to historical artifacts
without ambiguity.

**Why this priority**: Traceability is required for the audit claim but does
not block the core operator UX. It can be delivered after the catalog and
diagnostics are working.

**Independent Test**: Run the full validation pipeline against a known set of
decisions and inspect one output record. Confirm it contains both
`data.exclusion_gate.policy` and `D-65` in the same record for the same
decision reference.

**Acceptance Scenarios**:

1. **Given** migration is complete, **When** the pipeline generates a new
   ledger row referencing any decision, **Then** the row contains both the
   semantic key and the legacy ID for that decision.

2. **Given** migration is complete, **When** a verdict or validation report
   is written, **Then** every decision reference in that output contains both
   identifiers.

3. **Given** a record generated before migration (legacy ID only), **When**
   an auditor reads it, **Then** the legacy ID still resolves to a catalog
   entry so the record remains interpretable.

---

### User Story 4 — Catalog Integrity Enforcement (Priority: P4)

A developer adds a new study decision to the repository. The system validates
that the new entry has a semantic key, that the key is unique across the
catalog, that the legacy ID is not already in use, and that all required
fields are declared. If any check fails, the addition is rejected before it
can reach a shared environment.

**Why this priority**: Enforcement only adds value once the catalog is
populated and in use. It prevents future collisions but is not needed to
deliver the three higher-priority stories.

**Independent Test**: Submit a new decision entry that reuses an existing
legacy ID. Confirm rejection with a message identifying the collision.
Submit a valid entry. Confirm acceptance.

**Acceptance Scenarios**:

1. **Given** a new decision definition that omits the semantic key, **When**
   the validator runs, **Then** it rejects the entry and reports that the
   semantic key is missing.

2. **Given** a new decision entry whose legacy ID already appears in the
   catalog, **When** the validator runs, **Then** it rejects the entry and
   names the existing entry that holds that ID.

3. **Given** a legacy-only file written before this feature existed (contains
   only `decision_id: D-65`), **When** it is validated in compatibility mode,
   **Then** it passes without error, so no historical data is broken.

4. **Given** the catalog is valid and up to date, **When** a reference
   document is generated from it, **Then** the document is identical on two
   successive runs with no catalog changes (deterministic output).

---

### Edge Cases

- A legacy ID with no confirmed meaning (e.g., `D-12`) must be explicitly
  flagged as unresolved, not silently accepted or silently dropped.
- A legacy ID that appears with incompatible meanings in two locations
  (collision) must be detected and reported before any semantic key is
  assigned to it; no migration step may proceed on a unresolved collision.
- A decision that bundles multiple independent sub-decisions (e.g., baseline
  policy plus threshold plus scoring) may need to be split into separately
  approvable entries; the split decision belongs to the study owner and must
  be recorded before migration touches those entries.
- An attempt to reassign a legacy ID to a new concept must be rejected
  unconditionally — legacy IDs are immutable audit handles.
- A frozen artifact containing a bare legacy reference must not be
  modified as part of migration; only newly written outputs adopt the
  dual-ID format.
- A collision candidate (`D-30`) that is absent from the repository
  entirely requires explicit disposition (removed / never existed) rather
  than being left as a gap in the catalog.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST maintain a single authoritative decision catalog
  that maps each semantic key to its legacy ID, human title, description,
  domain, owner, list of consumers, required fields, and status.

- **FR-002**: The system MUST allow any decision to be retrieved by either its
  semantic key or its legacy ID; both lookups MUST return the same entry.

- **FR-003**: Any diagnostic or exception raised because a decision is open,
  incomplete, or missing a required field MUST include: semantic key, legacy
  ID, human title, status, the name of the missing or invalid field, and the
  consuming operation. Owner or resolution location MUST be included when
  known.

- **FR-004**: The catalog MUST pass a uniqueness check confirming that no two
  entries share a semantic key and no two entries share a legacy ID; this
  check MUST run before any consumer of the catalog executes.

- **FR-005**: Newly generated output records (ledger rows, verdict records,
  validation reports) MUST contain both the semantic key and the legacy ID for
  every decision they reference.

- **FR-006**: Legacy-only decision definitions (those that carry only a legacy
  ID and no semantic key) MUST continue to be accepted in compatibility mode
  without any change to existing behavior.

- **FR-007**: Any new decision definition that omits the semantic key MUST be
  rejected by the validator with a message identifying the missing field.

- **FR-008**: The system MUST detect and report all cases where a single
  legacy ID has been given incompatible meanings in different locations before
  any semantic key is assigned to it.

- **FR-009**: A human-readable decision reference document MUST be
  generatable from the catalog as a deterministic, repeatable operation; the
  generated document MUST be verified as current by the automated quality
  pipeline.

- **FR-010**: No frozen specification artifact may be modified as part of
  this migration; historical legacy IDs in frozen artifacts MUST remain
  readable indefinitely in compatibility mode.

### Key Entities

- **Decision Catalog Entry**: The canonical record for one study decision.
  Attributes: semantic key (unique), legacy ID (unique, immutable), human
  title, description, domain, owner, list of consumers, list of required
  fields, status, and any additional legacy aliases.

- **Decision Diagnostic**: The structured output produced when a consumer
  encounters an open, incomplete, or missing decision. Contains: semantic key,
  legacy ID, title, status, specific missing or invalid field, consuming
  operation, and owner or resolution pointer.

- **Decision Reference Document**: A generated, human-readable index of all
  catalog entries. Deterministic: identical inputs always produce identical
  output. Checked into the repository and verified by CI.

- **Legacy Decision File**: A pre-existing file that identifies a decision by
  its legacy ID only. Accepted in compatibility mode; deprecated for new
  authoring.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: After migration is complete, every legacy ID reference in source
  code, tests, specifications, configuration, and documentation resolves to
  exactly one catalog entry or is explicitly marked historical or unresolved —
  zero ambiguous references remain.

- **SC-002**: All five confirmed ID collisions (D-08, D-09, D-17, D-22, D-42)
  are resolved, each assigned an unambiguous owner-confirmed meaning, and each
  resolution is covered by a regression test that would catch a future
  reintroduction of the collision.

- **SC-003**: Every runtime path that previously emitted only a bare legacy ID
  now emits the full diagnostic structure; no new user-facing output contains
  only a legacy ID without its semantic key, title, and field context.

- **SC-004**: All existing test fixtures that used legacy-only decision
  references continue to pass without semantic changes after migration — zero
  regressions.

- **SC-005**: The decision reference document is verified as deterministic and
  current by the automated quality pipeline on every commit that touches the
  catalog — no manual step is required to keep it up to date.

- **SC-006**: No frozen specification is modified without a corresponding
  amendment record and new spec revision — the amendment log is verifiable by
  inspection.

## Assumptions

- The five known collision cases (D-08, D-09, D-17, D-22, D-42) will be
  resolved by the study owner before Phase 3 caller migration begins; the
  catalog and diagnostic layers can be built in Phase 2 without waiting for
  all collisions to be resolved, but migration of colliding callers is blocked
  until the owner confirms the intended meaning.
- `D-30` is absent from the repository and requires an explicit "not present"
  disposition in the catalog rather than a populated entry.
- The decision whether to split overloaded entries (D-54, D-65 each bundle
  multiple independent sub-decisions) belongs to the study owner and will be
  declared before Phase 3 migration touches those entries; this spec does not
  mandate a specific split.
- Frozen specification artifacts under `.factverify/spec/` and
  `spec-unlearning/` will not be bulk-edited; any reference inside them
  remains in legacy form and is handled by compatibility mode.
- The decision reference document generation is a fully automated,
  non-interactive operation that requires no human input to produce a correct
  result.
- Migration proceeds in four phases (reconcile → catalog + aliases → caller
  migration → deprecate bare IDs); each phase may be delivered and validated
  independently.
