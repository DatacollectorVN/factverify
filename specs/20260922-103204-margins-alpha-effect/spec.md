# Feature Specification: P0-5 Alpha and Practical Effect Size

**Feature Slug**: `20260922-103204-margins-alpha-effect`
**Created**: 2026-09-22
**Status**: Draft
**Input**: FV-SPEC — P0-5 Alpha and Practical Effect Size (requirements document)

## User Scenarios & Testing

### User Story 1 — Publish and Validate the Margins Contract (Priority: P1)

A researcher preparing FactVerify’s primary endpoint needs a single versioned statistical-policy artifact that declares error tolerances, units, and domains for every distinct policy quantity (false-rejection cap, confidence error, minimum absolute FCR reduction, channel/locality margins, and relearning tolerance references). The validator confirms the artifact is well-formed and rejects nulls, unknown fields, non-finite values, and mixed probability/percentage-point units.

**Why this priority**: Without a validated margins contract, calibration, power planning, and confirmatory analysis have no fixed operating point. This is the foundation for every other P0-5 requirement.

**Independent Test**: Validate a complete margins artifact with explicit units and domains for all required policy fields; pass. Validate an artifact with nulls, unknown fields, non-finite values, or mixed units; fail with file/field diagnostics.

**Acceptance Scenarios**:

1. **Given** a versioned margins artifact with distinct typed policy fields, **When** parsed, **Then** the FRR cap, confidence error, minimum absolute FCR reduction, channel/locality margins, and relearning tolerance references each have explicit units and domains.
2. **Given** nulls, unknown fields, non-finite values, or mixed probability/percentage-point units, **When** strict validation runs, **Then** validation fails and thresholds are not substituted for the FRR cap.

---

### User Story 2 — Record Policy Justification and Approvals (Priority: P2)

A researcher (with supervisor approval) must record why the chosen FRR cap and practical-success policy are acceptable. Variance alone does not decide what error rate is tolerable. Approval records capture population, false-rejection consequences, minimum worthwhile benefit, approver, date, and artifact revision.

**Why this priority**: Illustrative example values (e.g. a provisional 0.05 cap) must not become frozen policy without reviewed approval. Gatekeeping here prevents silent adoption of teaching examples.

**Independent Test**: Validate approval records covering FRR cap and practical-success policy with all required fields; pass. Validate an illustrative 0.05 cap or variance-derived tolerance without policy approval under strict readiness; fail.

**Acceptance Scenarios**:

1. **Given** approved decisions for the FRR cap and practical-success policy, **When** reviewed, **Then** population, false-rejection consequences, minimum worthwhile benefit, approver, date, and artifact revision are recorded.
2. **Given** an illustrative 0.05 cap or a variance-derived tolerance without policy approval, **When** strict readiness is checked, **Then** readiness fails.

---

### User Story 3 — Define Estimands, Denominators, and Calibration Selection (Priority: P3)

A statistician needs FRR and FCR estimands defined over explicit eligible populations, with weights, aggregation, coverage, and missing/non-identifiable mappings declared. Threshold selection must use calibration-only inputs under an FRR upper-bound constraint; point estimates alone do not establish the cap.

**Why this priority**: Wrong denominators or reading final-test outcomes during selection can reverse the study’s conclusion. Calibration rules that silently relax the cap invalidate the primary endpoint.

**Independent Test**: Map synthetic genuine/fake cases and check that unweighted rates match declared counts (e.g. 3/100 → 0.03 FRR; 12/40 → 0.30 FCR); empty denominators remain undefined. Evaluate candidate operating points under the upper-bound constraint; infeasible or final-test inputs are rejected without silent cap relaxation.

**Acceptance Scenarios**:

