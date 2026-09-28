# Research: P0-3 Attack Family and Per-Channel Query Budget

**Feature**: `20260922-091030-attack-query-budget`
**Date**: 2026-09-22

## R1: Attack Specification Structure

**Decision**: YAML document with three top-level sections: `arms` (evaluator allocations), `channels` (permitted attack pathways), and `accounting` (charging rules and policies).

**Rationale**: Mirrors P0-2's closure_templates.yaml pattern — a single versioned YAML artifact under `.factverify/spec/`. YAML is human-readable for the review process (FV-SPEC-041) and machine-parseable for validation. Three sections cleanly separate the matched-budget constraint (arms), the scientific scope (channels), and the fairness rules (accounting).

**Alternatives considered**:
- JSON: less readable for review; no comments support for recording decision rationale
- Multiple files: complicates revision protection (FV-SPEC-045) and digest computation
- TOML: less expressive for nested channel definitions

## R2: Channel Definition Pattern

**Decision**: Eight channels, each declaring: id, enabled/disabled, purpose, capability_requirements, policy_source, budget_source, reporting_condition. Disabled channels need no recipe but cannot receive active allocations.

**Rationale**: Sourced from P0-3 Study Guide §§3-4. The eight channels map to the FactVerify protocol's recovery/deployment checks (C4): prompt variation, adversarial wrapper, repeated sampling, few-shot priming, raw likelihood/rank, deployment transformation, relearning, and activation intervention. Each channel declares its access-profile dependency so FV-SPEC-035 can cross-check permissions.

**Alternatives considered**:
- Fewer channels with sub-types: more complex policy declarations; loses the 1:1 mapping to capability requirements
- Dynamic channel registration: violates the frozen-spec principle; channels must be predeclared

## R3: Accounting Unit Design

**Decision**: The fundamental unit is a "response trial" — one prompt evaluated on one checkpoint/transformation under one decoding configuration, producing one completion. Candidate scoring, confirmation calls, cached generations, and training steps are declared separately with explicit conversion rules.

**Rationale**: From P0-3 Study Guide §5. The key insight is that a single API call returning 8 completions is 8 trials, not 1. Candidate-score operations (teacher-forced) are a distinct unit from generation trials. This prevents hidden free observations from defeating budget matching (principle 4/I4).

**Alternatives considered**:
- API call as unit: hides sampling multiplicity; unfair to evaluators that use fewer samples per call
- Token-based only: doesn't capture the structural difference between generation and scoring

## R4: Matched Allocation Validation

**Decision**: Per-arm allocation vectors must sum to a common cap B as nonnegative integers. The validator checks B_native = B_semantic = B_factverify = B_cap. Additionally, each arm must report the cost vector (tokens, scored candidates, training steps, exports, wall-clock).

**Rationale**: From P0-3 §6 and handbook V15. Equal generation-trial totals are necessary but not sufficient for fairness. The cost vector captures that equal query counts do not imply equal resources (constraint C-6).

**Alternatives considered**:
- Floating-point allocations: introduces rounding issues; integer trials are cleaner
- Flexible cap per arm: defeats the entire matched-budget design

## R5: Adaptive Policy Bounding

**Decision**: Each channel declares a finite execution policy with predeclared search space, update rule, stop rule, and budget. Confirmation cap is inside the total. Unused allowance is reported but cannot be reallocated post-hoc.

**Rationale**: From P0-3 §7. Without predeclared bounds, adaptive search can consume unlimited budget. The confirmation reserve is declared upfront (FV-SPEC-039) and cross-checked against witness-rule routes (P0-6). This ensures the search is falsifiable: if the search space is exhausted without discovery, that is a negative result, not a reason to expand.

**Alternatives considered**:
- Unlimited adaptive search with post-hoc adjustment: violates principle 2 (no result-dependent choices)
- Fixed non-adaptive only: too restrictive; some channels legitimately need adaptive stopping

## R6: Event Fixture Replay

**Decision**: Offline event traces are JSON arrays of event records, each identifying arm, case, phase, channel, probe, sample/decoding settings, artifact/parent, operation/outcome, and cost units. The validator replays traces against the declared charge policy and verifies charges deterministically.

**Rationale**: From P0-3 §§5-8. Fixture replay is the primary validation mechanism — it confirms that the declared accounting rules produce the expected charges without running models. This aligns with constraint C-2 (zero model calls) and C-1 (determinism).

**Alternatives considered**:
- Live replay against actual models: violates offline constraint
- Schema-only validation without replay: misses accounting logic bugs

## R7: Clue Audit and Transformation Recipes

**Decision**: Clue audits are stored as manifest files under `.factverify/attacks/audit_manifests/`. Each manifest records exposure classifications against exact revision digests. Transformation recipes are inline in the channel definition within attacks.yaml, requiring all reproducibility fields (algorithm, parent, parameters, tokenizer, fitting-data exposure).

**Rationale**: From P0-3 §§3.1, 4, 8 and handbook §6.7. Version-bound audits ensure that attack inputs are reviewed for clue leakage at the exact revision used. Inline recipes in attacks.yaml keep the transformation specification co-located with its channel and subject to the same revision protection.

**Alternatives considered**:
- External recipe files: complicates revision protection; one more file to track
- Unversioned audits: defeats the purpose; a reviewed input can change silently

## R8: Validator Scope Extension Pattern

**Decision**: Add `"attacks"` to `SUPPORTED_SCOPES` in `tools/validate_spec.py`. Implement validation logic in a separate `tools/attack_validator.py` module (mirrors `tools/closure_validator.py`). Share CLI patterns: `--strict`, `--baseline-suite`, `--report`.

**Rationale**: Follows the established P0-1/P0-2 pattern. The thin CLI dispatcher keeps each scope's logic modular. New CLI flags specific to P0-3: `--event-fixtures` (for replay validation), `--access-profile` (for permission checking).

**Alternatives considered**:
- Single monolithic validator: violates the one-module-per-scope pattern; harder to test independently
- Separate CLI tool: fragments the interface; harder for CI to validate all scopes
