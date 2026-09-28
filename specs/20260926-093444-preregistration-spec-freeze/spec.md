# Feature Specification: P0-7 Pre-registration and Spec Freeze

**Feature Branch**: `20260926-093444-preregistration-spec-freeze`  
**Created**: 2026-09-26  
**Status**: Draft  
**Input**: User description: "FV-SPEC — P0-7 Pre-registration and Spec Freeze"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Author the Study Commitment Document (Priority: P1)

The researcher writes a versioned `preregistration.md` that gathers all upstream policy artifacts into a single auditable commitment. Every required section (primary question, baselines, hypotheses, controlled construction, units, sampling, evaluation, analysis, stopping, deviations, reporting) must reference a normative upstream artifact rather than restate its value. The validator confirms that all sections exist and that any authoritative value (α, budget, scorer policy) appears exactly once in the owning artifact.

**Why this priority**: Without a complete preregistration document there is nothing to freeze, validate, or tag. Everything downstream depends on this artifact existing and being internally consistent.

**Independent Test**: Can be fully tested by running `validate_spec.py --scope preregistration` against a complete fixture `preregistration.md` and verifying the report lists all required sections as present with no conflicting duplicates.

**Acceptance Scenarios**:

1. **Given** a `preregistration.md` with all required sections each referencing an upstream artifact, **When** the validator runs, **Then** the readiness report marks every section resolved and exits zero.
2. **Given** a `preregistration.md` with a missing "stopping" section, **When** the validator runs, **Then** it exits non-zero and names the missing section in the diagnostic output.
3. **Given** a document where α appears both in `margins.yaml` and inline in `preregistration.md`, **When** the validator runs, **Then** it reports a duplicate-value conflict and exits non-zero.

---

### User Story 2 - Record Prior Exposure and Registration Status (Priority: P1)

The researcher provides a dated exposure record stating which data splits or outcomes have been inspected, by whom, on what date, and the current registration status (local-only vs externally archived). The validator confirms the record is present, internally consistent, and that its claims are not contradicted by observable evidence.

**Why this priority**: A retrospective plan has no confirmatory standing. The exposure record is a prerequisite to any honest claim about the study's status.

**Independent Test**: Can be fully tested by running the validator against a synthetic fixture containing a reviewed exposure record and verifying diagnostics for each invalid state.

**Acceptance Scenarios**:

1. **Given** a reviewed exposure record listing access dates, actors, inspected outcomes, and a "local-only" registration status with matching evidence, **When** the validator runs, **Then** the exposure check passes.
2. **Given** a record that labels the final-test split "untouched" but lists an earlier inspection event covering it, **When** the validator runs, **Then** it fails the exposure check and names the contradiction.
3. **Given** a record that claims "publicly registered" without an archive URL or receipt, **When** the validator runs, **Then** it fails and requests archive evidence.

---

### User Story 3 - Define Staged Freeze Milestones (Priority: P1)

The researcher declares three distinct freeze milestones in the milestone manifest: `spec-v1` (design rules), `thresholds-v1` (selected thresholds, committed before final testing), and `protocol-v1` (post-ablation Stage B components). For any value that is not yet known, the manifest must contain a fully specified staged determination rule rather than a placeholder.

**Why this priority**: Design rules must be frozen before derived values. Allowing "decide later" entries in the milestone manifest invalidates the study's confirmatory character.

**Independent Test**: Can be fully tested by providing the validator with a milestone manifest fixture and asserting correct pass/fail behaviour for each milestone state.

**Acceptance Scenarios**:

1. **Given** a milestone manifest with all three milestones carrying explicit determination rules, **When** the validator runs, **Then** all milestone checks pass.
2. **Given** a manifest where `thresholds-v1` carries the comment "decide after pilot", **When** the validator runs, **Then** it fails and requests a staged determination rule.
3. **Given** a manifest where `protocol-v1` references a future ablation gate with an explicit condition, **When** the validator runs, **Then** it accepts the staged commitment as resolved.

---

### User Story 4 - Validate Split and Source Provenance (Priority: P1)

