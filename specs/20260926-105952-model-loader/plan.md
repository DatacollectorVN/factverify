# Implementation Plan: FV-MODEL — P2-0 Model Loader

**Branch**: `20260926-105952-model-loader` | **Date**: 2026-09-26 | **Spec**: [spec.md](spec.md)  
**Source**: `second-brain/ml-unlearning/requirements/FV-MODEL — P2-0.md` (draft)

## Summary

Every checkpoint in the study — base model ($M_0$), finetuned ($M_{FT}$), retain-only references ($M_R^{(k)}$), controls, and candidates — is loaded through a single public function `load_model`. It reads pinned revisions and file digests from `models.yaml` (at `spec-v1`), verifies every file before use, operates entirely offline, attaches LoRA adapters only to their matching base, and returns a `LoadedModel` carrying the model object, tokenizer, canonical identity hash, and the payload from which the hash was computed. No other module in the repository may call model-loading primitives.

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: PyTorch, Hugging Face Transformers (`AutoModelForCausalLM`, `AutoTokenizer`), PEFT (`PeftModel`, `load_peft_model`), PyYAML, hashlib (stdlib)  
**Storage**: Local filesystem (weight files, adapter directories); `models.yaml` spec artifact; no database  
**Testing**: pytest with a tiny local fixture model (avoids needing real HF downloads in CI)  
**Target Platform**: Linux GPU compute environment; offline after prefetch  
**Project Type**: Internal Python library (`src/models/` package within the study harness)  
**Performance Goals**: Load time and peak memory are recorded per role and adapter in the ledger (C-2); bounds are set after P3-5 feasibility study — not set here  
**Constraints**: Fail closed on any bad input (I8); no network access during a load; deterministic (identical logits, same seed, same device); all parameters from spec fields, never literals  
**Scale/Scope**: One loader serves all checkpoints across all study phases (P1-2, P2-1, P2-2, P2-3, P2-5, P2-7)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-checked after Phase 1 design.*

| # | Principle | Status | Notes |
|---|-----------|--------|-------|
| 1 | Spec Is Frozen (I8 · Fail Closed) | ✅ PASS | Loader takes explicit `spec_root`; raises before returning a model on any missing/invalid field; never writes to spec namespace |
| 2 | No Result-Dependent Choices | ✅ PASS | Loader has no interaction with thresholds, splits, or calibration data |
| 3 | Final Test Runs Once | ✅ PASS | Loader is stateless; does not affect test-pass execution logic |
| 4 | Equal Query Budgets (I4) | ✅ PASS | Loader is upstream of all evaluators; no query budget involvement |
| 5 | Seeded and Config-Driven | ✅ PASS | All model identities come from `models.yaml` spec fields; no magic literals in loader code |
| 6 | Ledger Everything | ✅ PASS | Loader returns `identity_hash` that P2-5 (FV-LEDG) records; loader itself does not write ledger rows |
| 7 | Gates Are Stop Points | N/A | Loader is not a gate |
| 8 | Wiki Governs Design | ✅ PASS | Sourced from `FV-MODEL — P2-0.md` and `FV-SPEC — P0-8`; three open decisions (D-46, D-48, D-50) are flagged |
| 9 | Equivalence and Inference Never Mix (I2) | N/A | Loader is not an evaluator |
| 10 | Claims Never Exceed the Channel (I3) | N/A | No verdicts produced by loader |
| 11 | Raw Maxima Are Never Verdicts (I5) | N/A | No scoring in loader |
| 12 | Prompts Are Not Replicates (I7) | N/A | No prompt handling in loader |

**All applicable gates pass. No violations.**

## Project Structure

### Documentation (this feature)

```text
specs/20260926-105952-model-loader/
├── plan.md              # This file
├── research.md          # Phase 0: decisions resolved
├── data-model.md        # Phase 1: entities and state
├── quickstart.md        # Phase 1: usage guide
├── contracts/
│   └── load_model.md    # Phase 1: public function contract
└── tasks.md             # Phase 2 output (/speckit.tasks — NOT created here)
```

### Source Code (repository root)

```text
src/models/
├── __init__.py          # exports: load_model, LoadedModel
├── loader.py            # load_model() — pinning, offline guard, precision, eval mode
├── verify.py            # file-digest verification (FV-MODEL-002)
├── identity.py          # canonical identity hash + payload (FV-MODEL-004)
└── adapters.py          # adapter attach, base-match check, adapter digest (FV-MODEL-005, 006)

scripts/
└── prefetch_models.py   # separate prefetch command (referenced by FV-MODEL-003)

tests/
└── test_models_loader.py  # all 9 named test hooks (FV-MODEL-001 through 009)
```

**Structure Decision**: Single project layout. `src/models/` is a new top-level package alongside the existing `src/eval/`, `src/cache/`, `src/controls/`, `src/stats/`, `src/train/`. No new top-level directories are needed. The prefetch script joins the existing `scripts/` directory.

## Complexity Tracking

No constitution violations — table not required.
