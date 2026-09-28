# Feature Specification: P1 Fact Bundle Preparation

**Feature Branch**: `20260928-224019-p1-bundle-prep`
**Created**: 2026-09-28
**Status**: Draft
**Input**: User description: "P1 data preparation — build source bundles (P1-3), fill neighbourhood stubs (P1-5), entailment audit (P1-4). Adjudication pool (make adjudicate) is complete at ≥40 accepted facts."

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Build Source Bundles (Priority: P1)

The researcher runs `build_bundles.py` against the adjudicated `facts.jsonl` and produces, for each accepted fact, a complete enumerated bundle of TOFU training records that express it — covering both the forward and inverse direction — together with a record-to-fact index and a leave-out manifest for each reference model training run.

The bundles become the training corpus for finetuning fictional authors into the base model. Without them, Phase 3 (Block 0 pilot) cannot start: there is no data to finetune on, and the leave-out manifests that define what a retain-only reference model trains on do not exist.

**Why this priority**: Every downstream task — neighbourhood population, entailment audit, finetuning, evaluation — depends on the bundle and index existing. It is the structural foundation of Stage A.

**Independent Test**: Running `build_bundles.py` against the accepted facts and verifying that `data/controlled/sources/bundles/<fact_id>.json`, `data/controlled/sources/index.jsonl`, and `data/controlled/leaveout/<k>.json` are written with correct content delivers a fully testable milestone.

**Acceptance Scenarios**:

1. **Given** an accepted fact in `facts.jsonl`, **When** `build_bundles.py` completes, **Then** `data/controlled/sources/bundles/<fact_id>.json` exists and contains at least the D-66 minimum number of records for both the forward and the inverse direction.
2. **Given** `data/controlled/sources/index.jsonl`, **When** any training record is looked up, **Then** the index returns the complete set of fact IDs that record expresses (possibly empty).
3. **Given** a TOFU record that expresses two target facts simultaneously, **When** the build runs, **Then** it is split, rewritten, or excluded per the D-66 policy, and the outcome is recorded in `transformations.jsonl`.
4. **Given** a training record that instantiates any evaluation template group, **When** the build runs, **Then** it raises and names the record and the conflicting group.
5. **Given** a leave-out manifest for fact k, **When** any record in that manifest is checked against the index, **Then** no record is indexed to fact k, and the manifest carries a dataset digest.
6. **Given** a fact without a gate verdict of `pass`, **When** `build_bundles.py` is invoked for that fact, **Then** it refuses and names the fact.

---

### User Story 2 — Populate Locality Neighbourhoods (Priority: P2)

The researcher runs `build_neighbourhoods.py` to replace all `[P1-5 stub]` placeholder entries in each fact contract's `retained_neighbourhood` field with real, sourced items drawn from the leave-out training set. The four buckets — same_subject, same_relation, compositional, global — must each contain at least the D-38 minimum, with no stubs remaining.

These neighbourhood items become the retain probes used by the evaluator (C5 locality channel) to measure whether unlearning damaged nearby knowledge.

**Why this priority**: Neighbourhood population depends on the bundle index from P1-3 but does not require the entailment audit. It can proceed as soon as bundles are ready, making it the second priority.

**Independent Test**: Running `build_neighbourhoods.py` on the accepted facts and verifying that `data/controlled/neighbourhoods.jsonl` contains ≥1 non-stub item per bucket per fact, with each item traceable to a leave-out record or a declared global source, delivers a testable slice.

**Acceptance Scenarios**:

1. **Given** an accepted fact, **When** `build_neighbourhoods.py` completes, **Then** `data/controlled/neighbourhoods.jsonl` contains items for that fact in all four approved buckets, each meeting the D-38 per-bucket minimum, with no `[P1-5 stub]` text remaining.
2. **Given** a same_subject or same_relation item, **When** checked against the record index and the fact's leave-out manifest, **Then** at least one record in the manifest expresses that item.
3. **Given** a global item, **When** its source is checked, **Then** it traces to a pinned TOFU `real_authors` or `world_facts` row (or a D-38-declared alternative), and no finetuning record is indexed to it.
4. **Given** a compositional item, **When** run through the entailment screen against its target fact, **Then** it is classified `clean` — the answer does not require the target fact.
5. **Given** a fictional entity used as a neighbourhood item for a construction-split fact, **When** checked against split assignments, **Then** it belongs to the construction split (not calibration or final-test).
6. **Given** a fact that cannot reach the D-38 minimum in any bucket from available retained facts, **When** the build runs, **Then** it raises naming the fact and the deficient bucket.

---

### User Story 3 — Entailment Audit (Priority: P3)

