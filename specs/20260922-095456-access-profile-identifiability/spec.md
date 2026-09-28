# Feature Specification: P0-4 Access Profile and the Identifiability Limit

**Feature Slug**: `20260922-095456-access-profile-identifiability`
**Created**: 2026-09-22
**Status**: Draft
**Input**: FV-SPEC — P0-4 Access Profile and the Identifiability Limit (requirements document)

## User Scenarios & Testing

### User Story 1 — Publish and Validate the Access Contract (Priority: P1)

A researcher preparing a FactVerify evaluation needs a single authoritative artifact (`.factverify/spec/access_profile.md`) that declares what each evaluator can observe, what roles exist, what information sources are permitted, and what historical access is available. The validator confirms the artifact is well-formed, all required fields resolve, and malformed or incomplete profiles are rejected.

**Why this priority**: Without a validated access contract, no downstream evaluator, control adapter, or reporting component knows what observations are permitted. This is the foundation for every other P0-4 requirement.

**Independent Test**: Run `python tools/validate_spec.py --scope access-profile --spec-root .factverify/spec --report reports/p0-4-validation.json` on a valid profile; exit 0 with a clean report. Run on a malformed profile; exit nonzero with file/field diagnostics.

**Acceptance Scenarios**:

1. **Given** a complete access_profile.md with valid frontmatter, **When** validated, **Then** observation boundary, capability scope, roles, input/external-information rules, historical access, provenance protocol, handling policies, and cross-file references all resolve without diagnostics.
2. **Given** malformed frontmatter, duplicate keys, unknown profile values, or missing required fields, **When** validated, **Then** validation fails with file/field diagnostics and nonzero exit.

---

### User Story 2 — Validate Observation Capabilities and Provenance (Priority: P2)

A researcher declares what each system can actually observe (text-only A, text+scores B, or internals C) at the serving-pipeline boundary. The validator checks that declared capabilities match the actual serving boundary — post-mask scores labelled as pre-mask B fail, partial internals labelled as unrestricted C fail. A reviewed provenance procedure identifies the tap, intervening processors, model/tokenizer identities, and evidence source.

**Why this priority**: Capability declarations determine which channels and attacks are valid. Without verified capabilities, budget allocations and permission cross-checks from P0-3 cannot be trusted.

**Independent Test**: Validate a profile with correct A/B/C declarations against fixture manifests; pass. Validate a profile claiming pre-mask B when the provider applies post-masking; fail with specific diagnostics.

**Acceptance Scenarios**:

1. **Given** an A/B/C capability declaration, **When** validated, **Then** available text/scores/internals, pre/post-processing location, vocabulary scope, top-k value (if applicable), candidate-scoring ability, and provider transformations are all explicit.
2. **Given** post-mask scores labelled pre-mask B or partial internals labelled unrestricted C, **When** validated, **Then** the declaration fails; restricted capabilities remain explicit rather than inferred from a profile letter.
3. **Given** a provenance procedure referencing a specific artifact, **When** reviewed, **Then** it identifies the tap, intervening processors, model/tokenizer identities, system/decoding manifests, evidence source, and checks against the relevant artifact.
4. **Given** an unverified provider boundary or evidence tied to a different artifact, **When** validated, **Then** raw-access readiness remains unverified.

---

### User Story 3 — Separate Observation from Intervention and Bound Sources (Priority: P3)

A researcher needs intervention permissions validated independently of observation profiles. Seeing logits (B) or weights (C) does not authorize arbitrary edits. The validator checks that operator/evaluator roles are separated, that enabled actions have approved recipe references, and that all permitted input and artifact sources (including historical checkpoints) are declared.

**Why this priority**: Prevents privilege escalation between observation and modification, and ensures external information (old checkpoints, supplied clues) is explicitly attributed rather than silently leaking answers.

**Independent Test**: Validate a profile where an operator exports a checkpoint for a B-only evaluator with separate role declarations; pass. Validate a profile with an unlisted fine-tune or undeclared historical source; fail.

**Acceptance Scenarios**:

1. **Given** an operator permitted to export a checkpoint for a B-only evaluator, **When** validated, **Then** operator/evaluator roles, approved recipe references, artifact lineage requirements, and evaluator observations are represented separately.
2. **Given** an unlisted fine-tune, activation edit, tokenizer change, or channel without required capabilities, **When** validated, **Then** the enabled action is rejected; neither B nor C grants blanket intervention permission.
3. **Given** a threat-model manifest, **When** checked, **Then** system/context/retrieval/demonstration control, target/answer-list exposure, historical artifacts, allowed actors, and resource references are explicit.
4. **Given** recovery from a saved pre-unlearning model, **When** checked, **Then** it is separately attributed to that artifact; undeclared history or information sources fail validation.

