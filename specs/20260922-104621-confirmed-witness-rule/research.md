# Research: P0-6 Confirmed-Witness Rule and Scorer

## R1 — Witness Artifact Format

**Decision**: Markdown with YAML frontmatter at `.factverify/spec/witness_rule.md` (same hybrid as `access_profile.md`).

**Rationale**: Constitution Spec Namespace and FV-SPEC-067 name `witness_rule.md`. The artifact needs structured fields (routes, rubric enums, refs) plus normative prose tables for decision layers. Pure YAML would lose the handbook-style decision tables; pure Markdown would weaken machine checks.

**Alternatives considered**:
- Pure YAML worksheet only: rejected — constitution and requirements mandate `witness_rule.md`; prose tables are part of the reviewed contract.
- Separate schema JSON + instance YAML: deferred — optional later; P0-4 pattern already validates frontmatter without a separate Draft-2020-12 schema.

## R2 — Three Separated Layers

**Decision**: Frontmatter and body MUST define three non-substitutable layers:

| Layer | Question | Output |
|-------|----------|--------|
| Response scoring | Does this response recover the contracted relation in context? | Label + refusal flag |
| Confirmation | Is the evidence reproducible under an approved route? | Candidate / confirmed witness |
| Case decision | Do recovery, locality, access, and completeness gates hold? | Accept / reject / non-identifiable / incomplete |

Using a response label as a final verdict fails validation (FV-SPEC-067).

**Rationale**: Study Guide §2; proposal v3 confirmation requirement; handbook V16/V18.

**Alternatives considered**:
- Binary pass/fail from a single correct answer: rejected — conflates layers and inflates false certification.
- Older Controlled-Setting formula with mandatory privacy term as primary: rejected — follow proposal v3 where it differs (privacy optional / scoped).

## R3 — Response Rubric Shape

**Decision**: Declare direction-aware expected answer roles (`object`, `subject`, `truth_value`, and explicit many-valued `set_membership` policy). Correctness and refusal are separate fields. Categories: correct, incorrect/contradictory, ambiguous, non-answer, technical_missingness, plus `refusal_flag: bool`. Ambiguity policy is a named field referencing D-34 (adjudicate / conservative_flag / analyze_separately) — never left to per-case judge discretion.

**Rationale**: FV-SPEC-068; Study Guide §§3–5; disclosure-plus-refusal and negated-entity fixtures.

**Alternatives considered**:
- Substring/entity presence as sufficient recovery: rejected — “Hà Nội is not the capital” false positive.
- Merge refusal into correctness: rejected — hides disclosure behind disclaimer language.

## R4 — Raw Score Semantics

**Decision**: Per likelihood/rank channel, require explicit: `normalization` (`total_logprob` | `length_normalized`), `tokenizer_prefix_policy`, `alias_aggregation`, `candidate_universe`, `tie_rule`, `observation_point`, `recovery_orientation`. Insufficient top-k / missing raw values → status `unavailable` or `invalid`, never silent approximation. Do not average correctness with raw rank on one scale.

**Rationale**: FV-SPEC-069; Study Guide §5.4; Constitution I5/I7 interactions with Route B.

**Alternatives considered**:
- Default length-normalize without declaration: rejected — changes quantity silently.
- Invent missing sequence likelihood from top-1 token rank: rejected — invalid approximation.

## R5 — Route A Family Independence

**Decision**: Route A requires two approved independent template family IDs with predeclared `grouping_policy_ref` (D-35), discovery vs confirmation roles, and repetition counts. Punctuation variants, language labels alone, clue-bearing responses, and false-statement rejection do not automatically supply two positive-target witnesses.

**Rationale**: FV-SPEC-070; Study Guide §6 Route A; Constitution I2 (clue/inference must not enter clean E recovery).

**Alternatives considered**:
- Any two correct paraphrases count: rejected — not independent under grouping policy.
- Language change alone as independence: rejected — Study Guide §6.

## R6 — Route B Seed Type

**Decision**: Route B statistic block requires `score_statistic_ref`, eligible prompts, margins/reference refs, `seed_type: training_or_update`, `seed_count`, and `reproducibility_rule`. Substituting decoding seeds, repeated queries, or export variants of one checkpoint fails confirmation.

**Rationale**: FV-SPEC-071; handbook V19; Constitution I7.

**Alternatives considered**:
- Treat decoding seed diversity as replication: rejected — observation-level, not intervention-level.
- Skip Route B until Profile B/C scores exist: allowed as `enabled: false` with explicit reason; at least one of A/B/C must remain enabled.

## R7 — Route C Criterion Crossing

