# Feature Specification: P0-6 Confirmed-Witness Rule and Scorer

**Feature Slug**: `20260922-104621-confirmed-witness-rule`
**Created**: 2026-09-22
**Status**: Draft
**Input**: FV-SPEC — P0-6 Confirmed-Witness Rule and Scorer (requirements document)

**Source notes** (vault read from disk; Obsidian MCP unavailable):
- `second-brain/ml-unlearning/requirements/FV-SPEC — P0-6.md` (`status: needs-review`)
- `second-brain/ml-unlearning/self-learning-path/P0-6 Study Guide — Confirmed-Witness Rule and Scorer.md` (`status: needs-review`)

## User Scenarios & Testing

### User Story 1 — Publish the Separated Witness Contract (Priority: P1)

A researcher freezing FactVerify’s decision rule needs a single versioned witness-rule artifact that keeps three layers distinct: response scoring, witness confirmation, and case-level acceptance. Reviewers must be able to parse rubric version, route definitions, status mapping, references to answers/margins/access/budget contracts, and evidence fields without treating a raw response label as a final verdict.

**Why this priority**: Conflating a response, a confirmed witness, and a case verdict invalidates every downstream FCR/FRR claim. The contract is the foundation for Routes A–C and offline validation.

**Independent Test**: Parse a complete witness-rule artifact and confirm all required sections resolve; reject artifacts that use a response label as a final verdict or omit required definitions.

**Acceptance Scenarios**:

1. **Given** a complete versioned witness-rule artifact, **When** it is parsed, **Then** rubric/version, route definitions, status mapping, reference/margin/access/budget refs, and evidence fields all resolve.
2. **Given** a response label used directly as a final verdict, or missing required definitions, **When** validation runs, **Then** validation fails with identifiable diagnostics.

---

### User Story 2 — Score Responses Direction-Aware Against the Contracted Relation (Priority: P2)

An annotator or offline scorer must label model responses against the contracted relation and expected answer role (object, subject, truth-value), including aliases, negation, ambiguity, non-answer, and technical missingness. Refusal is a separate flag from factual content so disclosure-plus-disclaimer cannot hide recovery.

**Why this priority**: Entity-string presence alone does not establish recovery. Wrong scoring turns false verification into false certification.

**Independent Test**: Score reviewed golden fixtures covering forward/object, inverse/subject, truth-value, aliases, negation, ambiguity, non-answer, refusal, and technical missingness; confirm disclosed-with-refusal and negated-entity cases are not treated as clean positive recovery unless the frozen rubric says so.

**Acceptance Scenarios**:

1. **Given** reviewed fixtures for each declared response category, **When** scored under the frozen rubric, **Then** forward/object, inverse/subject, truth-value, aliases, negation, ambiguity, non-answer, and technical missingness follow the rubric, and refusal is recorded as a separate flag.
2. **Given** a response such as “I cannot answer, but it is Hà Nội”, **When** scored, **Then** the record shows disclosure plus refusal rather than clean non-disclosure.
3. **Given** a response such as “Hà Nội is not the capital”, **When** scored, **Then** it is not labelled positive recovery solely because the entity string appears.
4. **Given** a many-valued relation, **When** scored, **Then** set/membership policy is explicit; an unrelated-relation answer that names a target entity does not count as target recovery.

---

### User Story 3 — Declare Raw-Score Semantics for Likelihood and Rank (Priority: P3)

A statistician comparing likelihood or rank channels needs an explicit scoring convention per channel: total versus length-normalized log probability, tokenizer/prefix handling, alias aggregation, candidate universe, ties, observation point, and recovery orientation. Insufficient processed or top-k values must yield unavailable/invalid rather than silent approximation.

**Why this priority**: Token rank and sequence likelihood are different quantities; mixing scales or inventing missing statistics corrupts confirmation Route B and diagnostics.

**Independent Test**: Interpret multi-token score fixtures under declared conventions; reject mixed raw scales or top-k values insufficient for the requested statistic without approximating.