The researcher confirms that entity/fact, reference-seed, template-group, and control-implementation isolation is satisfied across the construction, calibration, and final splits according to the declared policy. For TOFU-derived records, atomic-fact mappings and transformation lineage must be recorded; unmaterialised splits must reference an explicit materialization gate, not be reported as verified.

**Why this priority**: Author-level source splits do not automatically guarantee fact-level isolation. An unchecked split boundary can silently contaminate the calibration or final evaluation.

**Independent Test**: Can be fully tested by providing fixture manifests for each split and asserting the validator detects policy violations and correctly defers unmaterialised splits.

**Acceptance Scenarios**:

1. **Given** complete construction/calibration/final manifests with all isolation dimensions recorded, **When** the validator runs, **Then** the split-provenance check passes.
2. **Given** a TOFU-derived record with no atomic-fact mapping recorded, **When** the validator runs, **Then** it fails and names the missing transformation.
3. **Given** a manifest for the final split that has not yet been materialised but declares a future gate ID, **When** the validator runs, **Then** the split is reported "pending (gate N)" rather than verified or failed.

---

### User Story 5 - Specify the Primary Analysis and Reporting Contract (Priority: P1)

The researcher ensures that the preregistration references a complete analysis contract internally consistent with the policies from P0-3, P0-5, and P0-6: both delta comparisons, FRR cap, query budgets, weighting scheme, uncertainty and multiplicity handling, per-control-family FCR, coverage, locality and cost reporting all agree across documents.

**Why this priority**: A favorable secondary result cannot substitute for a failed primary endpoint. The analysis contract is the direct operationalisation of the study's scientific claims.

**Independent Test**: Can be fully tested against a fixture set of the three upstream policy documents plus a partially consistent preregistration, verifying that each cross-file conflict is reported.

**Acceptance Scenarios**:

1. **Given** resolved P0-3/P0-5/P0-6 policies and a preregistration that references them without inline overrides, **When** the validator cross-checks fields, **Then** the analysis contract check passes.
2. **Given** a preregistration where the FRR cap conflicts between the margins reference and an inline assertion, **When** the validator runs, **Then** it fails and names the conflicting fields and their sources.
3. **Given** a preregistration with an empty denominator field for one baseline, **When** the validator runs, **Then** it fails and identifies the missing denominator.

---

### User Story 6 - Declare Stopping and Deviation Recovery Procedures (Priority: P2)

The researcher records a predeclared recovery procedure for each recognised deviation event: feasibility failure, no feasible threshold, scoring bug, budget overrun, model revision, hardware failure, missing access, and cost limit. The preregistration also specifies that a broken final pass requires a full re-run on a fresh split; any superseding rule requires a documented amendment.

**Why this priority**: Unspecified retry and exclusion logic permits outcome selection after the fact. Recovery procedures must be recorded before any deviation can occur.

**Independent Test**: Can be fully tested by routing synthetic failure fixtures through the validator and asserting that each event type maps to exactly one declared procedure.

**Acceptance Scenarios**:

1. **Given** a preregistration with all eight deviation categories covered, **When** the validator checks stopping/deviation sections, **Then** all categories pass.
2. **Given** a preregistration missing the "budget overrun" recovery procedure, **When** the validator runs, **Then** it fails and names the missing category.
3. **Given** a preregistration that declares "patch and resume" for a broken final pass, **When** the validator runs, **Then** it fails with a message requiring full re-run on a fresh split.

---

### User Story 7 - Constrain and Audit Policy Amendments (Priority: P2)

The researcher provides a predeclared amendment protocol for any frozen decision that may legitimately change (e.g., the pilot alpha amendment window). The protocol records: allowed information, trigger condition, approver, deadline before final-test access, and links to any effect-size or sample-size changes. Any amendment lacking these fields, or informed by final-test outcomes, cannot inherit the original confirmatory claim.

**Why this priority**: Permitting a single revision is not the same as permitting an unrestricted one. The amendment protocol is what makes a planned revision traceable and bounded.

**Independent Test**: Can be fully tested by providing amendment fixtures with valid and invalid states and verifying that incomplete or post-hoc amendments are rejected.

**Acceptance Scenarios**:

