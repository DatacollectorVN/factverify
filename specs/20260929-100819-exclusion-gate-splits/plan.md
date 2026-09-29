# Implementation Plan: P1 Exclusion Gate and Entity-Disjoint Splits

**Branch**: `20260929-100819-exclusion-gate-splits` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/20260929-100819-exclusion-gate-splits/spec.md`

## Summary

After Pythia-410M is pinned, record D-65 and D-68 in a caller-supplied decisions file, probe the pinned base model with the applicable equivalence closure, and assign Block 0 splits of 8 construction facts and 8 calibration facts. The exclusion gate is `scripts/exclusion_gate.py`. Split assignment is `scripts/make_splits.py`. Neither script edits `.factverify/spec/`.

D-65 is a random-choice baseline of 0.5: a fact is `excluded_known` when any direction's accuracy is greater than 0.5. D-68 assigns no final-test pool; leftover eligible authors stay unassigned; each assigned split must contain occupation, birthplace, nationality, and genre.

Design sources, read from disk because the Obsidian vault tools were unavailable: [FV-DATA — P1-SIGNOFF](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-SIGNOFF.md) (status: in-progress), "Recommended order"; [FV-DATA — P1-2](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-2.md) (status: draft), FV-DATA-013–018; [FV-DATA — P1-6](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-DATA%20%E2%80%94%20P1-6.md) (status: draft), FV-DATA-035–039; [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md) (status: planned), Phase 1 and Phase 3 and the risk-register row "Base model already knows a fictional fact".

## Technical Context

**Language/Version**: Python 3.11 (managed by uv)
**Primary Dependencies**: PyYAML (decision records), PyTorch + Hugging Face Transformers via `src/models/load_model` only, existing `src/cache` and `src/ledger`, hashlib via `src/data/digests`
**Storage**: YAML decision file; JSONL gate results; JSON split file; Markdown gate report; SQLite ledger (`study_artifacts` row for the split digest); JSONL access-denial log
**Testing**: pytest (`tests/test_exclusion_gate.py`, `tests/test_splits.py`)
**Target Platform**: macOS / Linux. Unit tests use a fake model port. A real gate run needs the pinned Pythia-410M weights locally.
**Project Type**: Research data-preparation CLIs plus a split loader
**Performance Goals**: Unit tests finish without loading Pythia. A real gate run's cost is one greedy generation per applicable template per fact at the declared seed.
**Constraints**: Fail closed on an open decision, a hash mismatch, an empty probe grid, or a missing entailment audit. No edits under `.factverify/spec/`. Exclusion probes do not charge the evaluator query-budget accountant. Class I templates stay out of the accuracy denominator (I2).
**Scale/Scope**: Block 0. Current `facts.jsonl` has 30 draft contracts. D-68 asks for 16 assigned facts. The frozen closure file's relation manifest is `capital_of` and `alma_mater`, so a run against that file marks every TOFU fact `incomplete` until a spec amendment adds D-63 templates.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I8 — Spec Is Frozen / Fail Closed** | ✅ PASS | Decisions and seeds live in a caller-supplied YAML. Missing fields, an open row, or a model-hash mismatch refuse the run. `.factverify/spec/` is read only. |
| **No Result-Dependent Choices** | ✅ PASS | 0.5, the seed list, 8/8, and the four relations are recorded before verdicts or assignments. Too few eligible facts raises; the build does not shrink a split. |
| **Final Test Runs Once** | ✅ PASS | This assignment writes no final-test labels. `load_split` refuses a final-test read unless the ledger role is `final_test_pass`, and logs the refusal. |
| **I4 — Equal Query Budgets** | ✅ PASS | The gate is not an evaluator arm. It does not call `Accountant.query`. Completions go through `src/cache`. Cost is stored on the gate row for provenance. |
| **Seeded and Config-Driven** | ✅ PASS | Threshold, seeds, decoding, split counts, and the contamination trigger are fields on the decisions file. Tests may supply other closed values to prove the code reads the file. |
| **Ledger Everything** | ✅ PASS | Split seed and digest are an append-only `study_artifacts` row. Gate rows carry wall-clock, GPU-hours, and peak memory. Checkpoint rows are not reused for a multi-fact split file. |
| **Gates Are Stop Points** | ✅ PASS | Excluded share above the recorded trigger stops source-bundle construction until an owner decision is cited. |
| **Wiki Governs Design** | ✅ PASS | Behavior follows FV-DATA-013–018 and FV-DATA-035–039. Both requirement notes are `draft`. The sign-off note is `in-progress`. |
| **I2 — Equivalence/Inference Never Mix** | ✅ PASS | Accuracy uses class E templates with empty `extra_premises`, grouped by `primary_family`. Class I probes are listed aside and do not enter the fraction. |
| **I3 — Claims Never Exceed Channel** | ✅ PASS | A `pass` verdict means "not above the guessing baseline on this probe grid." It does not claim the fact is absent from the weights. |
| **I5 — Raw Maxima Not Verdicts** | ✅ PASS | The verdict statistic is direction accuracy against 0.5. Per-cell scores stay in the grid. |
| **I7 — Prompts Not Replicates** | ✅ N/A | No FCR estimate and no bootstrap in this feature. |
| **Code Quality** | ✅ REQUIRED | PEP 8, full annotations, ruff. `make lint` and `make test` before the feature is complete. |

**Post-design re-check**: All principles pass. The additive ledger table is recorded under Complexity Tracking because the checkpoint schema cannot hold a multi-fact split digest without a fake `fact_id`.

## Project Structure

### Documentation (this feature)

```text
specs/20260929-100819-exclusion-gate-splits/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── decisions.md
│   ├── exclusion_gate.md
│   └── splits.md
└── tasks.md             # /speckit.tasks — not created here
```

### Source Code

```text
scripts/
├── exclusion_gate.py        # P1-2 CLI
└── make_splits.py           # P1-6 CLI

src/data/
├── decisions.py             # load D-65 and D-68; refuse while open
├── exclusion.py             # probe grid, verdicts, contamination alarm
└── splits.py                # assignment, digest, final-test guard

src/models/
└── generate.py              # greedy completion; from_pretrained stays in loader.py

src/ledger/
├── schema.py                # additive study_artifacts table, schema version stays "1"
└── api.py                   # add_study_artifact

src/train/run.py             # _precheck calls require_pass when gate_report is set
scripts/build_bundles.py     # --gate-report enforces the contamination alarm

data/controlled/
├── block0_decisions.yaml    # closed D-65 and D-68 for the study run
├── facts.jsonl              # input; not rewritten
└── splits.json              # output

results/
├── exclusion_gate.jsonl
└── split_access.jsonl       # refused final-test loads

reports/
└── exclusion_gate.md

tests/
├── test_exclusion_gate.py   # FV-DATA-013–018
└── test_splits.py           # FV-DATA-035–039
```

**Structure Decision**: Scripts stay thin. Grid, verdict, and split rules live in `src/data/`. Model loading stays in `src/models/`. The cache and the ledger stay the existing modules. Tests never download Pythia.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| Additive `study_artifacts` table on ledger schema version `1` | FV-DATA-037 requires the split seed and digest in the ledger. `ensure_schema` rejects any `schema_version` other than `1`, so the table is created with `CREATE TABLE IF NOT EXISTS` and append-only triggers. | A checkpoint row would need a fake `fact_id` and a role outside `{base, finetuned, reference, control, candidate}`. Evaluation runs join to checkpoints. |