The researcher runs `entailment_audit.py` against every leave-out manifest to confirm that no retained training record duplicates or entails its target fact. Flagged records are human-adjudicated; confirmed failures are remediated (rewritten or the fact is excluded). The audit is bound to manifest digests so that any subsequent edit to records or manifests invalidates it.

This audit protects the validity of the entire study: if a retained record entails the target, the reference model $M_R$ already answers the target correctly, and no unlearning method can pass a clean positive reference — making Gate 1 results uninterpretable.

**Why this priority**: The audit is last because it consumes the bundles (P1-3) and must be completed before Phase 3 training begins. It requires human review time alongside the automated screen.

**Independent Test**: Running the audit on a single fact's leave-out manifest and verifying that all records are classified (`duplicate / entails / clue_bearing / clean`), every flagged record has a human adjudication label, and no confirmed failure remains unresolved, delivers a complete testable slice.

**Acceptance Scenarios**:

1. **Given** a leave-out manifest, **When** audited, **Then** no record in the manifest expresses the target fact in any declared direction under any approved alias.
2. **Given** a record that the D-67 method scores as entailing or clue-bearing for the target, **When** the audit runs, **Then** it is flagged with the method name, score, and threshold recorded.
3. **Given** audit results, **When** the report is built, **Then** every flagged record and every record in the D-67-sized unflagged sample has a human adjudication label and a reader ID.
4. **Given** a confirmed duplicate or entailment, **When** remediation is complete, **Then** a `transformations.jsonl` entry names the action taken, and a re-run of the audit on the updated manifest is clean.
5. **Given** a manifest whose digest has changed since the audit was recorded, **When** the training harness starts on that manifest, **Then** it raises and names the digest mismatch.
6. **Given** a fact with an unresolved confirmed failure when Phase 3 training begins, **Then** the harness refuses that fact.

---

### Edge Cases

- What happens when a TOFU record expresses both a target fact and a retained neighbour simultaneously? (D-66 multi-fact rewrite policy must not couple two reference models.)
- What happens when no TOFU records exist for a fact's inverse direction? (D-66 minimum; build raises; fact may need to be excluded or supplemented.)
- What happens when the entailment screen misses an entailing record? (D-67 unflagged sample estimates the miss rate; human adjudication provides ground truth for the sample.)
- What happens when all same_subject candidates for a fact belong to a different study split? (Build raises; neighbourhood must be sourced from world-facts or the fact reassigned.)
- What happens if a compositional item's independence from the target cannot be determined automatically? (Conservative policy: flagged for human adjudication; rejected if inconclusive.)

---

## Requirements *(mandatory)*

### Functional Requirements

**P1-3 — Source Bundles**

- **FR-001**: The bundle builder MUST include in each fact's bundle every training record that the record-to-fact index maps to that fact (FV-DATA-019).
- **FR-002**: Each bundle MUST contain at least the D-66 minimum number of training records in the forward direction and in the inverse direction (FV-DATA-020).
- **FR-003**: The bundle builder MUST NOT produce any training record whose text instantiates an evaluation template group declared in `closure_templates.yaml` (FV-DATA-021).
- **FR-004**: Every TOFU record that expresses more than one target fact MUST be split, rewritten, or excluded per the D-66 multi-fact policy, with the action and derived record IDs written to `transformations.jsonl` (FV-DATA-022).
- **FR-005**: The bundle builder MUST publish, for every training record, the set of fact IDs it expresses in `data/controlled/sources/index.jsonl` (FV-DATA-023).
- **FR-006**: Each leave-out manifest MUST contain no record indexed to any fact in that leave-out unit, and MUST carry a dataset digest (FV-DATA-024).
- **FR-007**: The bundle builder MUST refuse any fact that does not carry a gate verdict of `pass` from P1-2 (FV-DATA-018 guard).

**P1-5 — Locality Neighbourhoods**

- **FR-008**: The neighbourhood builder MUST populate every approved locality bucket (same_subject, same_relation, compositional, global, plus any D-38-declared additions) with at least the D-38 per-bucket minimum for each accepted fact (FV-DATA-030).
- **FR-009**: Every same_subject and same_relation item MUST be drawn from facts expressed in the target's leave-out training set and MUST NOT come from the target's own bundle (FV-DATA-031).
- **FR-010**: Every global item MUST trace to a pinned TOFU `real_authors` or `world_facts` row (or a D-38-declared alternative) and MUST NOT be indexed to any finetuning record (FV-DATA-032).
- **FR-011**: No compositional item MUST require the target fact to answer — it MUST pass the entailment screen against its target with result `clean` (FV-DATA-033).
- **FR-012**: No fictional entity in a target's neighbourhood MUST belong to a different study split from the target; global real-world items are exempt (FV-DATA-034).

**P1-4 — Entailment Audit**