1. **Given** an amendment record for the pilot alpha window with all required fields present and a deadline before final-test access, **When** the validator checks amendments, **Then** the amendment is accepted.
2. **Given** an amendment record missing the designated approver field, **When** the validator runs, **Then** it rejects the amendment and names the missing field.
3. **Given** evidence that the amendment was triggered after final-test outcomes were inspected, **When** the validator runs, **Then** it rejects the amendment and flags it as post-hoc.

---

### User Story 8 - Label Confirmatory vs Exploratory Claims (Priority: P2)

The researcher ensures that every analysis in the preregistration is labelled consistent with its timing, stage, and data-access history. Secondary analyses, Stage B runs, and unplanned analyses must be explicitly marked exploratory, with access limits, reference availability, and discovery timing recorded. A post-freeze paraphrase not pre-specified is reported exploratory and does not affect the primary denominator.

**Why this priority**: Mislabelling an exploratory result as confirmatory is the most common source of undetected p-hacking. Labelling must be enforced structurally.

**Independent Test**: Can be fully tested by providing a preregistration with mixed confirmatory and exploratory analyses and asserting that the validator catches any unlabelled or mislabelled entry.

**Acceptance Scenarios**:

1. **Given** a preregistration where all secondary and Stage B analyses carry "exploratory" labels with access notes, **When** the validator runs, **Then** the claim-labelling check passes.
2. **Given** a post-freeze paraphrase listed under the primary confirmatory analysis without an exploratory label, **When** the validator runs, **Then** it flags the entry and requires an exploratory label.
3. **Given** an exploratory analysis that correctly notes it does not alter the primary denominator, **When** the validator runs, **Then** it accepts the entry without error.

---

### User Story 9 - Verify Immutable Snapshot Integrity (Priority: P1)

The researcher runs the freeze tooling and receives a verifiable local snapshot in which: (a) `CHECKSUMS.sha256` contains exact byte hashes of all packaged artifacts excluding itself; (b) any embedded contract digest uses a documented canonical payload excluding the digest field; (c) the post-commit freeze receipt records the tag-target commit. Tampered bytes, a moved tag, or a receipt/tag mismatch must all cause verification to fail.

**Why this priority**: A self-referential hash cannot identify the bytes it claims to cover. If snapshot integrity cannot be verified independently, the freeze has no evidential value.

**Independent Test**: Can be fully tested using temporary-repository fixtures: run the freeze in dry-run mode (read-only), then in execution mode, and verify the receipt against the tag and checksums.

**Acceptance Scenarios**:

1. **Given** a correctly prepared snapshot, **When** `freeze.py --verify` runs, **Then** all artifact hashes match and the receipt references the correct tag-target commit.
2. **Given** a byte-modified artifact in the snapshot, **When** `freeze.py --verify` runs, **Then** it exits non-zero and names the file whose hash does not match.
3. **Given** a receipt generated before the final commit (referencing a stale commit ID), **When** `freeze.py --verify` runs, **Then** it fails and reports the tag-target mismatch.

---

### User Story 10 - Gate the Freeze Operation (Priority: P1)

The researcher cannot successfully execute a freeze unless every applicable readiness gate passes: all seven Phase 0 artifacts present and reviewed, decision register resolved, prior SPEC checks passing, tracked referenced files present, and staged obligations accounted for. The freeze tool refuses to create or overwrite a tag if any gate fails; a dry-run is always read-only.

**Why this priority**: Partial freezes are as dangerous as no freeze — they create the appearance of a commitment without its substance. The gate must be exhaustive and fail-closed.

**Independent Test**: Can be fully tested by providing fixture repositories with various incomplete states and asserting that the freeze gate blocks execution and the dry-run never writes.

**Acceptance Scenarios**:

1. **Given** a fixture repository where all gates pass, **When** `freeze.py --dry-run` runs, **Then** it reports all checks passed and makes no filesystem or git writes.
2. **Given** a repository with one unresolved decision in the decision register, **When** `freeze.py` runs, **Then** it exits non-zero naming the unresolved decision before any tag is created.
3. **Given** an existing `spec-v1` tag, **When** `freeze.py` attempts to create the same tag, **Then** it exits non-zero without overwriting the existing tag.