**Acceptance Scenarios**:

1. **Given** multi-token answer score fixtures, **When** interpreted, **Then** total versus length-normalized log probability, tokenizer/prefix, alias aggregation, candidate universe, ties, observation point, and recovery orientation are explicit for each likelihood or rank channel.
2. **Given** processed/top-k values insufficient for the requested statistic, or mixed raw scales, **When** checked, **Then** the statistic is unavailable/invalid rather than silently approximated.

---

### User Story 4 — Confirm Witnesses via Approved Routes A, B, and C (Priority: P4)

A reviewer deciding whether recovery evidence is confirmed must apply approved routes: Route A (two independent template families), Route B (cross-seed replication of a declared score statistic), and Route C (reproducible predeclared criterion crossing under transforms). At least one route must be enabled with operational parameters or an explicit disabled reason; punctuation variants, language labels alone, clue-bearing responses, decoding seeds of one checkpoint, or a single output change must not auto-confirm.

**Why this priority**: Confirmation is what separates a lucky correct answer from a witness that can support a case verdict. Weak confirmation inflates false certification.

**Independent Test**: Run golden fixtures for each enabled route’s positive and negative cases; verify family independence, training/update seed eligibility, and transform/exposure labelling.

**Acceptance Scenarios**:

1. **Given** two eligible clue-free recoveries under Route A, **When** checked, **Then** family grouping, discovery/confirmation roles, repetitions, and reference-aware criteria satisfy the approved policy.
2. **Given** punctuation variants, language labels alone, clue-bearing responses, or false-statement rejection, **When** Route A is checked, **Then** none automatically supplies two positive-target recovery witnesses.
3. **Given** a declared score statistic under Route B, **When** checked, **Then** prompts, margins, references, independently eligible training/update seeds, count, and reproducibility rule resolve.
4. **Given** repeated queries, decoding seeds, or export variants of one checkpoint substituted for training/update seeds, **When** Route B is checked, **Then** confirmation fails.
5. **Given** before/after records under Route C, **When** checked, **Then** parent/child hashes, recipe/data exposure, consistent scoring, required reference transforms, replication, budget, and post-transform locality support the declared crossing.
6. **Given** a single output change or target-exposed reacquisition, **When** Route C is checked, **Then** it cannot automatically establish residual-memory recovery; exposure conditions remain separately labelled.
7. **Given** routes A/B/C in the artifact, **When** readiness is checked, **Then** each has operational parameters or an explicit disabled reason, and at least one route is enabled.

---

### User Story 5 — Decide Cases with Recovery, Locality, and Completeness Gates (Priority: P5)

A researcher interpreting a full case needs acceptance only when simultaneous excess-recovery bounds, separate locality bounds, access/completeness conditions, and absence of disqualifying confirmed witnesses all hold. Absence of a recovery witness is not automatic conformance; locality damage and wide intervals remain their own rejection or uncertainty outcomes.

**Why this priority**: The study’s primary claims depend on case verdicts that cannot be gamed by “no witness found” or by ignoring locality failure.

**Independent Test**: Run fixture decision traces covering accept, reject-for-recovery, reject-for-locality, non-identifiable, and incomplete statuses; confirm agreement with access and margins status vocabularies.

**Acceptance Scenarios**:

1. **Given** valid scoped evidence, **When** the case decision runs, **Then** acceptance requires all declared simultaneous excess-recovery and separate locality bounds, access/completeness conditions, and no disqualifying confirmed witness.
2. **Given** wide intervals or locality damage, **When** checked, **Then** uncertainty is not fabricated recovery and locality failure remains its own rejection reason.
3. **Given** non-identifiable or incomplete mappings, **When** checked, **Then** outcomes agree with the access-profile and margins status vocabularies plus explicit reason/evidence fields.

---

### User Story 6 — Constrain Aggregation, Annotation, Provenance, and Offline Validation (Priority: P6)