1. **Given** synthetic genuine and fake cases, **When** mapped to estimands, **Then** FRR counts genuine rejections, FCR counts fake acceptances, and case weights, per-family/overall aggregation, coverage, and missing/non-identifiable mappings are explicit.
2. **Given** 3 genuine rejections out of 100 eligible genuine cases and 12 fake acceptances out of 40 eligible fake cases, **When** unweighted fixture rates are checked, **Then** results are 0.03 and 0.30; empty denominators are undefined, never reported as zero.
3. **Given** candidate operating points, **When** evaluated on calibration fixtures, **Then** eligibility uses an upper confidence bound on FRR at or below the approved FRR cap, with the approved selection-uncertainty procedure and a deterministic tie rule.
4. **Given** no feasible operating point or final-test inputs presented for selection, **When** selection is attempted, **Then** the system reports infeasible or rejects the input; the FRR cap is never silently relaxed.

---

### User Story 4 — Define Practical Success, Uncertainty, and Margin Coverage (Priority: P4)

A researcher needs an uncertainty-aware practical-success rule that requires improvement against both declared baselines under a common budget, an explicit dependence/multiplicity contract for confidence statements, and a compatible margin for every enabled channel and retained locality bucket.

**Why this priority**: Statistical improvement alone need not be worthwhile; ignoring dependence or missing local margins can conceal damage or overstate coverage.

**Independent Test**: Compute delta from fixture FCR values (e.g. 0.18 vs 0.30 → −0.12, twelve percentage points) and require both baseline comparisons for primary success. Reject row-wise independent resampling of correlated prompts or separate intervals labelled as joint coverage. Cross-check that every enabled channel and approved bucket has an oriented statistic, unit, reference, and margin.

**Acceptance Scenarios**:

1. **Given** FactVerify FCR 0.18 and a baseline FCR 0.30, **When** delta is computed, **Then** delta is −0.12 (12 percentage points); native and semantic-only comparisons use the declared common cap/budget.
2. **Given** only one baseline comparison meets the approved criterion, **When** overall success is checked, **Then** primary success is false; an upper-bound-on-delta rule is used only if explicitly adopted in the approved policy.
3. **Given** a paired checkpoint-by-fact design, **When** the uncertainty contract is reviewed, **Then** cluster/crossed structure, seed types, weighting, simultaneous family, confidence target, and paired resampling contract are explicit.
4. **Given** row-wise independent resampling of correlated prompts or separate intervals labelled as joint coverage, **When** checked, **Then** the analysis contract is rejected; zero observed errors do not imply zero uncertainty.
5. **Given** the attacks contract and the fact-contract bucket enum, **When** cross-checked, **Then** each enabled channel and approved retained bucket has an oriented statistic, unit, reference, and margin.
6. **Given** a missing bucket/channel margin or raw rank averaged with correctness, **When** checked, **Then** validation fails; mandatory privacy margins are not imported from superseded notes.

---

### User Story 5 — Sample-Size Handoff, Revision Protection, and Scoped Validation (Priority: P5)

A researcher needs a reproducible sample-size determination contract for the pilot, protection against unauthorized changes to frozen statistical policy, and a complete offline validation pass that reports digests, decision status, and deferred empirical work without fitting thresholds or running models.

**Why this priority**: Power must address the declared practical hypothesis; later calibration must not rewrite the selection rule; offline validation proves the contract is complete without pretending the study has been run.

**Independent Test**: Review a pilot-based sample-size plan with all required fields; flag power-against-zero used to justify exceeding the minimum effect, or underpowered designs. Compare baseline and amendment metadata so policy revisions require authorization. Run scoped offline validation on resolved policies and synthetic fixtures; fail on malformed inputs, stale approval, or inconsistent cross-file references without fitting thresholds.

**Acceptance Scenarios**:

1. **Given** a pilot-based sample-size plan, **When** reviewed, **Then** allowed inputs, target power, effect scenario, dependence model, feasibility limits, algorithm/version, and pre-final deadline are specified.
2. **Given** power against a zero effect used to justify exceeding the minimum worthwhile improvement, or an underpowered design, **When** checked, **Then** the mismatch or infeasibility is explicit; no final sample count is invented in this phase.
3. **Given** explicit baseline and amendment metadata, **When** compared, **Then** the frozen specification policy and later threshold-tag values are distinguished; changed policy requires a new revision and a permitted amendment.
4. **Given** final-outcome tuning or missing amendment authorization, **When** checked, **Then** the original confirmatory claim is disallowed and the baseline remains intact.
5. **Given** resolved policies and synthetic fixtures, **When** scoped offline validation runs, **Then** it produces scope, digests, checks, decision status, and deferred empirical/bootstrap computations.
6. **Given** malformed inputs, stale approval, or inconsistent witness/access/budget references, **When** strict validation runs, **Then** it fails without fitting thresholds or running models.

