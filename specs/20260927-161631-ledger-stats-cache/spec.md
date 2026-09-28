# Feature Specification: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Feature Branch**: `20260927-161631-ledger-stats-cache`  
**Created**: 2026-09-27  
**Status**: Draft  
**Source**: `second-brain/ml-unlearning/requirements/FV-LEDG — P2-5.md`, `FV-STAT — P2-6.md`, and `FV-CACHE — P2-7.md` (each status: draft)  
**Plan tasks**: P2-5, P2-6, P2-7 · **Spec dependency**: spec-v1  
**Input**: User description: "Combine the run ledger, cluster-bootstrap analysis, and generation cache so every checkpoint is provenance-backed, intervals respect checkpoint-by-fact dependence, and an identical generation is replayed once."

Design sources, read from disk because the Obsidian vault tools were unavailable: [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md), heading "Phase 2 — Harness and run ledger", tasks P2-5, P2-6, and P2-7; heading "Phase 4 — Block 1", tasks P4-3, P4-5, and P4-6, including the callout that the final-test pass runs once; heading "Phase 7" task P7-5; heading "Risk register", rows "Threshold leakage" and "Evaluation dominates wall-clock"; heading "Start here — first two weeks", item 3; and heading "Tracking conventions" (note status: planned). [Research Proposal — FactVerify (v3)](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/self-learning-path/Research%20Proposal%20%E2%80%94%20FactVerify%20(v3).md), headings "6.2 Cross-fitted split", "6.4 Primary endpoint", and "8. Statistical design" (note status: draft). [FactVerify — Phase 0 Build Handbook (Freeze Spec)](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/self-learning-path/FactVerify%20%E2%80%94%20Phase%200%20Build%20Handbook%20(Freeze%20Spec).md), invariants I6, I7, and I8, headings "6.4 One query needs a definition", "6.7 Transformations must be reproducible", "8.4 Zero errors is not a zero rate", and "8.7 Dependence and multiplicity", and check V23 (note status: draft). All three requirements notes are `draft`.

This feature is the provenance, the interval, and the replay underneath the study. A checkpoint or evaluation run is usable only when the ledger has a committed row that says what it is, where it came from, and what it cost. False-rejection rate, false-certification rate, and the difference in false-certification rate are reported with intervals that move whole checkpoint and fact blocks together and keep the two evaluators on the same cases. An identical generation request is computed once and replayed with the same content, and a different request never receives that content. The ledger stands before the first checkpoint exists. Retrofitting provenance after the checkpoints exist is how this study becomes irreproducible.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Refuse an unledgered checkpoint (Priority: P1)

A researcher asks whether a checkpoint may be evaluated. The ledger returns the checkpoint's role and split only when a committed row exists. A complete checkpoint row records identity hash, parent, configuration hash, seed, fact, split, role, tier, family and method, spec tag, git commit, dirty flag, cost, wall-clock, and status, and receives a row identifier and a timestamp. Role is one of base, finetuned, reference, control, or candidate. Tier is whatever decision D-56 records. A child row is accepted only when its parent row is already present, and reading that child's lineage returns the chain back to the base. A finished evaluation run is recorded with its checkpoint, arm, split, spec tag, thresholds tag, budget used, and pass number. A row missing any required field is rejected, and the rejection names the field.

**Why this priority**: An unledgered checkpoint has no role and no split, so it cannot enter a false-certification or false-rejection rate. The execution plan stands this ledger up before the first checkpoint exists.

**Independent Test**: Add one complete checkpoint row and read its role and split. Add one row with a single required field empty. Add one child whose parent is present and one whose parent is absent. Record one finished evaluation run, and one final-test evaluation run that omits the thresholds tag. Repeat a checkpoint add while D-56 is unresolved.

**Acceptance Scenarios**:

1. **Given** a checkpoint with a committed row, **When** an evaluator asks for it, **Then** the row's role and split are returned.
2. **Given** an identity hash with no row, **When** an evaluator asks for it, **Then** the ledger refuses and the checkpoint is unusable for evaluation.
3. **Given** a complete checkpoint record, **When** it is added, **Then** it is committed with a generated row identifier and a timestamp.
4. **Given** a checkpoint record with any required field empty, **When** it is added, **Then** it is rejected and the rejection names that field.
5. **Given** role one of base, finetuned, reference, control, or candidate, and a tier value decision D-56 records, **When** the row is added, **Then** it is accepted.
6. **Given** any other role or tier, **When** the row is added, **Then** it is rejected.
7. **Given** a parent row already present, **When** the child is added, **Then** the child's lineage is the full chain back to the base.
8. **Given** a named parent that is not in the ledger, **When** the child is added, **Then** the child is rejected.
9. **Given** a finished evaluation run, **When** it is recorded, **Then** checkpoint, arm, split, spec tag, thresholds tag, budget used, and pass number are present.
10. **Given** a final-test evaluation run without a thresholds tag, **When** it is recorded, **Then** it is rejected.
11. **Given** an unresolved D-56 record, **When** a checkpoint row is added, **Then** the add is refused and names D-56. The vocabulary requirement is not marked implemented while D-56 is open.

