# Validator Interface Contract: P0-3 Attack Specification

## CLI Interface

```
tools/validate_spec.py
  --scope attacks                  # Required. P0-3 scope.
  --spec-root PATH                 # Required. Default: .factverify/spec
  --contracts PATH                 # Required. P0-1 contract directory.
  --access-profile PATH            # Optional. P0-4 access profile for permission checks.
  --event-fixtures PATH            # Optional. Event trace fixtures for replay validation.
  --witness-rule PATH              # Optional. P0-6 witness rule for confirmation cross-check.
  --report PATH                    # Required. Output report path (JSON).
  [--strict]                       # Optional. Require resolved decisions & current audits.
  [--baseline-suite PATH]          # Optional. Prior attacks.yaml for revision check.
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0    | All requested checks passed |
| 1    | One or more validation failures |
| 2    | Missing/malformed inputs (spec, empty contracts, bad invocation) |

## Report Schema

```json
{
  "scope": "attacks",
  "spec_path": "/absolute/path/to/attacks.yaml",
  "spec_digest": "sha256:abcdef...",
  "upstream_digests": {
    "fact_contract_schema": "sha256:...",
    "closure_templates": "sha256:...",
    "access_profile": "sha256:... | not_provided"
  },
  "timestamp": "2026-09-22T12:00:00Z",
  "allocation_check": {
    "status": "pass|fail",
    "common_cap": 96,
    "arms": [
      {
        "arm_id": "native",
        "total": 96,
        "channel_breakdown": [
          {"channel_id": "prompt_variation", "trials": 60},
          {"channel_id": "confirmation", "trials": 12},
          {"channel_id": "locality", "trials": 24}
        ],
        "matches_cap": true
      }
    ]
  },
  "channel_permissions": {
    "status": "pass|fail|not_checked",
    "channels": [
      {
        "channel_id": "prompt_variation",
        "enabled": true,
        "permissions_met": true,
        "missing_capabilities": []
      }
    ]
  },
  "accounting_check": {
    "status": "pass|fail",
    "units_defined": true,
    "policies_complete": true,
    "unresolved_decisions": ["D-19"]
  },
  "event_replay": {
    "status": "pass|fail|not_requested",
    "traces_replayed": 5,
    "charges_deterministic": true,
    "policy_violations": []
  },
  "confirmation_check": {
    "status": "pass|fail|not_checked",
    "reservations": [
      {
        "reservation_id": "confirm_001",
        "route_ref": "witness_route_a",
        "sufficient": true,
        "double_funded": false
      }
    ]
  },
  "policy_check": {
    "status": "pass|fail",
    "policies": [
      {
        "policy_id": "adaptive_sampling",
        "bounded": true,
        "search_space_finite": true,
        "stop_rule_declared": true
      }
    ]
  },
  "audit_check": {
    "status": "pass|fail|not_checked",
    "manifests_found": 2,
    "revision_bound": true,
    "unreviewed_inputs": []
  },
  "transformation_check": {
    "status": "pass|fail|not_applicable",
    "recipes": [
      {
        "recipe_id": "gptq_4bit",
        "complete": true,
        "missing_fields": []
      }
    ]
  },
  "relearning_check": {
    "status": "pass|fail|not_applicable",
    "conditions_separated": true,
    "exposure_types": ["target_free", "target_exposed"]
  },
  "cost_records": [
    {
      "arm_id": "native",
      "cap": 96,
      "actual_trials": 90,
      "unused_trials": 6,
      "generation_trials": 80,
      "candidate_scores": 10,
      "input_tokens": 45000,
      "output_tokens": 12000,
      "training_steps": 0,
      "exports": 0,
      "wall_clock_seconds": 120.5
    }
  ],
  "revision_check": "not_requested | { status, details[] }",
  "deferred_checks": [
    "P0-5 margin thresholds (not yet available)",
    "P0-6 witness-rule confirmation mapping (if --witness-rule not provided)",
    "P0-7 preregistration cross-reference"
  ],
  "diagnostics": [],
  "summary": {
    "total_checks": 13,
    "passed": 11,
    "failed": 0,
    "deferred": 2
  }
}
```

## Diagnostic Format

```json
{
  "rule_id": "FV-SPEC-038",
  "item_id": "arm:native",
  "file": "attacks.yaml",
  "json_pointer": "/arms/0/total",
  "message": "Arm total (90) does not equal common cap (96)"
}
```

## Scope Semantics

- `attacks`: P0-3 attack specification validation only
- Ordinary mode: checks structure, allocations, accounting, policies, recipes; marks semantic readiness pending
- `--strict` mode: additionally rejects unresolved D-17–D-29/D-31, missing/stale audits, incomplete confirmation mappings, missing enabled-channel margins
- `--event-fixtures`: enables offline replay validation of event traces against declared charge policies
- `--access-profile`: enables cross-checking channel capabilities against declared permissions (FV-SPEC-035)
- `--witness-rule`: enables cross-checking confirmation reservations against witness-rule routes (FV-SPEC-039)
- Deferred checks (P0-5 margins, P0-7 preregistration) are listed but not evaluated
- Neither mode establishes full Phase 0 readiness

## Interaction with P0-1 and P0-2

- `--scope fact-contract` and `--scope closure-templates` continue to work unchanged
- `--scope attacks` validates upstream references to P0-1 and P0-2 artifacts
- Channel definitions reference closure template groups/splits for prompt-attack channels
- No P0-1 or P0-2 schema changes are introduced by P0-3
- P0-2's deferred check "P0-3 budget accounting" is resolved by this scope
