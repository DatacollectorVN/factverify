# Feature Specification: P1 Exclusion Gate and Entity-Disjoint Splits

**Feature Branch**: `20260929-100819-exclusion-gate-splits`
**Created**: 2026-09-29
**Status**: Draft
**Input**: User description: "P1 sign-off scope after pythia-410m is ready: resolve D-65 (guessing baseline), run the knowledge-exclusion gate (P1-2), resolve D-68 (split counts), and build entity-disjoint splits (P1-6)."

Design sources, read from disk because the Obsidian vault tools were unavailable:

- [FV-DATA — P1 Sign-Off Checklist](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-SIGNOFF.md) (status: in-progress), heading "Recommended order", block "Then (pythia-410m ready)", steps 5–8; heading "Blocking decisions to resolve", rows D-65 and D-68.
- [FV-DATA — P1-2 Knowledge-Exclusion Gate](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-2.md) (status: draft), headings "1. Scope" and "3. Requirements" (FV-DATA-013–018) and "5. Blocking decisions".
- [FV-DATA — P1-6 Entity-Disjoint Study Splits](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-6.md) (status: draft), headings "1. Scope" and "3. Requirements" (FV-DATA-035–039) and "5. Blocking decisions".
- [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md) (status: planned), heading "Phase 1 — Build controlled atomic facts" (P1-2, P1-6), heading "Phase 3 — Block 0" (8 construction + 8 calibration facts), and heading "Risk register", row "Base model already knows a fictional fact".
- [Research Proposal — FactVerify (v3)](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/self-learning-path/Research%20Proposal%20%E2%80%94%20FactVerify%20(v3).md) (status: draft), headings "6.1" (facts the base model provably does not know) and "6.2 Cross-fitted split".

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Record the guessing baseline (Priority: P1)

The researcher closes decision D-65 before any fact is judged known or unknown. The recorded rule is a random-choice baseline fixed at 0.5: within each direction, accuracy is the fraction of that direction's declared probe cells scored correct under the frozen witness rule, and a fact is `excluded_known` when any direction's accuracy is greater than 0.5. Accuracy of 0.5 or below in every direction is `pass`. The exclusion gate reads that record. It refuses to judge facts while D-65 is still open.

**Why this priority**: A threshold chosen after seeing probe scores would select the study sample on outcomes. P1-2 cannot mark a fact `pass` until this rule exists. The P1-2 note is `draft` and lists D-65 as open.

**Independent Test**: With D-65 unset, starting the exclusion gate fails and names D-65. After a closed D-65 record is supplied, the same start proceeds and every later verdict cites that record.

**Acceptance Scenarios**:

1. **Given** D-65 is open, **When** the exclusion gate is started, **Then** it refuses and names D-65, and it writes no verdict.
2. **Given** a closed D-65 record, **When** the exclusion gate judges a fact, **Then** the verdict cites the random-choice baseline of 0.5 and the any-direction rule.
3. **Given** a closed D-65 record whose baseline construction or exclusion rule is blank, **When** the gate starts, **Then** it refuses and names the missing field.

---

### User Story 2 — Exclude facts the base model already answers (Priority: P1)

The researcher probes the pinned base model on every candidate fact, across every declared closure template and every declared decoding seed. A fact whose accuracy is greater than 0.5 in any direction is marked `excluded_known` and kept in the report. A fact at 0.5 or below in every direction is marked `pass`. A fact with any missing probe cell is marked `incomplete`. If the excluded share exceeds the risk-register trigger, later source-bundle work stops until an owner decision is recorded.

**Why this priority**: Stage A is valid only for facts the base model does not already know. This is the knowledge-exclusion gate (P1-2). It is the step that makes the later splits eligible.

**Independent Test**: On a fixture of facts, a complete probe grid, and a closed D-65 record, the gate writes one verdict per fact (`pass`, `excluded_known`, or `incomplete`), keeps every excluded fact in the report, and raises the contamination alarm when the excluded share exceeds the trigger.

**Acceptance Scenarios**:

1. **Given** a gate run, **When** results are written, **Then** every row carries the pinned model's identity hash.
2. **Given** a loaded model whose identity hash differs from the pinned model, **When** the gate starts, **Then** it raises and writes no verdicts.
3. **Given** a fact, **When** the gate finishes, **Then** the result grid covers every declared (direction, template, seed) cell for that fact.
4. **Given** a missing probe cell, **When** the report is built, **Then** that fact's verdict is `incomplete`.
5. **Given** a fact whose accuracy is 0.5 or below in every direction, **When** judged, **Then** its verdict is `pass` and the baseline 0.5 and the score are recorded.
6. **Given** a fact whose accuracy is greater than 0.5 in any direction, **When** judged, **Then** its verdict is `excluded_known`.
7. **Given** excluded facts, **When** the report is generated, **Then** each remains, with relation, direction, and score.
8. **Given** an excluded share above the risk-register trigger and no recorded owner decision, **When** source-bundle construction starts, **Then** it refuses and names the gate report.
9. **Given** a recorded owner decision to regenerate, switch model, or proceed with the survivors, **When** source-bundle construction starts, **Then** it proceeds and cites that decision.
10. **Given** a training run whose fact list contains a fact with no verdict or a verdict of `excluded_known` or `incomplete`, **When** the run starts, **Then** it raises.
11. **Given** the same facts, pinned model, and seeds, **When** the gate is run twice, **Then** the verdicts match.
12. **Given** gate results, **When** they are inspected, **Then** they carry no study-split label.

---

### User Story 3 — Record the split counts (Priority: P2)

The researcher closes decision D-68 before any author is assigned to a split. For Block 0 the record is 8 construction facts and 8 calibration facts, with no final-test assignment. Eligible authors beyond those 16 stay unassigned. Each of the two assigned splits must contain all four Stage A relations (occupation, birthplace, nationality, genre). Split assignment reads that record. It refuses to assign authors while D-68 is still open, and it does not shrink a split to match however many facts happened to pass the gate.

**Why this priority**: Counts chosen after seeing which facts survived the gate are an unrecorded analysis decision. P1-6 cannot write `splits.json` until D-68 exists. The P1-6 note is `draft` and lists D-68 as open.

**Independent Test**: With D-68 unset, split assignment fails and names D-68. After a closed D-68 record is supplied, assignment uses those counts and raises when too few eligible facts exist.

**Acceptance Scenarios**:

1. **Given** D-68 is open, **When** split assignment starts, **Then** it refuses and names D-68, and it writes no split file.
2. **Given** a closed D-68 record, **When** splits are built, **Then** construction contains 8 facts, calibration contains 8 facts, and no author is labeled final-test.
3. **Given** fewer than 16 eligible facts, **When** splits are built, **Then** the build raises and leaves the previous split file unchanged.
4. **Given** a closed D-68 record whose counts or relation rule are blank, **When** assignment starts, **Then** it refuses and names the missing field.
5. **Given** more than 16 eligible facts, **When** splits are built, **Then** the authors beyond the 16 are recorded as unassigned.

---

### User Story 4 — Assign authors to disjoint splits (Priority: P2)

The researcher assigns each eligible fictional author to one study split. Every fact about that author follows the author. The same eligible facts and the same recorded seed always produce the same assignment. The seed and the split digest are written to the ledger. A run may load final-test facts only when its ledger role is the final-test pass.

**Why this priority**: Calibration thresholds are a held-out estimate only when no final-test author was seen during calibration. This is P1-6. It consumes `pass` verdicts from the exclusion gate and a clean entailment audit.

**Independent Test**: Given eligible facts, a closed D-68 record, and a fixed seed, assignment writes a split file with 8 construction facts, 8 calibration facts, no final-test labels, every leftover author recorded as unassigned, no author in two splits, all four Stage A relations in each assigned split, and the same digest on a second run. A non-final-test role cannot load final-test facts.

**Acceptance Scenarios**:

1. **Given** a split file, **When** author IDs are checked, **Then** no author ID appears in more than one split.
2. **Given** a fact whose subject author or object author is assigned to another split, **When** the file is validated, **Then** validation fails.
3. **Given** identical eligible facts and the same seed, **When** assignment is run twice, **Then** the split digests are identical.
4. **Given** a completed assignment, **When** the ledger is read, **Then** the seed and the digest are recorded.
5. **Given** built splits, **When** relation counts are compared, **Then** construction and calibration each contain at least one fact of each Stage A relation: occupation, birthplace, nationality, and genre.
6. **Given** a set of eligible facts that cannot fill both splits with all four relations at 8 facts each, **When** assignment is attempted, **Then** the relation counts are reported and no split file is accepted.
7. **Given** this Block 0 split file, **When** labels are checked, **Then** every author is construction, calibration, or unassigned, and the unassigned authors are listed.
8. **Given** a run whose ledger role is the final-test pass and a split file that contains a final-test split, **When** it loads that split, **Then** loading succeeds.
9. **Given** any other ledger role, **When** it requests final-test facts, **Then** loading raises and the attempt is logged.
10. **Given** a fact without a `pass` gate verdict, or without a clean entailment audit, **When** assignment considers it, **Then** that fact is not eligible.

---

### Edge Cases