---

### Edge Cases

- Empty eligible denominators for FRR or FCR are undefined and must not be reported as zero rates.
- Mixed probability and percentage-point units for the same or related fields fail validation.
- Illustrative teaching values (e.g. provisional 0.05) without approval records fail strict readiness.
- No feasible calibration operating point under the FRR upper bound reports infeasible; the cap is not relaxed.
- Final-test outcomes supplied to calibration or sample-size determination are rejected (no leakage).
- Only one of two baseline comparisons meeting the practical-success criterion yields overall primary success false.
- Zero observed errors still require a non-zero uncertainty statement under the declared procedure.
- Missing margin for any enabled channel or approved locality bucket fails coverage validation.
- Unauthorized or untagged changes to frozen statistical policy disallow the confirmatory claim.
- Strict mode with unresolved applicable blocking decisions fails readiness; non-strict mode may list pending decisions without inventing values.

## Requirements

### Functional Requirements

- **FR-001**: System MUST publish a versioned margins policy artifact with distinct typed fields for the FRR cap, confidence error, minimum absolute FCR reduction, channel/locality margins, and relearning tolerance references, each with explicit units and domains.
- **FR-002**: System MUST fail closed on nulls, unknown fields, non-finite values, mixed probability/percentage-point units, and any attempt to substitute thresholds for the FRR cap.
- **FR-003**: System MUST require approval records for the FRR cap and practical-success policy that record population, false-rejection consequences, minimum worthwhile benefit, approver, date, and artifact revision.
- **FR-004**: System MUST fail strict readiness when an illustrative teaching value or variance-derived tolerance is used without policy approval.
- **FR-005**: System MUST define FRR and FCR estimands over explicit eligible populations, including case weights, aggregation (per-family and overall), coverage, and mappings for missing/non-identifiable statuses.
- **FR-006**: System MUST treat empty denominators as undefined (never zero) and MUST reproduce declared unweighted fixture rates from synthetic counts.
- **FR-007**: System MUST constrain threshold selection to calibration-only inputs under an FRR upper-bound rule using the approved selection-uncertainty procedure and a deterministic tie-breaking rule.
- **FR-008**: System MUST report infeasible selection or reject final-test inputs for selection; it MUST NOT silently relax the FRR cap.
- **FR-009**: System MUST define an uncertainty-aware practical-success rule requiring both declared baseline comparisons under a common cap/budget; primary success is false unless both meet the approved criterion.
- **FR-010**: System MUST declare the uncertainty procedure with dependence structure, seed types, weighting, simultaneous family, confidence target, and paired resampling contract; it MUST reject procedures that treat correlated prompts as independent replicates or that label separate intervals as joint coverage.
- **FR-011**: System MUST require a compatible oriented margin (statistic, unit, reference) for every enabled recovery channel and every approved retained-locality bucket; it MUST reject missing margins and invalid aggregations (e.g. raw rank averaged with correctness).
- **FR-012**: System MUST define a reproducible sample-size determination contract for the pilot (allowed inputs, target power, effect scenario, dependence model, feasibility limits, algorithm/version, pre-final deadline) without inventing a final sample count in this phase.
- **FR-013**: System MUST reject unauthorized changes to frozen statistical policy; changed policy requires a new revision and permitted amendment metadata, distinguishing the frozen specification policy from later threshold-tag values.
- **FR-014**: System MUST provide scoped offline validation that produces scope, digests, checks, decision status, and deferred empirical work; strict mode MUST fail on malformed inputs, stale approval, or inconsistent cross-file references without fitting thresholds or running models.
- **FR-015**: System MUST keep alpha, confidence error, minimum effect, deltas, and channel/locality margins as distinct quantities with preserved units across validation and reporting.

