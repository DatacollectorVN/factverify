# Quickstart: P0-2 Closure Template Suite

**Feature**: `20260921-235511-closure-template-suite`
**Date**: 2026-09-22

## Prerequisites

- Python 3.11
- `uv` package manager
- Repository cloned with `.factverify/` directory included
- P0-1 contracts validated (run P0-1 validator first)

## Setup

```bash
uv sync
```

## Validate closure templates

```bash
# Validate the closure suite against contracts
uv run python tools/validate_spec.py \
  --scope closure-templates \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --bindings .factverify/closure/instance_bindings.json \
  --report reports/p0-2-validation.json
```

Expected: exit code 0, JSON report at `reports/p0-2-validation.json`.

## Validate with strict mode

```bash
# Strict mode: require resolved decisions and current reviews
uv run python tools/validate_spec.py \
  --scope closure-templates \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --bindings .factverify/closure/instance_bindings.json \
  --review-manifest .factverify/closure/review_manifest.json \
  --strict \
  --report reports/p0-2-validation.json
```

Expected: exit code 0 if all decisions resolved and reviews current; nonzero with diagnostics otherwise.

## Render a construction preview

```bash
# Render construction-split preview for human review
uv run python tools/validate_spec.py \
  --scope closure-templates \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --bindings .factverify/closure/instance_bindings.json \
  --split construction \
  --preview reports/p0-2-construction-preview.jsonl \
  --report reports/p0-2-validation.json
```

Expected: JSONL preview at `reports/p0-2-construction-preview.jsonl` with model_input and evaluator_metadata separated.

## Validate with baseline revision check

```bash
# Compare current suite against a frozen baseline
uv run python tools/validate_spec.py \
  --scope closure-templates \
  --spec-root .factverify/spec \
  --contracts .factverify/contracts \
  --bindings .factverify/closure/instance_bindings.json \
  --baseline-suite tests/fixtures/closure_templates/baselines/closure_templates.yaml \
  --report reports/p0-2-validation.json
```

Expected: exit code 0 if no unauthorized changes; nonzero if content changed without revision bump.

## Run tests

```bash
uv run pytest tests/test_closure_templates.py -v
```

Expected: all 18 named test hooks pass (`test_fv_spec_016_*` through `test_fv_spec_033_*`).

## Run P0-1 regression check

```bash
# Verify P0-1 tests still pass after P0-2
uv run pytest tests/test_contract_schema.py -v
```

Expected: all P0-1 tests pass unchanged.

## Integration test scenarios

1. **Happy path**: Validate demonstration suite → exit 0
2. **Missing suite**: Delete closure_templates.yaml temporarily → exit 2 with "suite not found"
3. **Bad routing**: Move an E template into controls → exit 1 with FV-SPEC-017 diagnostic
4. **Nonempty E premises**: Add a premise to an equivalence template → exit 1 with FV-SPEC-018 diagnostic
5. **Missing I provenance**: Remove premise_origins from an inference template → exit 1 with FV-SPEC-019 diagnostic
6. **Binding mismatch**: Map a forward binding to subject instead of object → exit 1 with FV-SPEC-020 diagnostic
7. **Unbalanced verification**: Add a true verification instance without a matching false → exit 1 with FV-SPEC-024 diagnostic
8. **Split leakage**: Put a construction preview template in final_test group → exit 1 with FV-SPEC-023 diagnostic
9. **Answer in model_input**: Include answer_key in a message → exit 1 with FV-SPEC-028 diagnostic
10. **Revision drift**: Change a template without bumping revision → exit 1 with FV-SPEC-031 diagnostic