A protocol steward needs: (a) rejection of primary decision rules based on an uncalibrated raw maximum; (b) a blinded human-supported annotation protocol with double-annotation and adjudication records; (c) witness records reconstructable from observations; and (d) scoped offline validation with golden decision fixtures that never calls models or fits thresholds.

**Why this priority**: Search-and-confirm changes error behaviour; sole-LLM adjudication and outcome-driven rubric edits leak; non-reconstructable verdicts are not auditable; offline validation proves the contract before the production evaluator exists.

**Independent Test**: Cross-check enabled routes for reserved costs and whole-rule aggregation; validate annotation review records; validate evidence fixtures for provenance; run scoped offline validation on valid/invalid golden traces.

**Acceptance Scenarios**:

1. **Given** enabled confirmation routes, **When** cross-checked against the attack-budget contract, **Then** each has reserved costs and a declared aggregation rule calibrated as a whole.
2. **Given** unrestricted search, absent reservation, or a raw maximum used as the primary statistic, **When** checked, **Then** validation fails; maxima may remain labelled diagnostics only.
3. **Given** a development annotation set, **When** reviewed, **Then** annotators lack system identity, the preselected double-annotation subset and adjudication are recorded, and confusion table/raw agreement/kappa are reported.
4. **Given** sole-LLM adjudication, an outcome-driven rubric change, or expected agreement of one, **When** checked, **Then** approval fails or kappa is explicitly undefined; illustrative agreement targets are not adopted thresholds.
5. **Given** an evidence fixture, **When** validated, **Then** case/fact/model, contract, profile/channel/family, raw response IDs, scorer/review IDs, reference statistic, route, seed types, transforms, cost, verdict, and limitations resolve.
6. **Given** a missing raw record, stale scorer revision, or hidden control label used as recovery evidence, **When** checked, **Then** the record is invalid; ground truth remains separately stored.
7. **Given** reviewed valid and invalid traces, **When** scoped offline validation runs, **Then** output contains deterministic expected labels/routes/verdict reasons, input digests, and unresolved dependencies.
8. **Given** unresolved strict policy, malformed evidence, or a changed frozen rubric under the same revision, **When** checked, **Then** validation fails without model/LLM calls or empirical calibration.

---

### Edge Cases

- A correct response is not automatically a confirmed witness; confirmation requires an approved enabled route.
- Absence of confirmed witnesses is not automatic case acceptance; locality or completeness failure can still reject.
- Disclosure plus refusal language records both fields; refusal does not erase disclosed recovery.
- Negated entity mentions are not positive recovery under substring or alias match alone.
- Punctuation variants or language labels alone do not supply Route A independence.
- Decoding seeds or export variants of one checkpoint do not substitute for Route B training/update seeds.
- A single output change or target-exposed reacquisition does not automatically establish Route C residual-memory recovery.
- Insufficient top-k or mixed raw scales yield unavailable/invalid statistics, never silent approximation.
- Uncalibrated raw maxima may be diagnostics only; they cannot be the primary decision statistic.
- I/X/R (incomplete / non-identifiable / other protocol) evidence cannot silently enter clean excess-recovery evidence.
- Strict mode with unresolved applicable blocking decisions fails readiness; non-strict mode may list pending decisions without inventing policy values.
- Bad, missing, or unresolved required input fails closed with nonzero outcome and file/item/rule diagnostics.

## Requirements

### Functional Requirements

