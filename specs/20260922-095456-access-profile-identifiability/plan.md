# Implementation Plan: P0-4 Access Profile and the Identifiability Limit

**Branch**: `20260922-095456-access-profile-identifiability` | **Date**: 2026-09-22 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/20260922-095456-access-profile-identifiability/spec.md`

## Summary

Deliver a validated access contract (`.factverify/spec/access_profile.md`) bounding observations, interventions, identifiability claims, and downstream status handling. The validator extends `tools/validate_spec.py` with `--scope access-profile` and 10 new validation rules (FV-SPEC-047 through FV-SPEC-056). All validation is offline — zero endpoint calls, model execution, or GPU jobs.

## Technical Context

**Language/Version**: Python 3.11 (managed by `uv`)
**Primary Dependencies**: PyYAML (YAML frontmatter parsing), click (CLI), hashlib (digests)
**Storage**: Markdown with YAML frontmatter (access_profile.md), JSON (reports, fixtures, manifests)
**Testing**: pytest with named test hooks `test_fv_spec_047_*` through `test_fv_spec_056_*`
**Target Platform**: macOS / Linux CLI
**Project Type**: CLI extension of `tools/validate_spec.py`
**Performance Goals**: Offline-only; sub-second validation on spec-sized inputs
**Constraints**: Zero endpoint/model calls; deterministic given same versioned inputs; fail closed on bad/missing input
**Scale/Scope**: ~10 validation rules, ~10 test classes, 3 access profiles (A/B/C), 4 outcome statuses, 6 blocking decisions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| 1. Spec Is Frozen (I8) | PASS | P0-4 contributes to `spec-v1`; access_profile.md is a normative artifact under `.factverify/spec/`. Not yet frozen. Fail-closed: missing/invalid fields → nonzero exit. |
| 2. No Result-Dependent Choices | PASS | All parameters are declared before outcomes. Capability states are input declarations, not post-hoc observations. |
| 3. Final Test Runs Once | N/A | P0-4 validates spec artifacts; does not run experiments. |
| 4. Equal Query Budgets (I4) | PASS | Cross-checks budget references from P0-3 attacks.yaml against declared access capabilities. |
| 5. Seeded and Config-Driven | PASS | All values come from profile fields and decision IDs, never literals. |
| 6. Ledger Everything | N/A | P0-4 is offline spec validation; ledger is P2-5. |
| 7. Gates Are Stop Points | PASS | 6 blocking decisions documented (D-13, D-14, D-27, D-28, D-29, D-31); no requirement reaches `implemented` while blocked. |
| 8. Wiki Governs Design | PASS | Design from P0-4 Study Guide and handbook; code follows spec. |
| 9. Equivalence and Inference Never Mix (I2) | PASS | Identifiability justification (FV-SPEC-052) keeps structural arguments separate from observation-based evidence. |
| 10. Claims Never Exceed the Channel (I3) | PASS | Core deliverable: claim templates constrained to declared profile, stage, and evidence scope (FV-SPEC-055). Profile A → non-identifiable verdict, never promoted. |
| 11. Raw Maxima Are Never Verdicts (I5) | PASS | Status contracts (FV-SPEC-053) prohibit silent promotion; missing measurements remain "incomplete". |
| 12. Prompts Are Not Replicates (I7) | N/A | P0-4 does not deal with prompt counts; that's P0-3/P0-6. |

No violations. Gate passes.

## Project Structure

### Documentation (this feature)

```text
specs/20260922-095456-access-profile-identifiability/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── validator-interface.md
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
tools/
├── validate_spec.py             # CLI entry point — extended with --scope access-profile
└── access_profile_validator.py  # NEW: P0-4 validation engine (mirrors attack_validator.py)

.factverify/
├── spec/
│   └── access_profile.md       # NEW: P0-4 deliverable (frozen spec artifact)
└── access/
    ├── capability_manifests/    # NEW: per-system capability/provenance records
    ├── identifiability/         # NEW: reviewed justification records
    ├── claim_templates/         # NEW: profile-scoped claim templates
    └── review_manifest.json     # NEW: P0-4 review records

tests/
├── test_access_profile.py       # NEW: 10 test classes (FV-SPEC-047–056)
├── conftest.py                  # Extended with P0-4 path constants
└── fixtures/
    └── access_profile/          # NEW: follows attack_spec/ pattern
        ├── valid/
        ├── invalid/
        └── baselines/
```

**Structure Decision**: Follows the established P0-1/P0-2/P0-3 pattern — thin CLI dispatch in `validate_spec.py`, full validation engine in a dedicated module, fixtures in `tests/fixtures/access_profile/`, artifacts under `.factverify/access/`.
