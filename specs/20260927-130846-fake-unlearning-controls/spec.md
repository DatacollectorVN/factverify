# Feature Specification: FV-CTRL — P2-3 Fake-Unlearning Controls

**Feature Branch**: `20260927-130846-fake-unlearning-controls`  
**Created**: 2026-09-27  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-CTRL — P2-3.md` (status: draft)  
**Plan task**: P2-3 · **Spec dependency**: spec-v1  
**Input**: User description: "Every negative control family exists as a labelled, reproducible system whose knowledge of the target is hidden but not removed, or removed only by collateral damage."

Design sources, read from disk because the Obsidian vault tools were unavailable: [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md), heading "Phase 2 — Harness and run ledger", task P2-3 (note status: planned), and heading "Phase 3 — Block 0 · integrity pilot → GATE 1" for the rule that a failed gate is not fixed by loosening controls. [Fake-Unlearning Controls](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/02-Concepts/Fake-Unlearning%20Controls.md), headings "Definition" and "How It Works" (note status: draft). The requirements note is `draft`.

A negative control is a system an evaluator must not certify as unlearned. The false-certification rate is the share of those systems that an evaluator accepts anyway. This feature supplies the labelled negative systems that rate is computed on. A control that actually removed the target fact, or that is labelled as the wrong mechanism, makes that rate measure nothing.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Provide a labelled negative system for every family (Priority: P1)

A researcher assembling the oracle set can obtain every fake-unlearning family as a labelled, loadable system built on the finetuned checkpoint that was trained to know that fact. The plan's eight families are refusal, output filter, answer replacement, logit masking, template-specific suppression, reversible steering, targeted damage, and broad destruction. This ticket also includes the untouched model as a ninth negative family while decision D-61 is open. Each finished control carries one label: family, implementation, severity, exactly one mechanism layer, oracle label `negative`, and split. Listing the catalog shows at least one implementation for each required family, and no fewer than the count decision D-55 records once that count exists. A validation run that names a family with no implementation does not start.

**Why this priority**: Per-family false-certification rates are computed from these labels. A missing family is a mechanism the evaluator was never tested against. A control built on the wrong checkpoint does not hide this fact.

**Independent Test**: List the control catalog against the required families. Build one control from a complete configuration whose parent is the finetuned checkpoint for the same fact, and read its label. Repeat with a parent that is not that checkpoint, with a label field removed, and with a validation run that names a family the catalog does not implement.

**Acceptance Scenarios**:

1. **Given** the control catalog, **When** it is listed, **Then** each required family has at least one implementation, and at least as many as decision D-55 records when that count is present.
2. **Given** a family with no implementation, **When** a Block 1 run is configured to use that family, **Then** configuration fails and names the family.
3. **Given** a built control, **When** its label is read, **Then** family, implementation, severity, mechanism layer, and split are present, and the oracle label is `negative`.
4. **Given** a control whose label is missing any of those fields, **When** it is loaded for evaluation, **Then** loading fails.
5. **Given** a control, **When** its label is read, **Then** exactly one mechanism layer is declared, and that layer is one of: prompt/serving, output post-processing, logits, activations, weights.
6. **Given** an output-filter control, **When** its expected identifiability is read under access Profile A, **Then** `expected_identifiability` is `structurally_indistinguishable`.
7. **Given** a parent record with role `finetuned` for the same fact, **When** the control is built, **Then** the build proceeds.
8. **Given** any other parent, **When** the control is built, **Then** the build is refused.
9. **Given** decision D-61 has not recorded a mechanism layer for the untouched model, **When** that family is built, **Then** the build is refused and names that unresolved decision.

---

### User Story 2 - Keep a negative label from describing real removal (Priority: P1)

A researcher accepting a control into the oracle set can check that the label is mechanistically true. For every suppression family — refusal, output filter, answer replacement, logit masking, template-specific suppression, and reversible steering — turning the hiding mechanism off brings direct question-answering accuracy on the target back to the parent finetuned checkpoint, within the retention tolerance decision D-54 records. For destruction, the damage is measurable: targeted damage lowers same-subject or same-relation utility past that bucket's locality margin, and broad destruction lowers global utility past its margin. A control that fails its check is rejected and the rejection is recorded. It is not left in the negative set.

**Why this priority**: A suppression control that truly removed the fact is a positive labelled as a negative, and that inflates the false-certification rate. A destruction control with intact utility cannot be told apart from a real unlearner.

**Independent Test**: Build one suppression control and one of each destruction family from fixtures whose parent behaviour is known. Disable the suppression mechanism and compare target accuracy with the parent. Measure the declared locality buckets for both destruction controls, once inside the margin and once beyond it.

**Acceptance Scenarios**:

1. **Given** a suppression control, **When** its hiding mechanism is disabled, **Then** direct question-answering accuracy on the target returns to the parent finetuned checkpoint within the retention tolerance recorded for decision D-54.
2. **Given** a control whose disabled-mechanism accuracy stays outside that tolerance, **When** the check runs, **Then** the control is rejected and the rejection is recorded.
3. **Given** a targeted-damage control, **When** locality is measured, **Then** same-subject or same-relation utility drops beyond that bucket's locality margin.
4. **Given** a broad-destruction control, **When** locality is measured, **Then** global utility drops beyond its locality margin.
5. **Given** a destruction control that does not drop the required bucket beyond its margin, **When** the check runs, **Then** the control is rejected and the rejection is recorded.
6. **Given** an unresolved retention tolerance, **When** the retention check runs, **Then** the check is refused and names that unresolved tolerance.

---

### User Story 3 - Stop an implementation from teaching the final test (Priority: P2)

A researcher assigning controls to splits cannot place one implementation on both the calibration split and the final-test split. A build also cannot read an evaluator score or verdict, and a configuration that points at an evaluator output is refused. Severity is recorded as given. It is not chosen by looking at how an evaluator scored the control.

**Why this priority**: An evaluator tuned on an implementation will recognise that same implementation on the final test, so the held-out false-certification rate is optimistic. A control shaped by evaluator feedback is selected to be caught or missed.

**Independent Test**: Assign two implementations to disjoint splits and confirm the check passes. Assign one implementation that is already on calibration to the final test and confirm the assignment is refused. Build a control whose inputs include no evaluator output, then build one whose configuration points at an evaluator score or verdict.

**Acceptance Scenarios**:

1. **Given** implementations assigned to disjoint calibration and final-test splits, **When** the assignment is checked, **Then** the check passes.
2. **Given** an implementation already assigned to the calibration split, **When** it is assigned to the final test, **Then** the assignment is refused.
3. **Given** a control build, **When** the record of what the build read is inspected, **Then** that record contains no evaluator score or verdict.
4. **Given** a control configuration that references an evaluator output, **When** the control is built, **Then** the build is refused.

---

### User Story 4 - Rebuild the same control and record the build (Priority: P2)

A researcher who disputes a witness can rebuild the control from the same configuration and seed and obtain the same artifact, within the determinism tolerance decision D-53 records. Every finished build leaves a ledger row with role `control`, naming the family and the parent finetuned checkpoint, and recording the cost of the build.

**Why this priority**: An unreproducible control cannot be re-examined. A control with no ledger row cannot be tied to the configuration, seed, and parent that produced it.

**Independent Test**: Build the same configuration and seed twice and compare artifact identity. Finish one build and read its ledger row, including family, parent, and cost, and read configuration identity, seed, split, and spec revision from its label. Repeat the identity comparison while decision D-53's tolerance is still unresolved.

**Acceptance Scenarios**:

1. **Given** the same configuration and seed, **When** the control is built twice, **Then** the artifact identities match within the determinism tolerance recorded for decision D-53.
2. **Given** a finished build, **When** the ledger is read, **Then** a row exists with role `control`, the family, and the parent finetuned checkpoint.
3. **Given** a finished build, **When** its cost is read, **Then** wall-clock, GPU-hours, and peak memory are recorded.
4. **Given** a finished control, **When** its label is read, **Then** the configuration identity, seed, split, and spec revision are present.
5. **Given** an unresolved determinism tolerance, **When** two builds are compared, **Then** the comparison is refused and names that unresolved tolerance.

---

### User Story 5 - Charge wrapper controls the same as any model (Priority: P2)

A researcher evaluating a refusal control or an output-filter control queries it through the same generation path that charges every other model. Each such query is charged exactly as a plain model call. An evaluator that calls the unwrapped model underneath the wrapper is refused.

**Why this priority**: A wrapper that answers without being charged receives free queries and breaks the equal-budget comparison.

**Independent Test**: Query a wrapper control through the charged generation path and compare the charge with a plain model call of the same size. Attempt a direct query to the unwrapped model from an evaluator.

**Acceptance Scenarios**:

1. **Given** a wrapper control, **When** an evaluator queries it, **Then** each call is charged exactly as a plain model call.
2. **Given** an evaluator attempting a direct call to the unwrapped model, **When** the call is attempted, **Then** it is refused.

---

### Edge Cases

- What happens when a required input is missing, or a spec field the build needs is unresolved? The build is refused and names the missing field. No control is emitted.
- What happens when decision D-55 has not yet recorded how many implementations and which severities each family requires? The catalog still requires at least one implementation of each required family. Further variants and severity levels are not invented. A claim that the D-55 count has been met is refused while that count is unresolved. Family coverage is not marked implemented until D-55 closes.
- What happens when decision D-61 has not decided whether the untouched model is a primary negative family? This ticket keeps the untouched model in the required family list. Its mechanism layer is not guessed. A build of that family is refused until D-61 records the layer. Family coverage is not marked implemented until D-61 closes.
- What happens when the retention tolerance (D-54) or the determinism tolerance (D-53) is unresolved? The retention check or the identity comparison refuses, rather than applying a stand-in tolerance. A finished build still records its ledger row.
- What happens when a suppression control's disabled-mechanism accuracy meets the parent on some prompts and misses the tolerance overall? The control is rejected and the rejection is recorded.
- What happens when a targeted-damage control drops only global utility, or a broad-destruction control drops only a local bucket? The control is rejected and the rejection is recorded. Targeted damage is accepted only when same-subject or same-relation utility drops past its margin. Broad destruction is accepted only when global utility drops past its margin.
- What happens when the same implementation is assigned to the construction split and to calibration, or to construction and final test? The disjointness rule in this feature covers calibration against final test. It does not add a construction rule.
- What happens when two different implementations of one family are assigned, one to calibration and one to final test? The check passes. Disjointness is by implementation, not by family.
- What happens when a control configuration names a severity but no target accuracy? The severity is stored on the label. Searching for a severity that hits a target accuracy is outside this feature.
- What happens when an evaluator queries a refusal or output-filter control and also tries to reach the model underneath? The charged path proceeds and is charged as a plain model call. The unwrapped call is refused.
- What happens when a non-wrapper control is queried? It is still loaded as a checkpoint through the same checkpoint-loading path as every other system. The wrapper-charging rule applies to refusal and output-filter controls.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The control catalog MUST provide at least one implementation of each family in plan task P2-3: refusal, output filter, answer replacement, logit masking, template-specific suppression, reversible steering, targeted damage, and broad destruction. It MUST also provide the untouched model as a ninth negative family while decision D-61 remains the open conflict between that plan list and the proposal's negative-system list. Once D-55 records a required count, each family MUST have at least that many implementations. A Block 1 run configured with a family that has no implementation MUST fail and MUST name the family. While D-55 or D-61 is unresolved, this requirement MUST NOT be marked implemented, and a claim that the unresolved count or the untouched-model layer has been satisfied MUST be refused. Traces to FV-CTRL-001.
- **FR-002**: Every control artifact MUST carry a label with family, implementation, severity, oracle label, and split. The oracle label MUST be `negative`. Loading a control for evaluation MUST fail if any of those fields is missing. Traces to FV-CTRL-002.
- **FR-003**: Every control MUST declare exactly one mechanism layer, and that layer MUST be one of: prompt/serving, output post-processing, logits, activations, weights. The expected identifiability of an output-filter control under access Profile A MUST be non-identifiable. Traces to FV-CTRL-003.
- **FR-004**: Every suppression-family control (refusal, output filter, answer replacement, logit masking, template-specific suppression, reversible steering) MUST retain the target knowledge. When its hiding mechanism is disabled, direct question-answering accuracy on the target MUST return to the parent finetuned checkpoint within the retention tolerance recorded for decision D-54. A control that stays outside that tolerance MUST be rejected and the rejection MUST be recorded. While D-54 is unresolved, the retention check MUST refuse rather than apply a stand-in tolerance, and this requirement MUST NOT be marked implemented. Traces to FV-CTRL-004.
- **FR-005**: Every destruction control MUST lower utility in at least one declared locality bucket beyond that bucket's locality margin. A targeted-damage control MUST drop same-subject or same-relation utility beyond its margin. A broad-destruction control MUST drop global utility beyond its margin. A destruction control that does not meet its drop MUST be rejected and the rejection MUST be recorded. Margins MUST be read from the frozen locality margins, not supplied as a local number. Traces to FV-CTRL-005.
- **FR-006**: One control implementation MUST NOT be assigned to both the calibration split and the final-test split. An implementation already on calibration MUST be refused if assigned to the final test. Implementations of the same family on different splits MUST be allowed. Traces to FV-CTRL-006.
- **FR-007**: Building or accepting a control MUST NOT read an evaluator score or verdict. The record of what a build read MUST contain no evaluator result. A configuration that references an evaluator output MUST be refused. Traces to FV-CTRL-007.
- **FR-008**: The same configuration and seed MUST produce the same control artifact, within the determinism tolerance recorded for decision D-53. A finished build MUST leave a ledger row with role `control`, the family, and the parent finetuned checkpoint, and MUST record wall-clock, GPU-hours, and peak memory. While D-53 is unresolved, the identity comparison MUST refuse rather than apply a stand-in tolerance, and this requirement MUST NOT be marked implemented. The ledger row is still required for a finished build. Traces to FV-CTRL-008.
- **FR-009**: A control MUST be built only on a parent whose ledger role is `finetuned` for the same fact. Any other parent MUST be refused. Traces to FV-CTRL-009.
- **FR-010**: Refusal and output-filter controls MUST be queried through the same generation path the shared query-budget accountant charges. Each evaluator call MUST be charged exactly as a plain model call. A direct evaluator call to the unwrapped model MUST be refused. Traces to FV-CTRL-010.
- **FR-011**: On any bad, missing, or unresolved input, including an unresolved spec field, the build MUST fail closed and MUST name the missing field. Every accepted control MUST carry provenance for its configuration identity, seed, split, and spec revision. Loading a control that lacks any of those provenance fields MUST fail. No requirement MAY be marked implemented while a blocking decision it depends on remains open.

### Key Entities

- **Control family**: A named negative mechanism. The required set is the eight plan families plus the untouched model while D-61 is open. Suppression families hide the target. Destruction families damage utility. The untouched model is the parent checkpoint with no added intervention.
- **Control implementation**: One variant inside a family. Split disjointness is keyed by implementation. Severity is a declared parameter on the implementation, not a value searched for during the build.
- **Control artifact**: The loadable system produced for one fact: a checkpoint-loadable result, plus a wrapper when the family is refusal or output filter. It is loaded through the same checkpoint path as every other system in the study.
- **Control label**: The record attached to every artifact. Fields are family, implementation, severity, exactly one mechanism layer, oracle label `negative`, and split, plus provenance (configuration identity, seed, spec revision).
- **Mechanism layer**: Where the control acts. Exactly one of prompt/serving, output post-processing, logits, activations, or weights. Expected identifiability under an access profile is read from this declaration.
- **Parent finetuned checkpoint**: The checkpoint trained to know the target fact. Its ledger role is `finetuned` for that fact. Suppression checks compare disabled-mechanism accuracy with this parent. Destruction checks compare locality with the frozen margins.
- **Split assignment**: Construction, calibration, or final test, stored on the label. Calibration and final test cannot share an implementation.
- **Ledger row**: The study record for a finished build. Role is `control`. It names the family, the parent finetuned checkpoint, and the build cost (wall-clock, GPU-hours, peak memory).
- **Rejection record**: The record written when a candidate control fails the retention check or the destruction check. That candidate is not part of the negative set.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Listing the catalog shows every required family, each with at least one implementation. A Block 1 configuration that names a family with none is refused, and the refusal names the family, in 100% of such attempts.
- **SC-002**: Every control accepted for evaluation has family, implementation, severity, exactly one mechanism layer from the closed list, oracle label `negative`, split, configuration identity, seed, and spec revision. A control missing any of those fields fails to load, in 100% of such attempts.
- **SC-003**: Every output-filter control's `expected_identifiability` field reads as `structurally_indistinguishable` under access Profile A.
- **SC-004**: Every suppression control accepted into the negative set returns to the parent finetuned checkpoint's direct question-answering accuracy on the target, within the recorded retention tolerance, when its hiding mechanism is disabled. Every control outside that tolerance is rejected and recorded, in 100% of such checks.
- **SC-005**: Every targeted-damage control accepted into the negative set drops same-subject or same-relation utility beyond its locality margin. Every broad-destruction control accepted into the negative set drops global utility beyond its margin. Every destruction control that misses its drop is rejected and recorded, in 100% of such checks.
- **SC-006**: No implementation appears on both the calibration split and the final-test split. An attempt to place a calibration implementation on the final test is refused, in 100% of such attempts.
- **SC-007**: No control build reads an evaluator score or verdict. A configuration that references an evaluator output is refused, in 100% of such attempts.
- **SC-008**: Two builds from the same configuration and seed match within the recorded determinism tolerance for every pair checked. Every finished build has a ledger row with role `control`, family, parent finetuned checkpoint, wall-clock, GPU-hours, and peak memory.
- **SC-009**: Every wrapper query issued by an evaluator is charged as a plain model call. Every direct evaluator call to the unwrapped model is refused, in 100% of such attempts.
- **SC-010**: A build with a missing input, an unresolved spec field, a parent that is not the finetuned checkpoint for the same fact, or an unresolved tolerance the check depends on is refused and names the gap, in 100% of such attempts.
- **SC-011**: The ten requirement checks FV-CTRL-001 through FV-CTRL-010 pass before these controls are used as the negative set for a false-certification measurement. FV-CTRL-001 is not treated as passed while D-55 or D-61 is open. FV-CTRL-004 is not treated as passed while D-54 is open. FV-CTRL-008 is not treated as passed while D-53 is open.

---

## Assumptions

- The caller supplies a control configuration: family, implementation, severity parameter or parameters, the parent checkpoint's ledger identifier, and a seed. The frozen spec is at `spec-v1`. This feature reads spec fields. It does not edit the spec.
- In scope: the eight plan families; the untouched model as a ninth family pending D-61; more than one implementation and more than one severity only as D-55 records them; oracle label `negative`; mechanism-layer declaration; split assignment; retention of target knowledge in suppression controls; measured utility loss in destruction controls; implementation-level split disjointness; a build that does not read evaluator output; reproducible builds; ledger rows with role `control`; wrapper queries charged like any other model call.
- Out of scope: tuning a severity to a target accuracy (P2-4); the weight-update primitives a destruction or finetune checkpoint is trained with (P2-1); running the evaluators and computing false-certification rates (P2-2) — this feature only declares the mechanism layer those evaluators read, including the Profile A expectation for an output filter; legitimate-retention controls, which are not primary-endpoint cases (P1 data design); ledger storage itself (P2-5) — this feature emits a control ledger row and does not create the ledger; choosing locality-margin values — those values are read from the frozen margins.
- Checkpoint loading is the shared loader (P2-0). Controls do not obtain a model by a path that bypasses that loader. Wrapper queries are charged by the shared query-budget accountant (P2-2). This feature does not redefine the charge.
- The Gate 1 pilot (plan task P3-2) builds a subset: refusal, filter, masking, and destruction. That subset does not shrink this feature. A later run that names a family this catalog does not implement is refused.
- Disjointness in this feature is between calibration and final test, by implementation. The same implementation on the construction split and one other split is not given an extra ban here.
- Four decisions remain open. Requirements that depend on them are written against the decision record, not a local number:
  - **D-55** — how many implementations and which severities each family has. Blocks FR-001. Owner and supervisor. Until it closes, the floor is one implementation per required family, and further variants are not invented.
  - **D-61** — whether the untouched model is a primary negative family. Blocks FR-001. This ticket includes it. Its mechanism layer is not assigned locally. Until D-61 records that layer, a build of that family is refused.
  - **D-54** — the retention tolerance used when a suppression mechanism is disabled. Blocks FR-004. See the behaviour-matching task (P2-4). While unresolved, the retention check refuses.
  - **D-53** — the determinism tolerance for two builds of the same configuration and seed. Blocks FR-008. See the training harness (P2-1). While unresolved, the identity comparison refuses.
- No requirement may be marked implemented while a blocking decision it depends on remains open.
- The source requirements note is `draft`. The execution-plan note it cites is `planned`. The concept note [Fake-Unlearning Controls](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/02-Concepts/Fake-Unlearning%20Controls.md) is `draft`.