---

### User Story 4 — Identifiability Justification and Status Contracts (Priority: P4)

A researcher must provide a reviewed justification for structural non-identifiability under the declared observation regime. The validator checks that identifiability arguments are scoped and reviewed — finite matching outputs do not establish universal observational equivalence. Four distinct outcome statuses (confirmed recovery, conformance, non-identifiable, incomplete) are enforced with no silent promotion between them.

**Why this priority**: Without scoped identifiability justifications, the study cannot claim that certain system pairs are indistinguishable. Without distinct statuses, missing evidence could silently become a pass.

**Independent Test**: Validate a profile with a reviewed identifiability justification referencing a synthetic simulator pair; pass. Validate a profile claiming non-identifiability from one matching refusal; fail. Validate status fixtures where each status has distinct evidence requirements; pass.

**Acceptance Scenarios**:

1. **Given** a synthetic simulator with identical allowed transcript distributions by construction, **When** reviewed, **Then** the system pair, permitted queries/history, observation boundary, argument, and revision are recorded separately from the hidden control label.
2. **Given** one matching refusal or a filter that misses one alias while blocking another, **When** checked, **Then** non-identifiability is not established; a valid distinguishing probe refutes the claimed equivalence.
3. **Given** status fixtures, **When** validated, **Then** confirmed recovery requires P0-6 evidence; conformance requires complete bounded acceptance; non-identifiable requires a scoped justification; incomplete covers missing/uncertain required evidence.
4. **Given** a missing raw score, known control label alone, or completed test without a confirmed witness, **When** checked, **Then** none automatically becomes non-identifiable, a fabricated witness, or conformance respectively.

---

### User Story 5 — Predeclared Reporting, Claim Templates, and Scoped CLI (Priority: P5)

A researcher needs predeclared reporting rules for non-identifiable and incomplete cases, approved claim templates constrained to their evidence scope, and a complete CLI validation pass. The validator cross-checks eligibility/denominator policies across access, witness, and margins artifacts. Claim templates are restricted to their declared profile, tests, interventions, budget, stage, and reference conditions. Strict mode requires all applicable decisions resolved, reviewed procedures, and resolved policy interfaces.

**Why this priority**: This is the integration and completeness layer — without it, individual validations are correct but uncoordinated, and claims could exceed their evidence basis.

**Independent Test**: Run full validation with `--strict`; pass only when all applicable decisions are resolved, all reviews are current, and all cross-file references agree. Run with `--baseline-suite`; changed frozen policy under unchanged revision fails.

**Acceptance Scenarios**:

1. **Given** resolved eligibility/denominator policies, **When** cross-checked, **Then** access, witness, and margins artifacts agree on status mappings, eligible populations, coverage, and separate non-identifiable/incomplete counts.
2. **Given** an unmapped status or an outcome-dependent exclusion, **When** checked, **Then** strict validation fails; oracle construction labels remain separate from auditor-visible evidence.
3. **Given** A/B/C claim templates, **When** reviewed, **Then** each names profile, completed tests, permitted interventions, budget, stage, and valid-reference condition where relevant; A states the output-simulation limitation.
4. **Given** universal erasure language, a mismatched profile label, or a causal-reference claim without a valid reference, **When** checked, **Then** approval fails; Stage B cannot inherit Stage A causal claims.
5. **Given** versioned manifests and synthetic fixtures, **When** validated, **Then** the report lists capabilities, permission conflicts, review state, cross-file checks, input digests, and deferred runtime provenance checks.
6. **Given** invalid references, unresolved applicable policies/reviews under strict mode, or changed frozen policy under unchanged revision, **When** checked, **Then** exit is nonzero.

---

### Edge Cases

- What happens when a profile declares capabilities for a system that has no corresponding manifest? Validation fails with a missing-manifest diagnostic.
- How does the system handle a profile referencing P0-5 margin fields that are not yet resolved? In non-strict mode, the check is listed as deferred. In strict mode, validation fails.
- What happens when a capability is declared as "unverified" rather than "declared" or "unavailable"? It is accepted as a valid state but flagged in the report; channels requiring that capability cannot be enabled until verification.
- How does the system handle a profile that omits the identifiability justification entirely? Validation passes structurally but the identifiability check reports "not_provided"; strict mode fails.
- What happens when the baseline suite references a profile version that no longer exists? Revision comparison fails with a diagnostic rather than silently skipping.

## Requirements

### Functional Requirements

