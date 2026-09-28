# Implementation Plan: P0-7 Pre-registration and Spec Freeze

**Branch**: `20260926-093444-preregistration-spec-freeze` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/20260926-093444-preregistration-spec-freeze/spec.md`

## Summary

Extend `tools/validate_spec.py` with a new `preregistration` scope (11 check functions, FV-SPEC-078 through FV-SPEC-088), and deliver `tools/freeze.py` — a new CLI tool that gates and executes the spec-v1 freeze (checksum manifest, annotated tag, post-commit receipt). Eleven test hooks in `tests/test_preregistration_freeze.py` cover all requirements; fixtures are synthetic and offline-only.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyYAML (YAML parsing), jsonschema + referencing (structural validation), click (CLI), hashlib (SHA-256 digests), subprocess (git operations in tests and freeze tool)  
**Storage**: YAML (`register.yaml`, `milestones.yaml`), Markdown + YAML frontmatter (`preregistration.md`, `exposure_record.md`), plain text (CHECKSUMS.sha256), JSON (validation reports, freeze receipt)  
**Testing**: pytest; `tmp_path` + `subprocess.run(["git", "init"])` for temporary-repository fixtures  
**Target Platform**: Local CLI, offline, Linux/macOS  
**Project Type**: CLI tools (`tools/preregistration_validator.py`, `tools/freeze.py`)  
**Performance Goals**: No model/GPU/network calls; deterministic; completes in < 5 seconds on a modern laptop  
**Constraints**: Offline-only; `--dry-run` is strictly read-only (no filesystem or git writes); tag overwrite is never permitted; fail-closed on missing or malformed inputs  
**Scale/Scope**: 7 spec artifacts; 4 input files; 11 test hooks; temporary-repository fixtures; 1 new CLI tool; 1 extended CLI tool

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Check | Result |
|-----------|-------|--------|
| 1. Spec Is Frozen (I8) | This task builds the freeze tooling; no existing `spec-v1` tag to violate. Tooling enforces the rule going forward. | PASS |
| 2. No Result-Dependent Choices | All normative values read from spec fields; FR-002 prevents inline duplicates; no thresholds hard-coded. | PASS |
| 3. Final Test Runs Once | FR-009 requires preregistration to declare "full re-run on fresh split" as the broken-pass recovery procedure; validator enforces this. | PASS |
| 4. Equal Query Budgets (I4) | Not applicable — this task adds no evaluator or query-issuing code. | N/A |
| 5. Seeded and Config-Driven | `validate_spec.py` and `freeze.py` read all values from spec fields; no magic numbers in code. | PASS |
| 6. Ledger Everything | Freeze receipt and readiness report serve as ledger entries for the spec-freeze event; format is consistent with `reports/` convention. | PASS |
| 7. Gates Are Stop Points | `freeze.py` refuses to proceed if any gate fails (fail-closed, non-zero exit, named diagnostics). Gate check list is exhaustive (8 checks). | PASS |
| 8. Wiki Governs Design | Design drawn from FV-SPEC P0-7 and the Execution Plan; research.md cites source notes. | PASS |
| 9–12. (Evaluation-specific) | Not applicable to spec validation tooling. | N/A |

No violations. No Complexity Tracking table required.

## Project Structure

### Documentation (this feature)

```text
specs/20260926-093444-preregistration-spec-freeze/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── cli-interface.md # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
tools/
├── validate_spec.py                  # extend: add "preregistration" scope + dispatch
├── preregistration_validator.py      # NEW: 11 check functions (FV-SPEC-078–088)
└── freeze.py                         # NEW: freeze workflow CLI (dry-run / execute / verify)

tests/
├── conftest.py                       # extend: add P0-7 path constants and fixtures
├── test_preregistration_freeze.py    # NEW: 11 test hooks
└── fixtures/
    └── preregistration/
        ├── valid/
        │   ├── preregistration_complete.md
        │   ├── preregistration_reviewed.md
        │   ├── exposure_record_valid.md
        │   ├── milestones_valid.yaml
        │   └── register_resolved.yaml
        └── invalid/
            ├── preregistration_missing_section.md
            ├── preregistration_duplicate_alpha.md
            ├── preregistration_patch_and_resume.md
            ├── preregistration_post_hoc_amendment.md
            ├── preregistration_unlabelled_exploratory.md
            ├── exposure_contradiction.md
            ├── exposure_unregistered_claim.md
            ├── milestones_tbd.yaml
            ├── milestones_missing.yaml
            └── register_open.yaml

