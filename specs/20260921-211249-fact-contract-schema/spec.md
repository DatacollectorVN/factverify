# Feature Specification: P0-1 Atomic-Fact Contract Schema

**Feature Branch**: `20260921-211249-fact-contract-schema`
**Created**: 2026-09-21
**Status**: Draft
**Input**: FV-SPEC requirements from `second-brain/ml-unlearning/requirements/FV-SPEC — P0-1.md`

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Validate a fact contract structurally (Priority: P1)

A researcher writes a JSON contract declaring the atomic fact to be unlearned — its triple, aliases, equivalent directions, retained neighbourhood, and clue boundary. They run a single validation command and receive a pass/fail verdict with actionable diagnostics for every structural error.

**Why this priority**: Without structural validation, downstream components (P0-2 closure templates, Phase 1 dataset construction) cannot trust their input. This is the foundation that every other Phase 0 artifact depends on.

**Independent Test**: Run `python tools/validate_spec.py --scope fact-contract --spec-root .factverify/spec --contracts .factverify/contracts` against both valid and invalid fixtures. A zero exit code with a clean report proves the story works.

**Acceptance Scenarios**:

1. **Given** a valid schema and a directory of valid contract instances, **When** the validation command runs, **Then** it exits 0 and produces a JSON report labelled `scope=fact-contract` listing every checked file as valid.
2. **Given** a contract missing a required semantic-core field (e.g. `triple`, `aliases`, `clue_boundary`), **When** the validation command runs, **Then** it exits nonzero with a diagnostic identifying the missing field, its JSON pointer, and the rule ID.
3. **Given** a contract with an undeclared property at any nesting level, **When** validated, **Then** it is rejected with a diagnostic identifying the unexpected property.
4. **Given** a missing schema file at the spec root, **When** the command runs, **Then** it exits nonzero with a clear error rather than silently falling back.

---

### User Story 2 - Detect frozen-contract edits without revision (Priority: P2)

A researcher modifies a previously frozen contract (changes an alias, a locality item, or the clue boundary) but forgets to increment the contract version. The validator catches this by comparing against a supplied baseline snapshot.

**Why this priority**: Once contracts are frozen at `spec-v1`, silent edits would invalidate the entire study. This story enforces the immutability guarantee before the freeze tooling is built.

**Independent Test**: Supply a `--baseline-contracts` directory containing a prior snapshot. Modify a contract without bumping the version. The validator rejects the change.

**Acceptance Scenarios**:

1. **Given** a prior frozen baseline and an identical contract, **When** revision validation runs, **Then** it passes.
2. **Given** a baseline and a contract with changed aliases but the same `contract_id`, **When** revision validation runs, **Then** it fails with a diagnostic identifying the changed fields.
3. **Given** unchanged canonical triple with an appropriately incremented contract version, **When** checked, **Then** the change is recognized as a valid new revision.
4. **Given** a changed canonical triple retaining the old `fact_id`, **When** checked, **Then** validation fails.
5. **Given** no `--baseline-contracts` flag, **When** the command runs, **Then** the report records `revision_check: not_requested` rather than claiming an edit-history check occurred.

---

### User Story 3 - Review demonstration contracts for semantic correctness (Priority: P3)

Two independent readers review the demonstration contracts (one real-entity Hà Nội illustration, one controlled-fictional contract) against the P0-1 guide's exercise items. Their classifications, disagreements, and adjudications are recorded in a structured review report.

**Why this priority**: JSON validity cannot prove entity resolution, co-reference, locality coverage, or a usable inference boundary. This human review is required before P0-1 handoff but depends on the structural validation being in place first.

**Independent Test**: Inspect `reports/p0-1-semantic-review.md` for two independent reader classifications, recorded disagreements, and adjudication decisions. Verify that all demonstration contracts referenced match their actual committed revisions.

**Acceptance Scenarios**:

1. **Given** both demonstration contracts, **When** two readers independently classify the guide's exercise items, **Then** the report records their labels, disagreements, and adjudications.
2. **Given** a descriptive clue proposed as an alias or a retained item that entails the target, **When** reviewed, **Then** the case is corrected or excluded with a recorded reason.
3. **Given** D-38, D-39, or D-40 still open, **When** handoff readiness is assessed, **Then** completion is blocked without labelling structurally valid fixtures as scientifically approved.

---

### Edge Cases

