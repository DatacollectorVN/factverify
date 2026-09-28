# Feature Specification: Base Model Selection and Pinning

**Feature Branch**: `20260926-101858-base-model-pinning`
**Created**: 2026-09-26
**Status**: Draft
**Source**: FV-SPEC-P0-8 (status: draft · blocked by D-46, D-47, D-48, D-49)
**Input**: second-brain/ml-unlearning/requirements/FV-SPEC — P0-8

> **Note:** The upstream requirements note carries `status: draft` and four open blocking decisions (D-46, D-47, D-48, D-49). No requirement reaches `implemented` while a decision it depends on is open. This spec records what must be true; decisions fill in which values satisfy it.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Record a Verifiable Model Identity (Priority: P1)

A researcher preparing the study needs to declare exactly which model the experiment will run on. They record the identity of every study role (Blocks 0–2 base model, Block 3 confirmation model) in the single canonical model-spec file. Once recorded, the file can be validated offline to confirm nothing has silently drifted.

**Why this priority**: Every downstream artefact — exclusion gate, ledger, generation cache — is only meaningful relative to the exact model it was computed on. This is the foundation; all other stories depend on it.

**Independent Test**: Can be fully tested by authoring a `models.yaml` containing one complete role entry and running the validator; it either passes all identity checks or reports exactly which fields are missing.

**Acceptance Scenarios**:

1. **Given** a `models.yaml` with a complete entry for every declared study role, **When** the validator runs, **Then** it exits zero and reports all identity checks passed.
2. **Given** a role entry with any field absent or set to a placeholder, **When** the validator runs in strict mode, **Then** it exits non-zero and names the missing role and field.
3. **Given** a role entry where the model revision is a branch name, a short hash, or a tag rather than a full 40-character hex commit hash, **When** the validator runs, **Then** it exits non-zero and names the offending revision field.

---

### User Story 2 — Verify File Integrity Without Network Access (Priority: P2)

A researcher or CI runner needs to confirm that a local model directory matches the frozen identity — for example after a re-download or a cache migration — without contacting the hub.

**Why this priority**: Reproducibility requires that the bytes on disk are exactly what was declared. A hash mismatch should be detectable at any time, offline, before any training or evaluation run begins.

**Independent Test**: Can be fully tested by recording the digests of a synthetic local model directory, then running the offline digest-check; pass on match, fail on any modification.

**Acceptance Scenarios**:

1. **Given** a local model directory whose files match the SHA-256 digests recorded in `models.yaml`, **When** the offline digest check runs, **Then** it passes without a network call.
2. **Given** a local directory where any weight, config, or tokenizer file has been modified, is missing, or has an extra file present, **When** the digest check runs, **Then** it fails and names every offending file.

---

### User Story 3 — Confirm Downstream Evidence Is Bound to the Frozen Model (Priority: P3)

A reviewer auditing the study needs to confirm that the exclusion-gate report, ledger rows, and cache manifests all record the same model-identity key as `models.yaml`. A mismatch means evidence was produced for a different model.

**Why this priority**: Without this binding, a model swap could go undetected after results exist, silently invalidating the study.

**Independent Test**: Can be fully tested by supplying a synthetic exclusion-gate report and ledger row that carry the correct frozen identity hash, then verifying the cross-check passes; swap the hash and verify it fails.

**Acceptance Scenarios**:

1. **Given** downstream artefacts (exclusion-gate report, ledger rows, cache manifest) that record the identity hash matching `models.yaml`, **When** the cross-check runs, **Then** it passes for each artefact.
2. **Given** a downstream artefact with a different or absent identity hash, **When** the cross-check runs, **Then** it fails and names the artefact and the mismatched field.
3. **Given** a downstream artefact that has not yet been produced (e.g. Block 3 cache before Block 3 runs), **When** the cross-check runs, **Then** it reports the check as `pending`, not passed and not failed.

---

### User Story 4 — Change a Model Only via the Amendment Protocol (Priority: P4)

A researcher who needs to swap or update a model after the spec is frozen must do so through the amendment protocol: record the change as a versioned amendment, create a new spec tag, and re-run the exclusion gate. The validator refuses a silent edit.

**Why this priority**: Unrecorded model changes are indistinguishable from data fabrication. The amendment protocol is the safeguard.

**Independent Test**: Can be fully tested by comparing a post-freeze `models.yaml` against the frozen snapshot; an unrecorded change must be rejected, while a change accompanied by a valid amendment record must be accepted.

**Acceptance Scenarios**:

1. **Given** a post-freeze change to `models.yaml` accompanied by a recorded amendment, a new spec version tag, and a re-run exclusion gate, **When** the validator checks the amendment, **Then** it accepts the change and the prior snapshot remains accessible.
2. **Given** a `models.yaml` whose content differs from the frozen snapshot with no amendment record, **When** the validator runs, **Then** it exits non-zero and refuses to pass.

---

### User Story 5 — Ensure Declared Models Match the Access Profile (Priority: P2)

A researcher configuring the study needs confirmation that every declared model can actually provide all observation and intervention channels the access profile enables. A model that cannot deliver logits or does not permit fine-tuning cannot satisfy a profile that requires them.

**Why this priority**: Declaring an incompatible model would make the study operationally impossible without a late-breaking amendment; catching it at spec-validation time is far cheaper.

**Independent Test**: Can be fully tested with a synthetic access profile and a set of model entries covering compatible and incompatible combinations; the validator must accept compatible entries and reject incompatible ones with a diagnostic.

**Acceptance Scenarios**:

