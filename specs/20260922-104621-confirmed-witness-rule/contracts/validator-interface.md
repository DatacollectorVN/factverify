# Validator Interface Contract: P0-6 Witness Rule

**Feature**: `20260922-104621-confirmed-witness-rule`
**Created**: 2026-09-22

---

## CLI Interface

### Command

```
python tools/validate_spec.py \
  --scope witness-rule \
  --spec-root .factverify/spec \
  --report reports/p0-6-validation.json \
  [--witness-dir .factverify/witness] \
  [--strict] \
  [--baseline-suite tests/fixtures/witness_rule/baselines/witness_rule.md]
```

### Arguments

| Flag | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `--scope` | string | yes | — | Must be `"witness-rule"` for P0-6 validation |
| `--spec-root` | path | yes | — | Root of `.factverify/spec/` containing `witness_rule.md` |
| `--report` | path | no | `None` | Output path for JSON validation report |
| `--witness-dir` | path | no | `{spec-root}/../witness` | Reviews, evidence, and review manifest directory |
| `--strict` | flag | no | `False` | Require resolved applicable decisions, current reviews, consistent cross-file policies |
| `--baseline-suite` | path | no | `None` | Baseline `witness_rule.md` for revision comparison |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All validation checks pass |
| 1 | One or more validation checks fail |
| 2 | Input file missing, malformed, or unparseable |

---

## Validation Rules

### Rule Dispatch

The validator executes checks in order FV-SPEC-067 through FV-SPEC-077. Each check produces:

```json
{
  "rule_id": "FV-SPEC-067",
  "rule_name": "witness_contract_artifact",
  "status": "pass | fail | deferred | skipped",
  "diagnostics": ["human-readable message", ...]
}
```

### Rule Summary

| Rule | Name | What it checks |
|------|------|----------------|
| FV-SPEC-067 | witness_contract_artifact | Versioned layers (score/confirm/case); reject response-as-verdict; required defs resolve |
| FV-SPEC-068 | direction_aware_rubric | Forward/object, inverse/subject, truth-value, aliases, negation, ambiguity, non-answer, missingness; refusal separate; many-valued policy |
| FV-SPEC-069 | raw_score_semantics | Per-channel conventions; insufficient top-k / mixed scales → unavailable/invalid |
| FV-SPEC-070 | route_a_confirmation | Two independent families; reject punctuation/language-only/clue/false-reject auto dual witnesses |
| FV-SPEC-071 | route_b_replication | Training/update seeds + declared statistic; reject decoding-seed / export-variant substitution |
| FV-SPEC-072 | route_c_verdict_flips | Criterion crossing + hashes/exposure/transforms/locality; reject single-flip / unlabeled reacquisition |
| FV-SPEC-073 | case_level_verdict | Simultaneous recovery + locality + access/completeness; no-witness ≠ accept; NI/incomplete alignment |
| FV-SPEC-074 | evidence_aggregation | Reserved costs; whole-rule aggregation; reject raw-maximum primary / unrestricted search |
| FV-SPEC-075 | blinded_annotation | Blinded double-annotation + adjudication metrics; reject sole-LLM / outcome-driven rubric edits |
| FV-SPEC-076 | reconstructable_records | Provenance fields; reject missing raw / stale scorer / hidden control-as-recovery |
| FV-SPEC-077 | scoped_cli_validation | Digests, fixture outcomes, pending deps; strict fail-closed; zero model/LLM/calibration |

### Deferred Checks (non-strict mode)

When `--strict` is not set, the following may be listed as `deferred` rather than failing:

- Unresolved open decision operational parameters (listed, not invented)
- P0-7 preregistration / amendment authorization
- P2-2 production semantic scorer / live confirmation
- P2-6 statistical engine execution
- P4 empirical calibration

When sibling artifacts exist, cross-checks against P0-1 answer roles, P0-2 families, P0-3 budgets, P0-4 statuses, and P0-5 margins run in both modes (fail on inconsistency).

---

## Report Schema

```json
{
  "scope": "witness-rule",
  "spec_root": ".factverify/spec",
  "timestamp": "ISO-8601",
  "input_digests": {
    "witness_rule.md": "sha256:...",
    "review_manifest.json": "sha256:..."
  },
  "checks": [
    {
      "rule_id": "FV-SPEC-067",
      "rule_name": "witness_contract_artifact",
      "status": "pass",
      "diagnostics": []
    }
  ],
  "fixture_results": [
    {
      "fixture_id": "disclosure_plus_refusal",
      "expected": {"correctness": "correct", "refusal_flag": true},
      "observed": {"correctness": "correct", "refusal_flag": true},
      "status": "pass"
    }
  ],
  "decision_status": [
    {"decision_id": "D-35", "status": "open"}
  ],
  "deferred": [
    "P2-2 production semantic scorer",
    "P4 empirical calibration"
  ],
  "overall": "pass"
}
```

---

## Deterministic Contract Interpreter

Golden fixtures exercise a **minimal deterministic interpreter** over declared fields (label mapping, route eligibility predicates, verdict gate conjunction). It is not a production semantic scorer:

- No model or LLM calls
- No empirical threshold fitting
- Fixture expected labels/routes/reasons must match exactly across identical runs (excluding timestamps)

---

## Fail-Closed Behaviour (I8)

| Condition | Exit | Notes |
|-----------|------|-------|
| Missing `witness_rule.md` | 2 | File diagnostics |
| Unparseable frontmatter | 2 | Parse diagnostics |
| Layer conflation / missing required defs | 1 | FV-SPEC-067 |
| Invalid golden / evidence fixtures | 1 | FV-SPEC-068–076 |
| Strict + unresolved applicable decisions | 1 | FV-SPEC-077 |
| Strict + stale annotation reviews | 1 | FV-SPEC-075/077 |
| Cross-file budget/status/margin mismatch | 1 | FV-SPEC-073/074/077 |
