# Feature Specification: FV-SPEC — Artifact Namespace Refactor

**Feature Branch**: `20261002-111741-artifact-namespace-refactor`
**Created**: 2026-10-02
**Status**: Draft
**Input**: User description: "FV-SPEC — Artifact Namespace Refactor"

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Migrate Legacy Artifact Tree (Priority: P1)

A developer runs a migration command to convert the current `.factverify/` tree (which mixes normative protocol, per-fact instances, approvals, reviews and runtime evidence) into the two-root layout, obtaining a full audit trail of what moved where and confirmation that no semantic content was silently dropped.

**Why this priority**: The entire refactor is invalid if legacy artifacts are not accounted for losslessly. This is the foundational step that enables every other story.

**Independent Test**: Can be tested by running the migration command against the current repository in dry-run mode and verifying it produces a complete old→new mapping with no unresolved items, then in execute mode verifying all source artifacts have exactly one recorded new identifier.

**Acceptance Scenarios**:

1. **Given** the current `.factverify/` tree, **When** the migration command runs in dry-run mode, **Then** it emits a complete old→new path mapping, flags any collisions, lists unresolved transformations, and writes nothing to disk.
2. **Given** the migration is executed, **When** semantic normalization is compared, **Then** every source artifact is accounted for and every old identifier has exactly one recorded new identifier.
3. **Given** a legacy Wikidata-backed fact (e.g. `wd-Q1858-P1376-Q881`), **When** it is migrated, **Then** the triple receives FactVerify-native canonical IDs and the Q/P references are retained as optional `external_refs` rather than discarded.
4. **Given** a migration failure partway through, **When** the source tree is inspected, **Then** it remains in its pre-migration state — no partial writes persist.

---

### User Story 2 — Validate Namespace Integrity (Priority: P2)

A developer or CI system runs a layout validator to confirm that the two roots are structurally sound: only frozen inputs exist under `.factverify/`, only runtime transactions and derived outputs exist under `.factverify_internal/`, and no prohibited artifact classes cross boundaries.

**Why this priority**: The claim that FactVerify separates pre-treatment commitments from post-treatment observations depends entirely on this boundary being mechanically enforced, not just documented.

**Independent Test**: Can be tested by seeding a repository with correct and boundary-violating artifact placements, running the validator, and verifying it accepts correct placements and rejects violations with clear error messages naming the artifact class.

**Acceptance Scenarios**:

1. **Given** a repository with correct two-root layout, **When** the namespace validator runs, **Then** it reports no violations.
2. **Given** a ledger, generation, checkpoint, score, witness, result, report, deviation or temporary file placed under `.factverify/`, **When** validation runs, **Then** it fails naming the artifact class and the violating path.
3. **Given** `.factverify/spec/models.yaml` or `.factverify/models.yaml` present, **When** layout validation runs, **Then** it fails and directs the caller to `model_policy.yaml` plus an explicit `config/models/*.yaml` selection.
4. **Given** two root paths that are identical or where one is nested inside the other, **When** initialization runs, **Then** it refuses and names the conflict.

---

### User Story 3 — Open an Experimental Run with Preflight Guard (Priority: P3)

A researcher opens a new training, unlearning or evaluation run. The harness performs a preflight check that verifies the frozen protocol receipt, the fact case bundle and the explicitly supplied model configuration before any model is loaded or any ledger row is committed.

**Why this priority**: Detecting a changed contract or missing fact file after a run completes is too late to protect the comparison. Preflight must guard the boundary between commitments and observations.

**Independent Test**: Can be tested in isolation by passing valid and invalid combinations of frozen protocol digest, fact manifest digest and model config digest to the preflight function, and verifying it accepts only fully matching inputs and refuses all others without writing any run directory or ledger row.

**Acceptance Scenarios**:

1. **Given** matching digests and permitted revisions for all three inputs, **When** preflight succeeds, **Then** the run bundle is created with read-only copies and the ledger records `model_config_id`, model-config digest, fact ID, split, protocol revision and model identity hash.
2. **Given** a missing or mismatched digest on any input, **When** preflight runs, **Then** no run directory or ledger run row is committed.
3. **Given** no explicit model config path supplied, **When** preflight runs, **Then** it refuses and explains that a versioned `config/models/*.yaml` is required.
4. **Given** a model role forbidden by `model_policy.yaml`, **When** preflight runs, **Then** it refuses and names the policy violation.

---

### User Story 4 — Record and Resolve Runtime Artifacts via the Ledger (Priority: P4)

A harness or evaluator records every runtime artifact to `.factverify_internal/` and registers it in the ledger before it is eligible for analysis. An analysis component that attempts to consume an unregistered file is refused.

**Why this priority**: Directory presence alone does not establish provenance, lineage, split, cost or completion status. The ledger is the authority for deciding whether an artifact is valid evidence.