**Decision**: Route C requires parent/child hashes, recipe/data exposure labels, consistent scoring before/after, required reference transforms, replication, budget consumption, and post-transform locality. Target-exposed reacquisition is labelled separately from residual-memory recovery. A single output change is insufficient.

**Rationale**: FV-SPEC-072; Study Guide §6 Route C.

**Alternatives considered**:
- Any before/after answer change = flip: rejected — must cross predeclared criterion with replication.
- Collapse exposure into recovery: rejected — target teaching can restore answers without residual memory.

## R8 — Case Verdict Gates

**Decision**: Acceptance requires conjunction of: simultaneous excess-recovery upper bounds vs channel margins (P0-5 refs), separate locality bucket gates, access/completeness conditions (P0-4 status vocabulary), and no disqualifying confirmed witness. “No witness” ≠ automatic accept. Wide intervals → inconclusive/incomplete per declared mapping (D-14/D-31), not fabricated recovery. Locality failure is its own rejection reason.

**Rationale**: FV-SPEC-073; Study Guide §§7–9, 11.

**Alternatives considered**:
- Pass when no recovery found: rejected — protocol incompleteness / locality damage still reject.
- Pool locality into one average: rejected — conceals bucket damage.

## R9 — Aggregation and Budget Reservation

**Decision**: Cross-check each enabled route against P0-3 reserved confirmation costs. Require a declared whole-rule `aggregation_policy` (calibrated as a search+confirm unit). Reject unrestricted search, absent reservation, or raw maximum as primary statistic; maxima may remain `diagnostic_only`.

**Rationale**: FV-SPEC-074; handbook V16/V18; Constitution I4/I5.

**Alternatives considered**:
- Primary verdict = max probe score: rejected — I5.
- Confirmation without budget reserve: rejected — changes false-alarm behaviour.

## R10 — Annotation Protocol

**Decision**: Require review records under `.factverify/witness/reviews/` documenting: blinded annotators (no system identity), preselected double-annotation subset, adjudication outcomes, confusion table, raw agreement, and kappa (or `kappa: undefined` when denominator zero). Sole-LLM adjudication or outcome-driven rubric change fails approval. Illustrative κ=0.8 is not an adopted threshold (D-37).

**Rationale**: FV-SPEC-075; Study Guide §10; proposal §8.

**Alternatives considered**:
- LLM-only labelling for control/witness labels: rejected — proposal forbids sole oracle.
- Freeze rubric after seeing final-test disputes: rejected — outcome-driven rewrite.

## R11 — Evidence Record Schema

**Decision**: Evidence fixtures (JSON) must resolve: `case_id`, `fact_id`, `model_hash`, contract ref, `access_profile`, channel, template family IDs, raw response IDs, scorer/review IDs, reference statistic, confirmation route, seed types/ids, transforms, budget consumed, verdict status, claim_scope, limitations. Missing raw record, stale scorer revision, or hidden control label as recovery evidence → invalid. Ground truth stored separately from evidence used as recovery.

**Rationale**: FV-SPEC-076; Study Guide §12 worksheet.

**Alternatives considered**:
- Verdict-only logs without raw IDs: rejected — non-reconstructable.
- Embed oracle control labels inside recovery evidence: rejected — leakage / circular proof.

## R12 — CLI Scope, Engine, and Fixtures

**Decision**: `--scope witness-rule`; engine in `tools/witness_rule_validator.py`; fixtures under `tests/fixtures/witness_rule/{valid,invalid,baselines}/` (aligned with `access_profile`). Requirements’ `tests/fixtures/p0_6/` is the same conceptual set. Report default `reports/p0-6-validation.json`. Optional `--witness-dir`, `--strict`, `--baseline-suite`.

**Rationale**: Consistency with P0-4; validate_spec already has a `--witness-rule` path flag used by attacks scope — extend scopes list and dispatch similarly to access-profile/margins.

**Alternatives considered**:
- Literal `tests/fixtures/p0_6/` only: acceptable but inconsistent with sibling features.
- Fold into `margins_validator.py`: rejected — different artifact and rule IDs; build order has P0-6 before/beside P0-5.

## R13 — Unresolved Decisions vs Strict Mode

**Decision**: Non-strict structural validation may report open decision refs (`DECISION_REQUIRED` / `null` operational parameters) as pending without inventing values. Strict readiness requires resolved applicable decisions, current annotation/rubric reviews, consistent cross-file policies (answers, closure, attacks budgets, access statuses, margins bounds), and at least one enabled route with complete parameters. Explicit `not_applicable` needs a reason.

**Rationale**: FV-SPEC-077; I8 fail-closed; same incremental pattern as P0-4/P0-5.

**Alternatives considered**:
- Block all validator work until D-* close: rejected — stalls Phase 0.
- Default teaching route parameters: rejected — teaching values become frozen policy.