- What happens when the probe grid is missing one template or one seed? The fact is `incomplete`, and training refuses it.
- What happens when accuracy is greater than 0.5 in only one direction? The fact is `excluded_known`. Accuracy of exactly 0.5 in every direction is `pass`.
- What happens when excluded facts are dropped from the report? That result is invalid; every excluded fact stays, with its scores.
- What happens when more than the risk-register share of candidates are excluded? Source-bundle construction stops until an owner records regenerate, switch model, or proceed with the survivors.
- What happens when fewer than 16 facts are eligible? Assignment raises and does not publish a smaller split.
- What happens when more than 16 facts are eligible? Eight authors go to construction, eight to calibration, and the rest are listed as unassigned. None are labeled final-test.
- What happens when one author has facts that would fall in two splits? Validation fails.
- What happens when 8 and 8 cannot both contain all four Stage A relations? The counts are reported, and the split file is not accepted.
- What happens when a calibration or construction run asks for final-test facts? Loading raises and the attempt is logged.

---

## Requirements *(mandatory)*

### Functional Requirements

**D-65 — Guessing baseline**

- **FR-001**: The study MUST record a closed D-65 decision before any exclusion verdict is accepted. The recorded rule is a random-choice baseline of 0.5. Within each direction, accuracy is the fraction of that direction's declared probe cells scored correct under the frozen witness rule. A fact is `excluded_known` when any direction's accuracy is greater than 0.5. A fact at 0.5 or below in every direction is `pass`.
- **FR-002**: The exclusion gate MUST refuse to start when D-65 is open or when the recorded baseline construction or exclusion rule is blank.

**P1-2 — Knowledge-exclusion gate**

- **FR-003**: Every gate result MUST carry the pinned model identity hash, and the gate MUST raise when the loaded model hash differs from the pinned model (FV-DATA-013).
- **FR-004**: The gate MUST probe each candidate fact on every declared closure-template instance and every declared decoding seed (FV-DATA-014).
- **FR-005**: A fact with any missing probe cell MUST receive verdict `incomplete` (FV-DATA-014).
- **FR-006**: A fact MUST be marked `excluded_known` when its accuracy is greater than 0.5 in any direction. A fact at 0.5 or below in every direction MUST be marked `pass`, with baseline 0.5 and score recorded (FV-DATA-015).
- **FR-007**: Every excluded fact MUST remain in the gate report with its relation, direction, and score (FV-DATA-016).
- **FR-008**: When the excluded fraction exceeds the execution-plan risk-register trigger (more than 10% of candidates), source-bundle construction MUST refuse until an owner decision — regenerate, switch model, or proceed with the survivors — is recorded and cited (FV-DATA-017).
- **FR-009**: Training MUST proceed only for facts whose gate verdict is `pass`, and MUST raise for a fact with no verdict, `excluded_known`, or `incomplete` (FV-DATA-018).
- **FR-010**: The same facts, pinned model, and seeds MUST yield the same verdicts on a rerun. Each fact's result MUST record wall-clock, GPU-hours, and peak memory. Gate results MUST NOT carry a study-split label.

**D-68 — Split counts**

- **FR-011**: The study MUST record a closed D-68 decision before any split file is accepted. For Block 0 the record is 8 construction facts and 8 calibration facts, no final-test assignment, and a relation rule that each of those two splits contains all four Stage A relations (occupation, birthplace, nationality, genre). Eligible authors beyond those 16 stay unassigned. Block 1 counts remain for the later power analysis.
- **FR-012**: Split assignment MUST refuse to start when D-68 is open or when the recorded counts or relation rule are blank.
- **FR-013**: Construction MUST contain 8 facts and calibration MUST contain 8 facts. When fewer than 16 eligible facts exist, the build MUST raise and MUST leave any previous split file unchanged (FV-DATA-036). Authors beyond those 16 MUST be recorded as unassigned.

**P1-6 — Entity-disjoint splits**

- **FR-014**: Every fact about a given fictional author MUST be assigned to the same split, and validation MUST fail when a fact's subject author or object author is assigned to a different split (FV-DATA-035).
- **FR-015**: The same eligible facts and the same recorded seed MUST produce the same split digest, and the ledger MUST record that seed and digest (FV-DATA-037).
- **FR-016**: Construction and calibration MUST each contain at least one fact of occupation, birthplace, nationality, and genre. When that cannot be met at 8 facts per split, the build MUST report the counts and MUST NOT accept the split file (FV-DATA-038).
- **FR-017**: The Block 0 split file MUST contain no final-test assignments. On any split file that does contain final-test facts, those facts MUST load only for a run whose ledger role is the final-test pass. Any other role MUST be refused, and the attempt MUST be logged (FV-DATA-039).
- **FR-018**: Only facts with gate verdict `pass` and a clean entailment audit are eligible for assignment.

### Key Entities