- What happens when the contracts directory is empty? The validator MUST fail closed with a clear diagnostic, not silently report success.
- What happens when the schema file itself is malformed JSON? The validator MUST exit nonzero with a parse-level diagnostic before attempting any contract validation.
- What happens when a contract contains valid JSON but references an undeclared locality bucket (e.g. a fifth bucket not in the approved enum)? The schema MUST reject it.
- What happens when optional metadata has source-permitted null freeze fields? Structural validation MUST accept them as valid draft values without asserting freeze readiness.
- What happens when Unicode strings (Vietnamese diacritics) are serialized and re-read? Content MUST be preserved without unapproved normalization or accent stripping.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST publish a Draft 2020-12 JSON Schema at `.factverify/spec/fact_contract.schema.json` that validates against its declared meta-schema (FV-SPEC-001).
- **FR-002**: Schema MUST reject contracts missing any required semantic-core field: `schema_version`, `contract_id`, `fact_id`, `triple`, `aliases`, `equivalent_directions`, `retained_neighbourhood`, `clue_boundary` (FV-SPEC-002).
- **FR-003**: Schema MUST reject undeclared properties at every object boundary, including nested objects (FV-SPEC-003).
- **FR-004**: Validator MUST enforce identifier grammar per role: entity IDs (Wikidata QID or project-local), relation IDs (Wikidata PID or project-local), fact IDs, and versioned contract IDs are not interchangeable (FV-SPEC-004).
- **FR-005**: Validator MUST reject identifiers that disagree with the contract's canonical fact identity — mismatched Q/P IDs in the fact key, or disagreement between `fact_id` and `contract_id` (FV-SPEC-005).
- **FR-006**: Schema MUST validate alias entries: non-empty text, valid language syntax, correct enum values, and relation aliases MUST include `argument_order` (FV-SPEC-006).
- **FR-007**: Validator MUST enforce direction-role consistency: forward requires given=subject/answer=object; inverse requires given=object/answer=subject; verification requires given=triple/answer=truth_value (FV-SPEC-007).
- **FR-008**: Schema MUST require coverage of every approved locality bucket (provisionally: same_subject, same_relation, compositional, global); four copies of one bucket MUST fail despite meeting minimum array length (FV-SPEC-008).
- **FR-009**: Schema MUST reject incomplete clue-boundary declarations: `equivalent_rule`, `clue_bearing_rule`, and `ambiguous_policy` are all required; empty rule text or undeclared policy enum values MUST fail (FV-SPEC-009).
- **FR-010**: Schema MUST validate supplied optional metadata using its source definition without making optional fields mandatory; source-permitted null freeze fields MUST remain valid (FV-SPEC-010).
- **FR-011**: Validation entry point MUST implement the scoped interface: `--scope fact-contract`, explicit `--spec-root`, `--contracts`, `--report`, with fail-closed exit semantics (FV-SPEC-011).
- **FR-012**: Component MUST ship two curated demonstration contracts: one Hà Nội real-entity illustration (labelled pretrained, not causal oracle) and one controlled-fictional contract of a different relation type (FV-SPEC-012).
- **FR-013**: Revision validator MUST reject semantic contract changes that reuse an existing frozen `contract_id`, using an explicitly supplied baseline (FV-SPEC-013).
- **FR-014**: P0-1 handoff MUST include an independent two-reader semantic review of demonstration contracts with recorded classifications, disagreements, and adjudications (FV-SPEC-014).
- **FR-015**: Validation MUST find the schema under `.factverify/spec/` without renaming the dot-directory; ignore or packaging rules that exclude it MUST be detected as a failure (FV-SPEC-015).

### Key Entities

- **Atomic-Fact Contract**: A JSON document declaring the deletion target — its subject-relation-object triple, aliases in multiple languages, equivalent query directions (forward, inverse, verification), a retained neighbourhood covering four locality buckets, and an explicit clue boundary separating equivalence from inference.
- **Fact Triple**: The core `(subject, relation, object)` with Wikidata or project-local identifiers. Each component has a canonical label and optional aliases.
- **Retained Neighbourhood**: Items that MUST survive unlearning, organized into four buckets (same-subject, same-relation, compositional, global) to enable locality measurement.
- **Clue Boundary**: The declared rule separating equivalent expressions of the target fact from inferential probes that supply independent premises. Determines which prompts enter the primary evaluation denominator.
- **Equivalent Directions**: Forward (given subject, answer object), inverse (given object, answer subject), and verification (given triple, answer truth value) with explicit role mappings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 15 FV-SPEC requirements have passing automated tests with named hooks (e.g. `test_fv_spec_001_schema_artifact`) before handoff.
- **SC-002**: Both demonstration contracts pass structural validation and include forward, inverse, and verification entries plus at least two retained items per approved locality bucket.
- **SC-003**: The validation command produces deterministic diagnostics: same input bytes and validator revision yield the same ordered output (excluding timestamps).
- **SC-004**: Two independent readers complete semantic review with recorded classifications and adjudications for all guide exercise items.
- **SC-005**: Validation runs offline with no network calls or model execution, from a clean checkout with declared dependencies only.
- **SC-006**: Every failing contract produces a diagnostic with a stable rule ID, file path, JSON pointer, and human-readable message — no failures are masked by a passing contract in the same batch.

## Assumptions

- The source-guide schema (P0-1 §2.5.4) is the starting interface; deliberate differences from it require recorded rationale.
- The four-bucket locality vocabulary (same_subject, same_relation, compositional, global) is implemented as provisional pending D-38 resolution.
- Python 3.11 with `uv` is the runtime; a JSON Schema Draft 2020-12 validation library is available.
- No training, unlearning, or model calls are made during validation — this is pure schema/data validation.
- The fictional demonstration contract is a small hand-authored example, not Phase 1 dataset generation output.
- Full V22 content hashing and freeze/tag creation are out of scope; only baseline-comparison revision checking is included.
- Decisions D-38 (locality bucket vocabulary), D-39 (finite alias/language scope), and D-40 (normalization policy) block handoff completion but do not block structural implementation.
