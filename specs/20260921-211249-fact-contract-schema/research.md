# Research: P0-1 Atomic-Fact Contract Schema

**Feature**: `20260921-211249-fact-contract-schema`
**Date**: 2026-09-21

## JSON Schema Draft 2020-12 Validation Library

**Decision**: Use `jsonschema` (Python) with `referencing` for `$ref` resolution.

**Rationale**: `jsonschema` is the most mature Python library for JSON Schema validation, supports Draft 2020-12, and provides detailed error paths (JSON pointers) in validation messages. It is actively maintained and widely used.

**Alternatives considered**:
- `fastjsonschema`: Faster but Draft 2020-12 support is incomplete; lacks `$defs` and `contains` with `allOf` composition needed by the schema.
- `pydantic`: Model-first rather than schema-first; would require maintaining both a Pydantic model and the authoritative JSON Schema, creating a drift risk.

## CLI Framework

**Decision**: Use `click` for the validator CLI.

**Rationale**: Lightweight, handles `--scope`, `--spec-root`, `--contracts`, `--report`, `--baseline-contracts` flags cleanly. Already common in Python CLI tools. No web framework overhead.

**Alternatives considered**:
- `argparse`: Built-in but verbose for multiple subcommands/options. Acceptable but `click` is more ergonomic.
- `typer`: Pydantic-based, heavier dependency. Unnecessary for a validation tool.

## Report Format

**Decision**: JSON report with structured fields: `scope`, `schema_path`, `schema_digest`, `checked_files`, `validity`, `diagnostics`, `revision_check`.

**Rationale**: Machine-readable for CI integration. Stable rule IDs (e.g. `FV-SPEC-002`) in diagnostics enable programmatic filtering. Human-readable console summary printed separately.

**Alternatives considered**:
- Markdown report: Harder to parse programmatically; use for semantic review (FR-014) where human readability matters more.
- JUnit XML: CI-native but doesn't fit the diagnostic structure well.

## Revision Comparison Strategy

**Decision**: Shallow JSON comparison of parsed contract content (excluding `freeze_policy.frozen_at` and `freeze_policy.content_sha256`) against a baseline directory.

**Rationale**: Full V22 self-hashing is out of scope per the requirements. Comparing parsed JSON detects semantic changes (alias additions, locality edits, clue boundary rewrites) without needing a canonical serialization convention. The `contract_id` version suffix is extracted and compared to detect version-bump omissions.

**Alternatives considered**:
- Byte-level file comparison: Too strict — whitespace/formatting changes would trigger false positives.
- Git diff: Requires git history; the baseline must be an explicit snapshot per FV-SPEC-013.

## Identifier Grammar Enforcement

**Decision**: Regex patterns in the schema for syntactic validation; supplemental Python checks in `validate_spec.py` for cross-field identity consistency (FV-SPEC-005).

**Rationale**: JSON Schema `pattern` can enforce that `fact_id` looks like `factverify:fact:wd-Q1858-P1376-Q881` and `contract_id` like `factverify:contract:wd-Q1858-P1376-Q881:v1`, but it cannot assert that the Q/P components in `fact_id` match those in `triple.subject.id` and `triple.relation.id`. That cross-field check requires Python code.

**Alternatives considered**:
- Schema-only validation: Insufficient for identity consistency.
- Full Python model validation (no schema): Loses the machine-readable schema that P0-2 and Phase 1 consume.

## Direction-Role Consistency

**Decision**: Supplemental Python assertion in `validate_spec.py` (not expressible in JSON Schema alone).

**Rationale**: JSON Schema `enum` on `direction`, `given`, and `answer` validates each independently but cannot enforce conditional combinations (e.g. forward → given=subject ∧ answer=object). The schema keeps the enum constraints; the validator adds the combination check.

## Locality Bucket Coverage

**Decision**: Use JSON Schema `allOf` + `contains` clauses (already in the source schema).

**Rationale**: The source schema at §2.5.4 already uses four `contains` clauses inside `allOf` on `retained_neighbourhood` to require each bucket. This is expressible in Draft 2020-12 without supplemental code.

## Test Organization

**Decision**: Single test file `tests/test_contract_schema.py` with named functions `test_fv_spec_NNN_*` mapping to FV-SPEC-001 through FV-SPEC-015.

**Rationale**: The requirements document specifies exact hook names. A single file keeps all P0-1 tests together. Fixtures are organized under `tests/fixtures/{valid,invalid,baselines}/`.