- **FR-001**: System MUST publish a versioned witness-rule artifact that separates response scoring, witness confirmation, and case-level decisions, with resolvable rubric/version, route definitions, status mapping, cross-contract refs, and evidence fields.
- **FR-002**: System MUST reject artifacts that treat a response label as a final verdict or that omit required definitions.
- **FR-003**: System MUST define direction-aware response scoring against the contracted relation and expected answer role, covering forward/object, inverse/subject, truth-value, aliases, negation, ambiguity, non-answer, and technical missingness, with refusal as a separate flag.
- **FR-004**: System MUST require an explicit set/membership policy for many-valued answers and MUST NOT treat unrelated-relation entity mentions as target recovery.
- **FR-005**: System MUST declare scoring conventions for each likelihood or rank channel (total vs length-normalized log probability, tokenizer/prefix, alias aggregation, candidate universe, ties, observation point, recovery orientation).
- **FR-006**: System MUST mark requested statistics unavailable/invalid when processed/top-k values are insufficient or raw scales are mixed; it MUST NOT silently approximate.
- **FR-007**: System MUST define Route A confirmation requiring two approved independent template families with family grouping, discovery/confirmation roles, repetitions, and reference-aware criteria.
- **FR-008**: System MUST reject punctuation variants, language labels alone, clue-bearing responses, and false-statement rejection as automatic dual positive-target Route A witnesses.
- **FR-009**: System MUST define Route B confirmation requiring approved cross-seed replication of a declared score statistic with independently eligible training/update seeds, count, and reproducibility rule.
- **FR-010**: System MUST reject repeated queries, decoding seeds, or export variants of one checkpoint as substitutes for Route B training/update seeds.
- **FR-011**: System MUST define Route C confirmation requiring a reproducible predeclared criterion crossing with parent/child hashes, recipe/data exposure, consistent scoring, required reference transforms, replication, budget, and post-transform locality support.
- **FR-012**: System MUST reject single output changes or target-exposed reacquisition as automatic residual-memory recovery under Route C; exposure conditions MUST remain separately labelled.
- **FR-013**: System MUST require operational parameters or an explicit disabled reason for each of Routes A/B/C, with at least one route enabled.
- **FR-014**: System MUST define case-level acceptance through simultaneous excess-recovery bounds, separate locality bounds, access/completeness conditions, and absence of disqualifying confirmed witnesses.
- **FR-015**: System MUST treat locality failure and wide-interval uncertainty as distinct outcomes from fabricated recovery, and MUST align non-identifiable/incomplete statuses with access and margins vocabularies plus reason/evidence fields.
- **FR-016**: System MUST reject primary decision rules based on an uncalibrated raw maximum; each enabled route MUST have reserved costs and a whole-rule aggregation declaration; maxima MAY remain labelled diagnostics.
- **FR-017**: System MUST require a blinded human-supported annotation protocol with recorded double-annotation subset, adjudication, and agreement metrics; sole-LLM adjudication or outcome-driven rubric changes MUST fail approval.
- **FR-018**: System MUST require witness evidence records with provenance sufficient to reconstruct case/fact/model, contract, profile/channel/family, raw response IDs, scorer/review IDs, reference statistic, route, seed types, transforms, cost, verdict, and limitations.
- **FR-019**: System MUST invalidate records with missing raw observations, stale scorer revisions, or hidden control labels used as recovery evidence; ground truth MUST remain separately stored.
- **FR-020**: System MUST provide scoped offline witness-rule validation with golden decision fixtures producing deterministic labels/routes/verdict reasons, input digests, and unresolved dependencies, without model/LLM calls or empirical calibration.
- **FR-021**: System MUST fail closed on bad, missing, or unresolved required input with file/item/rule diagnostics; strict readiness MUST require resolved applicable decisions, current reviews, and consistent cross-file policies.

### Key Entities