---

### User Story 2 - Keep the ledger append-only (Priority: P1)

A researcher correcting a ledger row adds a new row that points at the row it supersedes. The original row is unchanged. Any attempt to change or delete an existing row fails. Several jobs can add rows at the same time, and a job that stops halfway leaves no partial row. An export of every table, marked with its schema version, re-imports into an empty ledger as the same rows. An export from a newer schema version is refused by an older reader.

**Why this priority**: An editable ledger can be made to agree with any result after the fact. The release archive has to carry provenance a reader can load without the original machine.

**Independent Test**: Record a correction and read both rows. Attempt a change and a deletion of an existing row. Add a second row for an identity hash that does not point at the first. Add several rows at once, and interrupt one add before it finishes. Export, re-import into an empty ledger, and compare row counts and row digests. Offer a newer export to an older reader.

**Acceptance Scenarios**:

1. **Given** a correction, **When** it is recorded, **Then** a new row points at the superseded row and the original row is unchanged.
2. **Given** an attempt to change or delete an existing ledger row, **When** it is made through any path, **Then** it fails.
3. **Given** an identity hash that already has a committed row, **When** a second row is added that does not point at that row, **Then** the add is rejected.
4. **Given** several concurrent adds of one row each, **When** they finish, **Then** the ledger contains exactly that many new rows.
5. **Given** a writer stopped halfway through an add, **When** the ledger is opened again, **Then** no partial row exists.
6. **Given** a ledger, **When** it is exported and re-imported into an empty ledger, **Then** row counts and row digests match.
7. **Given** an export from a newer schema version, **When** an older reader imports it, **Then** the import is refused.

---

### User Story 3 - Guard the single final-test pass (Priority: P1)

A researcher recording a final-test row on a clean tree stores the git commit, a clean flag, and the spec tag. The same row from a dirty tree is rejected. A non-final row from a dirty tree is accepted and marked dirty. A disjointness check reports counts for fact, reference seed, and control implementation, and fails when any of those appears on both a calibration row and a final-test row, listing the offending rows. The first final-test pass on a split is recorded as pass 1. A later pass on that same split is refused unless an incident row references the first pass.

**Why this priority**: A final-test result from uncommitted code cannot be reproduced. A shared fact, seed, or control implementation, or an unrecorded second pass, turns the held-out estimate into a calibration curve. The execution plan's recovery from a broken pass is a recorded incident and a whole re-run.

**Independent Test**: Add one final-test row from a clean tree and one from a dirty tree, plus one non-final dirty row. Run the disjointness check on a disjoint ledger and on a ledger that shares one seed, one fact, or one control implementation. Open a first final-test pass, then open a second on the same split with no incident row, then again with an incident row that references the first pass.

**Acceptance Scenarios**:

1. **Given** a clean tree, **When** a final-test row is added, **Then** it is accepted with its commit, a clean flag, and its spec tag.
2. **Given** a dirty tree, **When** a final-test row is added, **Then** it is rejected.
3. **Given** a dirty tree, **When** a non-final row is added, **Then** it is accepted and marked dirty.
4. **Given** calibration and final-test rows that share no fact, reference seed, or control implementation, **When** the disjointness check runs, **Then** it succeeds and reports a count for each of those three dimensions.
5. **Given** one shared fact, reference seed, or control implementation across those splits, **When** the disjointness check runs, **Then** it fails and lists the offending rows.
6. **Given** no prior final-test pass on a split, **When** a pass opens, **Then** it is recorded as pass 1.
7. **Given** a prior final-test pass and no incident row referencing it, **When** another pass opens on that split, **Then** it is refused.
8. **Given** an incident row that references the first pass, **When** a later pass is recorded, **Then** the ledger accepts the record of that later pass.

---

### User Story 4 - Replay an identical generation once (Priority: P1)

A researcher issues a generation or scoring request. The cache key is derived from the model identity hash, the hash of the exact model input, every decoding parameter, and the request kind. The input hash is the exact string passed to the tokenizer after any chat template, with no further normalisation. Two requests that differ in any one key field land in different entries. Each sampled completion is keyed by its sample index and its seed, so a request for a sample that has not been stored is a miss. A stored entry is returned only after its content digest checks, and the lookup emits a hit. A corrupted entry is withheld, a corrupt event is emitted, and the request is treated as a miss. Recomputing the same content is a no-op. Different content for an existing key is refused and emits a conflict event carrying both digests. The cache root lies outside `.factverify/`. Every lookup emits exactly one event: hit, miss, conflict, or corrupt. An export carries a manifest of keys and digests and re-imports to the same lookups. Whether a hit costs query budget is the policy decision D-20 records and is applied by the query-budget accountant.

**Why this priority**: Evaluation time is the feasibility risk in the plan's risk register. A cache that serves the wrong entry corrupts verdicts, and a hit the accountant never sees cannot be charged under the frozen policy.

