# Validator Interface Contract

## CLI Interface

```
tools/validate_spec.py
  --scope fact-contract          # Required. Only P0-1 scope implemented.
  --spec-root PATH               # Required. Default: .factverify/spec
  --contracts PATH               # Required. Directory of JSON contract files.
  --report PATH                  # Required. Output report path (JSON).
  [--baseline-contracts PATH]    # Optional. Prior snapshot for revision check.
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All requested structural checks passed |
| 1 | One or more validation failures |
| 2 | Missing/malformed inputs (schema, empty contracts dir, bad invocation) |

## Report Schema

```json
{
  "scope": "fact-contract",
  "schema_path": "/absolute/path/to/fact_contract.schema.json",
  "schema_digest": "sha256:abcdef...",
  "timestamp": "2026-09-21T12:00:00Z",
  "checked_files": [
    {
      "path": "contract-name.json",
      "valid": true,
      "diagnostics": []
    }
  ],
  "revision_check": "not_requested | { status, details[] }",
  "summary": {
    "total": 2,
    "valid": 2,
    "invalid": 0
  }
}
```

## Diagnostic Format

```json
{
  "rule_id": "FV-SPEC-002",
  "file": "contract-name.json",
  "json_pointer": "/triple/subject",
  "message": "Required property 'id' is missing"
}
```

## Scope Semantics

- `fact-contract`: P0-1 structural validation only
- Other scopes: not implemented; exit with error "unsupported scope"
- `--scope full`: must fail closed or report unsupported, never claim full-spec success
