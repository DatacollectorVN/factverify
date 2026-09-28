# Validator Interface Contract: P0-2 Closure Templates

## CLI Interface

```
tools/validate_spec.py
  --scope closure-templates       # Required. P0-2 scope.
  --spec-root PATH                # Required. Default: .factverify/spec
  --contracts PATH                # Required. P0-1 contract directory.
  --bindings PATH                 # Required. Instance bindings JSON.
  --review-manifest PATH          # Optional. Review manifest JSON.
  --split SPLIT                   # Optional. construction|calibration|final_test
  --preview PATH                  # Optional. Output preview JSONL path.
  --report PATH                   # Required. Output report path (JSON).
  [--strict]                      # Optional. Require resolved decisions & current reviews.
  [--baseline-suite PATH]         # Optional. Prior suite snapshot for revision check.
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | All requested structural checks passed |
| 1    | One or more validation failures |
| 2    | Missing/malformed inputs (suite, empty contracts, bad invocation) |

## Report Schema

```json
{
  "scope": "closure-templates",
  "suite_path": "/absolute/path/to/closure_templates.yaml",
  "suite_digest": "sha256:abcdef...",
  "bindings_path": "/absolute/path/to/instance_bindings.json",
  "schema_path": "/absolute/path/to/fact_contract.schema.json",
  "timestamp": "2026-09-21T12:00:00Z",
  "checked_templates": [
    {
      "id": "direct_001",
      "class": "E",
      "valid": true,
      "diagnostics": []
    }
  ],
  "coverage": {
    "status": "pass|fail",
    "matrix": {
      "capital_of": ["direct", "inverse", "cloze", "paraphrase", "multilingual", "verification"],
      "alma_mater": ["direct", "inverse", "cloze", "paraphrase", "multilingual", "verification"]
    },
    "missing": []
  },
  "balance": {
    "status": "pass|fail",
    "blocks": [
      {
        "key": "wd-Q1858-P1376-Q881:capital_of:en:construction",
        "true_count": 2,
        "false_count": 2,
        "balanced": true
      }
    ]
  },
  "split_isolation": {
    "status": "pass|fail",
    "orphaned_templates": [],
    "cross_split_groups": [],
    "held_out_in_construction": []
  },
  "review_status": {
    "bilingual_approvals": "complete|incomplete|not_requested",
    "classification_review": "complete|incomplete|not_requested",
    "stale_reviews": []
  },
  "revision_check": "not_requested | { status, details[] }",
  "deferred_checks": ["P0-3 budget accounting", "P0-6 witness rule"],
  "diagnostics": [],
  "summary": {
    "total_templates": 42,
    "valid": 40,
    "invalid": 2,
    "deferred": 3
  }
}
```

## Diagnostic Format

```json
{
  "rule_id": "FV-SPEC-018",
  "template_id": "direct_001",
  "file": "closure_templates.yaml",
  "json_pointer": "/sets/equivalence/0/extra_premises",
  "message": "Equivalence template must have empty premises"
}
```

## Scope Semantics

- `closure-templates`: P0-2 structural validation only
- Ordinary mode: checks structure, marks semantic readiness pending
- `--strict` mode: additionally rejects unresolved D-38–D-43, missing/stale reviews
- Deferred checks (P0-3 budget, P0-6 witness) are listed but not evaluated
- Neither mode establishes full Phase 0 readiness

## Preview Output Format (JSONL)

Each line is a JSON object:

```json
{
  "instance_id": "direct_001__wd-Q1858-P1376-Q881",
  "model_input": [
    {"role": "user", "content": "Hà Nội is the capital of which country?"}
  ],
  "evaluator_metadata": {
    "contract_id": "factverify:contract:wd-Q1858-P1376-Q881:v1",
    "contract_version": "v1",
    "template_id": "direct_001",
    "group_id": "capital_direct_en",
    "split": "construction",
    "relation": "capital_of",
    "class": "E",
    "primary_family": "direct",
    "overlapping_attributes": [],
    "answer_role": "object",
    "answer_key": "Vietnam",
    "truth_label": null,
    "reporting_population": "equivalence",
    "premises": [],
    "review_ref": null
  }
}
```

## Interaction with P0-1

- `--scope fact-contract` continues to work unchanged
- `--scope closure-templates` additionally validates P0-1 contracts via the existing path
- Contract bindings reference P0-1 contract IDs and are checked against the P0-1 schema
- No P0-1 schema changes are introduced by P0-2