### Key Entities

- **Margins Policy Artifact**: Versioned statistical-policy contract declaring typed tolerances, units, domains, estimand definitions, selection rules, practical-success criteria, uncertainty procedure, channel/locality margins, sample-size handoff fields, and decision references.
- **Policy Approval Record**: Reviewed justification for the FRR cap and practical-success policy (population, consequences, minimum worthwhile benefit, approver, date, revision).
- **Estimand Definition**: FRR/FCR formulas over eligible populations with weights, aggregation, coverage, and status mappings (including missing and non-identifiable).
- **Calibration Selection Rule**: Calibration-only operating-point selection under an FRR upper-bound constraint with approved uncertainty procedure and deterministic ties.
- **Practical-Success Rule**: Uncertainty-aware comparison requiring both baseline arms under a common budget; delta expressed in declared units (e.g. percentage points).
- **Uncertainty Contract**: Dependence/multiplicity assumptions for confidence statements (cluster/crossed structure, seeds, weighting, simultaneous family, paired resampling).
- **Channel/Locality Margin**: Per-enabled-channel and per-retained-bucket oriented statistic with unit, reference, and margin value.
- **Sample-Size Handoff**: Pilot power-planning contract handed to later empirical phases; does not invent final N in P0.
- **Revision/Amendment Record**: Baseline vs amended policy metadata protecting staged statistical commitments.
- **Validation Report**: Offline check results with digests, decision status, pending/deferred work, and overall pass/fail.

## Success Criteria

### Measurable Outcomes

- **SC-001**: A complete valid margins policy validates successfully in a single offline pass and produces a report listing every required check with digests and decision status.
- **SC-002**: 100% of injected invalid cases among nulls, unknown fields, non-finite values, mixed units, empty-denominator zeroing, silent cap relaxation, single-baseline “success,” correlated-prompt independence, missing channel/bucket margins, and unauthorized policy edits are rejected with identifiable diagnostics.
- **SC-003**: Synthetic fixture rates match declared counts exactly for the documented FRR and FCR examples (0.03 and 0.30), and empty denominators remain undefined rather than zero.
- **SC-004**: Practical-success fixtures treat a −0.12 FCR delta as a 12 percentage-point improvement and require both baseline comparisons before primary success is true.
- **SC-005**: Strict readiness fails whenever applicable blocking decisions lack approved resolutions or approval records are stale; non-strict mode lists pending decisions without inventing policy values.
- **SC-006**: Two validation runs on identical versioned inputs produce identical check outcomes and digests (excluding run timestamps).
- **SC-007**: Offline validation completes without any model inference, GPU job, threshold fitting, or empirical bootstrap execution; deferred empirical/bootstrap work is explicitly listed.
- **SC-008**: Cross-file consistency with attacks (channels/budgets), access profile (status mappings), and fact-contract buckets is verified for every enabled channel and approved bucket, or validation fails.

## Assumptions

- Policy numeric values remain open under blocking decisions D-01 through D-16 and D-38; the artifact and validator are built against named fields and decision IDs, never against illustrative literals as frozen truth.
- A provisional FRR cap of 0.05 may appear only as an illustrative or provisional reference and does not constitute approved policy until D-01 (and related) approvals are recorded.
- Production bootstrap/statistics engines (later harness work), empirical calibration and power runs (later blocks), witness/scorer rules (P0-6), and freeze/publication (P0-7) are out of scope; this feature delivers the contract and offline validation only.
- Upstream fact-contract buckets, attack budgets/channels, and access-profile status mappings are available for cross-checks; missing downstream witness/preregistration artifacts may be deferred in non-strict mode and required in strict mode when applicable.
- Synthetic fixtures exercise contract behaviour only; they are not estimates of study performance.
- Explicit not-applicable decision resolutions are acceptable when accompanied by a recorded reason.
- Deterministic offline validation with fixed policy and fixture inputs is required; no teaching example becomes a default operating point.
