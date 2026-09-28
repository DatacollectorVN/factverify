# Feature Specification: P0-3 Attack Family and Per-Channel Query Budget

**Feature Branch**: `20260922-091030-attack-query-budget`
**Created**: 2026-09-22
**Status**: Draft
**Input**: Requirements from `FV-SPEC — P0-3.md` (P0-3 §§2-11; handbook §6, V14-V17)

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Publish and Validate Attack Specification (Priority: P1)

A researcher creates an `attacks.yaml` defining three evaluator arms (native, semantic-only, FactVerify), their permitted channels, and accounting rules. The validator confirms the artifact is well-formed: all channels resolve, evaluator arms are present, accounting units are declared, and structural integrity holds. Invalid inputs produce field-specific diagnostics. Enabled channels are cross-checked against the declared access profile to ensure observation access does not authorize interventions.

**Why this priority**: Without a validated attack specification, no downstream work (budgets, policies, reviews) can proceed. This is the foundational artifact for the attack domain, analogous to P0-1's fact contract schema.

**Independent Test**: Run the validator with `--scope attacks` on a valid attacks.yaml; exits 0 with a deterministic report. Run on malformed inputs; exits nonzero with diagnostics.

**Acceptance Scenarios**:

1. **Given** a complete attacks.yaml with three arms, channel IDs, accounting rules, and upstream references, **When** validated, **Then** all fields resolve and the report lists zero diagnostics for FV-SPEC-034.
2. **Given** duplicate keys, unknown channels, or missing required fields, **When** validated, **Then** validation fails with field-specific diagnostics referencing FV-SPEC-034.
3. **Given** an enabled channel whose observation, decoding, or intervention requirements exceed the declared access profile, **When** validated, **Then** validation fails with FV-SPEC-035 diagnostics.
4. **Given** a disabled channel, **When** validated, **Then** no executable recipe is required, but active allocations to it are rejected.

---

### User Story 2 - Validate Matched Allocations and Accounting Units (Priority: P2)

A researcher defines per-arm generation allocations and accounting units. The validator checks that all three evaluator arms sum to the declared common per-case cap, that each operation has a declared charging unit, and that cache/retry/failure/reference events follow their declared charge policies. Offline fixture traces confirm that event charges are deterministic and provenance-preserving.

**Why this priority**: Equal-budget comparison is the core methodological claim. Without validated accounting and matched allocations, the study's fairness guarantee is unverifiable.

**Independent Test**: Provide a valid attacks.yaml with allocation tables and event fixtures. The validator confirms allocations sum correctly, accounting units are declared, and fixture replays produce deterministic charges.

**Acceptance Scenarios**:

1. **Given** native, semantic-only, and FactVerify allocations, **When** summed, **Then** nonnegative integer generation allowances equal the common cap, with explicit allocation-to-channel mapping (FV-SPEC-038).
2. **Given** one request returning multiple completions, **When** replayed offline, **Then** each completion is charged as a separate generation trial with its own identity (FV-SPEC-036).
3. **Given** fixtures for cache hits, retries, transport failures, and discarded responses, **When** replayed, **Then** each matches the declared charge policy; reused observations are distinguished from new compute (FV-SPEC-037).
4. **Given** an omitted arm, unequal sum, or negative allowance, **When** validated, **Then** validation fails with FV-SPEC-038 diagnostics.
5. **Given** candidate scoring mixed with generation counts without an explicit conversion model, **When** validated, **Then** validation fails; they remain separately reported (FV-SPEC-036).

---

### User Story 3 - Reserve Confirmation Costs and Bound Adaptive Policies (Priority: P3)

A researcher declares confirmation-route budget reservations and finite execution policies for each attack channel. The validator cross-checks reservations against witness-rule routes, ensures no double-funded shared calls, and verifies that adaptive policies have bounded search spaces with declared stop rules.

**Why this priority**: Confirmation is part of evaluation effort, and unbounded adaptive search invalidates budget matching. These checks layer on top of US2's allocation validation.

**Independent Test**: Provide attacks.yaml with confirmation reservations and adaptive policy declarations plus scripted observation fixtures. The validator confirms reservations are sufficient, no double-funding occurs, and policy replays on scripted traces are deterministic.

**Acceptance Scenarios**:

1. **Given** witness-rule routes, **When** cross-checked, **Then** each maps to a reservation sufficient for its declared calls, including transformed/reference calls (FV-SPEC-039).
2. **Given** a fixed or adaptive policy, **When** replayed on scripted observations, **Then** search space, update/stop rules, and actual/unused allowances are determined (FV-SPEC-040).
3. **Given** an out-of-space action, cap overrun, or undeclared confirmation reallocation, **When** checked, **Then** the fixture replay refuses the action before charging (FV-SPEC-040).
4. **Given** a missing reservation or double-funded shared call, **When** checked, **Then** validation fails with FV-SPEC-039 diagnostics.