**Independent Test**: Can be tested by writing a file to the internal root without a ledger row, attempting to read it as evidence and verifying refusal; then registering it properly and verifying acceptance.

**Acceptance Scenarios**:

1. **Given** a committed runtime artifact, **When** queried by digest, **Then** the ledger returns its producer run, artifact class, path or URI and creation timestamp.
2. **Given** a file without a committed ledger row, **When** analysis attempts to consume it, **Then** analysis refuses it as unledgered.
3. **Given** a destination outside the internal root without an explicit external-blob declaration, **When** a runtime writer opens it, **Then** the writer refuses.
4. **Given** a file under `.factverify_internal/tmp/`, **When** registration is attempted as evidence, result or checkpoint, **Then** registration refuses.

---

### User Story 5 — Create and Validate Contracts with FactVerify-Native IDs (Priority: P5)

A dataset builder or researcher creates a new fact contract using FactVerify-native canonical identifiers for the fact, contract version, subject entity, relation and object entity. Wikidata and other external mappings attach as optional references but are not required for contract validity.

**Why this priority**: A fact must remain representable when an entity has no Wikidata record. Removing the external-authority dependency is a correctness requirement for the study's controlled fictional facts.

**Independent Test**: Can be tested by validating a contract for a purely fictional fact with no Wikidata mappings and verifying it passes; and by testing that a contract using Wikidata-shaped keys in canonical fields is rejected.

**Acceptance Scenarios**:

1. **Given** a fact whose entities do not exist in Wikidata, **When** its contract is validated, **Then** validation succeeds using only FactVerify-native IDs and labels.
2. **Given** `wikidata:Q…`, `wikidata:P…` or a `wd-Q…-P…-Q…` key in a canonical ID field, **When** strict validation runs, **Then** it fails and identifies the correct optional `external_refs` field instead.
3. **Given** a new contract version of the same semantic fact, **When** validated, **Then** `fact_id` and the contract local ID remain stable while only `:vN` increments.
4. **Given** an entity with no `external_refs`, **When** its local ID and label are valid, **Then** the contract passes without requiring network access or external lookups.
5. **Given** two entities sharing the same external reference or one malformed reference, **When** strict validation runs, **Then** it reports the collision or malformed mapping without rewriting either local ID.

---

### User Story 6 — Export a Portable Reproduction Snapshot (Priority: P6)

A researcher preparing a release exports a bounded, checksummed snapshot containing frozen inputs, selected ledger transactions, evidence, derived results and external-blob content-addressed references, so that a third party can reproduce the study findings in an empty environment.

**Why this priority**: `.factverify_internal/` is a live execution store; a reproduction claim requires a bounded immutable snapshot that can be verified independently.

**Independent Test**: Can be tested by exporting a small scope, importing into an empty directory, and verifying every included digest and ledger row is reproduced exactly.

**Acceptance Scenarios**:

1. **Given** a selected release scope, **When** exported and imported into an empty environment, **Then** every included digest and ledger row is reproduced.
2. **Given** an excluded large blob, **When** exported, **Then** its content-addressed reference and availability status remain in the manifest.

---

### Edge Cases

- What happens when the migration source tree is missing a normatively required artifact?
- How does the system handle a run directory whose artifact manifest no longer matches disk after a partial failure?
- What happens when two facts are assigned the same `<local-id>` during migration?
- How does the layout validator behave against a symlink that points across namespace boundaries?
- What happens when an external blob URI is inaccessible during strict reproduction validation?
- How does temporary-file cleanup interact with an in-progress run writing intermediate outputs to `.factverify_internal/tmp/`?

## Requirements *(mandatory)*

### Functional Requirements

**Storage layout and namespace boundary**

- **FR-001**: The system MUST expose exactly two storage roots — a frozen-input root (`.factverify/`) and a runtime-output root (`.factverify_internal/`) — resolved to distinct, non-overlapping, non-nested absolute paths.
- **FR-002**: The system MUST reject any write of a runtime-generated artifact (run transaction, checkpoint, generation, score, witness, verdict, deviation, cache shard, result, report or temporary file) under the frozen-input root.
- **FR-003**: The system MUST reject any runtime writer that attempts to create an artifact outside the internal root unless the artifact is declared as an external blob with a content-addressed reference.
- **FR-004**: Temporary files under `.factverify_internal/tmp/` MUST NOT satisfy any artifact dependency or support any reported verdict; their removal MUST NOT invalidate any finalized run or report.

**Freeze consolidation**

