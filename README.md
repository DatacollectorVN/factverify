# FactVerify

Validating evaluators for atomic-fact unlearning in LLMs.

**Goal:** measure ΔFCR on held-out oracle systems at FRR ≤ α with equal query
budgets, comparing a native evaluator, a semantic-only evaluator, and FactVerify.

The design lives in my Obsidian wiki, not here:
`second-brain/ml-unlearning/04-Experiments/FactVerify — Execution Plan.md`.
Seven phases, four gates. See `CLAUDE.md` for the working rules and
`CLI-SETUP.md` to connect a Claude Code session to the wiki.

## Status

Phase 0 (freeze the spec) / Phase 2 (harness and ledger). Nothing implemented yet.

| Gate | After | Question | Status |
|---|---|---|---|
| 1 | Block 0 | Can positives and hard negatives be separated at all? | not reached |
| 2 | Block 1 | Is ΔFCR real at FRR ≤ α? | not reached |
| 3 | Block 2 | Which components survive? | not reached |
| 4 | Block 3 | Does anything transfer to pretrained facts? | not reached |
