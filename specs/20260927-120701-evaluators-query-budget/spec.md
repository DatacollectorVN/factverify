# Feature Specification: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Feature Branch**: `20260927-120701-evaluators-query-budget`  
**Created**: 2026-09-27  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-EVAL — P2-2.md` (status: draft)  
**Plan task**: P2-2 · **Spec dependency**: spec-v1  
**Input**: User description: "Three evaluators return verdicts for the same cases while one accountant enforces the frozen query budget for all of them."

Design sources, read from disk because the Obsidian vault tools were unavailable: [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md), heading "Phase 2 — Harness and run ledger" (note status: planned), including the callout that the shared budget accountant is built before any evaluator. The requirements note is `draft`.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Charge every evaluation call under one equal budget (Priority: P1)

A researcher evaluates one case — a checkpoint, a fact, and a split — with three arms that must be comparable: native, semantic-only, and FactVerify. Before any arm starts, the shared accountant checks that the frozen attack specification gives all three arms the same declared total, and that cache, retry, and failed-request policies are resolved. Every model call is then charged to that case, that arm, and a named channel. A call that would exceed the remaining allocation is refused and recorded. Confirmation calls spend only the reserved confirmation line. When the case finishes, each arm has a cost record, including any allowance it did not use.

**Why this priority**: The primary comparison is an equal-budget comparison. One uncharged call, one arm with a larger cap, or confirmation budget moved into discovery makes that comparison a different claim. The execution plan requires this accountant before any evaluator.

**Independent Test**: Replay a scripted case with no live training. Start once with equal arm totals and once with unequal totals. Issue a batch of prompts and samples, one call inside the remaining allocation, one call past it, one confirmation, one discovery request against unused confirmation, and one each of a cache hit, a retry, and a transport failure. Read the budget record. Separately, point the review at an evaluator path that calls the model outside the accountant.

**Acceptance Scenarios**:

1. **Given** a batch of n prompts with k samples each, **When** the batch is issued to a named channel, **Then** n × k generation trials are charged to that channel on that case's arm, using the accounting unit in the frozen attack specification.
2. **Given** an evaluator path that calls the model outside the accountant, **When** the evaluators are reviewed, **Then** the review fails and names that call site.
3. **Given** remaining allocation at least as large as the call's charge, **When** the call is issued, **Then** it proceeds and the remainder decreases by that charge.
4. **Given** remaining allocation smaller than the call's charge, **When** the call is issued, **Then** the call is refused and the refused request is recorded.
5. **Given** three arm allocations that sum to the same declared total, **When** the run starts, **Then** it proceeds and records that total.
6. **Given** three arm allocations whose sums differ, **When** the run starts, **Then** it refuses and lists each arm's total.
7. **Given** a finished case, **When** its budget record is read, **Then** every cost-reporting field declared for the run is present for each arm, covering generated trials, scored candidates, input tokens, output tokens, exports, training steps, wall-clock, GPU-hours, peak memory, and permitted versus actual usage.
8. **Given** an arm that stopped early, **When** its budget record is read, **Then** the unused allowance is recorded as the remaining allowance.
9. **Given** a candidate witness, **When** confirmation runs, **Then** those charges are applied to the confirmation line and stop at its cap.
10. **Given** unused confirmation allowance, **When** discovery requests more calls, **Then** the request is refused unless the frozen unused-confirmation-reallocation field declares that the move is allowed.
11. **Given** a cache hit, a retry, and a transport failure, **When** each is charged, **Then** each charge matches the frozen policy for that event.
12. **Given** a cache, retry, or failed-request policy field that is still unresolved, **When** the run starts, **Then** it refuses.

---

### User Story 2 — Keep each arm inside its probes and its access profile (Priority: P2)

A researcher runs the three arms on the same case and needs each arm to see only the evidence it is allowed to use. The access profile decides which channels may run. The native arm is scored only on native-format probes. Semantic-only and FactVerify draw equivalence probes only from template groups assigned to that case's split. An inference-set template is reported on its own and is excluded from the primary equivalence score.

**Why this priority**: A native arm that uses closure probes is a different baseline. A calibration template reused on the final-test split makes the final estimate in-sample. A channel the profile forbids produces a claim the study cannot make. This story is usable once Story 1 can charge the channel the arm actually requests.

**Independent Test**: For one case, request a channel the profile permits and a logit or activation channel the profile forbids. Score the native arm on native probes, then route a closure-template probe to it. Draw equivalence probes for a final-test case and attempt to use an inference-set template in the primary equivalence score.

**Acceptance Scenarios**:

1. **Given** a channel the access profile permits, **When** it is requested, **Then** it runs and its calls are charged to that channel.
2. **Given** a logit or activation channel under a profile that forbids it, **When** it is requested, **Then** the request is refused.
3. **Given** a native-arm case, **When** it is scored, **Then** ROUGE-L, BERTScore, Truth Ratio, answer probability, and answer rank are computed on native-format probes.
4. **Given** a closure-template probe, **When** it is routed to the native arm, **Then** it is refused.
5. **Given** a final-test case, **When** equivalence probes are drawn, **Then** every template group belongs to the final-test assignment.
6. **Given** an inference-set template, **When** it is drawn for the primary equivalence score, **Then** it is refused for that score and appears only in the separate inference output.

---

### User Story 3 — Return one frozen verdict, with channel scores kept apart (Priority: P2)

A researcher receives one verdict per case per arm. The verdict is exactly one of four statuses, and it carries the access label of the profile in force. FactVerify issues a confirmed recovery witness only through the frozen witness rule, including a declared confirmation route. A single probe that crosses its bound is logged as a diagnostic. Correctness, probability, rank, and sampling frequency each keep their own score and bound.

**Why this priority**: Merging non-identifiable with incomplete, or forcing either into a pass or a rejection, changes the false-certification and false-rejection denominators. A raw maximum grows stricter as more probes are added, so arms would stop being comparable. Separate scores show which channel carried the evidence.

**Independent Test**: Evaluate a fixture case and read a single status plus its access label. Evaluate a control that is structurally indistinguishable under the profile. Decide a case with one unconfirmed bound crossing, and a case whose recovery was confirmed by a declared route. Emit channel scores and reject any single average of correctness, probability, rank, and sampling frequency.

**Acceptance Scenarios**:

1. **Given** any evaluated case, **When** its verdict is read, **Then** the verdict is exactly one of: confirmed recovery witness, conformant under the declared test, non-identifiable under this profile, or insufficient evidence/incomplete, and it carries the access label.
2. **Given** a control that is structurally indistinguishable under the profile, **When** it is evaluated, **Then** the verdict is non-identifiable under this profile.
3. **Given** a single probe that crosses its bound without confirmation, **When** the case is decided, **Then** the verdict is not a confirmed recovery witness, and the raw maximum is recorded as a diagnostic.
4. **Given** a recovery confirmed by a declared route, **When** the case is decided, **Then** the verdict is a confirmed recovery witness and the route is recorded.
5. **Given** a case, **When** scores are emitted, **Then** each channel has its own score and its own bound.
6. **Given** a result that averages correctness, probability, rank, and sampling frequency into one score, **When** it is checked, **Then** the check fails.
7. **Given** a finished verdict, **When** the row is read, **Then** it carries the checkpoint ledger identifier, the fact identifier, the split, the arm, and the spec revision.

---

### User Story 4 — Run final-test cases only under frozen thresholds (Priority: P2)

A researcher runs a final-test case only when the thresholds record is the one frozen under the thresholds tag, and the file digest matches that tag. A missing tag, a modified thresholds file, or a threshold supplied as an argument stops the case. The verdict row records the tag that was used.

**Why this priority**: Thresholds chosen after seeing final-test cases turn the headline result into a calibration curve. Calibration itself is a separate activity and is outside this gate.

**Independent Test**: Start a final-test case with a matching tag and digest, then repeat with a missing tag, a changed file, and a threshold passed in by argument. Confirm only the matching case proceeds, and that its verdict records the tag.

**Acceptance Scenarios**:

1. **Given** the frozen thresholds tag and a thresholds file whose digest matches that tag, **When** a final-test case runs, **Then** it proceeds and the verdict records the tag.
2. **Given** a missing thresholds tag, a modified thresholds file, or a threshold supplied as an argument, **When** a final-test case runs, **Then** it refuses.

---

### User Story 5 — Keep every raw generation for audit (Priority: P3)

A researcher finishing a case can open every raw completion that was charged, with the case, arm, channel, probe, and decoding parameters that produced it. The number of stored completions equals the number of charged generations. The store lives outside the spec namespace. Replaying the same inputs and seed from those stored generations yields the same verdicts and scores.

**Why this priority**: Blind annotation and witness audits need the original text. A score without the completion cannot be checked. Replay from the stored generations is what makes a repeated case the same case.

**Independent Test**: Finish a case that charged a known number of generations. Count the stored raw records and compare their identifiers with the charged calls. Configure a write path inside the spec namespace and confirm the run refuses. Replay the case from the stored generations and compare verdicts and scores.

**Acceptance Scenarios**:

1. **Given** any charged generation, **When** the case finishes, **Then** a raw record exists for it, containing the prompt, the completion, the decoding parameters, and the case, arm, channel, and probe identifiers, and the number of raw records equals the charged generation count.
2. **Given** a write path inside the spec namespace (`.factverify/`), **When** the run is configured with that path, **Then** the run refuses.
3. **Given** the same case inputs and seed, **When** the case is replayed from its stored generations, **Then** the verdicts and scores match the first run.

---

### Edge Cases

- What happens when the spec root is missing, a required spec file is unreadable, or a normative field is unresolved? The run refuses before the first model call and names the missing field.
- What happens when the accounting unit, the trial cap, the equality rule, the cache or failed-request policy, the confirmation-reallocation rule, the logit scope, or the incomplete-status mapping is still an open decision? The run reads the frozen spec field. While that field is unresolved, the run refuses. The decision stays open until the spec field is filled.
- What happens when a call's charge is exactly the remaining allocation? The call proceeds and the remainder becomes zero.
- What happens when a later call is issued after the remainder is zero? The call is refused and the refused request is recorded.
- What happens when confirmation reaches its cap with unused discovery allocation still available? Further confirmation calls are refused. Discovery allowance is left on the discovery line.
- What happens when an arm is permitted to run but stops before spending its allocation? The unused allowance remains visible on that arm's cost record.
- What happens when a semantic-only or FactVerify case is on the calibration split? Equivalence probes come only from template groups assigned to calibration. Final-test groups are refused for that case.
- What happens when a final-test case is started before a thresholds tag exists? The case refuses.
- What happens when a non-final split is evaluated before thresholds are frozen? The case may proceed under Stories 1–3 and 5. Its verdict carries the checkpoint ledger identifier and the spec revision. It does not require the frozen thresholds tag.
- What happens when stored generations are incomplete relative to the charged count? The case is not treated as finished for audit.
- What happens when the same case is replayed after a stored generation or a decoding parameter has changed? The replay is a different case. Matching verdicts are required only when inputs, seed, and stored generations are unchanged.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The evaluation MUST charge each model call to the case's arm and named channel, using the accounting unit declared in the frozen attack specification. A batch of n prompts with k samples each MUST charge n × k generation trials to that channel. Candidate scoring MUST follow that same accounting-unit field. A review of the evaluators MUST fail, naming the call site, if any model call is issued outside the shared accountant. Traces to FV-EVAL-001.
- **FR-002**: The evaluation MUST refuse any call whose charge exceeds the arm's remaining allocation for that channel, and MUST record the refused request. A call within the remaining allocation MUST proceed, and the remainder MUST decrease by the charge. The allocation value MUST come from the frozen attack specification. Traces to FV-EVAL-002.
- **FR-003**: The evaluation MUST refuse to start unless the frozen allocation declaration gives all three arms the same declared total. When the totals match, the run MUST proceed and MUST record that total. When they differ, the run MUST refuse and MUST list each arm's total. Traces to FV-EVAL-003.
- **FR-004**: The evaluation MUST record, for every finished case and every arm, each field the frozen cost-reporting declaration names: generated trials, scored candidates, input tokens, output tokens, exports, training steps, wall-clock, and permitted versus actual usage, together with GPU-hours and peak memory. An arm that stops early MUST keep its unused allowance visible as the remaining allowance. Traces to FV-EVAL-004.
- **FR-005**: The evaluation MUST charge confirmation calls only to the reserved confirmation line, and MUST stop at that line's cap. A discovery request that would spend unused confirmation allowance MUST be refused unless the frozen unused-confirmation-reallocation field declares that the move is allowed. Traces to FV-EVAL-005.
- **FR-006**: The evaluation MUST charge cache hits, retries, and failed requests exactly as the frozen cache, retry, and failed-request policies declare. If any of those policy fields is unresolved, the run MUST refuse to start. Traces to FV-EVAL-006.
- **FR-007**: The evaluation MUST refuse any channel the access profile does not permit, including a logit or activation channel under a profile that forbids it. A channel the profile permits MUST be allowed to run, and its calls MUST be charged to that channel. Traces to FV-EVAL-007.
- **FR-008**: The native arm MUST compute ROUGE-L, BERTScore, Truth Ratio, answer probability, and answer rank only on native-format probes. A closure-template probe routed to the native arm MUST be refused. Traces to FV-EVAL-008.
- **FR-009**: Semantic-only and FactVerify MUST draw equivalence probes only from template groups assigned to the case's split. On a final-test case, every template group used for the primary equivalence score MUST belong to the final-test assignment. An inference-set template MUST be refused for that primary score and MUST be reported only in the separate inference output. Traces to FV-EVAL-009.
- **FR-010**: Each case and arm MUST return exactly one verdict, and that verdict MUST be one of: confirmed recovery witness, conformant under the declared test, non-identifiable under this profile, or insufficient evidence/incomplete. The verdict MUST carry the access label of the profile in force. A control that is structurally indistinguishable under the profile MUST receive non-identifiable under this profile. The verdict row MUST carry the checkpoint ledger identifier, the fact identifier, the split, the arm, and the spec revision. Traces to FV-EVAL-010.
- **FR-011**: FactVerify MUST issue a confirmed recovery witness only through the frozen witness-rule decision, and MUST record the confirmation route that was used. A single probe that crosses its bound without confirmation MUST leave the verdict as something other than a confirmed recovery witness, and the raw maximum MUST be recorded as a diagnostic. Traces to FV-EVAL-011.
- **FR-012**: The evaluation MUST refuse a final-test case unless thresholds are loaded from the frozen thresholds record at the thresholds tag and the file digest matches that tag. The verdict MUST record the tag. A missing tag, a modified thresholds file, or a threshold supplied as an argument MUST refuse the case. Traces to FV-EVAL-012.
- **FR-013**: The evaluation MUST report each channel's score with that channel's own bound. It MUST reject a combined average of correctness, probability, rank, and sampling-frequency scores. Traces to FV-EVAL-013.
- **FR-014**: The evaluation MUST persist every raw completion with its case, arm, channel, probe identifier, prompt, and decoding parameters, outside the spec namespace (`.factverify/`). When a case finishes, the number of raw records MUST equal the charged generation count. A configured write path inside the spec namespace MUST refuse the run. The same case inputs, seed, and stored generations MUST reproduce the same verdicts and scores. Traces to FV-EVAL-014.
- **FR-015**: On any bad, missing, or unresolved input — including an unresolved spec field — the evaluation MUST fail closed before the first model call and MUST name the missing field. No requirement may be treated as implemented while a blocking decision it depends on remains open. The accountant requirements (FR-001 through FR-006) MUST be satisfied before the evaluator requirements (FR-008 through FR-013) are treated as ready.

### Key Entities

- **Case**: The unit being evaluated. It identifies a checkpoint by its ledger identifier, a fact, and a split (construction, calibration, or final-test).
- **Arm**: One of the three evaluators compared on that case: native, semantic-only, or FactVerify.
- **Channel**: A named evidence route assigned to an arm by the frozen attack specification. A request names the channel. The access profile allows or forbids it.
- **Query-budget accountant**: The single place that accepts or refuses model calls for every arm. It holds the case, the arm, the remaining allocation per channel, the confirmation line, and the cost record.
- **Budget record**: For one case and one arm, the permitted allocation, the amount charged, the amount refused, the unused remainder, and the cost vector.
- **Cost vector**: Generated trials, scored candidates, input tokens, output tokens, exports, training steps, wall-clock, GPU-hours, peak memory, and permitted versus actual usage.
- **Confirmation line**: The reserved portion of the budget that confirmation calls may spend. Discovery calls spend it only when the frozen reallocation field allows that move.
- **Verdict**: One status, the access label, the per-channel scores and bounds, any witness route or diagnostic raw maximum, and the provenance of the row (checkpoint ledger identifier, fact, split, arm, spec revision, and, on final test, the thresholds tag).
- **Raw generation**: The prompt, completion, decoding parameters, and the case, arm, channel, and probe identifiers for one charged generation.
- **Thresholds record**: The frozen thresholds file identified by the thresholds tag and its digest. Final-test cases load this record and no other threshold source.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every accepted evaluation charges every model call to one arm and one channel. Any review that finds a bypass names the call site, and that evaluation is not accepted.
- **SC-002**: No accepted call leaves an allocation below zero. Every refused overspend is present in the budget record as a refused request.
- **SC-003**: Every started run records one declared total shared by all three arms. Every unequal set of totals is refused, and the refusal lists each arm's total, in 100% of such attempts.
- **SC-004**: Every finished case has, for each arm, every declared cost-reporting field plus GPU-hours and peak memory. Every early stop still shows the unused remainder.
- **SC-005**: Confirmation charges stay within the confirmation cap. A discovery request that would spend confirmation allowance is refused unless the frozen reallocation field allows it, in 100% of such attempts.
- **SC-006**: On a fixture of one cache hit, one retry, and one transport failure, each charge matches the frozen policy. A run with an unresolved cache, retry, or failed-request field does not start.
- **SC-007**: Every verdict is one of the four statuses and carries its access label. Every structurally indistinguishable control under the profile in force receives non-identifiable under this profile.
- **SC-008**: An unconfirmed bound crossing is never returned as a confirmed recovery witness. Every confirmed recovery witness names its route. Every emitted channel score has its own bound, and a combined average of the four score kinds is rejected.
- **SC-009**: Every final-test case that runs records the frozen thresholds tag and was loaded from a file whose digest matches that tag. A missing tag, a modified file, and an argument-supplied threshold are refused in 100% of such attempts.
- **SC-010**: For every finished case, the number of stored raw generations equals the number of charged generations. A write path inside the spec namespace is refused.
- **SC-011**: Replaying a finished case from the same inputs, seed, and stored generations reproduces the same verdicts and scores for every pair checked.
- **SC-012**: The six accountant checks (FV-EVAL-001 through FV-EVAL-006) pass before any evaluator check (FV-EVAL-008 through FV-EVAL-013) is treated as ready. All fourteen requirement checks (FV-EVAL-001 through FV-EVAL-014) pass before a Block 0 scoring run uses these evaluators.

---

## Assumptions

- The caller supplies an explicit spec root and a case (checkpoint ledger identifier, fact identifier, split). The frozen spec is at `spec-v1`. This feature reads spec fields and does not edit the spec.
- In scope: the shared query-budget accountant; the native arm; the semantic-only arm; the FactVerify arm, including the channels the attack specification assigns to it and the frozen witness-rule decision; applying a thresholds record that is already frozen; the four-status verdict vocabulary; raw-generation persistence; the per-arm cost vector.
- Out of scope: choosing budget and channel values (the attack specification, P0-3); the witness-rule text (P0-6); selecting thresholds on the calibration split (P4-3); fake-unlearning controls (P2-3); cache storage (P2-7) — this feature applies the frozen charge policy to cache hits and consumes stored generations; confidence intervals and denominator arithmetic (P2-6); ledger storage (P2-5) — verdict rows cite the checkpoint ledger identifier and do not create the ledger.
- Model calls are made only through the accountant. Checkpoint loading is provided by the model loader (P2-0). Evaluators do not obtain a model by a path that bypasses that loader or the accountant.
- Cache hits, retries, and transport failures are charged as the frozen policies say. Generation storage and lookup live in the cache component (P2-7).
- Constraint C-3 of the requirements note asks every verdict row to carry a thresholds tag. This specification requires that tag on final-test rows, which is the case FV-EVAL-012 governs. Rows from construction or calibration carry the checkpoint ledger identifier and the spec revision. They do not require the frozen thresholds tag, because that tag does not exist until threshold selection finishes.
- The plan risk register compares evaluation time with training time. This feature records wall-clock, GPU-hours, and peak memory per arm so that comparison can be made. It does not add a stop rule for that comparison.
- Eight decisions remain open. Requirements that depend on them are written against the spec field: **D-14** (how incomplete and non-identifiable enter denominators; blocks FR-010), **D-17** (total trial cap per case; blocks FR-002), **D-18** (candidate-scoring accounting unit; blocks FR-001), **D-20** (cache and retry policy; blocks FR-006), **D-21** (failed-request policy; blocks FR-006), **D-22** (equal caps versus equal realized usage; blocks FR-003), **D-26** (unused-confirmation reallocation; blocks FR-005), **D-27** (logit scope under the relevant access profile; blocks FR-007). Runs can be specified and checked against fixture specifications before these close. While the governing field is unresolved, the run refuses.
- No requirement may be marked implemented while a blocking decision it depends on remains open.
- The source requirements note is `draft`. The execution-plan note it cites is `planned`.