- **FR-005**: The system MUST represent the complete study-level commitment through exactly five artifacts — `protocol.yaml`, `templates.yaml`, `model_policy.yaml`, `fact.schema.json` and `FREEZE.json` — without a study-global `models.yaml`.
- **FR-006**: `FREEZE.json` MUST record the revision, commit, timestamps, resolved decisions, approvals and content digests of all five frozen artifacts.
- **FR-007**: The system MUST reject any normative field present only in legacy prose, approval or review files with no mapping into the five declared artifacts, reporting the unmapped source path.
- **FR-008**: The system MUST fail and redirect callers whenever `.factverify/spec/models.yaml` or `.factverify/models.yaml` is detected, directing them to `model_policy.yaml` plus an explicit versioned model config selection.

**Fact case bundle**

- **FR-009**: The system MUST materialize every admitted fact as a five-file bundle (`contract.json`, `sources.jsonl`, `neighbourhood.jsonl`, `prompts.jsonl`, `manifest.json`) under `.factverify/facts/<fact_id>/` before that fact enters any intervention.
- **FR-010**: The fact manifest MUST record the split, protocol revision and digest of each sibling artifact; it MUST NOT bind a study-global model selection.
- **FR-011**: The system MUST refuse to open a run for any fact whose bundle has a missing file, digest mismatch or unresolved decision.

**Preflight and run isolation**

- **FR-012**: The system MUST verify `FREEZE.json`, the selected fact manifest and the explicitly supplied model configuration digest before opening any training, unlearning or evaluation run, and MUST commit no run directory or ledger row if any check fails.
- **FR-013**: Each run MUST store its manifest, frozen run config, event stream, metric stream, final verdict and artifact manifest under `.factverify_internal/runs/<run_id>/`.
- **FR-014**: The run manifest MUST bind fact ID, role, method, seed, split, protocol revision, code commit, `model_config_id`, model-config digest, model identity hash and config hash.
- **FR-015**: Any final file in a finalized run that is changed MUST cause integrity verification to fail against the run artifact manifest.

**Ledger authority**

- **FR-016**: The system MUST record every runtime artifact in `.factverify_internal/ledger.sqlite` before that artifact is eligible for analysis or reporting.
- **FR-017**: Any analysis component that attempts to consume a file without a committed ledger row MUST be refused, with the file reported as unledgered.

**External blob references**

- **FR-018**: Any checkpoint, cache shard or large artifact stored outside `.factverify_internal/` MUST be represented with a URI, byte size, content digest and producing run ID in both the ledger and the run artifact manifest.
- **FR-019**: During strict reproduction validation, any blob with a missing digest, size, producer or inaccessible URI MUST be reported as unavailable and no dependent verdict may be reproduced.

**FactVerify-native canonical identity**

- **FR-020**: The system MUST assign every fact, contract version, subject entity, relation and object entity a FactVerify-native identifier matching the forms `factverify:fact:<local-id>`, `factverify:contract:<local-id>:v<N>`, `factverify:entity:<local-id>` and `factverify:relation:<local-id>`.
- **FR-021**: `<local-id>` MUST be a non-empty lowercase identifier matching `[a-z0-9][a-z0-9_-]*`, stable after freeze; label changes or new external mappings MUST NOT change it.
- **FR-022**: The system MUST reject any Wikidata-shaped key (`wikidata:Q…`, `wikidata:P…`, `wd-Q…-P…-Q…`) in any canonical ID field, and MUST direct callers to the optional `external_refs` array instead.
- **FR-023**: Contract validity MUST NOT require any external knowledge-base lookup, network access or mapping.

**Optional external references**

- **FR-024**: The schema MUST provide an optional `external_refs[]` array on entities and relations, with required fields `scheme` and `external_id`, and optional fields `url`, `retrieved_at` and verification metadata.
- **FR-025**: The system MUST validate that no two entities share the same external reference and that all external references are well-formed, without rewriting either local ID.

**Migration**

- **FR-026**: The migration command MUST provide a dry-run mode that emits a complete old→new path mapping, collisions and unresolved transformations without writing anything to disk.
- **FR-027**: After a completed migration, every source artifact MUST be accounted for with exactly one recorded new identifier.
- **FR-028**: A failed migration MUST leave the source tree unchanged with no partial target writes.
- **FR-029**: Every legacy Wikidata-backed fact triple MUST receive FactVerify-native canonical IDs, with Q/P references retained as optional `external_refs`.

**Legacy retirement**

- **FR-030**: All legacy code, tests, fixtures, specifications and documentation affected by the migration MUST be inventoried before implementation starts, each recording artifact class, chosen action (`refactor`, `replace`, `delete` or `migration-only isolate`), rationale, replacement path and verification method.
- **FR-031**: After cutover, production code MUST contain no legacy path fallback, legacy reader/writer, dual-write behaviour or acceptance of the retired layout.
- **FR-032**: CI MUST fail and name any unallowlisted reference to a retired path or artifact (e.g. `.factverify/spec/models.yaml`, legacy contract directories, legacy runtime-output directories).

**Reproduction export**