**Independent Test**: Look up two requests that differ by one key field, two inputs that differ by one whitespace character, and the same rendered input hashed twice. Request sample indices that are stored and one that is not. Read an intact entry and a corrupted entry. Write an identical recomputation and a different recomputation. Initialise a cache root outside `.factverify/` and one inside it. Count events for one lookup. Export, re-import into an empty store, and import one bundle whose manifest digest disagrees with its content. Repeat key derivation while D-60 is unresolved.

**Acceptance Scenarios**:

1. **Given** two requests that differ in any one key field, **When** they are looked up, **Then** they map to different keys.
2. **Given** a request missing any key field, **When** it is looked up, **Then** the lookup is refused.
3. **Given** two inputs that differ by one whitespace character, **When** they are hashed, **Then** the hashes differ.
4. **Given** the same template-rendered input, **When** it is hashed twice, **Then** the hashes are identical.
5. **Given** requests for sample indices 1 through k, **When** they are served, **Then** k distinct entries are stored or returned.
6. **Given** a sample index that is not stored, **When** it is looked up, **Then** the lookup is a miss.
7. **Given** an intact entry, **When** it is read, **Then** it is returned with a hit event.
8. **Given** a corrupted entry, **When** it is read, **Then** it is withheld, a corrupt event is emitted, and the request is a miss.
9. **Given** a recomputed result identical to the stored entry, **When** it is written, **Then** the write leaves the stored entry as it was.
10. **Given** a different result for an existing key, **When** it is written, **Then** the write is refused and a conflict event carries both digests.
11. **Given** a cache root outside `.factverify/`, **When** the cache is initialised, **Then** it proceeds.
12. **Given** a cache root inside `.factverify/`, **When** the cache is initialised, **Then** it is refused.
13. **Given** a lookup, **When** it is served, **Then** exactly one event is emitted and the accountant can record it.
14. **Given** a path that returns cache content without emitting an event, **When** that path is checked, **Then** the check fails.
15. **Given** a cache, **When** it is exported and re-imported into an empty store, **Then** every key returns the same content digest.
16. **Given** an export whose manifest digest disagrees with its content, **When** it is imported, **Then** the import is refused.
17. **Given** an unresolved D-60 record, **When** a cache key is derived, **Then** derivation is refused and names D-60. The full-key requirement is not marked implemented while D-60 is open.
18. **Given** an unresolved D-20 record, **When** this feature's event requirement is reviewed, **Then** it is not marked implemented. This feature does not choose the budget charge for a hit.

---

### User Story 5 - Estimate intervals on checkpoint and fact blocks (Priority: P2)

A researcher asks for false-rejection rate, false-certification rate, and the difference in false-certification rate. Resampling draws the checkpoint and fact blocks declared in the margins file, and every prompt row of a selected block travels together. A request to resample individual prompt rows is refused. When the margins file declares a crossed design, checkpoints and facts are each resampled under that scheme. Analysing a crossed set under a nested scheme is refused. The difference in false-certification rate uses the same resample for both evaluators, so each draw indexes the same cases in both arms. Arms whose case sets differ are refused, and the refusal lists the unmatched cases. False-certification rate is reported for each control family and overall, under the aggregation decision D-10 records. A family with no evaluated cases reports a count of zero and does not report a rate. When the error count is zero, the point estimate is 0 and the upper bound is a positive value from the confidence procedure decision D-03 records. Multiplicity adjustment uses only the family and the procedure the margins file declares. The same verdict table, design, and seed produce the same estimates and bounds, and the output records the seed, the replicate count, and the design. A coverage check, on simulated data with a known rate and a known cluster structure, yields intervals whose empirical coverage sits within the tolerance decision D-57 records.

**Why this priority**: The headline claim is an interval on the difference in false-certification rate. Treating prompts as replicates understates uncertainty. This story is usable once verdict rows exist; it does not have to exist before the first checkpoint.

**Independent Test**: Draw one resample under a declared block design and confirm each selected block's prompt rows stay together. Request a prompt-row resample. Run a crossed design and a nested scheme on a crossed set. Estimate a paired difference on matched cases and on unmatched case sets. Estimate across families, including one family with no cases. Estimate a zero-error sample and reject a zero-width interval at zero. Adjust with a declared procedure and with an undeclared one. Run the same table, design, and seed twice. Run the coverage check while D-57 is closed, and confirm a prompt-row resample on the same simulated data covers below the nominal rate.

**Acceptance Scenarios**:

1. **Given** the block design the margins file declares, **When** a resample is drawn, **Then** every prompt row of a selected block is included together.
2. **Given** a request to resample individual prompt rows, **When** it is made, **Then** it is refused.
3. **Given** a crossed design flag, **When** resampling runs, **Then** checkpoints and facts are each resampled under the declared crossed scheme.
4. **Given** a crossed dataset analysed under a nested scheme, **When** the design is checked, **Then** the check is refused and names the mismatch.
5. **Given** verdicts from two arms on the same cases, **When** the difference in false-certification rate is estimated, **Then** each resample indexes identical cases in both arms.
6. **Given** arms with different case sets, **When** the difference is estimated, **Then** the estimate is refused and lists the unmatched cases.
7. **Given** verdicts that span control families and a closed D-10 record, **When** false-certification rate is estimated, **Then** the result has one row per family plus an overall row, aggregated as D-10 records.
8. **Given** a family with no evaluated cases, **When** the estimate is produced, **Then** that row reports a count of zero and does not report a rate.
9. **Given** zero errors in a set of cases and a closed D-03 record, **When** the rate is estimated, **Then** the point estimate is 0 and the upper bound is positive.
10. **Given** an estimate that returns a zero-width interval at 0, **When** it is checked, **Then** the check fails.
11. **Given** a declared multiplicity family and procedure, **When** adjustment runs, **Then** the adjusted values match the reference result on the fixture.
12. **Given** an undeclared family or procedure, **When** adjustment runs, **Then** it is refused.
13. **Given** the same verdict table, design, and seed, and a closed D-57 record, **When** estimation runs twice, **Then** every estimate and bound matches, and the output records the seed, the replicate count, and the design.
14. **Given** simulated clustered data with a known rate and a closed D-57 tolerance, **When** intervals are computed over the declared simulations, **Then** empirical coverage is within that tolerance of the nominal rate.
15. **Given** a prompt-row resample on that same simulated data, **When** coverage is measured, **Then** it falls short of the nominal rate.
16. **Given** an unresolved D-07, D-03, D-08, D-10, or D-57 record, **When** the estimate that depends on it is requested, **Then** the request is refused and names that decision. The depending requirement is not marked implemented while the decision is open.

---

### User Story 6 - Keep final-test rows out of threshold selection (Priority: P1)

A researcher selecting thresholds asks for the upper confidence bound on the false-rejection rate for each candidate threshold, using calibration rows only. The same request is refused when any input row has split final-test. A verdict row is accepted for analysis only when it carries a checkpoint ledger identifier and an evaluation-run identifier that the ledger knows. A missing or unknown identifier fails the load and names the row.

**Why this priority**: An upper bound computed on final-test cases to pick a threshold leaks the test into calibration. A verdict without provenance cannot be assigned to a split, a family, or a cluster. This guard can be tested before the interval estimator exists.

**Independent Test**: Call threshold selection on calibration rows and read one upper bound per candidate threshold. Call it again with one final-test row in the input. Load verdict rows whose ledger identifiers resolve, and one row whose checkpoint or evaluation-run identifier is missing or unknown.

**Acceptance Scenarios**:

1. **Given** calibration-split rows, **When** threshold selection is requested, **Then** the upper confidence bound on the false-rejection rate is returned for each candidate threshold.
2. **Given** any final-test row in the input, **When** threshold selection is requested, **Then** the request is refused.
3. **Given** verdict rows whose checkpoint and evaluation-run identifiers are in the ledger, **When** they are loaded for analysis, **Then** they are accepted.
4. **Given** a verdict row with a missing or unknown ledger identifier, **When** it is loaded, **Then** loading fails and names the row.

---

### Edge Cases

