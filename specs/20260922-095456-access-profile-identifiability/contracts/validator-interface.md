# Validator Interface Contract: P0-4 Access Profile

**Feature**: `20260922-095456-access-profile-identifiability`
**Created**: 2026-09-22

---

## CLI Interface

### Command

```
python tools/validate_spec.py \
  --scope access-profile \
  --spec-root .factverify/spec \
  --report reports/p0-4-validation.json \
  [--access-dir .factverify/access] \
  [--strict] \
  [--baseline-suite tests/fixtures/access_profile/baselines/access_profile.md]
```

### Arguments

| Flag | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `--scope` | string | yes | — | Must be `"access-profile"` for P0-4 validation |
| `--spec-root` | path | yes | — | Root of `.factverify/spec/` containing `access_profile.md` |
| `--report` | path | no | `None` | Output path for JSON validation report |
| `--access-dir` | path | no | `{spec-root}/../access` | Path to `.factverify/access/` containing manifests, justifications, claim templates |
| `--strict` | flag | no | `False` | Require all applicable decisions resolved, reviews current, cross-file references resolved |
| `--baseline-suite` | path | no | `None` | Path to baseline access_profile.md for revision comparison |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All validation checks pass |
| 1 | One or more validation checks fail |
| 2 | Input file missing, malformed, or unparseable |

---

## Validation Rules

### Rule Dispatch

The validator executes checks in order FV-SPEC-047 through FV-SPEC-056. Each check produces a result entry in the report with:

```json
{
  "rule_id": "FV-SPEC-047",
  "rule_name": "access_contract_artifact",
  "status": "pass | fail | deferred | skipped",
  "diagnostics": ["human-readable message", ...]
}
```

### Rule Summary

| Rule | Name | What it checks |
|------|------|----------------|
| FV-SPEC-047 | access_contract_artifact | Frontmatter schema, required fields, version format, profile enum |
| FV-SPEC-048 | observation_capabilities | Per-system A/B/C consistency, score_scope, provider transformations |
| FV-SPEC-049 | provenance_verification | Manifest existence, required fields, reviewer, hash format |
| FV-SPEC-050 | observation_intervention_separation | Intervention permissions independent of observation; role separation |
| FV-SPEC-051 | historical_external_access | All sources declared; historical artifacts attributed |
| FV-SPEC-052 | identifiability_justification | Scoped justification exists; finite matching ≠ universal equivalence |
| FV-SPEC-053 | status_contracts | Four statuses enforced; no silent promotion |
| FV-SPEC-054 | eligibility_reporting | Cross-file consistency: access ↔ witness ↔ margins |
| FV-SPEC-055 | claim_templates | Profile/stage scope; no universal erasure; no cross-stage causal inheritance |
| FV-SPEC-056 | scoped_cli_validation | Report output, strict mode, baseline comparison, zero endpoint calls |

### Deferred Checks (non-strict mode)

When `--strict` is not set, the following cross-file references are listed as `deferred` rather than causing failure:

- P0-5 margin threshold references
- P0-6 witness rule references
- P0-7 preregistration references

In `--strict` mode, these must all resolve or the check fails.

---

## Report Schema

```json
{
  "report_id": "uuid-string",
  "timestamp": "2026-09-22T12:00:00Z",
  "spec_root": ".factverify/spec",
  "scope": "access-profile",
  "strict": false,
  "profile_version": "1.0.0",
  "checks": [
    {
      "rule_id": "FV-SPEC-047",
      "rule_name": "access_contract_artifact",
      "status": "pass",
      "diagnostics": []
    }
  ],
  "capabilities": {
    "base_model": {"text": "verified", "scores": "unavailable", "internals": "unavailable"},
    "candidate": {"text": "verified", "scores": "declared", "internals": "unavailable"}
  },
  "permission_conflicts": [],
  "review_state": {
    "base_model": "current",
    "candidate": "pending"
  },
  "cross_file_checks": [
    {"target": "attacks.yaml", "resolved": true, "digest_match": true},
    {"target": "margins.yaml", "resolved": false, "digest_match": null}
  ],
  "input_digests": {
    "access_profile.md": "sha256:abc123...",
    "attacks.yaml": "sha256:def456..."
  },
  "deferred_checks": ["P0-5 margins", "P0-6 witness rule"],
  "baseline_comparison": null,
  "overall": "pass"
}
```

---

## Diagnostic Format

Each diagnostic string follows the pattern:

```
[RULE_ID] file:field — message
```

Examples:
```
[FV-SPEC-048] access_profile.md:systems.candidate.capabilities.scores — post-mask scores labelled as pre_mask; score_scope.type must be "post_mask"
[FV-SPEC-050] access_profile.md:interventions[0].actor_role — role "evaluator_1" not found in declared roles
[FV-SPEC-052] identifiability/j001.json:argument_type — empirical argument must note finite-observation limitation
[FV-SPEC-055] claim_templates/ct001.json:claim_text — universal erasure language detected: "completely removed"
```

---

## Integration Points

### Existing CLI (`tools/validate_spec.py`)

P0-4 adds `"access-profile"` to `SUPPORTED_SCOPES`. The `main()` function gains:
- `--access-dir` option (click.Path)
- Dispatch to `_run_access_profile_validation()` when `scope == "access-profile"`

### Validation Engine (`tools/access_profile_validator.py`)

Public entry point:
```python
def validate_access_profile(
    spec_root: str,
    access_dir: str,
    report_path: str | None = None,
    strict: bool = False,
    baseline_suite_path: str | None = None,
) -> tuple[bool, dict]:
    """
    Returns (passed: bool, report: dict).
    Exit code 0 if passed, 1 if not, 2 on input errors.
    """
```

### Cross-file Dependencies

| Artifact | Owner | P0-4 Role |
|----------|-------|-----------|
| `attacks.yaml` | P0-3 | Budget reference; channel permission cross-check |
| `margins.yaml` | P0-5 | Margin thresholds (deferred in non-strict) |
| `witness_rule.md` | P0-6 | Witness evidence requirements (deferred in non-strict) |
| `preregistration.md` | P0-7 | Claim template consistency (deferred in non-strict) |
| `fact_contract.schema.json` | P0-1 | Fact identity binding (resolved) |
| `closure_template.yaml` | P0-2 | Equivalence closure scope (resolved) |
