# Feature Specification: P0-2 Equivalence Closure and Inference-Set Implementation

**Feature**: `20260921-235511-closure-template-suite`
**Created**: 2026-09-21
**Status**: Draft
**Input**: FV-SPEC — P0-2 Equivalence Closure and Inference-Set Implementation

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Closure Artifact and Structural Validation (Priority: P1)

A researcher authors a closure template suite that classifies every prompt instance as equivalence (E), inference (I), retained control (R), or excluded (X). The validator checks that the artifact is well-formed, class routing is correct, E instances have empty premises, I instances carry provenance, identities are unique, and all references resolve.

**Why this priority**: Without a structurally valid closure artifact, no downstream evaluation (P0-3 attacks, P0-6 scoring) can consume the prompt suite. This is the foundational layer that everything depends on.

**Independent Test**: Run the validator with `--scope closure-templates` on a demonstration suite. It exits 0 on valid suites and nonzero with diagnostics on invalid ones. All structural rules (FV-SPEC-016 through FV-SPEC-022, FV-SPEC-026) are exercised.

**Acceptance Scenarios**:

1. **Given** a complete closure_templates.yaml with valid E/I/R/X routing, **When** validated, **Then** all template, group, context, and binding references resolve and the report shows zero diagnostics.
2. **Given** an E instance with nonempty premises, **When** validated, **Then** the validator rejects it with an FV-SPEC-018 diagnostic pointing to the offending template.
3. **Given** an I instance missing premise provenance, **When** validated, **Then** the validator rejects it with an FV-SPEC-019 diagnostic.
4. **Given** an X instance routed into the equivalence population, **When** validated, **Then** the validator rejects it with an FV-SPEC-026 diagnostic.
5. **Given** duplicate prompt IDs or equivalent prompt/context/answer bindings, **When** validated, **Then** the validator rejects the duplication with an FV-SPEC-022 diagnostic.

---

### User Story 2 — Contract Bindings and Template Coverage (Priority: P2)

A researcher binds closure templates to P0-1 contracts, ensuring answers map correctly to triple roles (forward→object, inverse→subject, verification→truth_value), all six prompt families are covered per relation type, retained controls bind to approved neighbourhood entries, and verification instances are balanced.

**Why this priority**: Correct bindings guarantee that prompts actually test the intended fact. Coverage ensures the suite is not accidentally limited to one phrasing style. These checks depend on the structural validation from US1 being in place.

**Independent Test**: Run the validator on a suite with bindings and contracts. It verifies answer-role mapping, relation-family coverage, retained-control bindings, and verification balance. Invalid bindings produce actionable diagnostics.

**Acceptance Scenarios**:

1. **Given** forward/inverse/verification bindings, **When** resolved against contracts, **Then** answers map to object, subject, and truth_value respectively; truth_label is explicitly mapped.
2. **Given** unauthorized target aliases or mismatched qualifiers in a binding, **When** validated, **Then** the validator rejects it with an FV-SPEC-020 diagnostic.
3. **Given** the approved relation manifest, **When** strictly validated, **Then** at least four relation types have applicable templates across all six families (direct, inverse, cloze, paraphrase, multilingual, verification).
4. **Given** a verification block for a contract/relation/language/split, **When** validated, **Then** true and false instance counts match.
5. **Given** R controls for a contract, **When** validated, **Then** all approved locality buckets are represented with valid retained-entry references.

---

### User Story 3 — Group/Split Isolation and Preview Rendering (Priority: P3)

A researcher assigns templates to groups and splits, then renders a construction preview for review. The validator ensures group membership resolves, near-duplicates stay grouped, calibration/final groups are disjoint, and rendered previews contain the complete declared model-visible context with answer keys separated from input.

**Why this priority**: Split isolation prevents data leakage between calibration and final test. Preview rendering enables human review of the complete prompt context before any model runs. Both depend on valid structure and bindings from US1/US2.

**Independent Test**: Run the validator with `--split construction --preview reports/p0-2-construction-preview.jsonl`. Verify group/split assignments, preview completeness, and metadata separation. Cross-split leakage or exposed answer keys produce diagnostics.

**Acceptance Scenarios**:

1. **Given** the reviewed grouping manifest, **When** validated, **Then** each template belongs to exactly one group with one split; near-duplicates remain grouped.
2. **Given** a construction preview request, **When** rendered, **Then** it contains no held-out (calibration/final_test) records.
3. **Given** fixed revisions and bindings, **When** rendered twice, **Then** ordered messages and instance IDs are identical.
4. **Given** a rendered instance, **When** projected to model_input, **Then** expected answers, truth labels, class, and review rationale are excluded from the messages.

---

### User Story 4 — Review Records and Revision Protection (Priority: P4)

A researcher records bilingual review of multilingual equivalence instances, independent classification review of the demonstration suite, and the validator protects frozen suite content from silent edits. Strict mode rejects unresolved decisions or stale approvals.

**Why this priority**: Review records are a process requirement for handoff — they cannot be automated. Revision protection ensures reproducibility. These are the final checks before the suite can be declared ready for downstream consumption.

