# Implementation Plan: Model Role Names and Versioned Model Configuration

**Branch**: `20260929-225846-model-role-config` | **Date**: 2026-09-29 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `specs/20260929-225846-model-role-config/spec.md`

## Summary

New model selections use the role names `controlled_fact_base` and `pretrained_fact_confirmation`. The frozen specification gains a policy document that names those roles and the checks a selection must pass. Concrete repositories, revisions, and file fingerprints move to named files under `config/models/`. `.factverify/spec/models.yaml` is not edited. There is no `spec-v1` git tag in this clone; the guard is a byte-for-byte comparison of that file.

The loader, the model validator, and prefetch all read one parser. New model identities use the validator's existing FV-SPEC-093 payload, which does not include the role name. The loader's current payload stays verifiable as identity schema version 1. Production commands take an explicit configuration path and an explicit role. New gate reports, ledger rows, cache entries, training runs, and evaluation runs store the configuration binding beside the model identity.

Design sources, read from disk because the Obsidian vault tools were unavailable: [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md) (status: planned), P0-8 and Phase 6 (P6-8); [FV-SPEC — P0-8](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-SPEC%20%E2%80%94%20P0-8.md) (status: draft), FV-SPEC-089–095; [FV-MODEL — P2-0](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-MODEL%20%E2%80%94%20P2-0.md) (status: draft), the `load_model` interface. The decision catalog, not the draft note, is the status of D-46 (closed), D-47 (open), D-48 (closed), and D-49 (closed).

## Technical Context

**Language/Version**: Python 3.11 (managed by uv)
**Primary Dependencies**: PyYAML (policy and model configuration). Hashing uses `hashlib` and `src/data/digests.sha256_file`. Model construction stays inside `src/models/loader.py`. Ledger and cache stay the existing SQLite modules. No new package.
**Storage**: YAML policy at `.factverify/spec/model_policy.yaml`; YAML selections under `config/models/`; additive nullable columns on ledger `checkpoints` and `evaluation_runs`; provenance fields on exclusion-gate JSONL rows and the Markdown report; additive nullable columns on cache `entries`; cache key payload gains `model_config_digest`
**Testing**: pytest. Loader tests keep using the local tiny model fixture. No test downloads weights.
**Target Platform**: macOS / Linux
**Project Type**: Research model-loading library, spec validator, and operator CLIs
**Performance Goals**: A refused configuration does no model construction and no network access. Policy checks and hashing are offline.
**Constraints**: Do not modify `.factverify/spec/models.yaml`. Do not create or move a git tag. Do not set the new amendment to `authorized: true`. Fail closed before `from_pretrained`. Identity schema version 1 remains computable. Ledger schema version stays `"1"`. Checkpoint `role` and checkpoint `identity_hash` keep their current meanings.
**Scale/Scope**: Two roles. One Block 0 debug configuration copied from the current Pythia pin. The confirmation role stays pending. Callers updated in this feature: `load_model`, `tools/models_validator.py`, `scripts/prefetch_models.py`, `scripts/exclusion_gate.py`, and `src/train/run.py`.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|---|---|---|
| **I8 — Spec Is Frozen / Fail Closed** | ✅ PASS | `models.yaml` bytes stay as they are. The policy file and one `amendment_log` entry are the amendment, with `authorized: false`. No tag is created. Missing configuration, missing role, unresolved fields, and hash mismatches refuse the run. |
| **No Result-Dependent Choices** | ✅ PASS | This feature selects no Block 1 model and does not fill D-47. `attn_impl: eager` on the debug configuration is the ticket's worked example for that file, not a value chosen from a result. |
| **Final Test Runs Once** | ✅ PASS | No final-test path is added or resumed. |
| **I4 — Equal Query Budgets** | ✅ PASS | The exclusion gate still does not call the query-budget accountant. Cache hits and misses stay inside `src/cache`. |
| **Seeded and Config-Driven** | ✅ PASS | Role purposes, the identity schema version written on new records, and the concrete pin live in the policy or in a named configuration. Production commands have no implicit configuration. |
| **Ledger Everything** | ✅ PASS | New checkpoint and evaluation rows gain the configuration binding. Old rows stay null and are not updated. `checkpoints.identity_hash` remains the checkpoint id. |
| **Gates Are Stop Points** | ✅ PASS | The amendment stays unauthorized. Tagging and `authorized: true` wait for the owner. |
| **Wiki Governs Design** | ✅ PASS | Role jobs follow P0-8 and P6-8. P0-8 and P2-0 are `draft`. The execution plan is `planned`. Catalog status overrides the draft note where they disagree (D-48 is closed). |
| **I2 — Equivalence/Inference Never Mix** | ✅ N/A | No probe scoring changes. |
| **I3 — Claims Never Exceed Channel** | ✅ PASS | No new claim about facts being absent from the weights. |
| **I5 — Raw Maxima Not Verdicts** | ✅ N/A | No verdict statistic changes. |
| **I7 — Prompts Not Replicates** | ✅ N/A | No FCR estimate. |
| **Code Quality** | ✅ REQUIRED | PEP 8, full annotations, ruff. `make lint` and `make test` before the feature is complete. |
| **Decision Identification** | ✅ PASS | D-46 and D-47 keep their catalog keys. This feature does not add a second key for either legacy id. New errors name the role and the field. They do not invent a new `D-*` id. |

