# Research: P0-4 Access Profile and the Identifiability Limit

## R1 — Access Profile Artifact Format

**Decision**: YAML frontmatter in a Markdown document (`access_profile.md`), consistent with the convention established for `witness_rule.md` in the spec namespace.

**Rationale**: The access profile contains both machine-readable fields (capabilities, roles, version, references) and prose sections (provenance procedure, identifiability justification, limitations). YAML frontmatter + Markdown body is the natural fit. Pure YAML would lose the narrative context; pure Markdown would require ad-hoc parsing.

**Alternatives considered**:
- Pure YAML: rejected — prose sections (provenance procedure, identifiability argument) don't fit well in YAML values.
- JSON with separate prose files: rejected — splits a single conceptual artifact into multiple files with cross-reference overhead.
- Structured Markdown with heading-based parsing: rejected — fragile; YAML frontmatter is standard and tooling-friendly.

## R2 — Capability Vocabulary

**Decision**: Four-value state vocabulary: `declared`, `verified`, `unavailable`, `unverified`. Profile letters A/B/C are shorthand labels, not capability states.

**Rationale**: The requirements doc (FV-SPEC-048) explicitly distinguishes "declared" from "verified" — a provider claiming raw scores doesn't mean we've confirmed pre-mask access. `unavailable` is an explicit negative. `unverified` means declared but not yet confirmed. Profile A/B/C summarizes what's *intended*, but each specific capability (text, scores, internals, candidate_scoring, controllable_decoding) carries its own state independently.

**Alternatives considered**:
- Binary available/unavailable: rejected — loses the declared-vs-verified distinction that FV-SPEC-048/049 require.
- Three-value (declared/verified/unavailable): rejected — needs an explicit "haven't checked yet" state for partial verification.

## R3 — Frontmatter Schema Structure

**Decision**: The YAML frontmatter contains structured fields for version, profile, per-system capabilities, measurement_point, score_scope, provenance references, permitted_sources, interventions, historical_access, handling_policies, budget_ref, claim_refs, and blocking_decisions. Each system gets a sub-mapping under `systems:` with its own capabilities, manifest_ref, and verification_state.

**Rationale**: Per-system capabilities allow different systems (e.g., base model vs. unlearned candidate vs. reference) to declare different access levels. This matches the evaluator architecture where the reference model might have C-level access while the candidate has only A.

**Alternatives considered**:
- Single flat capability list: rejected — different systems in the protocol may have different access levels.
- Separate profile files per system: rejected — over-fragmentation for what's typically 2-4 systems.

## R4 — Intervention vs. Observation Separation

**Decision**: The profile has two independent sections: `observations` (what can be seen) and `interventions` (what can be modified). Each intervention has: `action`, `actor_role`, `approved_recipes`, `artifact_lineage`, `requires_capabilities`. Seeing logits (B) or weights (C) does not automatically populate the interventions section.

**Rationale**: FV-SPEC-050 explicitly requires this separation. An evaluator with B-level observation might need an operator (different role) to export a checkpoint for quantization. The recipe reference and lineage requirement prevent undeclared modifications.

**Alternatives considered**:
- Combined permission model: rejected — conflates observation and modification rights, which is exactly the bug FV-SPEC-050 prevents.

## R5 — Status Contract Design

**Decision**: Four statuses as an enum: `confirmed_recovery`, `conformance`, `non_identifiable`, `incomplete`. Each has a `requires` field listing the evidence types needed. No automatic promotion path exists between statuses.

**Rationale**: FV-SPEC-053 requires distinct statuses with no silent promotion. A missing raw score → `incomplete`, not `non_identifiable`. A completed test without a confirmed witness → `incomplete`, not `conformance`. The status contract is a lookup table, not a state machine — there are no transitions, only evidence-based assignments.

**Alternatives considered**:
- Status with promotion rules: rejected — promotion is exactly what FV-SPEC-053 prohibits.
- Free-text status: rejected — not machine-checkable.

## R6 — Identifiability Justification Format

**Decision**: A structured JSON record under `.factverify/access/identifiability/` with fields: `justification_id`, `revision`, `system_pair`, `observation_boundary`, `permitted_queries`, `historical_access`, `argument_type` (constructive/empirical), `argument_summary`, `reviewer_id`, `review_date`, `limitations`.

**Rationale**: FV-SPEC-052 requires a reviewed, scoped justification. The structured format makes validation possible (check required fields, verify revision, confirm review). The `argument_type` field distinguishes construction-time proofs (synthetic simulators) from empirical arguments, which have different evidence standards.

**Alternatives considered**:
- Free-text Markdown only: rejected — can't validate field presence or revision binding.
- Embedded in access_profile.md frontmatter: rejected — justifications are per-system-pair, not per-profile; could be multiple.

## R7 — Cross-File Reference Validation

**Decision**: Cross-file references use relative paths from `.factverify/spec/`. The validator resolves references, checks file existence, and validates digest matches where digests are declared. Deferred checks (P0-5 margins, P0-6 witness rule, P0-7 preregistration) are listed in the report but not validated in non-strict mode.

**Rationale**: P0-4 depends on P0-3 (channel requirements), P0-5 (margin thresholds), P0-6 (witness rules), and P0-7 (claim templates). Not all are finalized yet. The validator needs to work during incremental development (non-strict) while flagging incomplete cross-references in strict mode.

**Alternatives considered**:
- Strict-only cross-file checks: rejected — blocks development until all P0-x tasks complete.
- No cross-file checks: rejected — misses the integration validation that is P0-4's key value.

## R8 — Claim Template Validation

**Decision**: Claim templates are JSON files under `.factverify/access/claim_templates/` with fields: `template_id`, `profile` (A/B/C), `stage` (A/B), `completed_tests`, `permitted_interventions`, `budget_ref`, `reference_condition`, `claim_text`, `limitations`, `reviewer_id`, `review_date`. Validation checks that profile matches the access profile's declared level, stage is consistent with data source, and universal erasure language is rejected.

**Rationale**: FV-SPEC-055 requires claim templates scoped to evidence. A Profile A claim must state the output-simulation limitation. A Stage B claim cannot inherit Stage A causal references. The template structure makes these checks automatable.

**Alternatives considered**:
- Unstructured claim prose: rejected — can't automatically check profile/stage consistency.
- Single monolithic claims file: rejected — each claim template is independently reviewable.
