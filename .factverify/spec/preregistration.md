---
status: needs-review
version: "1"
digest: "sha256:f816b9ddbbd096bbd81b14c1f3d0ac7ae03de81de69efcb4fb3d8d759ed10767"
receipt_location: reports/spec-v1-freeze-receipt.json
staged_milestones: [spec-v1, thresholds-v1, protocol-v1]
amendment_log:
  - id: AMD-001
    trigger: "Concrete model selections need to change without editing the historical model snapshot."
    allowed_information: "Protocol structure only. No exclusion-gate scores, calibration outcomes, or final-test outcomes."
    approver: "study owner"
    deadline_before_final_access: "2027-03-01"
    effect_size_link: "margins.yaml#minimum_fcr_reduction_absolute"
    sample_size_link: "margins.yaml#sample_size_handoff"
    previous_value: "Concrete pins live in .factverify/spec/models.yaml."
    new_value: "Policy lives in .factverify/spec/model_policy.yaml. Concrete selections live in config/models/. Effect size and sample size are unchanged."
    authorized: false
    post_hoc: false
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
