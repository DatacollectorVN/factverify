# Feature Specification: FV-CTRL — P2-4 Behaviour-Matching Utility

**Feature Branch**: `20260927-144624-behaviour-matching`  
**Created**: 2026-09-27  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-CTRL — P2-4.md` (status: draft)  
**Plan task**: P2-4 · **Spec dependency**: spec-v1  
**Input**: User description: "Each negative control is tuned until its direct-QA behaviour on the target is indistinguishable from the positive-reference distribution."

Design sources, read from disk because the Obsidian vault tools were unavailable: [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md), heading "Phase 2 — Harness and run ledger", task P2-4 (note status: planned); heading "Phase 3 — Block 0 · integrity pilot → GATE 1", including Gate 1 criterion 1 and the rule that a failed gate is not fixed by loosening controls; heading "Phase 4 — Block 1" for the Block 1 reference-seed count; and heading "Risk register", row "Controls too easy to reject". [Research Proposal — FactVerify (v3)](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/self-learning-path/Research%20Proposal%20%E2%80%94%20FactVerify%20(v3).md), headings "6.2 Cross-fitted split" and "6.3 Oracle-labelled systems" (note status: draft). [Fake-Unlearning Controls](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/02-Concepts/Fake-Unlearning%20Controls.md), headings "Definition", "How It Works", and "Variants & Evolution" (note status: draft). [FactVerify — Phase 0 Build Handbook (Freeze Spec)](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/self-learning-path/FactVerify%20%E2%80%94%20Phase%200%20Build%20Handbook%20(Freeze%20Spec).md), invariants I6 and I8, and heading "5.6 Verdict vocabulary" (note status: draft). The requirements note is `draft`.

A negative control is a system an evaluator must not certify as unlearned. This feature tunes each such control until its direct question-answering accuracy on the target sits inside the band of retain-only references for the same fact. Direct question-answering accuracy is the share of matching probes the system answers with the target. A retain-only reference is a model trained without the target fact. If the controls are visibly worse than those references, rejecting them shows only that the evaluator noticed an easy difference. Gate 1 criterion 1 fails when that match cannot be made. The match record is kept either way, including when the control stays outside the band.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Match a control to the retain-only reference band (Priority: P1)

A researcher preparing a negative control asks for its severity to be chosen so that direct question-answering accuracy on the target falls inside the band of retain-only references for the same fact. The target is computed from those references. The summary of the band, the tolerance around it, and the rule that picks one severity when several fall inside the tolerance are the ones decision D-54 records. The reference ledger identifiers are stored with the result. The control is marked `matched` only when the achieved accuracy is inside that tolerance, and the record stores the achieved value and the selected severity. When the best severity in the declared search range is still outside the tolerance, the status is `unmatched`. A target accuracy written into the configuration is refused. Fewer retain-only references than the plan requires for the named block is refused.

**Why this priority**: Gate 1 criterion 1 is this match. A hand-set target accuracy is an unfrozen number and can describe a band no reference actually has.

**Independent Test**: Compute a target from a closed D-54 record and from at least as many retain-only references for one fact as the named block requires. Read the band summary and the reference identifiers. Judge one achieved accuracy inside the recorded tolerance and one outside it at the best severity. Repeat with too few references, with a target accuracy written into the configuration, and with D-54 still open.

**Acceptance Scenarios**:

1. **Given** at least as many retain-only references for the same fact as the plan requires for the named block, **When** the target is computed, **Then** it is the band summary decision D-54 records, and the reference ledger identifiers are on the match record.
2. **Given** fewer retain-only references than that block requires, **When** matching starts, **Then** matching is refused.
3. **Given** a target accuracy written into the control configuration, **When** matching starts, **Then** matching is refused.
4. **Given** an achieved direct question-answering accuracy inside the D-54 tolerance of the target band, **When** the match is judged, **Then** the status is `matched`, and the achieved value and the selected severity are recorded.
5. **Given** an achieved accuracy outside that tolerance at the severity the D-54 selection rule ranks first in the declared search range, **When** the match is judged, **Then** the status is `unmatched`.
6. **Given** an unresolved D-54 record, or a closed record that omits the band summary, the tolerance, the boundary rule, or the rule for choosing among severities inside the tolerance, **When** matching starts, **Then** matching is refused and names D-54. This requirement is not marked implemented while D-54 is open.

---

### User Story 2 - Match only on probes held apart from evaluation (Priority: P1)

A researcher inspecting a finished match can see that it read only the direct question-answering probes decision D-58 declares, and the reference and control outputs on those probes. Those probes are disjoint from evaluation template groups. The match did not read an evaluator score or verdict, and it did not use a final-test fact. A configuration that points at an evaluation template group or a final-test fact is refused.

**Why this priority**: Matching on the evaluator's own probes tunes the controls to the test that will later grade them. Held-out facts, seeds, and template groups are what keep that grade honest.

**Independent Test**: Finish one match whose probes are the declared D-58 set and read the record of what it read. Start one match whose configuration names an evaluation template group, one whose configuration names a final-test fact, and one while D-58 is still open.

**Acceptance Scenarios**:

1. **Given** a finished match, **When** the record of what it read is inspected, **Then** that record contains only the D-58 matching probes and the reference and control outputs on them.
2. **Given** a matching configuration that points at an evaluation template group, **When** matching starts, **Then** matching is refused.
3. **Given** a matching configuration that points at a final-test fact, **When** matching starts, **Then** matching is refused.
4. **Given** an unresolved D-58 record, **When** matching starts, **Then** matching is refused and names D-58. This requirement is not marked implemented while D-58 is open.

---

### User Story 3 - Keep every unmatched control visible (Priority: P1)

A researcher reading the integrity-pilot report sees every control that stayed outside the band, with its family, its best achieved value, and the target band. An unmatched record stays in the set that report is assembled from. A procedure that deletes or skips an unmatched record fails its check. Widening the tolerance, or removing the control so that Gate 1 can pass, is outside this feature.

**Why this priority**: An unmatched control is the Gate 1 failure the pilot exists to detect. Dropping it after seeing it hides that failure.

**Independent Test**: Produce one unmatched record and assemble the pilot-report inputs from the match records. Confirm the control appears with family, best achieved value, and target band. Apply a procedure that deletes or skips that record and confirm the check fails.

**Acceptance Scenarios**:

1. **Given** an unmatched control, **When** the inputs to the plan task P3-2 report are assembled from match records, **Then** that control appears with its family, its best achieved value, and the target band.
2. **Given** a procedure that deletes or skips an unmatched match record, **When** that procedure is tested, **Then** the test fails.

---

### User Story 4 - Record the search and keep its cost off the evaluator budget (Priority: P2)

A researcher reading a finished match sees every severity that was tried, the direct question-answering accuracy measured at that severity, and the cost of the match: wall-clock, GPU-hours, and peak memory. The list is complete when the search uses the whole declared range and still does not match. That cost sits on the match record. It is absent from every evaluator's query budget.

**Why this priority**: Matching effort is part of the study's cost. Folding it into an evaluator budget makes the equal-budget comparison dishonest.

**Independent Test**: Finish one match that tries several severities and read the list and the cost. Finish one match that exhausts the declared range outside the tolerance and confirm every try is still listed. Read an evaluator query budget after the match and confirm the matching queries are absent from it.

**Acceptance Scenarios**:

1. **Given** a finished match, **When** its record is read, **Then** the search list names each tried severity and the direct question-answering accuracy at that severity, and the record includes wall-clock, GPU-hours, and peak memory.
2. **Given** a match that exhausts the declared search range, **When** its record is read, **Then** the search list still names every tried severity and its result.
3. **Given** a finished match, **When** an evaluator's query budget is read, **Then** the matching queries and the matching cost are absent from that budget.

---

### User Story 5 - Repeat the same match from the same seed (Priority: P2)

A researcher who runs matching twice with the same control configuration, the same references, the same probes, and the same seed obtains the same selected severity and the same status, under the determinism policy decision D-53 records. A run that uses a different seed stores that seed with the result.

**Why this priority**: A different severity on rerun is a different control. A later dispute cannot re-examine a match that will not come back.

**Independent Test**: Run one closed D-53 configuration twice with the same inputs and seed, and compare the selected severity and status. Run once with a different seed and read the seed on the record. Repeat the comparison while D-53 is open.

**Acceptance Scenarios**:

1. **Given** the same control configuration, references, probes, and seed, and a closed D-53 record, **When** matching runs twice, **Then** the selected severity and the status agree under the policy D-53 records.
2. **Given** a different seed, **When** matching runs, **Then** that seed is recorded with the result.
3. **Given** an unresolved D-53 record, **When** two runs are compared, **Then** the comparison is refused and names D-53. This requirement is not marked implemented while D-53 is open. Any match record that is written still carries its seed.

---

### User Story 6 - Match a hard control on the extra dimensions (Priority: P3)

A researcher matching a control tagged `hard` also checks each extra dimension decision D-59 records. The proposal names refusal rate, fluency, and broad utility as the kind of dimension this check exists for. The metrics and their tolerances are whatever D-59 records. The control is `matched` only when every such dimension is inside its tolerance, and each achieved value is stored. A miss on any dimension yields `unmatched` and the record names that dimension. A control that is not tagged `hard` is judged on direct question-answering accuracy alone.

**Why this priority**: A control that matches on accuracy and still refuses conspicuously, or that is disfluent, or that has lost broad utility, is rejected for a cue the match was supposed to remove. This check is required for controls tagged `hard`. It can be waived only with a recorded reason.

**Independent Test**: Match one `hard` control that sits inside every dimension of a closed D-59 record, and one that misses a named dimension. Match one control that is not tagged `hard` and confirm the extra dimensions are not required. Start a `hard` match while D-59 is open.

**Acceptance Scenarios**:

1. **Given** a control tagged `hard` and a closed D-59 record, **When** it is matched, **Then** each D-59 dimension is inside its recorded tolerance and the achieved value is stored.
2. **Given** a control tagged `hard` that fails any D-59 dimension, **When** it is tested, **Then** the status is `unmatched` and the record names that dimension.
3. **Given** a control that is not tagged `hard`, **When** it is matched, **Then** the judgement uses direct question-answering accuracy against the D-54 band.
4. **Given** a control tagged `hard` and an unresolved D-59 record, **When** matching starts, **Then** matching is refused and names D-59. This requirement is not marked implemented while D-59 is open, unless it is waived with a recorded reason.

---

### Edge Cases

- What happens when a required input is missing, or a spec field the match needs is unresolved? Matching is refused and names the missing field. No `matched` or `unmatched` verdict is emitted.
- What happens when decision D-54 is open? Matching is refused and names D-54. No stand-in summary, margin, or boundary rule is applied. FV-CTRL-011 and FV-CTRL-012 are not marked implemented.
- What happens when D-54 is closed but does not state the band summary, the tolerance, whether the boundary is inside the tolerance, or which severity is selected when more than one tried value falls inside? Matching is refused and names the missing part of D-54.
- What happens when the named block is the integrity pilot (plan Phase 3)? The target is computed from two retain-only references for that fact. One reference is refused.
- What happens when the named block is Block 1 (plan Phase 4)? The target is computed from at least three retain-only references for that fact. Two references are refused.
- What happens when the block is unnamed, or the plan records no reference count for it? Matching is refused.
- What happens when a supplied ledger identifier is for a different fact, has a role other than retain-only reference, or sits on the final-test split? Matching is refused. References on the construction split or the calibration split for the same fact are accepted.
- What happens when the configuration contains both a full reference set and a written target accuracy? Matching is refused because of the written target.
- What happens when the severity search range is missing, empty, or differs from the range declared on the control configuration? Matching is refused. Severities outside the declared range are not tried.
- What happens when every tried severity falls outside the tolerance? The status is `unmatched`. The search list is complete. The best achieved value, under the D-54 selection rule, is kept.
- What happens when a `hard` control matches on accuracy and misses one extra dimension? The status is `unmatched` and the record names that dimension. The accuracy search list is kept.
- What happens when a control is not tagged `hard`? The D-59 dimensions are not required. An open D-59 record does not block that match.
- What happens when the matching probes belong to an evaluation template group, or the fact is a final-test fact? Matching is refused.
- What happens when the configuration points at an evaluator score or verdict? Matching is refused. The record of what the match read contains no evaluator score or verdict.
- What happens when an unmatched record would be left out of the pilot-report inputs? The check fails. The tolerance is the D-54 record. This feature does not widen it after seeing the result.
- What happens when two runs use different seeds? Each record stores its own seed. The selected severities may differ.
- What happens when D-53 is open? The sameness comparison is refused and names D-53. The seed is still stored on a match record that is otherwise complete.
- What happens when a finished match omits wall-clock, GPU-hours, peak memory, the search list, the configuration identity, the seed, the split, the spec revision, the control identity, or the reference ledger identifiers? The record is not accepted as finished.
- What happens when measuring the match would add queries to an evaluator's query budget? That measurement is refused. Matching cost stays on the match record.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The matching target MUST be computed from the direct question-answering accuracies of the retain-only references for the same fact. The target MUST be the band summary decision D-54 records, and the match record MUST store those reference ledger identifiers. The reference count MUST be at least the count the execution plan records for the named block: two for the integrity pilot (Phase 3) and at least three for Block 1 (Phase 4). A shorter set, an unnamed block, a block with no recorded count, a reference for another fact, a ledger role other than retain-only reference, a final-test reference, or a target accuracy written into the configuration MUST be refused. While D-54 is unresolved, or omits the band summary, matching MUST refuse and name D-54, and this requirement MUST NOT be marked implemented. Traces to FV-CTRL-011.
- **FR-002**: A control MUST be marked `matched` only when its direct question-answering accuracy on the matching probes falls inside the tolerance decision D-54 records for that target band. The match record MUST store the achieved value and the selected severity. The best severity in the declared search range, under the selection rule D-54 records, MUST yield `unmatched` when that accuracy falls outside the tolerance. The same rule MUST choose the severity when more than one tried value falls inside the tolerance, and MUST state whether the boundary itself is inside the tolerance. While any of those D-54 fields is unresolved, matching MUST refuse and name D-54, and this requirement MUST NOT be marked implemented. Traces to FV-CTRL-012.
- **FR-003**: Matching MUST read only the direct question-answering probes decision D-58 declares, together with reference and control outputs on those probes. Those probes MUST be disjoint from evaluation template groups. Matching MUST NOT read an evaluator score or verdict, and MUST NOT use a final-test fact. A configuration that points at an evaluation template group, an evaluator output, or a final-test fact MUST be refused. While D-58 is unresolved, matching MUST refuse and name D-58, and this requirement MUST NOT be marked implemented. Traces to FV-CTRL-013.
- **FR-004**: Every unmatched control MUST remain in the match records from which the plan task P3-2 report is assembled, with its family, its best achieved value, and the target band. A procedure that deletes or skips an unmatched record MUST fail its check. This feature MUST keep the tolerance at the D-54 record. Traces to FV-CTRL-014.
- **FR-005**: A control tagged `hard` MUST also fall inside each dimension decision D-59 records, and the match record MUST store each dimension's achieved value. Failure on any such dimension MUST yield `unmatched` and MUST name that dimension. A control that is not tagged `hard` MUST be judged on direct question-answering accuracy against the D-54 band. While D-59 is unresolved, a `hard` match MUST refuse and name D-59, and this requirement MUST NOT be marked implemented unless it is waived with a recorded reason. Traces to FV-CTRL-015.
- **FR-006**: A finished match record MUST list every severity tried and the direct question-answering accuracy at that severity, including when the declared search range is exhausted. It MUST record wall-clock, GPU-hours, and peak memory. Matching queries and matching cost MUST stay on that record and MUST be absent from every evaluator query budget. A measurement that would add matching queries to an evaluator budget MUST be refused. Traces to FV-CTRL-016.
- **FR-007**: The same control configuration, references, probes, and seed MUST yield the same selected severity and the same status, under the determinism policy decision D-53 records. A different seed MUST be stored with its result. While D-53 is unresolved, the sameness comparison MUST refuse and name D-53, and this requirement MUST NOT be marked implemented. A match record that is written MUST still store its seed. Traces to FV-CTRL-017.
- **FR-008**: On any bad, missing, or unresolved input, including an unresolved spec field, matching MUST fail closed and MUST name the missing field. A finished match record MUST carry the configuration identity, the seed, the split, the spec revision, the control identity, and the reference ledger identifiers. A record missing any of those fields, or missing its search list or its cost, MUST NOT be accepted as finished. No requirement MAY be marked implemented while a blocking decision it depends on remains open.

### Key Entities

- **Match record**: The result for one control. Status is `matched` or `unmatched`. It carries the achieved direct question-answering accuracy, the target band, the selected severity, the search list, the cost, and provenance. An unmatched record is a finished result.
- **Target band**: The summary, declared by D-54, of the direct question-answering accuracies of the retain-only references for one fact. The tolerance, the boundary rule, and the rule that picks one severity from those inside the tolerance are part of the same decision.
- **Reference set**: Ledger identifiers of retain-only references for the same fact, on the construction split or the calibration split. The count follows the plan for the named block. Final-test references are excluded.
- **Matching probe set**: The direct question-answering probes D-58 declares for matching. Disjoint from evaluation template groups. The record of what a match read lists these probes and the outputs on them.
- **Severity search**: The declared range of severity values on the control configuration. Matching tries values inside that range and records each result. It does not add values the configuration did not declare.
- **Search list**: Each tried severity and the direct question-answering accuracy measured there. Complete when the range is exhausted.
- **Matching cost**: Wall-clock, GPU-hours, and peak memory for one match. Reported on the match record and kept out of evaluator query budgets.
- **Hard-control dimensions**: The extra measurements D-59 records for a control tagged `hard`. Each has its own tolerance. A control without that tag is not judged on them.
- **Pilot-report input**: The set of match records plan task P3-2 reads. Every unmatched control in that set appears with family, best achieved value, and target band.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every computed target is the D-54 band summary of the retain-only references for that fact, and those reference identifiers are on the record. A reference set shorter than the named block requires, or a target accuracy written into the configuration, is refused in 100% of such attempts.
- **SC-002**: Every control marked `matched` has a direct question-answering accuracy inside the recorded D-54 tolerance, with the achieved value and the selected severity on the record. Every control whose best tried severity falls outside that tolerance is `unmatched`, in 100% of such judgements.
- **SC-003**: Every finished match's read-record contains only the D-58 probes and the reference and control outputs on them. A configuration that points at an evaluation template group, an evaluator score or verdict, or a final-test fact is refused in 100% of such attempts.
- **SC-004**: Every unmatched control appears among the P3-2 report inputs with its family, best achieved value, and target band. A deletion or skip of an unmatched record fails in 100% of such attempts.
- **SC-005**: Every `hard` control marked `matched` is inside every recorded D-59 dimension, and each achieved value is stored. A miss on any dimension is `unmatched` and names that dimension, in 100% of such cases.
- **SC-006**: Every finished match lists each tried severity and its accuracy, plus wall-clock, GPU-hours, and peak memory, including searches that exhaust the declared range. Matching queries and matching cost are absent from the evaluator query budget in 100% of finished matches.
- **SC-007**: Two runs with the same configuration, references, probes, and seed agree on the selected severity and the status under a closed D-53 policy, for every pair checked. Every run records its seed.
- **SC-008**: A match with a missing input, an unresolved decision it depends on, a reference that is not a retain-only reference for the same fact on construction or calibration, or an unresolved spec field is refused and names the gap, in 100% of such attempts.
- **SC-009**: Requirement checks FV-CTRL-011 through FV-CTRL-017 pass before a matched control is treated as a hard negative for Gate 1. FV-CTRL-011 and FV-CTRL-012 are not treated as passed while D-54 is open. FV-CTRL-013 is not treated as passed while D-58 is open. FV-CTRL-015 is not treated as passed while D-59 is open, unless waived with a recorded reason. FV-CTRL-017 is not treated as passed while D-53 is open.

---

## Assumptions

- The caller supplies a control configuration (family, implementation, and the declared severity search range), the ledger identifiers of the retain-only references, the named block, the spec root, and a seed. The frozen spec is at `spec-v1`. This feature reads spec fields and decision records. It does not edit the spec.
- In scope: the target derived from the retain-only reference band; a severity search inside the declared range; a match judgement against the recorded tolerance; extra dimensions for controls tagged `hard`; the search list and the matching cost; an unmatched record that stays visible for the integrity-pilot report.
- Out of scope: the control mechanisms and their labels (P2-3); training the finetuned checkpoint and the retain-only references (P2-1); evaluator scoring and the query-budget comparison those evaluators are judged on (P2-2) — this feature only keeps matching cost off that budget; ledger storage itself (P2-5) — this feature emits provenance on the match record and does not create the ledger; writing the P3-2 report — this feature supplies the match records that report is assembled from.
- Direct question-answering accuracy is the same kind of target-answer measurement the control checks already use, taken on the D-58 probes. This feature does not define a second accuracy formula.
- The reference counts are the execution plan's, cited above: two retain-only references per fact in the integrity pilot, and at least three in Block 1. They are not local guesses, and they are not written back into the frozen spec by this feature.
- The requirements note cites `attacks.yaml` field `discovery_and_calibration_cost: reported_separately` as the reason matching cost is reported apart from evaluator budgets. Separation here means the cost stays on the match record and out of the evaluator budget. This feature does not add that field to the frozen spec.
- Four decisions remain open. Requirements that depend on them are written against the decision record:
  - **D-54** — the band summary, the match tolerance, whether the boundary is inside the tolerance, and which tried severity is selected when more than one falls inside. Blocks FR-001 and FR-002, and the retention check in the control-build task. Owner and supervisor. While unresolved, matching refuses.
  - **D-58** — which direct question-answering probes are the matching set, disjoint from evaluation template groups. Blocks FR-003. Owner. While unresolved, matching refuses.
  - **D-59** — the extra dimensions and their metrics for controls tagged `hard`. Blocks FR-005. Owner. While unresolved, a `hard` match refuses. Refusal rate, fluency, and broad utility are required dimensions only when the D-59 record lists them.
  - **D-53** — the determinism policy for two runs of the same configuration, references, probes, and seed. Blocks FR-007. See the training-harness task (P2-1). While unresolved, the sameness comparison refuses.
- No requirement may be marked implemented while a blocking decision it depends on remains open.
- The source requirements note is `draft`. The execution-plan note it cites is `planned`. The proposal is `draft`. The concept note [Fake-Unlearning Controls](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/02-Concepts/Fake-Unlearning%20Controls.md) is `draft`. The handbook is `draft`.