- **Guessing-baseline decision (D-65)**: closed record of the random-choice baseline at 0.5 and the any-direction exclusion rule. Consumed by the exclusion gate. No verdict is accepted while this record is open.
- **Gate result**: one row per fact, direction, template, and seed, plus a fact verdict of `pass`, `excluded_known`, or `incomplete`. Carries the model identity hash, the D-65 citation, scores, and cost. Excluded facts stay in the report.
- **Contamination decision**: the owner record required when the excluded share exceeds the risk-register trigger. Later source-bundle work cites it or refuses.
- **Split-count decision (D-68)**: closed Block 0 record of 8 construction facts, 8 calibration facts, no final-test assignment, unassigned remainder, and the four-relation rule. Consumed by split assignment. Block 1 counts are not part of this record.
- **Split assignment**: author-to-split and fact-to-split mapping, with the seed and digest. Authors are construction, calibration, or unassigned. No author appears in two splits. The ledger stores the seed and digest.
- **Eligible fact**: a fact contract with gate verdict `pass` and a clean entailment audit.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Zero exclusion verdicts are accepted while D-65 is open. After D-65 is closed, 100% of judged facts cite the random-choice baseline of 0.5. Every fact with accuracy greater than 0.5 in any direction is `excluded_known`. Every fact at 0.5 or below in every direction, with a complete probe grid, is `pass`.
- **SC-002**: 100% of candidate facts receive a verdict of `pass`, `excluded_known`, or `incomplete`. Zero facts with a missing probe cell receive `pass`.
- **SC-003**: 100% of `excluded_known` facts remain in the gate report with relation, direction, and score.
- **SC-004**: When the excluded share is above 10% and no owner decision is recorded, source-bundle construction refuses in every such case.
- **SC-005**: Zero training runs start on a fact whose verdict is missing, `excluded_known`, or `incomplete`.
- **SC-006**: Two gate runs on the same facts, pinned model, and seeds produce identical verdicts.
- **SC-007**: Zero split files are accepted while D-68 is open. A published Block 0 file has 8 construction facts, 8 calibration facts, zero final-test labels, and every remaining eligible author listed as unassigned. A shortfall below 16 eligible facts publishes nothing.
- **SC-008**: Zero authors appear in more than one split. Construction and calibration each contain all four Stage A relations, or the file is not accepted. Two assignments of the same eligible facts and seed produce the same digest, and that seed and digest are present on the ledger row.
- **SC-009**: 100% of attempts to load final-test facts under a non-final-test role are refused and logged.

---

## Assumptions

- **Scope is the pythia-ready block only.** This feature is steps 5–8 of the P1 sign-off recommended order: close D-65, run the exclusion gate, close D-68, assign entity-disjoint splits. Adjudication, fact contracts, source bundles, the entailment audit, and locality neighbourhoods stay in the earlier "Now" block and in the P1 fact-bundle-preparation spec.
- **Pinned model.** The Block 0 base model is already pinned (constitution: D-46 resolved to EleutherAI/pythia-410m at revision 9879c9b; D-49 resolved to base). The P1-2 requirements note is still `draft` and still lists D-46 and D-49 as open; this spec treats the pin as a precondition and binds every gate row to the identity hash, so a later model change requires a new gate run.
- **Entailment audit is a precondition for eligibility.** P1-4 is out of this feature. Split assignment admits only facts that already have a `pass` verdict and a clean audit.
- **D-65 is closed for this spec.** Owner choice Q1: A. Random-choice baseline at 0.5; exclude when any direction's accuracy is greater than 0.5. This matches the sign-off example. Relation-marginal and subject-name baselines are not used.
- **D-68 is closed for Block 0.** Owner choice Q2: A. 8 construction and 8 calibration, matching the execution plan's Phase 3 header. No final-test pool is drawn. Remaining eligible authors stay unassigned. Each assigned split must contain all four Stage A relations (D-63: occupation, birthplace, nationality, genre), or the build publishes nothing.
- **Block 1 counts wait for the power analysis.** The proposal's Block 1 sizes (about 40 calibration and 40 final-test facts, adjusted by the pilot) are not chosen in this feature. The final-test loader guard remains, so a later file that does contain final-test facts still loads them only for the final-test pass.
- **Contamination trigger is already stated.** The execution plan risk register sets the early warning at an exclusion-gate failure for more than 10% of candidates. That figure is the alarm trigger, not a new threshold.
- **Template-group assignment (D-42) is out of scope.** It remains an open handoff on the P1-6 note and is not resolved here.
- **Gate before splits.** Exclusion results carry no split label. Split assignment runs only after `pass` verdicts exist.
- **Spec freeze.** Nothing under the frozen specification is edited by this feature. D-65 and D-68 are recorded as study decisions. They are not silent constants in code.