**Independent Test**: Supply `--strict` with a review manifest. The validator checks that bilingual approvals exist for multilingual E instances, classification reviews are recorded with exact revisions, and frozen baselines match. Missing reviews or unauthorized changes produce diagnostics.

**Acceptance Scenarios**:

1. **Given** English/Vietnamese equivalence instances, **When** reviewed, **Then** relation, direction, qualifiers, negation, answer identity, and clue-freedom are checked and recorded.
2. **Given** unlabelled full-context instances, **When** independently classified, **Then** labels, rationale, disagreements, and adjudications are recorded against exact revisions.
3. **Given** an explicit baseline suite, **When** compared to the current suite, **Then** identical content passes; changed wording, binding, class, split, or label requires a new revision.
4. **Given** open decisions or missing reviews under `--strict`, **When** validated, **Then** strict readiness fails with specific diagnostics.

---

### User Story 5 — Scoped CLI and Regression Fixtures (Priority: P5)

The validator extends its CLI with `--scope closure-templates` and ships regression fixtures covering every validation boundary. P0-1 behaviour remains compatible and .factverify artifacts validate from a clean checkout.

**Why this priority**: The CLI and fixtures are the delivery mechanism for all validation logic. They depend on everything above being implemented first.

**Independent Test**: Run the full test suite (`tests/test_closure_templates.py`). All 18 FV-SPEC hooks (016–033) pass. P0-1 tests continue to pass unchanged.

**Acceptance Scenarios**:

1. **Given** valid inputs and `--scope closure-templates`, **When** validated, **Then** a scoped report is produced; checks outside scope are listed as deferred.
2. **Given** invalid required input under `--strict`, **When** validated, **Then** exit is nonzero with file/item/rule diagnostics.
3. **Given** the offline fixture suite, **When** run, **Then** positive/negative cases for FV-SPEC-016 through FV-SPEC-032 produce requirement-labelled results.
4. **Given** P0-2 added to the repository, **When** P0-1 tests are run, **Then** all P0-1 tests continue to pass.

---

### Edge Cases

- What happens when a closure template references a contract that does not exist or has been superseded? Validation fails with a diagnostic identifying the missing contract.
- What happens when a template has overlapping family attributes (e.g., Vietnamese cloze)? The template gets one stable identity with one primary family plus overlapping attributes recorded as metadata.
- What happens when a reviewer approves an instance, but the underlying template or binding is later modified? Strict validation fails because the review digest no longer matches the current content.
- What happens when the same answer string appears in both an equivalence prompt and a retained control? Both are valid — the equivalence prompt tests the target fact while the control tests a different relation for the same entity.
- What happens when `--split final_test` is requested? Only explicit `final_test` split records are rendered; no construction or calibration records leak.
- What happens when the suite YAML has duplicate keys? Validation fails at parse time with the affected location.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001** (FV-SPEC-016): System MUST publish a complete closure_templates.yaml at the resolved spec root. All template, group, context, and binding references must resolve. Malformed YAML, duplicate keys, missing fields, or unresolved references must fail validation with the affected location.

- **FR-002** (FV-SPEC-017): System MUST enforce class routing: E→equivalence set, I→inference set, R/X→controls. Multiple classes, misplaced classes, or unresolved ambiguous confirmatory items must fail strict validation.

- **FR-003** (FV-SPEC-018): System MUST require empty premises (extra_premises: []) for every equivalence instance. Missing or nonempty premises must fail validation.

- **FR-004** (FV-SPEC-019): System MUST attach premise provenance to every inference instance: subtype, nonempty premises, origins, bridge/support status, and separate reporting flag.

- **FR-005** (FV-SPEC-020): System MUST reject bindings inconsistent with their declared contract roles. Forward→object, inverse→subject, verification→truth_value. Unauthorized target aliases, unresolved placeholders, and mismatched qualifiers must fail validation.

- **FR-006** (FV-SPEC-021): System MUST cover all six prompt families (direct, inverse, cloze, paraphrase, multilingual, verification) for every approved relation type. At least four relation types must have applicable templates across all families.

- **FR-007** (FV-SPEC-022): System MUST maintain unique prompt identities. Each logical prompt instance has one stable ID with one primary family plus overlapping attributes. Duplicate IDs or equivalent bindings must be rejected.

- **FR-008** (FV-SPEC-023): System MUST assign each template to one declared group with one split. Near-duplicates must remain grouped. Calibration/final groups must be disjoint. Cross-split group reuse or construction previews containing held-out records must fail validation.

- **FR-009** (FV-SPEC-024): System MUST provide balanced true/false verification instances per contract/relation/language/split block. Oracle labels must be withheld from model input.

- **FR-010** (FV-SPEC-025): System MUST bind every R control to an approved retained-neighbourhood entry. All approved locality buckets must be represented.

- **FR-011** (FV-SPEC-026): System MUST exclude X instances from equivalence and inference populations. Excluded instances are omitted or marked diagnostic-only with their exclusion reason.

