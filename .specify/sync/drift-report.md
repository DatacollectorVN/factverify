# Spec Drift Report

Generated: 2026-09-26T07:27:06Z
Project: factverify
Scope: `20260926-101858-base-model-pinning` — drift between `spec.md` (FR-001–FR-009, SC-001–SC-007, acceptance scenarios) and the implementation.

Wiki sources (Obsidian MCP unavailable; read from disk):
- `second-brain/ml-unlearning/04-Experiments/FactVerify — Execution Plan.md` — Phase 0 table, **P0-8 Select and pin base model(s)** (`status` of the plan note is not re-checked here).
- `second-brain/ml-unlearning/requirements/FV-SPEC — P0-8.md` — **§2 Interface**, **§3 Requirements** (FV-SPEC-089–095), **§5 Blocking decisions**, **§6 Verification matrix**. Note is `status: draft` and `blocked_by: [D-46, D-47, D-48, D-49]`.

## Summary

| Category | Count |
|----------|-------|
| Specs Analyzed | 1 |
| Requirements Checked | 16 (9 FR + 7 SC) |
| ✓ Aligned | 4 (25%) |
| ⚠️ Drifted | 5 (31%) |
| ✗ Not Implemented | 7 (44%) |
| 🆕 Unspecced Code | 1 |

The validator, live `models.yaml`, fixtures, and CLI `--scope models` exist. The named pytest hooks in FV-SPEC-P0-8 §6 do not. `tasks.md` still marks T001–T031 unchecked even though most of the code is present. Freeze still lists seven artifacts, so `models.yaml` is not part of `spec-v1` yet.

## Detailed Findings

### Spec: 20260926-101858-base-model-pinning — Base Model Selection and Pinning

#### Aligned ✓

- FR-002: Only 40-character hex revisions are accepted. `check_fv_spec_090_immutable_revision` uses `^[0-9a-f]{40}$` and rejects `main` and short hashes. → `tools/models_validator.py:191`
- FR-003: Offline SHA-256 digest check against a local directory, with pending when `--model-dir` or `files: {}` is absent. Extra top-level files, missing files, and mismatches are named. → `tools/models_validator.py:237`
- FR-006: Exclusion-gate JSON is compared to the computed identity hash; missing report, ledger, and cache manifests are `pending`, not `fail`. → `tools/models_validator.py:415`
- FR-008: `reports/p0-8-validation.json` is a structured per-check report with `pass` / `fail` / `pending` and diagnostics, matching the data-model shape. → `tools/models_validator.py:555`; live report `reports/p0-8-validation.json`

Acceptance scenarios that match this code (untested): US1.1–US1.3, US2.1, US3.1–US3.3, US4.2.

#### Drifted ⚠️

- FR-001: Spec says every non-pending role has a complete identity, and a staged Block 3 entry is `pending` until its deadline; a passed deadline without resolution fails. Code skips pending roles (overall 089 is `pass`), never compares `deadline` to today, and does not restrict `variant` to `base` | `instruct`. Non-strict `DECISION_REQUIRED` is silent `pass`, not `pending` and not a warning. CLI contract says non-strict mode warns on placeholders.
  - Location: `tools/models_validator.py:142`
  - Severity: moderate
  - Live evidence: `reports/p0-8-validation.json` records FV-SPEC-089 as `pass` while `blocks_0_2` is still `DECISION_REQUIRED`. Data-model state table says pre-D46 non-strict is `pending`.

- FR-004: Spec and FV-SPEC-092 require every enabled observation and intervention channel (including logits) to be supported; API-only or no-finetune licences must fail under a profile that needs logits or parameter updates. Code only inspects `fine_tune` / `export_checkpoint` vs `licence` containing `api_only`. It does not check observation/logit channels, `variant`, open-weight/auth markers, or `DECISION_REQUIRED` licences. `check_fv_spec_092_access_profile` has no `strict` argument.
  - Location: `tools/models_validator.py:302`
  - Severity: major
  - Acceptance: US5.2 is only partially covered.

- FR-005: Spec requires one canonical payload (`repo_id`, `model_revision`, `tokenizer_revision`, `dtype`, `adapter_digest`) hashed as `sha256:` + hex via `json.dumps(..., sort_keys=True, ensure_ascii=False)`. The validator implements that. P2-0 `src/models/identity.py` uses a different payload (`role`, `base_repo`, `base_revision`, `attn_impl`, compact JSON, no `sha256:` prefix). The system therefore does not have a single identity hash. Wiki FV-SPEC-093 says the hash is implemented by `src/models/` (P2-0).
  - Location: `tools/models_validator.py:86` vs `src/models/identity.py:10`
  - Severity: major

- FR-007: Spec and US4.1 require a recorded amendment, a new spec version tag, and a re-run exclusion gate. Code accepts a freeze mismatch if any `preregistration.md` line contains both `models.yaml` and `amendment`. It does not check a new tag or an exclusion-gate re-run. `freeze.py` still omits `models.yaml` from `SPEC_ARTIFACTS`, so the amendment check cannot become a real freeze gate.
  - Location: `tools/models_validator.py:477`; `tools/freeze.py:32`
  - Severity: major
  - Acceptance: US4.1 drifted.

- FR-009: Validation is CPU-only and issues no network calls. Wall-clock runtime is not recorded in the JSON report. Wiki constraint C-2 also requires runtime to be recorded.
  - Location: `tools/models_validator.py:555`
  - Severity: minor

