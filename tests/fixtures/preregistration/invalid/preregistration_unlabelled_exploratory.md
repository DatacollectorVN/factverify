---
status: reviewed
version: "1"
digest: ""
receipt_location: reports/spec-v1-freeze-receipt.json
staged_milestones: [spec-v1, thresholds-v1, protocol-v1]
amendment_log: []
deviation_log: []
review_date: "2026-09-26"
reviewer: "Supervisor"
---

## Primary Question
ref: margins.yaml#primary_endpoint — Does FactVerify reduce FCR?

## Baselines
ref: margins.yaml#baselines — Native evaluator; Semantic-only evaluator.

## Hypotheses
ref: margins.yaml#hypothesis — FactVerify ΔFCR is lower than both baselines.

## Controlled Construction
ref: fact_contract.schema.json, closure_templates.yaml — Fictional facts.

## Evaluation Units
The atomic fact is the evaluation unit.

## Sampling
ref: margins.yaml#n_facts_target — Sample size by staged rule.

## Evaluation Protocol
ref: attacks.yaml, witness_rule.md, access_profile.md — Five-channel protocol.

## Primary Analysis
ref: margins.yaml — ΔFCR comparison with equal query budgets.

## Stopping Rules
ref: margins.yaml#stopping_rules — Eight deviation categories: feasibility_failure, no_feasible_threshold, scoring_bug, budget_overrun, model_revision, hardware_failure, missing_access, cost_limit. Broken final pass → full re-run.

## Deviations
ref: preregistration.md#amendment_log — Amendments follow predeclared protocol.

## Reporting
ref: witness_rule.md — Analysis classification:
- Primary endpoint (RQ1, ΔFCR): label: confirmatory
- Stage B pretrained facts: will be reported as-is (no label assigned)
- Unplanned analyses: label: exploratory