- **FR-012** (FV-SPEC-027): System MUST render the complete declared model-visible context including system text, demonstrations, and history. Rendering must be deterministic: identical versioned inputs produce identical ordered messages and instance IDs.

- **FR-013** (FV-SPEC-028): System MUST separate answer keys from model input. Expected answers, truth labels, class, and review rationale must remain in evaluator_metadata, not in model_input messages.

- **FR-014** (FV-SPEC-029): System MUST require bilingual approval for each multilingual equivalence instance, checking relation, direction, qualifiers, negation, answer identity, and clue-freedom. Missing or stale approval must fail strict readiness.

- **FR-015** (FV-SPEC-030): System MUST record independent classification review of the demonstration suite with labels, rationale, disagreements, adjudications, and exact revision references. Unresolved disputes must block strict handoff.

- **FR-016** (FV-SPEC-031): System MUST reject changed frozen suite content under an unchanged revision. Changed wording, binding, class, split, premise, or label requires a new revision.

- **FR-017** (FV-SPEC-032): System MUST implement scoped fail-closed validation with `--scope closure-templates`. Checks outside scope are listed as deferred. Invalid input, invalid baselines, or open decisions under `--strict` produce nonzero exit with diagnostics.

- **FR-018** (FV-SPEC-033): System MUST ship regression fixtures exercising every validation boundary (FV-SPEC-016 through FV-SPEC-032) with requirement-labelled results. P0-1 behaviour must remain compatible.

### Key Entities

- **Closure Template Suite** (closure_templates.yaml): The versioned collection of all prompt templates, organized into equivalence/inference/control/exclusion sets with group and split assignments, relation coverage, and policy references.

- **Template Instance**: A single prompt record with ID, class (E/I/R/X), group, language, format, text/context references, relation applicability, answer role, premises, and family/attribute metadata.

- **Instance Binding**: A mapping from a template to a specific contract, context, alias set, candidate, and retained entry. Stored in instance_bindings.json.

- **Review Manifest**: A record of reviewer identity, date, labels, rationale, adjudication results, bilingual approval status, and decision references, tied to exact suite revisions and content digests.

- **Preview Record**: A rendered instance containing stable instance ID, ordered model_input messages, and separate evaluator_metadata. Output as JSONL for human review.

- **Template Group**: A named collection of near-duplicate templates assigned to exactly one split (construction, calibration, or final_test).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All 18 FV-SPEC requirements (016–033) have corresponding test hooks that pass with both positive and negative fixtures.
- **SC-002**: The closure artifact covers all six prompt families for every approved relation type, with at least four relation types represented.
- **SC-003**: Verification instance blocks achieve exact true/false balance (count match) within each contract/relation/language/split block.
- **SC-004**: Preview rendering is deterministic — two runs on the same versioned inputs produce byte-identical output (excluding timestamps).
- **SC-005**: Zero answer-key leakage: no rendered model_input contains expected answers, truth labels, or classification metadata.
- **SC-006**: Group/split isolation verified — no template appears in more than one split, and construction previews contain zero held-out records.
- **SC-007**: All P0-1 tests continue to pass after P0-2 is added to the repository.
- **SC-008**: Strict validation correctly rejects suites with unresolved blocking decisions (D-38 through D-43) or missing/stale reviews.

## Assumptions

- P0-1 contracts and the P0-1 validator are complete and available at `.factverify/contracts/` and `tools/validate_spec.py` respectively. The P0-1 schema is frozen and will not change during P0-2 implementation.
- Blocking decisions D-38 through D-43 may remain open during development. The validator accepts provisional values in ordinary mode but rejects unresolved decisions under `--strict`. No requirement reaches `implemented` status while its blocking decision is open.
- The six prompt families (direct, inverse, cloze, paraphrase, multilingual, verification) are the complete set defined by the P0-2 study guide. No additional families will be added without a new spec revision.
- Bilingual review applies to English/Vietnamese instances as the two languages used in the demonstration suite. Additional languages would require extending the review scope.
- The closure artifact format is YAML (not JSON), following the P0-2 study guide convention. The instance bindings and review manifest remain JSON.
- Reviewed P0-1 inputs are required for handoff but provisional fixtures support development. P0-2 grouping does not establish P0-6/D-35 statistical independence or P1 fact/entity isolation.
- The approximately 10% inference heuristic from the study guide is not a validated pass threshold — it is informational only.
- Normalization policy for bilingual review comes from the actual contract policy, not inferred from the schema's normalizationSpec field.

## Dependencies

- **Upstream**: P0-1 contracts (`.factverify/contracts/`), P0-1 schema (`.factverify/spec/fact_contract.schema.json`), P0-1 validator (`tools/validate_spec.py`)
- **Blocking decisions**: D-38 (locality buckets), D-39 (aliases/languages), D-40 (normalization), D-41 (relation coverage), D-42 (group/split assignments), D-43 (seat-of-government ontology)
- **Downstream consumers**: P0-3 (attacks/budgets), P0-6 (scoring/witness decisions), P1 (dataset construction), P2 (model execution)
