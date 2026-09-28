# Specification Quality Checklist: FV-CTRL — P2-4 Behaviour-Matching Utility

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-27
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validation iteration 1 (2026-09-27): all items pass.
- Content is written for the study owner. Domain terms (direct question-answering accuracy, retain-only reference, false-certification, Gate 1, template group, query budget) are defined in the spec or taken from the frozen spec vocabulary. No language, framework, library, or module is named.
- Open decisions D-54, D-58, D-59, and D-53 are recorded as fail-closed assumptions. The requirements note already assigns their treatment (cite the decision, do not invent a literal). They are not left as clarification markers. D-54 also owns the band summary, the boundary rule, and the rule that picks one severity when several fall inside the tolerance, because the requirements note leaves that choice open.
- Reference counts (two in the integrity pilot, at least three in Block 1) are cited from the execution plan, headings Phase 3 and Phase 4. They are not new local numbers.
- Recorded match cost (wall-clock, GPU-hours, peak memory) is a required study outcome from the requirements note, constraint C-2, not a technology choice. The requirements note cites `attacks.yaml` `discovery_and_calibration_cost: reported_separately`; the spec keeps matching cost on the match record and out of the evaluator budget, and does not edit the frozen spec.
- Sources read from disk because the Obsidian vault tools were unavailable. Requirements note status: draft. Execution plan status: planned. Proposal status: draft. Concept note Fake-Unlearning Controls status: draft. Handbook status: draft.