---

### User Story 11 - Provide Offline Validation and Freeze Fixtures (Priority: P2)

The researcher can run the full validation and freeze workflow in a temporary repository without any model, GPU, or network calls. All test fixtures are synthetic, tests are deterministic, and test evidence records any partial local preparation. The CLI returns non-zero exit codes with diagnostics for failure, invalid baseline, and absent publication request.

**Why this priority**: Freeze mechanics must be testable before a real study registration, and independently of any specific model run or external service.

**Independent Test**: Can be fully tested by running `pytest tests/test_preregistration_freeze.py` in an isolated environment with no network access and asserting all tests pass.

**Acceptance Scenarios**:

1. **Given** valid temporary-repository fixtures, **When** the full test suite runs offline, **Then** all 11 test hooks pass and no network calls are made.
2. **Given** a fixture that requests external publication without a prior freeze receipt, **When** the CLI runs, **Then** it exits non-zero and declines to contact any registry.
3. **Given** a partially prepared fixture (checksums computed but tag not yet created), **When** the freeze dry-run runs, **Then** the readiness report records the partial state without fabricating a completed snapshot.

---

### Edge Cases

- What happens when a blocking decision is recorded as "open" at freeze time — does the tool report all open decisions or only those applicable to the current scope?
- How does the tool handle a `preregistration.md` that references an artifact file deleted from the repository since the last validation?
- What happens when `freeze.py --dry-run` is run inside a repository with uncommitted changes — does it warn, fail, or proceed?
- How does the validator distinguish a "staged future commitment" (acceptable) from an "open normative choice" (not acceptable) in the milestone manifest?
- What happens when the same fact appears in both the calibration and final splits due to an alias that was not de-duplicated?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The `validate_spec.py` tool MUST check that `preregistration.md` contains all required sections (primary question, two baselines, hypotheses, controlled construction, units, sampling, evaluation, analysis, stopping, deviations, reporting) and that each section references a normative upstream artifact.
- **FR-002**: The `validate_spec.py` tool MUST fail with a non-zero exit and named diagnostics when any authoritative value (α, query budget, scorer policy) appears in more than one location.
- **FR-003**: The `validate_spec.py` tool MUST verify that the exposure record contains: access dates, actors, inspected outcomes, internal-tag or external-archive status, and evidence references.
- **FR-004**: The `validate_spec.py` tool MUST reject a record that labels final-test data "untouched" while also listing an inspection event that covered it.
- **FR-005**: The milestone manifest MUST declare all three freeze milestones (`spec-v1`, `thresholds-v1`, `protocol-v1`); each unknown future value MUST carry a fully specified staged determination rule, never a placeholder.
- **FR-006**: The `validate_spec.py` tool MUST verify entity/fact, reference-seed, template-group, and control-implementation isolation across construction, calibration, and final splits; unmaterialised splits MUST be reported "pending (gate N)", never "verified".
- **FR-007**: The `validate_spec.py` tool MUST cross-check FRR cap, query budgets, weighting, uncertainty handling, per-control-family FCR, coverage, locality, and cost reporting across P0-3, P0-5, P0-6, and the preregistration, failing on any conflict.
- **FR-008**: The preregistration MUST declare a named recovery procedure for each of the eight recognised deviation event types (feasibility failure, no feasible threshold, scoring bug, budget overrun, model revision, hardware failure, missing access, cost limit).
- **FR-009**: The preregistration MUST specify that a broken final pass requires a full re-run on a fresh split; any superseding rule MUST be a documented amendment, not a silent substitution.
- **FR-010**: The amendment record MUST include: allowed information, trigger condition, approver, deadline before final-test access, and linked effect-size/sample-size changes; missing fields MUST cause validation to fail.
- **FR-011**: Every analysis in the preregistration MUST carry a label consistent with its timing, stage, and data access; unlabelled or inconsistently labelled entries MUST fail validation.
- **FR-012**: `CHECKSUMS.sha256` MUST contain exact byte hashes of all packaged artifacts excluding itself; the contract digest MUST use a canonical payload excluding the digest field; the freeze receipt MUST record the tag-target commit, not the committing commit's own ID.
- **FR-013**: `freeze.py` MUST refuse to create or overwrite a freeze tag unless all applicable readiness gates pass; `--dry-run` MUST be read-only with no filesystem or git writes.
- **FR-014**: `freeze.py --verify` MUST fail and name the affected artifact when any artifact byte hash does not match the stored checksum.
- **FR-015**: The full test suite MUST be executable offline with no model, GPU, or network calls; each test MUST be deterministic given its fixture state.
- **FR-016**: The CLI MUST return a non-zero exit code with named diagnostics for: validation failure, invalid baseline, external-publication request when absent, and any gate-check failure.
- **FR-017**: `freeze.py` MUST never overwrite an existing freeze tag; attempting to do so MUST exit non-zero identifying the existing tag.

