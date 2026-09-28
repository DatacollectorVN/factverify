# Feature Specification: FV-MODEL — P2-0 Model Loader

**Feature Branch**: `20260926-105952-model-loader`  
**Created**: 2026-09-26  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-MODEL — P2-0.md` (status: draft)  
**Plan task**: P2-0 · **Spec dependency**: spec-v1

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Load any study checkpoint reproducibly (Priority: P1)

A researcher runs an evaluation pass and needs to load a base model, finetuned checkpoint, retain-only reference, control, or candidate identically — same weights, same precision, same identity record — regardless of which machine or run it is on. They provide a role name and a path to the frozen spec; the loader returns a ready-to-use model object and a stable identity hash.

**Why this priority**: Every downstream component — the exclusion gate, evaluators, ledger, and cache — depends on consistent, verified loading. Without a single verified entry point, two runs of "the same" model can silently diverge, invalidating comparisons.

**Independent Test**: Call the loader with the same role on two separate machines; confirm that the returned identity hash and payload are byte-identical and that the model produces identical outputs for a fixed input and seed.

**Acceptance Scenarios**:

1. **Given** a valid role declared in the frozen `models.yaml`, **When** the loader is invoked with that role and the spec root, **Then** the returned model and tokenizer revisions equal the commit hashes declared for that role.
2. **Given** an unknown role, or a caller-supplied revision override, **When** the loader is invoked, **Then** it raises a descriptive error before loading any weights.
3. **Given** all local files matching their recorded digests, **When** the loader runs, **Then** the model is returned successfully.
4. **Given** a locally modified, missing, or extra file, **When** the loader runs, **Then** it raises naming the problematic file; no model object is returned.
5. **Given** all files present locally and network access disabled, **When** the loader runs, **Then** the model loads without initiating any network activity.
6. **Given** a missing local file, **When** the loader runs, **Then** it raises a missing-file error rather than attempting a download.
7. **Given** hardware that supports the dtype and attention implementation declared in `models.yaml`, **When** the loader runs, **Then** every parameter has the declared dtype and the attention implementation matches the declaration.
8. **Given** hardware that cannot honour the declared dtype or attention implementation, **When** the loader runs, **Then** it raises instead of falling back silently.
9. **Given** a loaded model, **When** the same input is scored twice with the same seed on the same device, **Then** the logits are identical (dropout is disabled).

---

### User Story 2 — Attach a LoRA adapter to a verified base (Priority: P2)

A researcher loads a finetuned or unlearned checkpoint, stored as a base model plus a LoRA adapter directory produced by the training harness. They provide the adapter path alongside the role; the loader verifies the adapter was trained on exactly the loaded base, attaches it, computes the adapter digest, and includes both in the returned identity record.

**Why this priority**: Attaching an adapter to the wrong base produces a checkpoint that matches no reference in the study. The identity hash must reflect the full composite checkpoint so that the ledger and cache remain consistent.

**Independent Test**: Load a role with and without an adapter path; confirm that the identity hashes differ, that the adapter digest appears in the payload of the combined load, and that loading with a mismatched adapter raises before any attachment occurs.

**Acceptance Scenarios**:

1. **Given** an adapter directory whose metadata records the identity hash of the loaded base, **When** the loader is called with that adapter path, **Then** the returned model includes the adapter and the adapter digest is present in the identity payload.
2. **Given** an adapter directory whose metadata records a different or missing base identity, **When** the loader is called, **Then** it raises before attaching anything.
3. **Given** an unchanged adapter directory, **When** loaded twice, **Then** the adapter digest is identical both times.
4. **Given** one changed byte in the adapter directory, **When** loaded, **Then** the adapter digest, and therefore the full identity hash, changes.

---

### User Story 3 — Enforce a single loading gate across the repository (Priority: P3)

A developer adds new evaluation or training code and must not bypass the loader by calling model-loading primitives directly elsewhere. A static repository check (runnable in CI) confirms that all model-loading calls are inside the designated module.

**Why this priority**: A single bypass produces a checkpoint with no digest check and no identity hash, silently invalidating the study's provenance chain.

**Independent Test**: Run the static check on the repository; confirm it passes on the current codebase and fails when a model-loading call is introduced outside the designated module.

**Acceptance Scenarios**:

1. **Given** the current repository, **When** the static check runs, **Then** model-loading primitives appear only inside the designated model-loading module.
2. **Given** a model-loading call added outside the designated module, **When** the check runs in CI, **Then** CI fails naming the file and line number.

---

### Edge Cases

- What happens when `models.yaml` is absent, unreadable, or not at the declared spec revision?
- How does the loader behave when a role is present in `models.yaml` but no local files have been downloaded yet?
- What if the same adapter directory is passed for two different base roles?
- What if the declared dtype is not representable on available hardware (e.g., bf16 on a CPU-only machine)?
- What if a caller explicitly passes a revision override argument to circumvent pinning?
- What happens when `models.yaml` lists a digest for a file that exists but is zero bytes?

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The loader MUST accept a role name and a spec root path, then load model weights and tokenizer only at the revisions `models.yaml` declares for that role — no caller-supplied repository IDs, revision overrides, or bare model names are accepted.
- **FR-002**: The loader MUST verify every weight, config, and tokenizer file against the digests recorded in `models.yaml` before returning any model object; a mismatch, missing file, or extra file raises an error naming the offending item.
- **FR-003**: The loader MUST operate entirely from local storage; it MUST NOT initiate any network activity during a load. File retrieval is the responsibility of a separate, explicit prefetch command.
- **FR-004**: The loader MUST return a canonical identity hash and identity payload computed as defined in the frozen spec, byte-identical across machines for identical inputs (role, adapter, spec root).
- **FR-005**: The loader MUST refuse to attach an adapter whose recorded base identity does not match the loaded base model's identity hash; it MUST raise before applying any adapter weights.
- **FR-006**: The loader MUST compute a content digest over the adapter's weight and config files at load time and include it in the identity payload.
- **FR-007**: The loader MUST apply exactly the dtype and attention implementation declared in `models.yaml`; it MUST raise rather than fall back silently when hardware cannot honour the declaration.
- **FR-008**: The loader MUST return every model in evaluation mode with stochastic layers disabled; callers that need training mode MUST switch it themselves after receiving the model.
- **FR-009**: No code outside the designated model-loading module MUST call model-loading primitives for models, tokenizers, or adapters; a repository-wide static check MUST enforce this boundary in CI.
- **FR-010**: On any bad, missing, or unresolvable input, the loader MUST raise a descriptive error naming the role, file, or field before returning any model object — no silent fallbacks of any kind.

### Key Entities

- **LoadedModel**: The return value of the loader; carries the model object (in evaluation mode, optionally with adapter attached), the tokenizer, the identity hash string, and the identity payload (the canonical fields used to compute the hash).
- **Role**: A named key in `models.yaml` mapping to a specific model source, pinned revision, tokenizer revision, file digests, dtype, and attention policy. Roles cover base models, finetuned checkpoints, retain-only references, controls, and candidates.
- **Adapter directory**: A LoRA adapter produced by the training harness (P2-1); contains weight and config files plus a metadata record that includes the base identity hash of the model the adapter was trained on.
- **Identity hash**: A content digest over a canonical payload (base revision, adapter digest if present, dtype, and any additional fields the spec declares); serves as the primary key in the run ledger and generation cache.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every model loaded during the study has a recorded identity hash and payload — zero loads occur without one.
- **SC-002**: Loading the same role and adapter on two different machines produces byte-identical `identity_hash` and `identity_payload` values, verified across all roles exercised in the pilot.
- **SC-003**: Any corrupted, substituted, or missing file causes the loader to raise before returning a model object, in 100% of cases.
- **SC-004**: The static repository check finds zero model-loading primitive calls outside the designated module at all times on the main branch.
- **SC-005**: All nine test hooks (FV-MODEL-001 through FV-MODEL-009) pass green before any downstream component (P1-2 exclusion gate, P2-1 harness, P2-2 evaluators, P2-5 ledger, P2-7 cache) begins integration work.
- **SC-006**: An adapter whose base identity mismatches raises an error before any adapter weights are applied, in 100% of such attempts.

---

## Assumptions

- Models are pre-fetched to local storage by a separate prefetch command before study runs begin; the loader never downloads files.
- The `models.yaml` spec artifact is at the `spec-v1` tag and is frozen; the loader reads it but never modifies it.
- Adapter directories are produced by the training harness (P2-1) and include a metadata record containing the base identity hash; the format of this record is agreed between P2-0 and P2-1 before either is finalised.
- Hardware capabilities (dtype and attention implementation support) are validated by environment setup before the loader is invoked; the loader raises on incompatibility but does not attempt remediation.
- Three decisions remain open and block the corresponding requirements until resolved: **D-46** (base model selection, blocks FR-001 for final values), **D-48** (dtype and attention policy, blocks FR-004 and FR-007 for final values), **D-50** (adapter evaluation vs. merge policy, blocks FR-005). Code and tests can be written against spec fields using a local fixture model before these close.
- The identity-hash computation algorithm is fully defined by FV-SPEC P0-8 §093; the loader implements it, not invents it.
- No requirement may be marked `implemented` while a blocking decision it depends on remains open (per the requirements note conventions).