- What happens when a required input is missing, or a spec field this feature needs is unresolved? The operation is refused and names the missing field. A rejected ledger write leaves the ledger unchanged. An incomplete cache key is an error and is never looked up as a shorter key.
- What happens when decision D-56 is open? A checkpoint row is refused and names D-56. No stand-in tier is stored. The role and tier vocabulary requirement is not marked implemented.
- What happens when a checkpoint row names no parent? It is accepted as a root, and lineage stops at that row. A row that names a parent absent from the ledger is rejected.
- What happens when two rows would use the same identity hash? The second add is a correction only when it is a new row that points at the first. A second committed row with the same identity and no supersession pointer is rejected.
- What happens when a correction points at a row that does not exist? The correction is rejected.
- What happens when an incident row does not reference the first final-test pass? A second pass on that split is still refused.
- What happens when the disjointness check is asked about a ledger with only one of the two splits? It succeeds and reports a count of zero on the empty split for each dimension.
- What happens when a shared template group is the only overlap? This feature's disjointness check covers fact, reference seed, and control implementation. Template-group disjointness stays with the spec-freeze check V13.
- What happens when decision D-60 is open? Cache-key derivation is refused and names D-60. Software versions are neither forced into the key nor left out by a local choice.
- What happens when decision D-20 is open? Lookups still emit one event once the key can be derived. The budget charge for a hit is not chosen here, and the event requirement is not marked implemented.
- What happens when a cache entry's digest matches and the completion is empty? The entry is returned as a hit. Emptiness is content, and it still has a digest.
- What happens when two requests differ only by letter case? They are different inputs, and they hash differently.
- What happens when a scoring request and a generation request share a model, an input, and decoding parameters? They are different keys, because request kind is part of the key.
- What happens when the margins file omits the resampling design, the confidence procedure, the multiplicity family, or the aggregation rule? The estimate that needs the missing field is refused and names it. No default scheme is applied.
- What happens when decision D-06 is open? The check that both arms use the same cases still runs. A weighted estimate, and family aggregation under D-10, is refused and names the open decision. No weight is invented.
- What happens when a control family has cases and zero errors? The row reports the case count, a point estimate of 0, and a positive upper bound from the D-03 procedure.
- What happens when threshold selection is requested and the input mixes calibration rows with one final-test row? The request is refused. The calibration rows are not used on their own in that call.
- What happens when a final-report estimate is requested on final-test rows that are ledgered and disjoint? The estimate proceeds. The final-test refusal applies to threshold selection.
- What happens when a verdict's ledger identifiers exist but the checkpoint role or split is missing on that row? The load fails and names the row.

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: A checkpoint MUST be unusable for evaluation unless the ledger has a committed row for it. A lookup of a committed row MUST return that row's role and split. A lookup of an identity hash with no row MUST be refused. Traces to FV-LEDG-001.
- **FR-002**: A checkpoint row MUST be rejected when any required field is empty: identity hash, parent (except a root, which names none), configuration hash, seed, fact, split, role, tier, family and method, spec tag, git commit, dirty flag, cost, wall-clock, or status. A complete row MUST be committed with a generated row identifier and a timestamp. A rejected write MUST leave the ledger unchanged and MUST name the empty field. While D-56 is unresolved, this requirement MUST NOT be marked implemented, because tier is one of the required fields. Traces to FV-LEDG-002.
- **FR-003**: Role MUST be one of base, finetuned, reference, control, or candidate. Tier MUST be a value decision D-56 records. Any other value MUST be rejected. While D-56 is unresolved, a checkpoint add MUST be refused and name D-56, and this requirement MUST NOT be marked implemented. Traces to FV-LEDG-004.
- **FR-004**: A checkpoint row that names a parent MUST be rejected when that parent is not already in the ledger. When the parent is present, the child's lineage MUST be the full chain back to the base. A row that names no parent is a root. Traces to FV-LEDG-005.
- **FR-005**: An existing ledger row MUST stay unchanged. A correction MUST be a new row that points at the superseded row. An attempt to change or delete an existing row MUST fail. A second row for an identity hash that does not point at the existing row MUST be rejected. Traces to FV-LEDG-003.
- **FR-006**: Concurrent adds MUST commit whole rows. After several writers each add one row, the ledger MUST contain exactly that many new rows. A writer stopped halfway MUST leave no partial row. This requirement may be waived only with a recorded reason. Traces to FV-LEDG-011.
- **FR-007**: A final-test row from a clean tree MUST be accepted with its git commit, a clean flag, and its spec tag. A final-test row from a dirty tree MUST be rejected. A non-final row from a dirty tree MUST be accepted and marked dirty. Traces to FV-LEDG-006.
- **FR-008**: The disjointness check MUST succeed, with a count per dimension, when no fact, reference seed, or control implementation appears on both a calibration row and a final-test row. It MUST fail and list the offending rows when any of those three is shared. Traces to FV-LEDG-007.
- **FR-009**: The first final-test pass on a split MUST be recorded as pass 1. A later pass on that same split MUST be refused unless an incident row references the first pass. Traces to FV-LEDG-008.
- **FR-010**: An evaluation run MUST be recorded with checkpoint, arm, split, spec tag, thresholds tag, budget used, and pass number. A final-test evaluation run without a thresholds tag MUST be rejected. Traces to FV-LEDG-009.
- **FR-011**: The ledger export MUST include every table and its schema version, and re-import into an empty ledger MUST reproduce the same row counts and row digests. An export from a newer schema version MUST be refused by an older reader. Traces to FV-LEDG-010.
- **FR-012**: A cache key MUST be derived from the model identity hash, the hash of the exact model input, every decoding parameter, and the request kind (generation or scoring). Two requests that differ in any one of those fields MUST map to different keys. A request missing any key field MUST be refused. The input hash MUST be the exact string passed to the tokenizer after any chat template, with no further normalisation. While D-60 is unresolved, key derivation MUST be refused and name D-60, and this requirement MUST NOT be marked implemented. Traces to FV-CACHE-001 and FV-CACHE-002.
- **FR-013**: Each sampled completion MUST be keyed by its sample index and its seed. Requests for sample indices 1 through k MUST yield k distinct entries. A sample index that is not stored MUST be a miss. Traces to FV-CACHE-003.
- **FR-014**: Every lookup MUST emit exactly one event, and that event MUST be one of hit, miss, conflict, or corrupt. A path that returns cache content without an event MUST fail its check. The budget charge for a hit is the policy decision D-20 records and is applied by the query-budget accountant. While D-20 is unresolved, this requirement MUST NOT be marked implemented. Traces to FV-CACHE-004.
- **FR-015**: An entry MUST be returned only after its content digest checks, and that return MUST emit a hit. A corrupted entry MUST be withheld, MUST emit a corrupt event, and MUST be treated as a miss. Traces to FV-CACHE-005.
- **FR-016**: An existing cache entry MUST NOT be replaced by different content under the same key. An identical recomputation MUST leave the stored entry as it was. A different result MUST be refused and MUST emit a conflict event carrying both digests. Traces to FV-CACHE-006.
- **FR-017**: A cache root inside `.factverify/` MUST be refused. A cache root outside that namespace MUST be accepted. Traces to FV-CACHE-007.
- **FR-018**: A cache export MUST include a manifest of keys and digests. Re-import into an empty store MUST return the same content digest for every key. An export whose manifest digest disagrees with its content MUST be refused. Traces to FV-CACHE-008.
- **FR-019**: Resampling MUST use the checkpoint and fact block levels declared in the margins file, and every prompt row of a selected block MUST be included together. A request to resample individual prompt rows MUST be refused. A crossed design MUST resample checkpoints and facts under the declared crossed scheme. A crossed dataset analysed under a nested scheme MUST be refused. While D-07 is unresolved, resampling MUST be refused and name D-07, and this requirement MUST NOT be marked implemented. Traces to FV-STAT-001 and FV-STAT-002.
- **FR-020**: The difference in false-certification rate MUST be computed from paired per-case differences using the same resample for both evaluators. Each resample MUST index identical cases in both arms. Arms with different case sets MUST be refused, and the refusal MUST list the unmatched cases. Case weighting is decision D-06. While D-06 is unresolved, a weighted estimate MUST be refused and name D-06. Traces to FV-STAT-003.
- **FR-021**: False-certification rate MUST be reported for each control family and overall, aggregated as decision D-10 records. A family with no evaluated cases MUST report a count of zero and MUST NOT report a rate. While D-10 is unresolved, this estimate MUST be refused and name D-10, and this requirement MUST NOT be marked implemented. Traces to FV-STAT-004.
- **FR-022**: When an error count is zero, the estimate MUST report a point estimate of 0 and a positive upper bound computed by the procedure decision D-03 records. A zero-width interval at 0 MUST fail its check. While D-03 is unresolved, this estimate MUST be refused and name D-03, and this requirement MUST NOT be marked implemented. Traces to FV-STAT-005.
- **FR-023**: Multiplicity adjustment MUST use only the family and the procedure declared in the margins file. Adjusted values MUST match the reference result on the fixture for that declared procedure. An undeclared family or procedure MUST be refused. While D-08 is unresolved, adjustment MUST be refused and name D-08, and this requirement MUST NOT be marked implemented. Traces to FV-STAT-006.
- **FR-024**: The same verdict table, design, and seed MUST produce the same estimates and bounds. The output MUST record the seed, the replicate count, and the design. Replicate count, interval type, and coverage-check tolerance are decision D-57. While D-57 is unresolved, estimation that would choose those locally MUST be refused and name D-57, and this requirement MUST NOT be marked implemented. Traces to FV-STAT-007.
- **FR-025**: A coverage check on simulated data with a known rate and a known cluster structure MUST produce intervals whose empirical coverage is within the D-57 tolerance of the nominal rate. A prompt-row resample on the same data MUST fall short of that nominal rate. This requirement may be waived only with a recorded reason. While D-57 is unresolved, the check MUST be refused and name D-57. Traces to FV-STAT-009.
- **FR-026**: Threshold selection MUST return the upper confidence bound on the false-rejection rate for each candidate threshold when every input row is from the calibration split. It MUST be refused when any input row has split final-test. Traces to FV-STAT-008.
- **FR-027**: A verdict row MUST be rejected for analysis when its checkpoint ledger identifier or its evaluation-run identifier is missing or unknown to the ledger. The rejection MUST name the row. Rows whose identifiers resolve MUST be accepted. Traces to FV-STAT-010.
- **FR-028**: On any bad, missing, or unresolved input, the operation MUST fail closed and MUST name the missing field. No requirement MAY be marked implemented while a blocking decision it depends on remains open.