.factverify/
├── spec/
│   └── preregistration.md            # NEW: study commitment document
├── decisions/
│   └── register.yaml                 # NEW: decision register (all D-IDs)
├── milestones/
│   └── milestones.yaml               # NEW: three milestone entries
└── exposure/
    └── exposure_record.md            # NEW: exposure record

reports/
├── p0-7-validation.json              # generated by validate_spec.py
└── spec-v1-freeze-receipt.json       # generated by freeze.py --execute (post-commit)

.factverify/
└── CHECKSUMS.sha256                  # generated by freeze.py --execute (pre-commit)
```

**Structure Decision**: Single-project layout (Option 1), consistent with all prior P0 tasks. New files added to `tools/`, `tests/`, and `.factverify/`. No new top-level directories.

## Implementation Notes (for /speckit.tasks)

### preregistration_validator.py — function mapping

Each function follows the existing convention: `check_fv_spec_<NNN>_<short_name>(frontmatter, body, ...) -> list[dict]`

| Function | FV-SPEC | Tests |
|----------|---------|-------|
| `check_fv_spec_078_artifact(fm, body)` | 078 | `test_fv_spec_078_artifact` |
| `check_fv_spec_079_exposure(fm, exposure_fm)` | 079 | `test_fv_spec_079_exposure` |
| `check_fv_spec_080_milestones(milestones)` | 080 | `test_fv_spec_080_milestones` |
| `check_fv_spec_081_splits(milestones, register)` | 081 | `test_fv_spec_081_splits` |
| `check_fv_spec_082_analysis(fm, body, register)` | 082 | `test_fv_spec_082_analysis` |
| `check_fv_spec_083_deviations(fm, body)` | 083 | `test_fv_spec_083_deviations` |
| `check_fv_spec_084_amendments(fm)` | 084 | `test_fv_spec_084_amendments` |
| `check_fv_spec_085_claims(fm, body)` | 085 | `test_fv_spec_085_claims` |
| `check_fv_spec_086_integrity(spec_root, checksums_path)` | 086 | `test_fv_spec_086_integrity` |
| `check_fv_spec_087_freeze(spec_root, register, exposure_fm, milestones, report)` | 087 | `test_fv_spec_087_freeze` |
| `check_fv_spec_088_cli(freeze_repo)` | 088 | `test_fv_spec_088_cli` |

The module also exports `_NO_MODEL_CALLS = True` (same pattern as `witness_rule_validator.py`).

### freeze.py — gate sequence

Gate checks run in this order (all must pass before any write):
1. All seven spec artifacts present and non-empty
2. `preregistration.md` passes `--scope preregistration --strict`
3. All prior SPEC scopes pass regression check
4. Decision register: all applicable decisions resolved or not-applicable
5. Exposure record `status: reviewed`
6. Milestone manifest: all three milestones have git_tag or complete staged_rule
7. No existing tag named `--tag`
8. No raw model outputs, checkpoints, or credentials inside `.factverify/`

### validate_spec.py extension

- Add `"preregistration"` to `SUPPORTED_SCOPES`
- Add four new `--option` flags (with defaults, ignored by other scopes)
- Add `_run_preregistration_validation()` dispatch function
- Wire into the existing `if scope == "..."` chain

### conftest.py extension

Add constants and session fixtures for P0-7:
```python
PREREGISTRATION_MD = SPEC_ROOT / "preregistration.md"
PREREGISTRATION_FIXTURES = FIXTURES / "preregistration"
PR_VALID = PREREGISTRATION_FIXTURES / "valid"
PR_INVALID = PREREGISTRATION_FIXTURES / "invalid"
DECISIONS_DIR = REPO / ".factverify" / "decisions"
MILESTONES_DIR = REPO / ".factverify" / "milestones"
EXPOSURE_DIR = REPO / ".factverify" / "exposure"
P0_7_REPORT = REPO / "reports" / "p0-7-validation.json"
```