---

### User Story 4 - Target-Exposure Review and Reproducible Transformations (Priority: P4)

A researcher specifies attack-input clue audits and transformation recipes. The validator requires version-bound exposure classifications for attack inputs (wrappers, few-shot demos, conversation contexts), and complete recipes for enabled transformations (export algorithms, quantization parameters, parent lineage). Relearning conditions are separately specified by target exposure.

**Why this priority**: Without clue audits, a successful answer may come from supplied information rather than model memory. Without reproducible transformation specs, interventions cannot be replicated.

**Independent Test**: Provide audit manifests and transformation recipes. The validator confirms exposure classifications are recorded against exact revisions, recipes have all required fields, and relearning conditions distinguish target-free from target-exposed conditions.

**Acceptance Scenarios**:

1. **Given** attack inputs with wrappers, few-shot demonstrations, or full conversation contexts, **When** reviewed, **Then** aliases, inverse forms, indirect clues, and exposure classifications are recorded against exact revisions (FV-SPEC-041).
2. **Given** an enabled export or activation intervention, **When** validated, **Then** recipe/version, parent identity, parameters, tokenizer/decoding, fitting-data exposure, reference treatment, and output-provenance fields are specified (FV-SPEC-042).
3. **Given** enabled relearning, **When** validated, **Then** target-free and target-exposed conditions have distinct reporting with declared data, schedule, optimizer, trainable parameters, and tolerance reference (FV-SPEC-043).
4. **Given** an export missing algorithm/group size/calibration corpus, **When** validated, **Then** validation fails with FV-SPEC-042 diagnostics.
5. **Given** an unreached relearning threshold, **When** reported, **Then** censored/not-reached results are required; no invented finite time (FV-SPEC-043).

---

### User Story 5 - Cost Reports, Revision Protection, and Scoped CLI (Priority: P5)

A researcher generates cost-report records, checks frozen-policy integrity against baselines, and uses the scoped CLI for end-to-end validation. The validator produces per-arm cost records consumable by the Phase 2 accountant, rejects changed frozen content under unchanged revisions, and provides deterministic reports with checked/deferred rule listings.

**Why this priority**: This is the integration layer: cost records feed Phase 2, revision protection ensures methodological integrity, and the CLI ties everything together for CI and handoff.

**Independent Test**: Run the full validator with `--strict` and `--baseline-suite`. Verify cost records preserve units and provenance, revision changes are caught, and the report lists all checked/deferred rules.

**Acceptance Scenarios**:

1. **Given** an offline trace, **When** summarized, **Then** caps, actual/unused usage, generation trials, score operations, tokens, training steps, exports, and wall-clock retain their units and provenance (FV-SPEC-044).
2. **Given** an explicit baseline with policy and manifest digests, **When** compared, **Then** unchanged content passes; changed channels, budgets, or stopping rules require a new revision (FV-SPEC-045).
3. **Given** valid inputs under strict mode, **When** validated, **Then** a deterministic report lists checked/deferred rules, per-arm totals, event charges, and input digests (FV-SPEC-046).
4. **Given** unresolved decisions or missing reviews under strict mode, **When** validated, **Then** exit is nonzero with diagnostics; no model calls or training occur (FV-SPEC-046).

---

### Edge Cases

- What happens when a channel is declared disabled but receives an active allocation? Validation fails (FV-SPEC-034/038).
- How does the system handle missing access profile inputs? Fail closed: enabled channels without matching permissions are rejected (FV-SPEC-035).
- What happens when candidate scoring and generation counts are mixed without a conversion model? Validation fails; they remain separately reported (FV-SPEC-036).
- How does the system handle a discarded response? Its observation is still charged (FV-SPEC-037).
- What happens when an adaptive policy encounters an out-of-space action? The replay refuses the action before charging (FV-SPEC-040).
- How does the system handle direct answer disclosure in attack inputs? Routed to supplied-answer diagnostics; never enters clean equivalence recovery (FV-SPEC-041).
- What happens when a relearning threshold is unreached? Reporting requires censored/not-reached results; no invented finite time (FV-SPEC-043).
- How does the system handle exploratory attacks added after policy freeze? They cannot silently enter the frozen confirmatory policy (FV-SPEC-045).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST publish a versioned attacks.yaml under the specification root with all three evaluator arms, channel IDs, accounting rules, and upstream references resolving (FV-SPEC-034).
- **FR-002**: System MUST reject enabled channels whose observation, decoding, historical-checkpoint, or intervention requirements exceed the declared access profile (FV-SPEC-035).
- **FR-003**: System MUST declare the charging unit for each permitted operation, keeping generation trials, candidate score operations, and token counts as distinct units (FV-SPEC-036).
- **FR-004**: System MUST define accounting outcomes for cache hits, retries, transport failures, discarded responses, and reference evaluations, distinguishing new compute from reused observations (FV-SPEC-037).
- **FR-005**: System MUST validate that all three evaluator arms' allocations sum to the declared common per-case cap as nonnegative integers with explicit allocation-to-channel mapping (FV-SPEC-038).
- **FR-006**: System MUST require a budget reservation for every enabled confirmation route, sufficient for declared calls, and reject double-funded shared calls (FV-SPEC-039).
- **FR-007**: System MUST declare a finite execution policy for each attack channel, with bounded search space, update/stop rules, and deterministic replay on scripted traces (FV-SPEC-040).
- **FR-008**: System MUST require version-bound clue audits for attack inputs, recording aliases, inverse forms, indirect clues, and exposure classifications against exact revisions (FV-SPEC-041).
- **FR-009**: System MUST require a complete recipe for each enabled transformation, including algorithm, parent identity, parameters, tokenizer/decoding, fitting-data exposure, and output provenance (FV-SPEC-042).
- **FR-010**: System MUST specify relearning conditions separately by target exposure, with distinct reporting for target-free and target-exposed conditions (FV-SPEC-043).
- **FR-011**: System MUST define per-arm cost records preserving units, provenance, and explicit reporting of missing measurements, cached observations, and reference budgets (FV-SPEC-044).
- **FR-012**: System MUST reject changed frozen policy content (channels, budgets, recipes, stopping rules) under an unchanged revision (FV-SPEC-045).
- **FR-013**: System MUST provide scoped offline validation producing deterministic reports with checked/deferred rules, per-arm totals, event charges, and input digests, with zero model calls, GPU jobs, or training (FV-SPEC-046).