### Key Entities

- **Checkpoint row**: One immutable record of a checkpoint. It carries identity hash, parent, configuration hash, seed, fact, split, role, tier, family and method, spec tag, git commit, dirty flag, cost, wall-clock, status, row identifier, and timestamp. Role is the oracle role. Tier is the D-56 value.
- **Evaluation-run row**: One immutable record of a finished evaluation. It carries run identifier, checkpoint, arm, split, spec tag, thresholds tag, budget used, and pass number.
- **Incident row**: A record that references an earlier final-test pass. A later pass on that same split is recordable only when this row exists.
- **Lineage**: The parent chain from a checkpoint row back to its root.
- **Disjointness report**: Counts, and on failure the offending rows, for fact, reference seed, and control implementation across calibration and final-test rows.
- **Ledger export**: Every ledger table plus its schema version. Re-import reproduces the same rows. A newer schema version is refused by an older reader.
- **Cache request**: Model identity hash, exact model input after any chat template, decoding parameters including seed and sample index, and request kind (generation or scoring).
- **Cache entry**: The completion or the scores, token counts, time of creation, content digest, and the producer run identifier.
- **Cache event**: Exactly one of hit, miss, conflict, or corrupt for each lookup. The budget charge for a hit is outside this feature.
- **Cache export**: A portable bundle plus a manifest of keys and digests.
- **Verdict row**: One case for analysis. It carries checkpoint ledger identifier, fact, arm, verdict, oracle label, control family, split, and evaluation-run identifier.
- **Estimate table**: False-rejection rate, false-certification rate overall and per control family, and the difference in false-certification rate against each baseline, each with its interval, counts, and seed. The output also records replicate count, design, spec tag, and the digest of the input.
- **Margins record**: The resampling design (D-07), case weighting (D-06), confidence procedure (D-03), multiplicity family and procedure (D-08), and aggregation (D-10), read from the frozen margins file. This feature does not edit that file.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every checkpoint an evaluator uses has a committed ledger row, and the lookup returns its role and split. An identity hash with no row is refused in 100% of such lookups.
- **SC-002**: Every accepted checkpoint row contains each required field and a generated row identifier and timestamp. A row with an empty required field is rejected, naming that field, in 100% of such adds, and the ledger is unchanged.
- **SC-003**: Every accepted role is one of base, finetuned, reference, control, or candidate, and every accepted tier is a D-56 value. Any other value is rejected in 100% of such adds. No checkpoint row is accepted while D-56 is open.
- **SC-004**: Every child whose parent is present has a lineage that reaches the base. Every child that names an absent parent is rejected in 100% of such adds.
- **SC-005**: Every correction is a new row pointing at an unchanged original. Every attempt to change or delete an existing row fails. A second row for an identity hash that does not point at the existing row is rejected in 100% of such adds.
- **SC-006**: Concurrent adds of one row each leave exactly that many rows. An interrupted add leaves no partial row.
- **SC-007**: Every final-test row from a clean tree stores commit, clean flag, and spec tag. Every final-test row from a dirty tree is rejected. Every non-final dirty row is stored marked dirty.
- **SC-008**: A disjoint ledger passes the check with a count for fact, reference seed, and control implementation. A ledger that shares any one of those across calibration and final-test fails and lists the offending rows, in 100% of such checks.
- **SC-009**: The first final-test pass on a split is pass 1. A second pass on that split with no incident row referencing the first is refused in 100% of such attempts.
- **SC-010**: Every recorded evaluation run carries checkpoint, arm, split, spec tag, thresholds tag, budget used, and pass number. A final-test run without a thresholds tag is rejected in 100% of such records.
- **SC-011**: Ledger re-import reproduces row counts and row digests in 100% of round trips. A newer schema export is refused by an older reader in 100% of such imports.
- **SC-012**: Requests that differ in any key field, including one whitespace character in the model input, map to different keys in 100% of such pairs. A request missing a key field is refused. The same rendered input hashes identically on repetition. Sample indices 1 through k yield k distinct entries, and an unstored index is a miss.
- **SC-013**: Every intact read returns the entry with a hit. Every corrupted read is withheld, emits corrupt, and is a miss. Every conflicting write is refused and the event carries both digests. An identical recomputation leaves the stored entry as it was.
- **SC-014**: A cache root inside `.factverify/` is refused in 100% of such initialisations. Every lookup emits exactly one event. A path that returns content without an event fails its check.
- **SC-015**: Cache re-import returns the same content digest for every key. An export whose manifest digest disagrees with its content is refused in 100% of such imports.
- **SC-016**: Under a declared block design, every resample keeps each selected block's prompt rows together. A prompt-row resample is refused. A crossed design resamples checkpoints and facts under that scheme, and a nested scheme on a crossed set is refused.
- **SC-017**: Every paired difference indexes the same cases in both arms. Unmatched case sets are refused and the unmatched cases are listed, in 100% of such estimates.
- **SC-018**: Every family estimate has one row per family plus an overall row under a closed D-10 record. A family with no cases reports a count of zero and no rate. A zero-error estimate reports point estimate 0 and a positive upper bound under a closed D-03 record. A zero-width interval at 0 fails its check.
- **SC-019**: Declared multiplicity adjustments match the fixture reference. An undeclared family or procedure is refused. Two runs with the same verdict table, design, and seed match on every estimate and bound, and the output records seed, replicate count, and design.
- **SC-020**: On the declared coverage simulations, empirical coverage is within the D-57 tolerance of the nominal rate, and a prompt-row resample on the same data falls short of that rate.
- **SC-021**: Threshold selection on calibration rows returns one false-rejection upper bound per candidate threshold. A call that includes any final-test row is refused in 100% of such calls.
- **SC-022**: Verdict rows with resolvable ledger identifiers are accepted. A missing or unknown identifier fails the load and names the row, in 100% of such rows.
- **SC-023**: Requirement checks FV-LEDG-001 through FV-LEDG-011, FV-STAT-001 through FV-STAT-010, and FV-CACHE-001 through FV-CACHE-008 pass before a checkpoint is evaluated, an interval is reported, or a cached generation is treated as the original. FV-LEDG-002 and FV-LEDG-004 are not treated as passed while D-56 is open. FV-CACHE-001 is not treated as passed while D-60 is open. FV-CACHE-004 is not treated as passed while D-20 is open. FV-STAT-001 and FV-STAT-002 are not treated as passed while D-07 is open. FV-STAT-004 is not treated as passed while D-10 is open. FV-STAT-005 is not treated as passed while D-03 is open. FV-STAT-006 is not treated as passed while D-08 is open. FV-STAT-007 and FV-STAT-009 are not treated as passed while D-57 is open. A weighted estimate is not treated as passed while D-06 is open. FV-LEDG-011 and FV-STAT-009 may be waived only with a recorded reason.

