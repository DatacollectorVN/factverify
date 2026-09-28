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
ref: fact_contract.schema.json, closure_templates.yaml — Fictional facts with references.

## Evaluation Units
The atomic fact is the evaluation unit.

## Sampling
ref: margins.yaml#n_facts_target — Sample size by staged rule.

## Evaluation Protocol
ref: attacks.yaml, witness_rule.md, access_profile.md — Five-channel protocol.

## Primary Analysis
ref: margins.yaml — ΔFCR comparison with equal query budgets.

## Stopping Rules
ref: margins.yaml#stopping_rules — Eight deviation categories:
- feasibility_failure: abandon study if controlled construction is infeasible
- no_feasible_threshold: report infeasible, gate fails
- scoring_bug: patch and resume from last checkpoint
- budget_overrun: halt immediately, report as deviation
- model_revision: treat as hardware_failure equivalent
- hardware_failure: pause and resume if checkpointed, else report
- missing_access: report as cost_limit equivalent
- cost_limit: halt and report
Broken final pass: patch and resume is acceptable if changes are documented.

## Deviations
ref: preregistration.md#amendment_log — Amendments follow predeclared protocol.

## Reporting
ref: witness_rule.md — Confirmatory: primary endpoint. Exploratory: Stage B analyses carry label: exploratory.