Other implementation notes (not separate FRs):

- Extra-file detection walks only `model_dir.iterdir()`, not nested paths (`tools/models_validator.py:284`). US2.2 is weaker than the spec text.
- `SHA256_FILE_RE` is defined and never used, so `files` values are not format-checked until a byte comparison runs.
- CLI `--scope` help still lists the older scopes and does not mention `models`; `--access-profile` help still describes the attacks scope (`tools/validate_spec.py:389`).
- `tasks.md` T001–T031 remain `[ ]` while the validator, fixtures, and live artifact exist.

#### Not Implemented ✗

- SC-001: Named hooks `tests/test_models_spec.py::test_fv_spec_089_identity` … `test_fv_spec_095_amendment` do not exist. Wiki §6 verification matrix is still all ☐. T015–T017, T019, T021, T023, T025, T030 are unimplemented.
- SC-002: No amendment-check fixture suite, so “zero false-passes on a silent swap” is not measured.
- SC-003: No digest-check tests against the synthetic `model_dir` fixture.
- SC-004: No two-run / single-field hash matrix in this spec’s tests. The loader hash (see FR-005) would fail that matrix if it were run.
- SC-005: No tests that classify downstream artefacts as `pass` / `fail` / `pending`.
- SC-006: No recorded runtime and no sub-60s assertion on the synthetic suite.
- SC-007: D-46, D-47, D-48, D-49 are not in `.factverify/decisions/register.yaml`. Live `models.yaml` is still `DECISION_REQUIRED` / `pending`. Wiki §5 says add these IDs to the register when reviewed. This is the expected blocked state, not a coding miss — but the success criterion is unmet.

Also missing relative to the plan (supporting SC-001 / spec assumptions):

- T027: `tools/freeze.py` `SPEC_ARTIFACTS` still has 7 names; `_check_artifacts_present` still says “seven spec artifacts”.
- T028: V01 / FV-SPEC-087 required-file list does not include `models.yaml`.

### Unspecced Code 🆕

| Feature | Location | Lines | Suggested Spec |
|---------|----------|-------|----------------|
| models.yaml source-convention note | `docs/models-yaml-model-source.md` | 70 | `20260926-101858-base-model-pinning` (or a handbook note) |

`src/models/`, `scripts/prefetch_models.py`, and `tests/test_models_loader.py` belong to `20260926-105952-model-loader`, not this spec. They are listed under conflicts, not as unspecced.

## Inter-Spec Conflicts

1. **`models.yaml` schema.** This spec uses a top-level `roles` map with `model_revision`, `variant`, `licence`. P2-0 (`src/models/spec.py`) reads a flat map keyed by role with `revision`, `attn_impl`, and no `roles` wrapper. Live `.factverify/spec/models.yaml` follows P0-8. The loader fixture `tests/fixtures/models_loader/models.yaml` follows P2-0. `load_model` cannot parse the live spec artifact.
2. **Identity hash (FR-005 / FV-SPEC-093 / P2-0 FR-004).** Two incompatible canonical forms. P2-0 research.md Decision 1 acknowledges it may need to match P0-8 later; the code has already shipped the other form. Wiki P0-8 §3 FV-SPEC-093 says P2-0 implements the P0-8 definition.
3. **File digest strings.** P0-8 fixtures use `sha256:<64-hex>`. P2-0 fixtures use bare hex. A directory valid for one checker fails the other.
4. **D-48 coverage.** Wiki P0-8 §5 defines D-48 as dtype *and* attention implementation. This spec’s `models.yaml` has `dtype` only. P2-0 requires `attn_impl`.
5. **Eighth artifact.** This spec’s assumption and T027/T028 require `models.yaml` in freeze + V01. P0-7 freeze still enumerates seven files. Wiki P0-8 §2 flags this as a review item that must be resolved before implementation.
6. **Quickstart vs live report.** `quickstart.md` Step 1 expects all checks `pending` pre-decision. Live non-strict run records 089, 090, and 092 as `pass`.

## Recommendations

1. Write `tests/test_models_spec.py` with the seven wiki hooks (FV-SPEC-089–095) against `tests/fixtures/models_spec/`. Until those are green, SC-001–SC-006 stay unmet and no requirement should move to `implemented`.
2. Make P2-0 `src/models/identity.py` and `src/models/spec.py` consume the P0-8 schema and hash payload. Do not keep two `models.yaml` shapes. Surface whether `attn_impl` belongs in P0-8 `models.yaml` (D-48) rather than guessing.
3. Add `models.yaml` to `SPEC_ARTIFACTS` and to the V01/FV-SPEC-087 required-file list so freeze cannot complete without the eighth artifact.
4. Tighten FR-004 to observation channels (logits) as well as `fine_tune` / `export_checkpoint`, and FR-007 to require a new spec tag plus exclusion-gate re-run — or record an explicit waiver if P0-8 will only do the string-match amendment check.
5. Record wall-clock in `p0-8-validation.json`. Treat unresolved `DECISION_REQUIRED` as `pending` in non-strict mode, and fail a pending role whose `deadline` has passed.
6. Add D-46–D-49 to `.factverify/decisions/register.yaml` as `open` / `pending` (wiki §5). Leave SC-007 unchecked until those close.
7. Tick `tasks.md` to match the code that already exists, or treat the unchecked boxes as the remaining work (tests + freeze/V01).