### Key Entities

- **Preregistration document** (`preregistration.md`): Versioned study commitment artifact containing or referencing all required sections. Lives at `.factverify/spec/preregistration.md`. Single normative source for study design commitments.
- **Checksum manifest** (`CHECKSUMS.sha256`): Exact byte hashes for all packaged artifacts excluding itself. Produced and consumed by `freeze.py`.
- **Freeze receipt** (`reports/spec-v1-freeze-receipt.json`): Records target commit, tag object and target, timestamp, checksum-file digest, and registration status. Generated after the snapshot commit.
- **Readiness report** (`reports/p0-7-validation.json`): Records readiness status, decision-register state, all gate checks, staged obligations, and input digests. Generated by `validate_spec.py`.
- **Milestone manifest**: Declares `spec-v1`, `thresholds-v1`, and `protocol-v1` milestones with either resolved values or fully specified staged determination rules.
- **Exposure record**: Dated, reviewed document listing data-access events, actors, inspected outcomes, and current registration status.
- **Amendment record**: Structured document for each predeclared policy revision: trigger, approver, deadline, allowed information, and links to dependent parameter changes.
- **Decision register**: Canonical list of all open and resolved design decisions (D-IDs). The strict freeze gate requires all applicable decisions to be resolved.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A researcher can produce a complete, validated `preregistration.md` and pass all 11 validation hooks in a single `validate_spec.py` run on a correctly assembled fixture set — zero false-positive passes.
- **SC-002**: A freeze dry-run completes without making any filesystem or git writes, as verified by a git-status assertion in the fixture test before and after the run.
- **SC-003**: A freeze execution on a valid fixture repository produces a verifiable snapshot: `freeze.py --verify` exits zero and all artifact hashes match.
- **SC-004**: Every gate-check failure produces a named diagnostic sufficient to identify the failing artifact, field, or decision ID — no silent failures or generic error messages.
- **SC-005**: The full test suite (`tests/test_preregistration_freeze.py`) passes in an offline environment with no network access, confirming zero dependency on external services.
- **SC-006**: Attempting to create a second `spec-v1` tag always exits non-zero and leaves the existing tag unmodified, as confirmed by a pre/post tag-object comparison in fixtures.
- **SC-007**: Cross-file policy conflicts (e.g., conflicting α values across `margins.yaml` and `preregistration.md`) are detected and reported with source file and field name in 100% of synthetic conflict fixtures.

## Assumptions

- The six sibling artifacts from P0-1 through P0-6 exist in the repository (at least as fixture stubs) before P0-7 tooling is implemented; the validator does not create them.
- α = 0.05 is treated as provisional; no threshold value is hard-coded in `validate_spec.py` or `freeze.py` — all values are read from spec fields.
- The researcher does not intend to perform external registration as part of this task; the tooling supports it as an optional future step but does not require or trigger it.
- The decision register (D-IDs) is maintained as a structured file or database accessible to `validate_spec.py`; its format is compatible with the existing ledger infrastructure.
- Python 3.11 managed by `uv` is the runtime; `validate_spec.py` and `freeze.py` are standalone CLI tools in the `tools/` directory, consistent with existing project layout.
- Temporary-repository fixtures are self-contained (created and destroyed within the test session) and do not touch the live study repository or any real data splits.
- The non-circular digest approach described in the §2 source-reconciliation note is the accepted design; the implementation does not need to support the legacy circular approach.
