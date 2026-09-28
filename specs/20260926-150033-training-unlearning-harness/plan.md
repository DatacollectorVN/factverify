# Implementation Plan: FV-HARN — P2-1 Training and Unlearning Harness

**Branch**: `20260926-150033-training-unlearning-harness` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)  
**Source**: `second-brain/ml-unlearning/requirements/FV-HARN — P2-1.md` (draft)

## Summary

Every finetuned checkpoint ($M_{FT}$), retain-only reference ($M_R$), and unlearned candidate is produced by one entry point, `run_job`, from one job configuration and one seed. The job fails closed before the first training step when the configuration is incomplete, the manifest is violated, a reference leaks its source bundle, the reference procedure drifts from its paired finetune, or a reference seed is already recorded for that fact on another split. A successful return happens only after checkpoint metadata is written and exactly one ledger row is committed. Model weights are loaded only through `load_model` (P2-0). Ledger storage stays in P2-5; this feature supplies the row and a narrow write/query port.

Numeric hyperparameters (D-51), LoRA rank / alpha / target modules (D-52), and the determinism tolerance (D-53) are required configuration fields. This plan does not choose their study values.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyTorch, Hugging Face Transformers, PEFT (LoRA via `get_peft_model` / `save_pretrained` only — `from_pretrained` stays inside `src/models/`), PyYAML, hashlib (stdlib). Model loading through the existing `load_model` API.  
**Storage**: Adapter directories on the local filesystem (`metadata.json`, `fv_adapter_meta.json`, PEFT weights). Ledger rows go through a `LedgerPort`; `ledger.sqlite` is owned by P2-5. Job configs under `configs/train/`.  
**Testing**: pytest. Named hooks in `tests/test_harness.py`. Tiny local fixture model and one-step jobs so CI does not download weights or require a GPU.  
**Target Platform**: Linux GPU for study runs; CPU fixture for the harness tests  
**Project Type**: Internal Python library plus CLI (`python -m src.train.run`) inside the study harness  
**Performance Goals**: Cost is recorded per job (wall-clock, GPU-hours, peak memory, steps, examples). Numeric bounds are set at Gate 1 from the P3-5 feasibility pass, not in this plan.  
**Constraints**: Fail closed before the first training step (I8). No magic numbers: every hyperparameter is a declared config field. Manifest-only reads. Reference procedure matches the paired finetune except for the closed identity allowlist. Success requires a committed ledger row. PEP 8, full type annotations, `ruff check` and `ruff format`. Do not edit `.factverify/spec/` or `spec-unlearning/`.  
**Scale/Scope**: One harness for finetune, retain-only reference, and four unlearning methods (GA, GradDiff, NPO, RMU), used by P3-1, P4-2, and the P6-4 relearning primitive. Block 3 learning-rate sweep, fake controls, evaluation, and ledger storage are out of scope.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