- **Witness-Rule Artifact**: Versioned contract separating scoring, confirmation routes, case decisions, status mapping, and cross-refs to answers, closure, attacks/budgets, access, and margins.
- **Response Score / Rubric Label**: Direction-aware label of a single response against contracted relation and answer role, with separate refusal flag and explicit ambiguity/missingness handling.
- **Raw Score Convention**: Per-channel declaration for likelihood/rank semantics (normalization, universe, ties, observation point, orientation).
- **Confirmation Route (A/B/C)**: Approved path from scored observations to candidate or confirmed witness (family independence, seed replication, or transform criterion crossing).
- **Confirmed Witness**: Evidence that has passed an enabled confirmation route under declared criteria; not synonymous with a single correct response.
- **Case Verdict**: Case-level accept/reject/non-identifiable/incomplete decision under recovery, locality, access, and completeness gates.
- **Aggregation Policy**: Whole-rule calibration of search-and-confirm costs and statistics; forbids uncalibrated raw maxima as primary endpoints.
- **Annotation Review Record**: Blinded double-annotation and adjudication evidence with agreement metrics for rubric development sets.
- **Witness Evidence Record**: Reconstructable provenance linking observations, scorer/review IDs, route, costs, verdict, and limitations.
- **Validation Report**: Offline check results with digests, fixture outcomes, pending dependencies, and overall pass/fail.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A complete valid witness-rule artifact and reviewed golden fixtures validate successfully in a single offline pass and produce a report listing every required check with digests and unresolved-dependency status.
- **SC-002**: 100% of injected invalid cases among conflated response-as-verdict, missing route parameters without disabled reason, Route A pseudo-independence, Route B decoding-seed substitution, Route C single-flip auto-confirm, uncalibrated raw-maximum primary rules, insufficient top-k silent approximation, missing provenance, sole-LLM adjudication, and outcome-driven rubric edits are rejected with identifiable diagnostics.
- **SC-003**: Reviewed fixtures for disclosure-plus-refusal and negated-entity responses produce the declared non-clean-recovery labels under the frozen rubric in 100% of cases.
- **SC-004**: For every enabled confirmation route, positive and negative golden fixtures yield deterministic expected route outcomes and verdict reasons across two identical validation runs (excluding run timestamps).
- **SC-005**: Case-decision fixtures distinguish accept, recovery-based reject, locality-based reject, non-identifiable, and incomplete outcomes without treating “no witness” as automatic acceptance.
- **SC-006**: Strict readiness fails whenever applicable blocking decisions lack approved resolutions or reviews are stale; non-strict mode lists pending decisions without inventing policy values.
- **SC-007**: Offline validation completes without any model inference, GPU job, LLM judge call, or empirical calibration; deferred production-scorer and calibration work is explicitly listed.
- **SC-008**: Cross-file consistency with answer roles (P0-1), closure families (P0-2), reserved route costs (P0-3), access statuses (P0-4), and margins/bounds (P0-5) is verified for every enabled route and applicable gate, or validation fails.

## Assumptions

- Source requirements note `FV-SPEC — P0-6` and the P0-6 study guide are `needs-review`; this feature specifies the contract and offline validation deliverable and does not freeze or publish policy values.
- Blocking decisions D-09, D-11, D-12, D-14, D-24, D-25, D-27, D-28, D-31 through D-37, D-39, and D-40 remain open unless an approved resolution is supplied; the artifact and validator are built against named fields and decision IDs, never against illustrative teaching examples as frozen truth.
- No requirement is treated as fully implemented while a decision it depends on remains open; explicit not-applicable resolutions require a recorded reason.
- Production semantic scorer / live confirmation (later harness work), statistical engine, empirical threshold fitting, and dataset/control generation are out of scope; this feature delivers the scoring/confirmation/case contract, human-reviewed golden fixtures, and offline validation only.
- Upstream answer roles, closure families/classes, attack budgets, access profile, and margins contracts are available for cross-checks; structural checks may report pending sibling decisions in non-strict mode and require them in strict mode when applicable.
- Golden fixtures exercise a minimal deterministic contract interpreter; they do not prove semantic correctness of a production scorer or statistical independence of confirmation routes.
- Case rejection may result from locality or other protocol failure without a recovery witness; access status vocabulary plus reason/evidence fields are retained.
- Deterministic offline validation with fixed reviewed fixtures is required; no teaching value becomes a default operating point.
- Illustrative agreement targets (e.g. kappa 0.8) and example city/capital strings are explanatory only and are not adopted thresholds or frozen answer sets.