**Post-design re-check**: All principles pass. Two expansions are recorded under Complexity Tracking: a new file in the spec directory, and additive ledger and cache columns on schema version `"1"`.

## Project Structure

### Documentation (this feature)

```text
specs/20260929-225846-model-role-config/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── model-policy.md
│   ├── model-config.md
│   ├── load-and-prefetch.md
│   └── provenance.md
└── tasks.md             # /speckit.tasks — not created here
```

### Source Code

```text
.factverify/spec/
├── models.yaml                 # unchanged bytes
├── model_policy.yaml           # new frozen policy
└── preregistration.md          # AMD-001 appended; digest recomputed

config/models/
└── block0-debug-pythia-410m.yaml

src/models/
├── spec.py                     # one parser for policy and configuration
├── identity.py                 # version 1 verifier; version 2 writer
├── loader.py                   # required model_config path
└── verify.py                   # compare sha256:-prefixed fingerprints

src/ledger/
├── schema.py                   # nullable binding columns
└── api.py                      # write them on new checkpoint and eval rows

src/cache/
├── key.py                      # key includes model_config_digest
└── store.py                    # nullable binding columns; no key migration

src/data/exclusion.py           # binding on each row and on the report
src/train/config.py             # required model_config path
src/train/run.py                # pass the path; refuse a gate report with another binding

scripts/exclusion_gate.py       # --model-config required; no default role
scripts/prefetch_models.py      # same parser; no network until the document is valid

tools/models_validator.py       # call the shared parser; keep FV-SPEC-089–095
tools/freeze.py                 # SPEC_ARTIFACTS gains model_policy.yaml

tests/
├── test_models_spec.py
├── test_models_loader.py
├── test_model_config.py        # aliases, conflicts, tamper, identity versions
└── fixtures/models_*/
```

**Structure Decision**: Parsing lives in `src/models/spec.py`. The validator, the loader, and prefetch call it. Provenance is extra columns and report fields. No second model-loading entry point.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|---|---|---|
| New file `.factverify/spec/model_policy.yaml` beyond the constitution's seven-artifact sentence. `models.yaml` is already an eighth artifact. | FR-005 keeps the concrete pin out of future edits of the frozen snapshot. The policy is the normative model document for the next revision. | Editing `models.yaml` in place would change the snapshot this feature is required to preserve. |
| Additive nullable columns on ledger schema version `"1"` and on the cache `entries` table | New rows must store the configuration binding. `ensure_schema` rejects any `schema_version` other than `"1"`, as it did for `decision_key`. | Putting the model identity in `checkpoints.identity_hash` would collide with the checkpoint id. Putting the study role in `checkpoints.role` would collide with reference / control / candidate. |
