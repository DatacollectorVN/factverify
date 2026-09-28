---
status: needs-review
version: "1"
digest: "sha256:dcfd75802295c4dacc2db5bf2c2b62aafb51ba3efbfd5544115aaef40a947795"
receipt_location: reports/spec-v1-freeze-receipt.json
staged_milestones: [spec-v1, thresholds-v1, protocol-v1]
amendment_log: []
deviation_log: []
---

## Primary Question
ref: margins.yaml#primary_endpoint — Does FactVerify reduce FCR at fixed FRR ≤ α?

## Baselines
ref: margins.yaml#baselines — Native evaluator; Semantic-only evaluator.

## Hypotheses
ref: margins.yaml#hypothesis — FactVerify ΔFCR < Native ΔFCR and FactVerify ΔFCR < Semantic-only ΔFCR at FRR ≤ α.

## Controlled Construction
ref: fact_contract.schema.json, closure_templates.yaml — Fictional facts finetuned into a base model with leave-one-fact-out references.

## Evaluation Units
ref: fact_contract.schema.json — The atomic fact is the evaluation unit. One checkpoint × N facts × M prompts = N*M responses, not N*M experiments.

## Sampling
ref: margins.yaml#n_facts_target — Sample size determined by staged rule at P4-3. Stratified by popularity, relation, tokenisation, alias count, baseline knowledge, and inferability.

## Evaluation Protocol
ref: attacks.yaml, witness_rule.md, access_profile.md — Five-channel protocol (C1–C5): native metrics, equivalence closure, control calibration, recovery and deployment, locality and utility.

## Primary Analysis
ref: margins.yaml — ΔFCR comparison at FRR ≤ α with equal query budgets. Cluster bootstrap over checkpoint/fact blocks. All parameters frozen before final testing.

## Stopping Rules
ref: margins.yaml#stopping_rules — Eight deviation categories: feasibility_failure, no_feasible_threshold, scoring_bug, budget_overrun, model_revision, hardware_failure, missing_access, cost_limit. Broken final pass → full re-run on fresh split, never patch and resume.

## Deviations
ref: preregistration.md#amendment_log — Amendments follow the predeclared amendment protocol. All post-freeze changes require a new tag and a recorded justification.

## Reporting
ref: witness_rule.md — Confirmatory: primary endpoint (RQ1, ΔFCR at FRR ≤ α). Exploratory: Stage B pretrained facts, unplanned analyses, post-freeze paraphrases. Secondary/Stage B analyses carry label: exploratory. Post-freeze paraphrase analyses carry label: exploratory.
