# Research: P1 Fact Bundle Preparation

**Feature**: 20260928-224019-p1-bundle-prep
**Date**: 2026-09-28

---

## D-66 — Records per direction and multi-fact rewrite policy

**Decision**: Minimum **3 records per direction** (forward and inverse) per bundle for Block 0 pilot. Multi-fact TOFU rows are **split** into single-target records where the subject/relation/object can be isolated; **excluded** with a logged reason if splitting would corrupt the text or if no clean single-target form exists.

**Rationale**: 3 gives a small but non-trivial training signal for both directions (avoiding the reversal curse) without imposing a minimum that most TOFU entities can't meet at this stage. Exclusion is safer than rewriting because rewriting introduces generated text that may not match the TOFU style, and the entailment audit cannot easily validate generated text.

**Alternatives considered**:
- Minimum 1: too weak; a single training record is vulnerable to memorization artifacts.
- Minimum 5: may exclude too many facts from the Block 0 pilot pool of ~35.
- LLM rewriting of multi-fact rows: adds API cost and provenance complexity; deferred to Block 1 if needed.

---

## D-69 — Leave-out unit: fact-level vs group-level

**Decision**: **Leave-one-fact-out** — each target fact $k$ gets its own manifest containing all training records except those in fact $k$'s bundle.

**Rationale**: The simplest unit that is scientifically correct for Stage A. Group-level leave-out (leave-one-author-out) would be needed if facts about the same author entail each other — but the entailment audit (P1-4) catches this. If the audit finds inter-fact entailments within an author, those facts will be handled by remediation (exclusion or rewrite) before manifests are finalized.

**Alternatives considered**:
- Leave-one-author-out: more expensive (fewer training authors per run) and unnecessary if entailment audit is effective. Deferred to Block 1 if fact-level proves insufficient.

---

## D-38 — Locality bucket vocabulary and per-bucket minimum

**Decision**: **4 buckets** as currently defined — same_subject, same_relation, compositional, global. Per-bucket minimum: **1 item** for Block 0. No fifth bucket for Block 0.

**Rationale**: 1 item per bucket is the smallest non-trivial neighbourhood that still exercises all four locality dimensions. The P1-5 stubs in the current facts.jsonl already have same_subject and same_relation filled for most facts; compositional and global stubs need to be replaced. Block 1 will revisit the minimum based on Block 0 locality variance.

**Alternatives considered**:
- 3 items per bucket: desirable for statistical reasons but risks excluding too many facts at Block 0 stage. Revisit at P4-1 power analysis.
- Fifth bucket (e.g. cross-entity compositional): deferred — no agreed vocabulary yet.

---

## D-39 — Alias/language scope for entailment check

**Decision**: **English-only, contract-declared aliases only** for Block 0. The entailment check (FV-DATA-025) tests for the subject alias, relation alias, and object alias as declared in each fact contract's `aliases` field, in both argument orders (forward and inverse).

**Rationale**: Block 0 is instrument validation; multilingual scope is a Block 3 concern. Restricting to contract-declared aliases keeps the duplication check deterministic and free of model calls.

**Alternatives considered**:
- All Wikipedia aliases: would require an external lookup not available at Block 0 compute level.
- NLP-based alias expansion: adds non-determinism; deferred to D-39's full resolution before Block 1.

---

## D-42 — Template-group assignment (training-wording disjointness)

**Decision**: Template group membership is read directly from `closure_templates.yaml` (`group` field on each template). A training record is disallowed if its text, after stripping the fact values, matches the surface pattern of any template in any group.

**Rationale**: The spec (FV-SPEC-021) already defines `group` on each template. Reading it from the file keeps the check spec-coupled rather than hard-coded.

**Implementation note**: The matching is pattern-level (does the training record use the same question wording as an evaluation template?), not answer-level. This is conservative — any surface match disqualifies the record regardless of whether the answer is correct. Records from TOFU's narrative paragraphs are unlikely to match question-format templates.

---

## D-67 — Entailment method, flag threshold, and unflagged sample size

**Decision**:
- **Duplication check (FV-DATA-025)**: exact string match for subject alias + object alias in the record text, in both argument orders. No model call. Fast, deterministic, zero false negatives for verbatim TOFU rows.
- **Entailment screen (FV-DATA-026)**: LLM judge (same Anthropic client already used in the pipeline) with a binary prompt: "Does this training record allow a reader to infer [subject] [relation] [object] without being told the answer?" Response cached. Flag threshold: judge says "yes".
- **Unflagged sample size**: 10% of unflagged records, minimum 5, maximum 20 per fact. Human adjudicates all flagged + this sample.

**Rationale**: The duplication check catches the easy cases (verbatim TOFU QA rows) without any model cost. The LLM judge covers descriptive paragraphs that could identify the answer through clue-bearing context (e.g. "the LGBTQ+ author from Santiago who writes true crime" identifies nationality without stating it). The 10% sample gives an empirical miss-rate estimate; capping at 20 keeps human effort tractable for Block 0's ~35 facts.

**Alternatives considered**:
- NLI model (e.g. NLI-DeBERTa): faster than LLM, but requires a separate model download and is less reliable on TOFU's varied text styles. Revisit for Block 1 if LLM cost is prohibitive.
- Exhaustive human review of all records: correct but infeasible at scale. The sampled approach with a miss-rate estimate is the standard in data auditing.

---

## Current data state (observed 2026-09-28)

- `data/tofu_derived/mentions.jsonl`: 1720 total — 197 accepted, 3 rejected, 1387 pending, 133 span_unresolved.
- `data/controlled/facts.jsonl`: 35 draft contracts covering occupation, birthplace, nationality, genre across ~10 fictional authors.
- `data/tofu_derived/transformations.jsonl`: existing transformation records from the extraction phase; build_bundles.py will append to this file.
- `data/tofu_derived/reviewer_response_cache.jsonl`: 542 entries (from adjudication); not consumed by P1-3/P1-4/P1-5.
- TOFU dataset: available at `~/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68/` (pinned in source_manifest.json).
- `data/controlled/sources/`: does not exist yet — created by build_bundles.py.
- `data/controlled/leaveout/`: does not exist yet.
- `data/controlled/neighbourhoods.jsonl`: does not exist yet.
- `results/entailment_audit.jsonl`: does not exist yet.
