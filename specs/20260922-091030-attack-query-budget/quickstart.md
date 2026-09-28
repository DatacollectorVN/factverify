# Quickstart: P0-3 Attack Family and Per-Channel Query Budget

**Feature**: `20260922-091030-attack-query-budget`
**Date**: 2026-09-22

## Prerequisites

- Python 3.11
- `uv` package manager
- Repository cloned with `.factverify/` directory included
- P0-1 contracts validated (run P0-1 validator first)
- P0-2 closure templates validated (run P0-2 validator first)

## Setup

```bash
uv sync
```

## Validate attack specification

```bash
# Validate the attack specification
uv run python tools/validate_spec.py \
  --scope attacks \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --report reports/p0-3-validation.json
```

Expected: exit code 0 (with expected diagnostics for unresolved decisions), JSON report at `reports/p0-3-validation.json`.

## Validate with access profile

```bash
# Cross-check channel permissions against access profile
uv run python tools/validate_spec.py \
  --scope attacks \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --access-profile .factverify/spec/access_profile.md \
  --report reports/p0-3-validation.json
```

Expected: exit code 0 if all enabled channels have matching permissions; nonzero with FV-SPEC-035 diagnostics otherwise.

## Validate with event fixture replay

```bash
# Replay event traces against declared charge policies
uv run python tools/validate_spec.py \
  --scope attacks \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --event-fixtures .factverify/attacks/event_fixtures.json \
  --report reports/p0-3-validation.json
```

Expected: exit code 0 if all traces replay deterministically; nonzero with FV-SPEC-036/037 diagnostics otherwise.

## Validate with strict mode

```bash
# Strict mode: require resolved decisions and current audits
uv run python tools/validate_spec.py \
  --scope attacks \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --access-profile .factverify/spec/access_profile.md \
  --witness-rule .factverify/spec/witness_rule.md \
  --event-fixtures .factverify/attacks/event_fixtures.json \
  --strict \
  --report reports/p0-3-validation.json
```

Expected: exit code 0 if all decisions resolved, audits current, and permissions matching; nonzero with diagnostics otherwise.

## Validate with baseline revision check

```bash
# Compare current spec against a frozen baseline
uv run python tools/validate_spec.py \
  --scope attacks \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --baseline-suite tests/fixtures/attack_spec/baselines/attacks.yaml \
  --report reports/p0-3-validation.json
```

Expected: exit code 0 if no unauthorized changes; nonzero if content changed without revision bump.

## Run tests

```bash
uv run pytest tests/test_attack_spec.py -v
```

Expected: all 13 named test hooks pass (`test_fv_spec_034_*` through `test_fv_spec_046_*`).

## Run P0-1/P0-2 regression check

```bash
# Verify P0-1 and P0-2 tests still pass after P0-3
uv run pytest tests/test_contract_schema.py tests/test_closure_templates.py -v
```

Expected: all P0-1 + P0-2 tests pass unchanged.

## Integration test scenarios

1. **Happy path**: Validate demonstration attacks.yaml with all three arms -> exit 0
2. **Missing spec**: Delete attacks.yaml temporarily -> exit 2 with "spec not found"
3. **Unequal allocations**: Set native arm total to 90 while cap is 96 -> exit 1 with FV-SPEC-038 diagnostic
4. **Permission violation**: Enable activation intervention without internal_access -> exit 1 with FV-SPEC-035 diagnostic
5. **Mixed units**: Mix generation counts with candidate scoring without conversion model -> exit 1 with FV-SPEC-036 diagnostic
6. **Hidden free observation**: Cache hit not declared in charge policy -> exit 1 with FV-SPEC-037 diagnostic
7. **Missing confirmation reservation**: Enable witness route without reservation -> exit 1 with FV-SPEC-039 diagnostic
8. **Unbounded adaptive policy**: Omit stop rule from adaptive policy -> exit 1 with FV-SPEC-040 diagnostic
9. **Clue leakage**: Direct answer disclosure in attack input not flagged -> exit 1 with FV-SPEC-041 diagnostic
10. **Incomplete recipe**: Export transformation missing algorithm/calibration corpus -> exit 1 with FV-SPEC-042 diagnostic
11. **Unseparated relearning**: Target-free and target-exposed conditions not distinguished -> exit 1 with FV-SPEC-043 diagnostic
12. **Revision drift**: Change a channel without bumping revision -> exit 1 with FV-SPEC-045 diagnostic
13. **Strict with open decisions**: Run strict mode with D-17 unresolved -> exit 1 with FV-SPEC-046 diagnostic