- **FR-033**: The system MUST export a portable, checksummed reproduction snapshot containing frozen inputs, selected ledger transactions, evidence, derived results and external-blob references under a single release manifest.
- **FR-034**: Importing a reproduction snapshot into an empty environment MUST reproduce every included digest and ledger row.

**Configuration**

- **FR-035**: The two root paths MUST be configurable via `FACTVERIFY_SPEC_ROOT` and `FACTVERIFY_INTERNAL_ROOT`; CLI flags MUST allow explicit overrides; code MUST NOT infer roots from the current working directory after initialization.
- **FR-036**: A concrete model configuration MUST be supplied as an explicit path to a versioned `config/models/<model-config-id>.yaml`; it MUST NOT be inferred from either root.

### Key Entities

- **Frozen-input root (`.factverify/`)**: The immutable namespace holding study-level protocol artifacts and per-fact case bundles. No runtime-generated artifact may be written here after spec freeze.
- **Runtime root (`.factverify_internal/`)**: The append-only namespace holding all run transactions, ledger, cache, checkpoints, evidence, results, reports, deviations and temporaries.
- **Fact case bundle**: A five-file directory under `.factverify/facts/<fact_id>/` representing one admitted fact. Immutable after fact freeze.
- **FREEZE.json**: A single receipt at the root of `.factverify/` recording revisions, timestamps, decisions, approvals and content digests for the five normative artifacts.
- **Run bundle**: A directory under `.factverify_internal/runs/<run_id>/` containing the complete record of one experimental run — manifest, config snapshot, event stream, metrics and verdict.
- **Ledger**: `.factverify_internal/ledger.sqlite` — the transaction authority for all runtime artifacts.
- **External blob reference**: A content-addressed pointer (URI, byte size, digest, producer run ID) registered in both the ledger and the run artifact manifest for artifacts stored outside `.factverify_internal/`.
- **FactVerify-native ID**: A stable, project-internal identifier of the form `factverify:<type>:<local-id>` (or `factverify:contract:<local-id>:vN`), independent of any external knowledge base.
- **Model selection config**: A versioned file under `config/models/<model-config-id>.yaml` supplied explicitly per run. Its bytes and digest are snapshotted into the run bundle at preflight.
- **Model policy**: `.factverify/model_policy.yaml` — the frozen study-level policy governing permitted model roles. Not a concrete model selection.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every legacy `.factverify/` artifact appears in the migration report with exactly one recorded new identifier — zero unaccounted-for artifacts after a completed migration.
- **SC-002**: The layout validator accepts 100% of correct two-root placements and rejects 100% of cross-boundary placements in the verification test suite, naming the violated artifact class in every rejection.
- **SC-003**: Preflight detects 100% of missing or mismatched digests across frozen protocol, fact manifest and model config, refusing all affected runs without writing any run directory or ledger row.
- **SC-004**: Zero unledgered artifacts are consumable by analysis — every attempt to consume an unregistered file is refused.
- **SC-005**: Contract validation accepts 100% of contracts using only FactVerify-native IDs and rejects 100% of contracts using Wikidata-shaped keys in canonical ID fields.
- **SC-006**: After migration and cutover, CI detects and fails on 100% of unallowlisted references to retired paths, verified by the reference-scan test suite.
- **SC-007**: A reproduction snapshot imported into an empty environment reproduces every included digest and ledger row, verified by a roundtrip test on a representative sample.
- **SC-008**: All namespace checks (layout validation, preflight, ledger registration) complete without any model call — no GPU resources are required.
- **SC-009**: Every finalized run manifest binds all required provenance fields: fact ID, role, method, seed, split, protocol revision, code commit, `model_config_id`, model-config digest, model identity hash and config hash.

## Assumptions

- The migration runs against the repository state as of 2026-10-02; preventing concurrent writes to `.factverify/` during migration is the operator's responsibility.
- `config/models/` already contains at least one versioned model config (e.g. `block0-debug-pythia-410m.yaml`); the migration does not create model configs.
- The existing `fact_contract.schema.json` contains the semantic content to be migrated to `fact.schema.json`; no scientific schema semantics change beyond identity and external-reference fields.
- D-71 and D-72 are resolved and authoritative; this spec does not reopen either decision.
- The existing `model_policy.yaml` is moved to `.factverify/model_policy.yaml` as a path-only change; its semantic content does not change during this refactor.
- `.factverify/spec/models.yaml` has been retired and will not be recreated; this is asserted by layout validation.
- Atomic filesystem writes (via temporary-file-then-rename) are available on the target platform for the fail-closed transaction requirement.
- Git history serves as the recovery mechanism for deleted legacy files; no archive copies are maintained in the working tree after cutover.
- P0–P2 tests that express scientific decisions are updated to pass against the new layout without changing any threshold, seed or statistical parameter.
