# Validator Interface Contract: P0-5 Margins

**Feature**: `20260922-103204-margins-alpha-effect`
**Created**: 2026-09-22

---

## CLI Interface

### Command

```
python tools/validate_spec.py \
  --scope margins \
  --spec-root .factverify/spec \
  --report reports/p0-5-validation.json \
  [--margins-dir .factverify/margins] \
  [--strict] \
  [--baseline-suite tests/fixtures/margins_spec/baselines/margins.yaml]
```

### Arguments

| Flag | Type | Required | Default | Description |
|------|------|----------|---------|-------------|
| `--scope` | string | yes | — | Must be `"margins"` for P0-5 validation |
| `--spec-root` | path | yes | — | Root of `.factverify/spec/` containing `margins.yaml` |
| `--report` | path | no | `None` | Output path for JSON validation report |
| `--margins-dir` | path | no | `{spec-root}/../margins` | Approvals and review manifest directory |
| `--strict` | flag | no | `False` | Require resolved applicable decisions, current reviews, consistent cross-file policies |
| `--baseline-suite` | path | no | `None` | Baseline `margins.yaml` for revision comparison |

### Exit Codes

| Code | Meaning |
|------|---------|
| 0 | All validation checks pass |
| 1 | One or more validation checks fail |
| 2 | Input file missing, malformed, or unparseable |

---

## Validation Rules

### Rule Dispatch

The validator executes checks in order FV-SPEC-057 through FV-SPEC-066. Each check produces:

```json
{
  "rule_id": "FV-SPEC-057",
  "rule_name": "margins_contract_artifact",
  "status": "pass | fail | deferred | skipped",
  "diagnostics": ["human-readable message", ...]
}
```

### Rule Summary

| Rule | Name | What it checks |
|------|------|----------------|
| FV-SPEC-057 | margins_contract_artifact | Versioned typed fields, units, domains; reject null coercion, unknown fields, non-finite, mixed units; no threshold-for-alpha substitution |
| FV-SPEC-058 | policy_approval | Approval records for FRR cap and practical-success; illustrative/unapproved values fail strict |
| FV-SPEC-059 | estimands_denominators | FRR/FCR estimands, weights, aggregation, status maps; empty denominators undefined; fixture rates 0.03 / 0.30 |
| FV-SPEC-060 | calibration_selection | Calibration-only; UCB(FRR) ≤ α eligibility; deterministic ties; infeasible / no final-test leakage |
| FV-SPEC-061 | practical_effect | Both baselines under common budget; delta units; conjunction for primary success |
| FV-SPEC-062 | uncertainty_dependence | Dependence/multiplicity contract; reject independent correlated-prompt resampling; zero errors ≠ zero uncertainty |
| FV-SPEC-063 | channel_locality_coverage | Margin per enabled channel and locality bucket; reject invalid aggregations; no superseded privacy import |
| FV-SPEC-064 | sample_size_handoff | Pilot power contract fields; flag power-against-zero vs d_min; no final N in P0 |
| FV-SPEC-065 | revision_protection | Baseline/amendment comparison; unauthorized policy change disallows confirmatory claim |
| FV-SPEC-066 | scoped_cli_validation | Report digests/decision status/deferred work; strict fail-closed; zero model/GPU/threshold-fitting |

### Deferred Checks (non-strict mode)

When `--strict` is not set, the following may be listed as `deferred` rather than failing:

- P0-6 witness-rule cross-checks
- P0-7 preregistration / amendment authorization
- P2-6 production bootstrap execution
- P4 empirical calibration and power runs

In `--strict` mode, applicable decisions must be resolved, approval reviews current, and required cross-file policies consistent (attacks channels/budgets, access status mappings, fact-contract buckets).

---

## Report Schema

```json
{
  "report_id": "uuid-string",
  "timestamp": "2026-09-22T12:00:00Z",
  "spec_root": ".factverify/spec",
  "scope": "margins",
  "strict": false,
  "margins_version": "0.1.0-demo",
  "checks": [
    {
      "rule_id": "FV-SPEC-057",
      "rule_name": "margins_contract_artifact",
      "status": "pass",
      "diagnostics": []
    }
  ],
  "decision_status": {
    "D-01": "open",
    "D-02": "open"
  },
  "input_digests": {
    "margins.yaml": "sha256:...",
    "attacks.yaml": "sha256:..."
  },
  "deferred_checks": [
    "P0-6 witness rule",
    "P0-7 amendment authorization",
    "P2-6 bootstrap engine",
    "P4 empirical calibration/power"
  ],
  "baseline_comparison": null,
  "overall": "pass"
}
```

---

## Diagnostic Format

```
[RULE_ID] file:field — message
```

Examples:
```
[FV-SPEC-057] margins.yaml:frr_cap.unit — mixed probability/percentage_points units are not allowed
[FV-SPEC-058] approvals/frr_cap.json:approver_id — missing approval for illustrative frr_cap value
[FV-SPEC-059] margins.yaml:estimands.frr — empty denominator is undefined, not 0.0
[FV-SPEC-060] margins.yaml:threshold_selection.data — final-test inputs forbidden for selection
[FV-SPEC-061] margins.yaml:practical_success — primary success requires both native and semantic_only
[FV-SPEC-062] margins.yaml:uncertainty.resampling_contract — correlated prompts are not independent replicates
[FV-SPEC-063] margins.yaml:locality_margins.compositional — missing oriented margin for bucket
[FV-SPEC-065] margins.yaml:version — frozen policy changed under unchanged revision
```

---

## Integration Points

### Existing CLI (`tools/validate_spec.py`)

P0-5 adds `"margins"` to `SUPPORTED_SCOPES`. The `main()` function gains:
- `--margins-dir` option (click.Path)
- Dispatch to `_run_margins_validation()` when `scope == "margins"`
- `--contracts` remains optional for this scope (same pattern as `access-profile`)

### Validation Engine (`tools/margins_validator.py`)

Public entry point:

```python
def validate_margins(
    spec_root: str | Path,
    margins_dir: str | Path,
    report_path: str | Path | None = None,
    strict: bool = False,
    baseline_suite_path: str | Path | None = None,
) -> tuple[bool, dict]:
    """Returns (passed, report). Exit 0 if passed, 1 if not, 2 on input errors."""
```

### Cross-file Dependencies

| Artifact | Owner | P0-5 Role |
|----------|-------|-----------|
| `fact_contract.schema.json` | P0-1 | Locality bucket enum |
| `attacks.yaml` | P0-3 | Enabled channels, common cap/budget |
| `access_profile.md` | P0-4 | Status mappings for estimand eligibility |
| `witness_rule.md` | P0-6 | Deferred non-strict; required when present in strict |
| `preregistration.md` | P0-7 | Amendment authorization (deferred non-strict) |