- **FR-013**: The audit MUST fail when any record in a leave-out manifest expresses its target in any declared direction under any approved alias (FV-DATA-025).
- **FR-014**: The audit MUST flag every retained record that the D-67 method scores as entailing or clue-bearing for the target, storing the method name, score, and threshold (FV-DATA-026).
- **FR-015**: A human adjudication label and reader ID MUST be recorded for every flagged record and for a D-67-sized random sample of unflagged records (FV-DATA-027).
- **FR-016**: Every confirmed duplicate or entailment MUST be resolved by rewriting or excluding the fact, with the action in `transformations.jsonl`; a re-audit on the updated manifest MUST be clean (FV-DATA-028).
- **FR-017**: The audit result MUST be bound to manifest digests; the training harness MUST raise if a manifest digest has changed since the audit was recorded (FV-DATA-029).

### Key Entities

- **Source Bundle** (`data/controlled/sources/bundles/<fact_id>.json`): the complete set of TOFU training records that express a target fact, partitioned by direction. Input to the leave-out manifest builder and the entailment audit.
- **Record-to-Fact Index** (`data/controlled/sources/index.jsonl`): many-to-many map from training record ID to the set of fact IDs it expresses. Consumed by the neighbourhood builder, audit, and leave-out builder.
- **Leave-Out Manifest** (`data/controlled/leaveout/<k>.json`): the training record IDs that constitute the retain-only dataset for reference model $M_R^{(k)}$ — provably excludes fact k. Consumed by the training harness (P2-1) and entailment audit.
- **Neighbourhood Item** (`data/controlled/neighbourhoods.jsonl`): a retain probe in one of four locality buckets, with its expected answer and source citation. Consumed by the locality evaluator (C5 channel).
- **Audit Result** (`results/entailment_audit.jsonl`): per (unit, record, target) classification — `duplicate | entails | clue_bearing | clean` — with method, score, and human adjudication label.
- **Transformation Record** (`data/tofu_derived/transformations.jsonl`): lineage entry for any record that was split, rewritten, or excluded, tracing back to the original TOFU row.

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Every accepted fact with a `pass` gate verdict has a non-empty source bundle covering both forward and inverse directions — 0 facts may proceed to finetuning without a bundle.
- **SC-002**: Every leave-out manifest contains 0 records indexed to its target fact (verified by automated test against the record-to-fact index).
- **SC-003**: Every accepted fact's neighbourhood contains 0 `[P1-5 stub]` placeholders and ≥ D-38 minimum items in each of the four approved locality buckets.
- **SC-004**: The entailment audit classifies 100% of records in every leave-out manifest; every flagged record has a human adjudication label; 0 confirmed duplicates or entailments remain unresolved.
- **SC-005**: The audit digest-binding check is verified by a passing automated test — any manifest change causes the training harness to refuse.
- **SC-006**: `make test` passes all tests in `tests/test_bundles.py`, `tests/test_neighbourhoods.py`, and `tests/test_entailment_audit.py`.

---

## Assumptions

- **Adjudication complete**: P1-0 (`make adjudicate`) has produced ≥40 accepted facts; no further adjudication runs are needed before P1-3 begins.
- **Execution order**: P1-3 must complete before P1-5 or P1-4 begin; both consume the bundle index and leave-out manifests.
- **D-66 (records per direction, multi-fact policy)**: open decision; must be resolved before `build_bundles.py` is implemented. Provisional: minimum 3 records per direction; multi-fact records split where possible, excluded otherwise.
- **D-69 (leave-out unit definition)**: open decision; must be resolved before leave-out manifests are built. Provisional: leave-one-fact-out — each fact gets its own manifest.
- **D-38 (bucket vocabulary and per-bucket minimum)**: open decision for P1-5. Provisional: 4 buckets as currently defined, minimum 1 item per bucket for Block 0 pilot.
- **D-39 (alias/language scope)**: open decision for P1-4 entailment check. Provisional: English-only for Block 0, using only the aliases declared in each fact contract.
- **D-67 (entailment method, threshold, sample size)**: open decision for P1-4. Provisional: exact-string match for duplication check (FV-DATA-025); LLM judge for entailment screen (FV-DATA-026); unflagged sample = 10% of clean records, minimum 5.
- **D-42 (template-group assignment)**: open decision blocking training-wording disjointness check (FR-003). Script must read template-group assignments from `closure_templates.yaml`, not hard-coded.
- **Scope**: Block 0 pilot facts only (construction + calibration splits). Final-test facts are excluded from all outputs until the final-test pass (FV-DATA-018 guard enforced).
- **No model or API calls in P1-3 or P1-5**: both scripts are CPU-only; GPU and API budget is not consumed.