### Key Entities

- **Attack Specification**: The versioned attacks.yaml defining evaluator arms, channels, accounting rules, allocations, policies, and upstream references. Central artifact consumed by all downstream validation.
- **Evaluator Arm**: One of three evaluators (native, semantic-only, FactVerify) with its own allocation, channel set, and policy declarations.
- **Channel**: A named attack pathway (e.g., paraphrase, sampling, multilingual, quantization, relearning) with enabled/disabled status, purpose, capability requirements, policy source, and budget allocation.
- **Accounting Unit**: The declared charging unit for an operation (generation trials, score operations, tokens, training steps) kept distinct and never silently pooled.
- **Event Trace**: An offline fixture record identifying arm, case, phase, channel, probe, sample/decoding settings, artifact/parent, operation/outcome, and cost charges.
- **Adaptive Policy**: A finite execution policy for a channel, specifying search space bounds, update/stop rules, discovery/confirmation limits.
- **Confirmation Reservation**: A budget set-aside for witness-rule confirmation routes, tracked separately from discovery allocations.
- **Transformation Recipe**: A complete specification for an enabled intervention (export, quantization, activation patching), including algorithm, parameters, parent lineage, and provenance.
- **Clue Audit Manifest**: A version-bound record of exposure classifications for attack inputs, tracking aliases, inverse forms, and indirect clues.
- **Cost Record**: A per-arm summary preserving caps, actual/unused usage, trial counts, token counts, training steps, exports, wall-clock, and compute units.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of enabled channels in a valid attacks.yaml resolve against the declared access profile without permission violations.
- **SC-002**: All three evaluator arm allocations sum exactly to the common per-case cap with zero tolerance; every validated specification achieves exact budget matching.
- **SC-003**: Offline fixture replay produces identical charges given the same versioned inputs and event order; zero nondeterministic outcomes across repeated validations.
- **SC-004**: Every enabled confirmation route maps to a sufficient budget reservation; zero routes without coverage after validation passes.
- **SC-005**: Frozen policy content is protected: 100% of unauthorized changes (modified channels, budgets, recipes, or stopping rules under an unchanged revision) are detected and rejected.
- **SC-006**: Validation completes with zero model calls, zero GPU jobs, zero training operations, and zero actual exports.
- **SC-007**: P0-1 and P0-2 regression tests remain green; zero regressions introduced by P0-3 additions.

## Assumptions

- P0-1 fact contracts and P0-2 closure templates are available as upstream inputs; their validation is handled by their respective scopes.
- P0-4 (access profiles), P0-5 (margins/tolerances), and P0-6 (witness rules/confirmation routes) provide interfaces consumed by P0-3 validation; their unresolved state blocks strict-mode readiness but not offline development with fixture data.
- The 14 blocking decisions (D-17 through D-29, D-31) are open; all requirements are built against spec fields and decision IDs, not literal values. No requirement reaches `implemented` while a blocking decision is open.
- Disabled channels require no executable recipe but cannot receive active allocations.
- Equal query counts across evaluator arms do not imply equal compute or resources; this distinction is maintained in cost reporting.
- Runtime enforcement and actual cost collection are P2-2 responsibilities; P0-3 validates the specification contract only.
- Synthetic/construction fixtures only; no final-test observations are used for policy selection (split integrity constraint).
