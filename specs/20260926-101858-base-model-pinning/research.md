# Research: Base Model Selection and Pinning

## Decision: Validator module pattern
- **Chosen**: Follow `tools/access_profile_validator.py` — a standalone `tools/models_validator.py` with a `validate_models_spec()` entry point returning `(bool, dict)`, dispatched via a new `_run_models_validation()` function in `tools/validate_spec.py`.
- **Rationale**: Every prior scope (access-profile, margins, witness-rule, preregistration) uses this pattern; consistency keeps the CLI dispatcher uniform and tests predictable.
- **Alternatives considered**: Embedding all checks directly in `validate_spec.py`. Rejected — the access-profile validator alone is 1600 lines; a dedicated module keeps validate_spec.py as a pure dispatcher.

## Decision: models.yaml structure
- **Chosen**: YAML file under `.factverify/spec/models.yaml`. Top-level key `roles` maps role names (e.g. `blocks_0_2`, `block_3_confirmation`) to their identity entries. Each entry has `repo_id`, `model_revision`, `tokenizer_revision`, `variant`, `dtype`, `licence`, `files` (dict of filename → `sha256:<hex>`), and optionally `status: pending` for staged commitments.
- **Rationale**: Mirrors the `roles` pattern in `access_profile.md` (YAML frontmatter). YAML is the existing format for all spec artifacts except `fact_contract.schema.json`. A flat per-role structure keeps cross-file comparison simple.
- **Alternatives considered**: JSON. Rejected — all spec artifacts that are human-edited use YAML or Markdown+YAML. Using JSON would break consistency with `margins.yaml`, `attacks.yaml`, `closure_templates.yaml`.

## Decision: Canonical model-identity hash payload (FV-SPEC-093)
- **Chosen**: `json.dumps({"repo_id": ..., "model_revision": ..., "tokenizer_revision": ..., "dtype": ..., "adapter_digest": ...}, sort_keys=True, ensure_ascii=False)` → `sha256:<hex>`. `adapter_digest` is `null` when no adapter is attached.
- **Rationale**: Deterministic: `json.dumps(..., sort_keys=True)` produces identical bytes across Python versions for the same values. Minimal: only the fields that identify the exact weights are included; display names, licence, and file paths are not part of the identity hash (they may change without the weights changing).
- **Alternatives considered**: Hashing the YAML entry directly. Rejected — YAML formatting and comment whitespace is not stable; canonical JSON is.

## Decision: Immutable-revision check (FV-SPEC-090)
- **Chosen**: Accept only strings matching `/^[0-9a-f]{40}$/`. Reject branches (`main`, `master`), tags (not hex), short hashes (< 40 chars), or absent/null values.
- **Rationale**: Hugging Face Hub uses 40-character SHA-1 commit hashes as the immutable revision identifier. This is the narrowest constraint that rules out all mutable identifiers.
- **Alternatives considered**: Allowing 64-char SHA-256 (Git 2.x objects). Not needed for Hugging Face Hub in the current study period; can be extended via amendment if needed.

## Decision: File-digest check (FV-SPEC-091)
- **Chosen**: The `files` dict in each role entry maps relative filenames to `sha256:<hex>` strings. The offline check recomputes SHA-256 for each recorded file and compares. Files present on disk but absent from the manifest, and files in the manifest missing from disk, both fail.
- **Rationale**: Same scheme as `CHECKSUMS.sha256` in `tools/freeze.py` — the project already has a working reference implementation.
- **Alternatives considered**: Recording file sizes alongside hashes. Not needed for the study; hashes alone are sufficient and simpler.

## Decision: Access-profile cross-check (FV-SPEC-092)
- **Chosen**: Load `access_profile.md` and extract declared `interventions`. For each intervention requiring `fine_tune` or `export_checkpoint`, check that the model's `licence` field does not contain `api_only` and is not `DECISION_REQUIRED`. Also check that all models are open-weight (repo_id resolvable without authentication markers). In strict mode, resolve the declared profile letter against the model variant.
- **Rationale**: The access profile is a YAML-frontmatter file we already load in `access_profile_validator.py`. The models validator reads it separately (no circular import) to extract the intervention channel requirements.
- **Note**: At P0-8 time, the study is declared Profile A (all capabilities `unavailable`); the cross-check will mostly pass by construction. The check exists to catch future profile upgrades that are incompatible with the pinned model.

## Decision: Downstream-binding check (FV-SPEC-094)
- **Chosen**: Check three downstream locations, each treated as `pending` if absent:
  1. `reports/exclusion_gate.md` or `reports/exclusion_gate.json` (P1-2 output)
  2. `ledger.sqlite` rows with `role` column referencing the same model (P2-5 output)
  3. Cache manifests under `src/cache/` (P2-7 output)
  When a file exists, read its declared model-identity hash and compare against the hash computed from `models.yaml`. A mismatched hash fails; an absent file is `pending`.
- **Rationale**: The requirements note is explicit that absent-but-expected artefacts are `pending`, not fail. This design is consistent with how `freeze.py` handles gate 1 (artifact present check).

## Decision: Amendment check (FV-SPEC-095)
- **Chosen**: The validator computes a SHA-256 digest of the current `models.yaml` content. If `CHECKSUMS.sha256` exists (i.e. the spec has been frozen), it checks whether the stored digest matches the current content. If they differ, it looks for an amendment record in `preregistration.md` referencing `models.yaml`. If no amendment is found, it fails.
- **Rationale**: Reuses the existing `CHECKSUMS.sha256` mechanism from `tools/freeze.py`. No new tracking file is needed.

## Decision: Eighth-artifact reconciliation (freeze.py + V01)
- **Chosen**: Add `models.yaml` to `SPEC_ARTIFACTS` in `tools/freeze.py`. This makes the artifact count 8. The comment in `_check_artifacts_present()` refers to "seven" — update it to "eight". The `SUPPORTED_SCOPES` set in `validate_spec.py` gains `"models"`.
- **Rationale**: Required by the spec: `models.yaml` is a normative spec artifact and must be covered by the freeze checksum.
- **Note**: FV-SPEC-087 (readiness report) and any validator check that asserts "seven artifacts" must also be updated. The P0-7 preregistration validator's V01 check (required-file list) must include `models.yaml`. This is flagged in the spec as a local review item; it is part of this implementation's scope.

## Decision: CLI invocation
- **Chosen**: `python tools/validate_spec.py --scope models --spec-root .factverify/spec [--strict] [--report reports/p0-8-validation.json] [--model-dir <path>] [--access-profile <path>] [--downstream-report <path>]`
- **model-dir**: path to a local model directory to run the digest check against (optional; digest check is `pending` if absent)
- **access-profile**: defaults to `<spec-root>/access_profile.md`
- **downstream-report**: path to an exclusion-gate report to cross-check (optional; treated as `pending` if absent)
- **Rationale**: Consistent with all other scopes. Optional arguments have sensible defaults so the simplest invocation (just `--scope models --spec-root`) still runs the structural checks.

## No NEEDS CLARIFICATION remaining
All design questions resolved above. The four open study decisions (D-46, D-47, D-48, D-49) are design decisions that the researcher must resolve; they do not affect the validator's structural design.