1. **Given** open-weight models whose access modalities cover every channel enabled in `access_profile.md`, **When** the cross-check runs, **Then** all channels are confirmed supported.
2. **Given** a model that is API-only or whose licence forbids fine-tuning, under a profile requiring logit access or parameter updates, **When** the cross-check runs, **Then** it fails and names the unsatisfied channel.

---

### Edge Cases

- What happens when the `models.yaml` file is absent entirely? (Validator must exit non-zero with a clear diagnostic, not silently pass.)
- What happens when a declared role is listed but its entry is completely empty? (Treated as all fields missing; strict mode rejects it.)
- What happens when a downstream artefact references a model that was legally amended away? (The prior snapshot must still be reachable; the cross-check compares against the current frozen identity, not the old one, but the amendment log must record the transition.)
- What happens if the Block 3 model is declared as a staged commitment with a deadline? (The entry is reported `pending` at validation time; validation does not fail on a declared-pending staged entry, but does fail if the deadline passes without resolution.)

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST record a complete model-identity entry for every declared study role in a single canonical spec file; any missing or placeholder field causes validation to fail in strict mode.
- **FR-002**: The system MUST accept only 40-character hexadecimal commit hashes as model and tokenizer revision identifiers; any other form (branch, tag, short hash, absent) causes validation to fail.
- **FR-003**: The system MUST record a SHA-256 digest for every weight, configuration, and tokenizer file belonging to each pinned model, and MUST verify a local directory against those digests without a network call.
- **FR-004**: The system MUST cross-check declared models against the enabled channels in the access profile and refuse any model that cannot satisfy every enabled observation or intervention channel.
- **FR-005**: The system MUST define a single canonical payload and hash function for model identity such that identical inputs produce byte-identical hashes across machines and runs, and any single-field change produces a different hash.
- **FR-006**: The system MUST cross-check every downstream artefact (exclusion-gate report, ledger rows, cache manifests) against the frozen model-identity hash and fail when a mismatch is found; an artefact not yet produced is reported `pending`.
- **FR-007**: The system MUST refuse any post-freeze modification to the model-spec file that is not accompanied by a valid recorded amendment and a new spec version tag.
- **FR-008**: The system MUST emit a structured validation report (pass/fail/pending per check, with diagnostics) suitable for CI consumption.
- **FR-009**: Validation MUST complete without GPU access and MUST complete digest verification without a network call; wall-clock runtime MUST be recorded.

### Key Entities

- **Model role**: A named position in the study design (e.g. Blocks 0–2 base model, Block 3 confirmation model) with its full identity record. A role without a resolved decision is recorded as a declared-pending entry, not filled with a placeholder value.
- **Model identity**: The tuple of (repo identifier, model commit revision, tokenizer commit revision, dtype, adapter digest) that uniquely and immutably identifies one exact set of weights.
- **Model-identity hash**: The canonical SHA-256 digest of the model-identity tuple. Every downstream artefact carries this key so evidence can be bound to the exact model.
- **Spec amendment**: A versioned record documenting a post-freeze change to the model-spec file, including motivation, new spec tag, and confirmation that the exclusion gate was re-run on the new model.
- **Access profile**: The declared set of observation channels (e.g. logit access) and intervention channels (e.g. parameter updates) the study requires; sourced from FV-SPEC-P0-4.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of model-spec validation checks (FV-SPEC-089 through FV-SPEC-095) pass with green test hooks before any training or evaluation run begins.
- **SC-002**: A silent post-freeze model swap is caught and rejected in every test case — zero false-passes on the amendment check across all fixtures.
- **SC-003**: The offline digest check catches 100 % of single-file modifications, additions, and deletions in the synthetic fixture suite without a network call.
- **SC-004**: The identity hash is byte-identical for identical inputs across at least two independent runs, and differs for every single-field variation in the test matrix.
- **SC-005**: All downstream-binding cross-checks correctly classify each artefact as `pass`, `fail`, or `pending` — zero misclassifications across the full fixture set.
- **SC-006**: The full validation run (all checks, all roles, digest verification) completes on CPU-only hardware in under 60 seconds on the synthetic fixture suite.
- **SC-007**: The four blocking decisions (D-46, D-47, D-48, D-49) are resolved and recorded before any role entry transitions from `pending` to `implemented`.

---

## Assumptions

- The base model for Blocks 0–2 will be an open-weight model with publicly accessible weight files and a permissive fine-tuning licence (decision D-46 is still open; this assumption will be verified when D-46 closes).
- The Block 3 confirmation model may be declared as a staged commitment with a deadline; the spec structure supports `pending` entries and does not require it to be resolved before Blocks 0–2 work begins.
- The dtype and precision policy (D-48) will be resolved before the first training run; until then, the `dtype` field is declared `DECISION_REQUIRED` and validation is non-strict on that field only until D-48 closes.
- The variant decision (D-49, base vs instruct) is blocking for prompt and refusal-control design; the spec field is required, but no example value is assumed here.
- Downstream artefacts do not all exist at spec-freeze time; the validator treats absent-but-expected artefacts as `pending`, not failures, until the relevant phase runs.
- The canonical path for the model-spec file is `.factverify/spec/models.yaml` (following handbook §11.1); any plan reference to `spec/models.yaml` resolves to this path.
- FV-SPEC-087 (readiness report) and V01 (required-file list) must be updated to include `models.yaml` as the eighth spec artefact; that update is a prerequisite for this feature to reach `verified` status and is tracked as a local review item in FV-SPEC-P0-8.
- Synthetic fixtures (a small local model directory with known digests) are sufficient for all verification; no real model download is required to make the test suite green.