Design notes were read from disk. The Obsidian MCP server is not available in this session.

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | CLI and `run_job` take an explicit `spec_root`. Missing, null, or `DECISION_REQUIRED` fields raise before the first step. The harness never writes the spec namespace. |
| 2 | No Result-Dependent Choices | ✅ PASS | Hyperparameters, LoRA settings, and the determinism tolerance are config fields. D-51, D-52, and D-53 stay open. Reference seeds are refused when the ledger already has that fact+seed on another split (I6). |
| 3 | Final Test Runs Once | ✅ PASS | The harness does not open evaluation passes. It refuses a reference seed reused across splits so a later final-test pass cannot share reference seeds with calibration. |
| 4 | Equal Query Budgets (I4) | ✅ PASS | No evaluator queries. Training cost is a recorded vector (wall-clock, GPU-hours, peak memory, steps, examples), matching handbook §6.5's "budget is a vector". |
| 5 | Seeded and Config-Driven | ✅ PASS | Data order, adapter init, and dropout come from the declared seed. The field-name registry lists keys, never study values. |
| 6 | Ledger Everything | ✅ PASS | Success is returned only after `LedgerPort.commit_checkpoint`. SQLite schema, append-only triggers, and the CLI stay in FV-LEDG (draft). Study checkpoints are not run until that port is backed by the real ledger. Tests use an in-memory port. |
| 7 | Gates Are Stop Points | ✅ PASS | This plan does not set Gate 1 cost bounds or loosen any control. |
| 8 | Wiki Governs Design | ✅ PASS | Execution Plan (status: planned), heading "Phase 2 — Harness and run ledger", task P2-1. Retain-Only Reference Model (status: needs-review), heading "How It Works" ($M_R=\mathcal{A}(D\setminus F)$). Handbook (status: draft): I6, I7, I8, §6.5, §6.7. FV-HARN and FV-LEDG are draft. |
| 9 | Equivalence and Inference Never Mix (I2) | N/A | No probes. |
| 10 | Claims Never Exceed the Channel (I3) | N/A | No verdicts. |
| 11 | Raw Maxima Are Never Verdicts (I5) | N/A | No scoring. |
| 12 | Prompts Are Not Replicates (I7) | ✅ PASS | Each job produces one checkpoint. Seeds are update seeds recorded on the row. The harness does not treat prompts or samples as replicates. |
| 13 | Code Quality | ✅ PASS | New modules under `src/train/` and `tests/test_harness.py` carry annotations and pass ruff. |

**All applicable gates pass. No violations.** Post-design re-check: the ledger port, the procedure allowlist, and the two metadata files do not add a gate violation. D-51, D-52, and D-53 remain open on purpose.

## Project Structure

### Documentation (this feature)

```text
specs/20260926-150033-training-unlearning-harness/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── run_job.md
│   ├── job_config.md
│   ├── checkpoint_metadata.md
│   └── ledger_port.md
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/train/
├── __init__.py          # exports: run_job, JobResult, FactVerifyHarnessError
├── errors.py            # FactVerifyHarnessError
├── config.py            # FV-HARN-001, FV-HARN-004 — load, hash, procedure match
├── seeding.py           # FV-HARN-002
├── manifests.py         # FV-HARN-003 — source-bundle exclusion
├── data.py              # FV-HARN-006 — manifest-only reads and access log
├── methods/             # FV-HARN-005
│   ├── __init__.py      # name → trainer registry
│   ├── finetune.py
│   ├── ga.py
│   ├── graddiff.py
│   ├── npo.py
│   └── rmu.py
├── checkpoint.py        # FV-HARN-007 — stage, metadata, publish, rollback
├── cost.py              # FV-HARN-009
├── ledger.py            # LedgerPort protocol (storage is P2-5)
└── run.py               # FV-HARN-008, FV-HARN-010 — orchestration and CLI

configs/train/           # operator job files (no study values until D-51–D-53 close)
tests/
├── test_harness.py      # test_fv_harn_001 … test_fv_harn_010
└── fixtures/harness/    # tiny corpus, manifests, job YAMLs
```

**Structure Decision**: Single project. `src/train/` is the package the execution plan already assigns to P2-1. Module files match the trace targets in FV-HARN. No new top-level package. `from_pretrained` remains only in `src/models/` (existing FV-MODEL-009 scan).

## Complexity Tracking

No constitution violations — table not required.

## Open decisions (do not close in implementation)

| ID | What stays unset | Blocks study values for |
|----|------------------|-------------------------|
| D-51 | Unlearning hyperparameters per method for Blocks 0–2 | FR-001, FR-005 |
| D-52 | LoRA rank, alpha, target modules shared by $M_{FT}$ and $M_R$ | FR-001 |
| D-53 | Determinism policy and adapter-digest tolerance | FR-002 |

Fixture job files under `tests/fixtures/harness/` may carry concrete numbers so the hooks can run. Those numbers are test inputs, not Block 0–2 settings. No requirement is marked implemented while its decision is open.
