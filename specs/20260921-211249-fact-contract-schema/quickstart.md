# Quickstart: P0-1 Atomic-Fact Contract Schema

**Feature**: `20260921-211249-fact-contract-schema`
**Date**: 2026-09-21

## Prerequisites

- Python 3.11
- `uv` package manager
- Repository cloned with `.factverify/` directory included

## Setup

```bash
uv sync
```

## Validate contracts

```bash
# Validate all contracts against the schema
uv run python tools/validate_spec.py \
  --scope fact-contract \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --report reports/p0-1-validation.json
```

Expected: exit code 0, JSON report at `reports/p0-1-validation.json`.

## Validate with revision check

```bash
# Compare contracts against a frozen baseline
uv run python tools/validate_spec.py \
  --scope fact-contract \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --baseline-contracts tests/fixtures/baselines \
  --report reports/p0-1-validation.json
```

Expected: exit code 0 if no unauthorized changes; nonzero with diagnostics if a contract changed without version bump.

## Run tests

```bash
uv run pytest tests/test_contract_schema.py -v
```

Expected: all 15 named test hooks pass (`test_fv_spec_001_*` through `test_fv_spec_015_*`).

## Verify the schema itself

```bash
# Quick meta-schema check
uv run python -c "
import json
from jsonschema import Draft202012Validator
schema = json.load(open('.factverify/spec/fact_contract.schema.json'))
Draft202012Validator.check_schema(schema)
print('Schema is valid Draft 2020-12')
"
```

## Verify dot-directory inclusion

```bash
# Ensure .factverify/ is not excluded by gitignore
git check-ignore -v .factverify/spec/fact_contract.schema.json
# Expected: no output (not ignored)
```

## Integration test scenarios

1. **Happy path**: Run validator on included demonstration contracts → exit 0
2. **Missing schema**: Delete schema temporarily, run validator → exit nonzero with "schema not found"
3. **Bad contract**: Add an unknown field to a contract copy → exit nonzero with "additionalProperties" diagnostic
4. **Revision drift**: Copy a contract to baselines, change an alias in the current version without bumping version → exit nonzero with revision diagnostic
5. **Empty directory**: Point `--contracts` at an empty directory → exit nonzero with "no contracts found"