---

## Assumptions

- The caller supplies checkpoint records, evaluation-run records, verdict rows, cache requests, the spec root, and a seed. The frozen spec is at `spec-v1`. This feature reads spec fields and decision records. It does not edit `.factverify/spec/`.
- In scope: the run ledger for checkpoints and evaluation runs, including lineage, append-only corrections, split disjointness, and the single final-test pass; cluster intervals for false-rejection rate, false-certification rate, and the difference in false-certification rate; the generation cache, including key, integrity, conflict, events, location, and export.
- Out of scope: producing checkpoints (plan tasks P2-1 and P2-3); computing the model identity hash (P2-0), which this feature stores and keys on as it is given; verdict content and query-budget charging (P2-2), including whether a cache hit costs budget (D-20, enforced there); the values of the statistical policy, which live in the margins file (P0-5); the power analysis (P4-1); the gate status table. The raw-generation archive used for annotation may share storage with the cache. This feature's duty is replay of an identical request.
- The execution plan's tracking conventions name role as reference, control, or candidate, and task P2-5 names tier. The ledger requirements note keeps both, and its role vocabulary is base, finetuned, reference, control, and candidate. This spec follows that note. Tier has no values until D-56.
- A root checkpoint names no parent. That is the reading on which a base row can exist and lineage can end. A named parent that is absent is a broken chain and is rejected.
- A second committed row for an identity hash is accepted only as a superseding correction. The requirements note requires append-only corrections and does not describe a silent second row for the same identity.
- The disjointness dimensions this feature checks are fact, reference seed, and control implementation, which is what FV-LEDG-007's scenarios test. The proposal's cross-fitted split also names semantic templates. Template-group disjointness remains check V13 in the spec freeze. This feature does not add a fourth dimension.
- The ledger requirements interface names a tabular export and a structured export. Both carry the schema version and re-import to the same rows.
- Cache entries record the time of creation and the producer run identifier, from the cache note's provenance constraint. Generations stay outside `.factverify/`, which is check V23.
- The cache holds outputs only. It has no split logic and does not move a fact, a seed, a template group, or a control implementation between calibration and final-test.
- Nine decisions remain open. Requirements that depend on them are written against the decision record:
  - **D-56** — what `tier` means (block number, pilot / decisive / stress, or dropped in favour of role). Blocks FR-002 and FR-003. Owner. While unresolved, a checkpoint add is refused.
  - **D-60** — whether software versions are part of the cache key. Blocks FR-012. Owner. While unresolved, key derivation is refused.
  - **D-20** — whether a cache hit costs query budget. Blocks FR-014. Owner. The charge is applied by the query-budget accountant. While unresolved, the event requirement is not marked implemented.
  - **D-07** — dependence structure and resampling design. Blocks FR-019. Owner. While unresolved, resampling is refused.
  - **D-06** — case definition and weighting. Blocks a weighted paired estimate and family aggregation. Owner. The same-case pairing check does not wait on a weight. The requirements note's decision table lists D-06 against FV-STAT-003 and FV-STAT-004; the FV-STAT-003 header lists no blocker. This spec follows the decision table for weighting and follows the FV-STAT-003 text for pairing.
  - **D-10** — overall versus per-family aggregation. Blocks FR-021. Owner. While unresolved, the family estimate is refused.
  - **D-03** — confidence procedure for a zero error count. Blocks FR-022. Owner and supervisor. While unresolved, a zero-error estimate is refused. The handbook's numerical illustration is not adopted as the procedure.
  - **D-08** — multiplicity family and procedure. Blocks FR-023. Owner. While unresolved, adjustment is refused.
  - **D-57** — replicate count, interval type, and coverage-check tolerance. Blocks FR-024 and FR-025. Owner. While unresolved, estimation that would choose those locally is refused.
- No requirement may be marked implemented while a blocking decision it depends on remains open.
- The three source requirements notes are `draft`. The execution-plan note is `planned`. The proposal is `draft`. The handbook is `draft`.