- **FR-001**: System MUST publish a versioned access_profile.md with machine-readable frontmatter declaring observation boundary, capabilities, roles, provenance protocol, permitted sources, intervention rules, historical access, handling policies, and cross-file references.
- **FR-002**: System MUST validate that each declared capability (A/B/C) accurately describes the serving-pipeline boundary — post-mask scores labelled pre-mask MUST fail, partial internals labelled unrestricted MUST fail.
- **FR-003**: System MUST require a reviewed provenance procedure identifying the tap, intervening processors, model/tokenizer identities, system/decoding manifests, and evidence source for each declared measurement boundary.
- **FR-004**: System MUST validate intervention permissions independently of observation profiles — B or C observation access MUST NOT grant blanket intervention permission.
- **FR-005**: System MUST require all permitted input and artifact sources (including historical checkpoints) to be explicitly declared; undeclared sources MUST fail validation.
- **FR-006**: System MUST require a reviewed identifiability justification for structural non-identifiability claims; finite matching outputs MUST NOT establish universal observational equivalence.
- **FR-007**: System MUST enforce four distinct outcome statuses (confirmed recovery, conformance, non-identifiable, incomplete) with no silent promotion between them.
- **FR-008**: System MUST reference predeclared reporting rules for non-identifiable and incomplete cases, cross-checking eligibility/denominator policies across access, witness, and margins artifacts.
- **FR-009**: System MUST restrict approved claim templates to their declared evidence scope — universal erasure language, mismatched profile labels, and causal-reference claims without a valid reference MUST fail.
- **FR-010**: System MUST provide scoped offline validation via `--scope access-profile` with report output, strict mode, and baseline comparison. Zero endpoint calls or model execution MUST occur during validation.

### Key Entities

- **Access Profile**: The versioned artifact declaring observation boundary, capabilities, roles, permitted sources, and handling policies for all evaluator systems.
- **Capability Declaration**: Per-system record of what is observable (A: text-only, B: text+scores, C: internals) at the actual serving-pipeline boundary, with verification state (declared, verified, unavailable, unverified).
- **Provenance Procedure**: Reviewed protocol identifying the measurement tap, intervening processors, model/tokenizer identity, and evidence source for each system's declared boundary.
- **Intervention Permission**: Role-separated record of what modifications (exports, fine-tunes, tokenizer changes) are approved, with recipe references and artifact lineage.
- **Threat-Model Manifest**: Declaration of permitted input sources, external information, historical artifacts, allowed actors, and resource references.
- **Identifiability Justification**: Scoped, reviewed argument for why certain system pairs are structurally non-identifiable under the declared observation regime.
- **Status Contract**: Definition of four outcome statuses (confirmed_recovery, conformance, non_identifiable, incomplete) with distinct evidence requirements and no automatic promotion.
- **Claim Template**: Profile-scoped, stage-labelled template declaring what evidence supports what conclusion, constrained to the declared observation/intervention boundary.
- **Capability/Provenance Manifest**: Per-system referenced record binding artifact hashes to declared capabilities and measurement evidence.
- **Validation Report**: Machine-readable output listing capabilities, permission conflicts, review state, cross-file checks, input digests, and deferred checks.

## Success Criteria

### Measurable Outcomes

- **SC-001**: All 10 validation rules (FV-SPEC-047 through FV-SPEC-056) have passing positive and negative test fixtures, with 100% of acceptance scenarios automated.
- **SC-002**: The validator detects 100% of capability mismatches (post-mask labelled pre-mask, partial labelled unrestricted) in synthetic fixture suites.
- **SC-003**: No silent status promotion occurs across any combination of status fixtures — each of the four statuses requires its own distinct evidence path.
- **SC-004**: Cross-file consistency checks between access profile, P0-3 attack spec, and P0-5/P0-6/P0-7 interfaces agree on all mapped statuses and eligible populations.
- **SC-005**: Validation completes with zero endpoint calls, zero model execution, and zero GPU jobs in all modes (normal, strict, baseline comparison).
- **SC-006**: Existing P0-1, P0-2, and P0-3 test suites remain green after P0-4 implementation (no regressions).
- **SC-007**: Deterministic output — same versioned inputs produce identical capability checks, status mappings, and reports (excluding timestamps).

## Assumptions

- The access profile uses YAML frontmatter in a Markdown document (consistent with existing `.factverify/spec/` conventions).
- Capability states follow a four-value vocabulary: declared, verified, unavailable, unverified — as described in the requirements document.
- P0-5 (margins), P0-6 (witness rules), and P0-7 (preregistration) interfaces are not yet finalized; cross-file checks against these are listed as deferred in non-strict mode.
- Runtime provenance verification (actually checking that a live endpoint matches its declared boundary) is out of scope — P0-4 validates the declared contract, not the live system.
- Synthetic fixtures for identifiability and status testing use construction-time labels only; no actual model execution is required.
- The blocking decisions (D-13, D-14, D-27, D-28, D-29, D-31) remain open during development; requirements are built against spec fields, not literals.
