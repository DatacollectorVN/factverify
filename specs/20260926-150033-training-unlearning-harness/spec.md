# Feature Specification: FV-HARN — P2-1 Training and Unlearning Harness

**Feature Branch**: `20260926-150033-training-unlearning-harness`  
**Created**: 2026-09-26  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-HARN — P2-1.md` (status: draft)  
**Plan task**: P2-1 · **Spec dependency**: spec-v1  
**Input**: User description: "Every finetuned, reference, and unlearned checkpoint is produced from one config file and one seed, reproducibly."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Produce one auditable checkpoint from one config and one seed (Priority: P1)

A researcher starts a training job by supplying a single job configuration and the frozen spec. The job trains only the items named on its data manifest, derives every random choice from the declared seed, and returns success only after the adapter checkpoint carries complete metadata and exactly one ledger row with a full cost record exists. If the configuration is incomplete, the manifest is violated, or the ledger or metadata cannot be written, the job fails before it can be treated as a study checkpoint.

**Why this priority**: The reference band and every false-rejection-rate estimate treat each seed as an independent replicate of one procedure. A checkpoint that cannot be regenerated, or that has no ledger row, cannot be audited or placed in a split.

**Independent Test**: Run the same complete configuration and seed twice on the same hardware class under the declared determinism policy, and confirm that training-item order matches and adapter digests agree within the declared tolerance. Separately, omit one required hyperparameter, request an item that is not on the manifest, and force a ledger or metadata write failure; each attempt ends as a failure before a checkpoint is published as successful.

**Acceptance Scenarios**:

1. **Given** a job configuration that declares every hyperparameter the chosen method uses, **When** the job starts, **Then** a hash of the full resolved configuration is computed and stored in the checkpoint metadata.
2. **Given** a job configuration missing any hyperparameter the chosen method uses, **When** the job starts, **Then** it fails naming that field, and no built-in default is substituted.
3. **Given** the same configuration, seed, and hardware class under the declared determinism policy, **When** the job is run twice, **Then** the training-item order is identical and the adapter digests match within the declared tolerance.
4. **Given** two jobs that differ only in the declared seed, **When** both run, **Then** the training-item order differs and each seed is recorded in that checkpoint's metadata.
5. **Given** a completed job, **When** its data-access record is compared with its manifest, **Then** the two sets of training items are equal.
6. **Given** a request for a training item that is not on the manifest, **When** the job runs, **Then** it fails naming that item.
7. **Given** a finished job, **When** its checkpoint metadata is read, **Then** base identity hash, parent checkpoint hash, configuration hash, seed, role, and method are all present and non-null. For a finetune or a retain-only reference, the parent is the base identity.
8. **Given** a metadata write failure, **When** the job ends, **Then** the job is marked failed and the adapter is not published.
9. **Given** a finished job, **When** it returns success, **Then** exactly one ledger row exists for that checkpoint.
10. **Given** a ledger write failure, **When** the job ends, **Then** the job returns failure.
11. **Given** a finished job, **When** its ledger row is read, **Then** wall-clock, GPU-hours, peak memory, training steps, and training examples are all populated.
12. **Given** a job that crashes, **When** the outcome is recorded, **Then** the partial cost is still written with status `failed`.
13. **Given** a missing configuration, an unreadable configuration, or an unresolved spec field, **When** the job is started, **Then** it fails closed before the first training step and names the missing field.

---

### User Story 2 — Train a retain-only reference that differs only by the missing fact (Priority: P2)

A researcher trains a retain-only reference for a target fact. The reference must use the same procedure as its paired finetune: the same base, the same learning rate, the same number of epochs, and the same adapter settings. It may differ only in which training items it sees and which seed it uses. It must exclude every document in the target fact's source bundle, and its seed must not already have been used for that fact on another split.

**Why this priority**: A reference that saw the fact, or that was trained by a different procedure, measures the wrong thing. A seed shared across calibration and final test makes the final estimate partly in-sample. The reference band is unusable until this story holds.

**Independent Test**: Submit a reference configuration that differs from its paired finetune only in the data manifest and the seed, with a manifest disjoint from the target source bundle and a seed unused for that fact. Confirm the job proceeds and records the excluded bundle identifier and the paired finetune's configuration hash. Then repeat with one leaked bundle document, one changed learning rate, and one seed already recorded under another split; each attempt fails naming the offending document, field, or seed.

**Acceptance Scenarios**:

1. **Given** a reference manifest that shares no document with the target fact's source bundle, **When** the reference job starts, **Then** it proceeds and records the excluded bundle identifier.
2. **Given** a reference manifest that contains any document from that source bundle, **When** the job starts, **Then** it fails naming the document.
3. **Given** a reference configuration that differs from its paired finetune only in the data manifest and the seed, **When** it is validated, **Then** it passes and records the paired finetune's configuration hash.
4. **Given** a reference configuration that also differs in learning rate, epochs, adapter settings, or base identity, **When** it is validated, **Then** it fails listing the differing fields.
5. **Given** a seed that has not yet been recorded for that fact, **When** the reference job starts, **Then** it proceeds.
6. **Given** a seed already recorded in the ledger for that fact under a different split, **When** the reference job starts, **Then** it fails.

---

### User Story 3 — Select an unlearning method by name (Priority: P3)

A researcher produces an unlearned checkpoint by naming one of the four study methods — gradient ascent, gradient difference, negative preference optimization, or representation misdirection — in the job configuration. The checkpoint records that method and the hyperparameters it actually used. An unrecognised method name is rejected before any training data is loaded.

**Why this priority**: Candidate comparisons are attributable only when checkpoints differ by the declared method and its hyperparameters. This story sits on the same job, manifest, seed, metadata, and ledger rules as Story 1.

**Independent Test**: Run each of the four method names on the fixture model and confirm each produces a checkpoint whose metadata names the method and its hyperparameters. Submit an unknown method name and confirm the job fails before loading data.

**Acceptance Scenarios**:

1. **Given** each of the four method names on the fixture model, **When** the job runs, **Then** a checkpoint is produced whose metadata records the method name and that method's hyperparameters.
2. **Given** an unknown method name, **When** the job is started, **Then** it fails before loading training data.

---

### Edge Cases

- What happens when the job configuration is missing, unreadable, or leaves a spec field unresolved? The job fails closed before the first training step, naming the missing field.
- What happens when a method's hyperparameters or the shared adapter settings are still an open decision? The job reads those values from the configuration and the frozen spec, and leaves the decision open until the spec field is filled.
- What happens when the same configuration and seed are repeated on a different hardware class, or when the declared determinism tolerance is still open? Digest agreement is judged only under the declared hardware class and the declared tolerance.
- What happens when metadata is only partly written? The job is marked failed and the adapter is not published.
- What happens when the process crashes after some steps and before a normal return? Partial cost is recorded with status `failed`, and the job is not reported as successful.
- What happens when a retain-only reference's manifest is disjoint from the source bundle but the paired finetune configuration hash cannot be resolved? Validation fails closed before training.
- What happens when an unlearning job has no parent checkpoint to record? The parent field is required and non-null; for finetune and retain-only reference jobs it is the base identity, and for an unlearning job it is the checkpoint the method is applied to. A missing parent fails the job and the adapter is not published.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The harness MUST refuse to start a job whose configuration does not declare every hyperparameter the chosen method uses. It MUST name the missing field and MUST NOT substitute a built-in default. On a complete configuration, it MUST compute a hash over the full resolved configuration and write that hash into the checkpoint metadata. Traces to FV-HARN-001.
- **FR-002**: The harness MUST derive training-item order, adapter initialisation, and dropout randomness from the job's declared seed. The same configuration, seed, and hardware class under the declared determinism policy MUST yield the same training-item order and adapter digests within the declared tolerance. Two different seeds MUST yield different training-item order, and each seed MUST be recorded in checkpoint metadata. Traces to FV-HARN-002.
- **FR-003**: The harness MUST refuse to train a retain-only reference whose data manifest contains any document from the target fact's source bundle, and MUST name that document. A manifest disjoint from that bundle MUST be allowed to proceed, and the job MUST record the excluded bundle identifier. Traces to FV-HARN-003.
- **FR-004**: The harness MUST refuse a reference job whose resolved configuration differs from its paired finetune configuration in any field other than the data manifest and the seed, and MUST list the differing fields. A reference that differs only in those two fields MUST pass validation and MUST record the paired finetune's configuration hash. Traces to FV-HARN-004.
- **FR-005**: The harness MUST run gradient ascent (GA), gradient difference (GradDiff), negative preference optimization (NPO), or representation misdirection (RMU) when the configuration's method field names that method, and MUST record the method name and its hyperparameters in checkpoint metadata. An unknown method name MUST fail the job before training data is loaded. Traces to FV-HARN-005.
- **FR-006**: The harness MUST read only training items listed on the job's data manifest. The data-access record of a completed job MUST equal the manifest item set. A request for an unlisted item MUST fail the job, naming that item. Traces to FV-HARN-006.
- **FR-007**: The harness MUST write, into every checkpoint's metadata, the base identity hash, parent checkpoint hash, configuration hash, seed, role, and method, each present and non-null. For a finetune and for a retain-only reference, the parent MUST be the base identity. For an unlearning job, the parent MUST be the checkpoint the method is applied to. If metadata cannot be written, the job MUST be marked failed and the adapter MUST NOT be published. Traces to FV-HARN-007.
- **FR-008**: The harness MUST report a job successful only after exactly one ledger row for that checkpoint has been committed. A ledger write failure MUST cause the job to return failure. The committed row MUST carry the checkpoint's configuration hash, seed, split, role, and spec revision. Traces to FV-HARN-008.
- **FR-009**: The harness MUST record wall-clock, GPU-hours, peak memory, training steps, and training examples for every job. A crash MUST still record the partial cost with status `failed`. Traces to FV-HARN-009.
- **FR-010**: The harness MUST refuse a reference job whose seed is already recorded for the same fact under a different split. A seed not yet recorded for that fact MUST be allowed to proceed. Traces to FV-HARN-010.
- **FR-011**: On any bad, missing, or unresolved input — including an unresolved spec field — the harness MUST fail closed before the first training step. No requirement may be treated as implemented while a blocking decision it depends on remains open.

### Key Entities

- **Job configuration**: The single operator-supplied description of a job. It names the role, the method, the base role, the data manifest, the seed, and every hyperparameter the method uses. Its hash is taken over the full resolved configuration.
- **Data manifest**: The explicit list of training-item identifiers this job may read. For a retain-only reference, the list must be disjoint from the target fact's source bundle.
- **Source bundle**: The set of documents that teach a target fact. A retain-only reference excludes the whole bundle, and the job records the excluded bundle identifier.
- **Adapter checkpoint**: The trained adapter together with its metadata record: base identity hash, parent checkpoint hash, configuration hash, seed, role, and method.
- **Ledger row**: The single committed run record for a checkpoint. It carries configuration hash, seed, split, role, spec revision, status, and the cost record. A successful job has exactly one such row.
- **Cost record**: Wall-clock, GPU-hours, peak memory, training steps, and training examples. A crashed job stores the partial vector with status `failed`.
- **Retain-only reference**: A checkpoint paired with a finetune. It uses the same procedure and base, and differs only in the data manifest and the seed. It records the paired finetune's configuration hash.
- **Unlearning method**: One of four named procedures — gradient ascent (GA), gradient difference (GradDiff), negative preference optimization (NPO), representation misdirection (RMU) — selected only by the configuration's method field.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every checkpoint reported as successful has exactly one configuration hash, one seed, one role, and one method recorded, and exactly one committed ledger row. Zero successful checkpoints lack any of these.
- **SC-002**: Two runs of the same configuration, seed, and hardware class under the declared determinism policy produce the same training-item order and adapter digests within the declared tolerance, for every pair checked in the pilot.
- **SC-003**: A missing hyperparameter, an unknown method, a leaked source-bundle document, a procedure mismatch, an unlisted training item, or a seed already used for that fact on another split causes the job to fail before the first training step, naming the offending field, document, item, or seed, in 100% of such attempts.
- **SC-004**: Every successful job's ledger row has all five cost fields populated. Every crashed job still has a partial cost record with status `failed` and is not reported as successful.
- **SC-005**: Every accepted retain-only reference differs from its paired finetune only in the data manifest and the seed, and records both the excluded source-bundle identifier and the paired finetune's configuration hash.
- **SC-006**: The data-access record of every completed job equals that job's manifest, with zero training items read from outside the manifest.
- **SC-007**: All ten requirement checks (FV-HARN-001 through FV-HARN-010) pass before any Block 0 training run uses the harness.

---

## Assumptions

- The operator starts each job with one configuration and the frozen spec root. Model loading and identity hashing are provided by the model loader (P2-0); this feature consumes a verified base and writes adapter metadata the loader can check.
- Controlled facts, source bundles, and splits already exist (P1). The harness consumes an explicit manifest of training-item identifiers; it does not choose the split.
- Ledger storage is provided by the ledger component (P2-5). This feature supplies one row per checkpoint, the fields that row must carry, and the rule that success follows a committed row.
- In scope: finetune checkpoints, retain-only references, the four named unlearning methods, seeding, configuration validation, checkpoint metadata, run records, and cost capture.
- Out of scope: model loading and hashing (P2-0); fake-unlearning controls (P2-3); evaluation and the query-budget accountant (P2-2); ledger storage internals (P2-5); the relearning attack policy, which lives in the attack specification — this feature only supplies the training primitive; the Block 3 learning-rate sweep (P6-4).
- The frozen spec is at `spec-v1`. The harness reads spec fields and does not edit `spec-unlearning/`.
- For a finetune or a retain-only reference, the parent recorded in metadata is the base identity, as the requirements note states. For an unlearning job, the parent is the checkpoint the method is applied to, following the parent-to-child lineage the note cites.
- The ledger row's provenance fields are those named by constraint C-3 of the requirements note — configuration hash, seed, split, and spec revision — together with role.
- Three decisions remain open. Requirements that depend on them are written against the spec field: **D-51** (unlearning hyperparameters per method for Blocks 0–2; blocks FR-001 and FR-005 for final values), **D-52** (adapter rank, scaling, and target modules shared by the finetune and the retain-only reference; blocks FR-001 for final values), **D-53** (determinism policy and the reproducibility tolerance for adapter digests; blocks FR-002 for the numeric tolerance). Jobs can be specified and checked against fixture configurations before these close.
- No requirement may be marked implemented while a blocking decision it depends on remains open.
- The source requirements note is `draft`. Design notes it cites, including the retain-only reference note, should be treated as draft until they pass review.
