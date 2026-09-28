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
ref: margins.yaml#primary_endpoint — Does FactVerify reduce FCR at fixed FRR ≤ α?

## Baselines
ref: margins.yaml#baselines — Native evaluator; Semantic-only evaluator.

## Hypotheses
ref: margins.yaml#hypothesis — FactVerify ΔFCR < Native ΔFCR and FactVerify ΔFCR < Semantic-only ΔFCR at FRR ≤ α.

## Controlled Construction
ref: fact_contract.schema.json, closure_templates.yaml — Fictional facts finetuned into a base model with leave-one-fact-out references.

## Evaluation Units
The atomic fact is the evaluation unit. One checkpoint × N facts × M prompts = N*M responses, not N*M experiments.

## Sampling
ref: margins.yaml#n_facts_target — Sample size determined by staged rule at P4-3.

## Evaluation Protocol
ref: attacks.yaml, witness_rule.md, access_profile.md — Five-channel protocol (C1–C5).

## Primary Analysis
ref: margins.yaml — ΔFCR comparison at FRR ≤ α with equal query budgets. Cluster bootstrap over checkpoint/fact blocks.

## Deviations
ref: preregistration.md#amendment_log — Amendments follow the predeclared amendment protocol.

## Reporting
ref: witness_rule.md — Confirmatory: primary endpoint. Exploratory: Stage B pretrained facts, unplanned analyses, post-freeze paraphrases.
