# Research: FV-SPEC — Artifact Namespace Refactor

**Feature**: `20261002-111741-artifact-namespace-refactor`
**Date**: 2026-10-02

---

## Finding 1: `spec-v1` is not yet tagged

**Decision**: Proceed without an amendment procedure.
**Rationale**: `git tag -l` returns no output — `spec-v1`, `thresholds-v1`, and `protocol-v1` do not exist. The spec namespace is pre-freeze. Layout changes (directory restructure, file renames, schema updates) do not require a new tag or a preregistration amendment. Constitution Principle 1 is satisfied.
**Alternatives considered**: Waiting until after freeze and doing the refactor as an amendment. Rejected — the whole point is to get the layout right *before* the spec freeze.

---

## Finding 2: Model-config split is already partially implemented

**Decision**: Treat `src/models/spec.py` as the foundation for FV-SPEC-110; do not rewrite it.
**Rationale**: `src/models/spec.py` already implements `load_model_policy`, `load_model_configuration`, `resolve_role`, and `config_digest`. The ledger schema (`src/ledger/schema.py`) already has `model_config_id`, `model_config_digest`, `model_identity_hash`, and `identity_schema_version` columns in both `checkpoints` and `evaluation_runs` tables. `config/models/block0-debug-pythia-410m.yaml` exists and is the correct format. The key remaining work for FV-SPEC-110 is wiring preflight to call these functions and snapshot the config bytes into the run bundle.
**Alternatives considered**: Rewriting the model loader from scratch. Unnecessary — the existing code is correct and tested.

---

## Finding 3: `fact_contract.schema.json` has dual-authority ID patterns — must be tightened

**Decision**: Update `fact.schema.json` (renamed) to allow only `factverify:` prefixed IDs in canonical fields; remove the `source` required field from `entityRef` and `relationRef`; add optional `external_refs[]`.
**Rationale**: The current schema permits `wikidata:Q…` and `wikidata:P…` in canonical ID fields:
```json
"pattern": "^(?:wikidata:Q[1-9][0-9]*|factverify:entity:[a-z0-9][a-z0-9_-]*)$"
```
It also requires `source: "wikidata" | "factverify_internal"` on every entity and relation. FV-SPEC-108/109 require removing Wikidata as a canonical identity authority and making external mappings optional. The revised pattern for `entityRef.id` must be `^factverify:entity:[a-z0-9][a-z0-9_-]*$` only.
**Alternatives considered**: Making Wikidata IDs a first-class alternate identifier (not just external_ref). Rejected by D-72 — FactVerify must own canonical identity.

---

## Finding 4: Two existing contracts demonstrate the migration strategy

**Decision**: Apply the identity migration transform as follows and confirm with a dry-run report.
**Rationale**:
- `factverify-contract-wd-Q1858-P1376-Q881-v1.json` uses Wikidata IDs as entity/relation canonical IDs and has `source: "wikidata"`. After migration: `fact_id` → `factverify:fact:hanoi_capital_of_vietnam`, entity/relation IDs → `factverify:entity:hanoi` etc., Wikidata Q/P numbers → `external_refs: [{scheme: "wikidata", external_id: "Q1858"}]`, `source` field dropped.
- `factverify-contract-invented_scientist_alma_mater-v1.json` already uses native IDs but still has `source: "factverify_internal"` on entities. After migration: `source` field dropped; no `external_refs` needed.
**Alternatives considered**: Keeping Q/P numbers in a special `wikidata_id` top-level field rather than `external_refs[]`. Rejected — `external_refs[]` is more general and works for any external authority.

---

## Finding 5: `tools/freeze.py` scans `.factverify/spec/` with 8 artifacts — must update to 5 artifacts under `.factverify/`

**Decision**: Refactor `freeze.py` to target the new layout. `SPEC_ARTIFACTS` changes from 8 files under `.factverify/spec/` to the 4 normative files directly under `.factverify/` that precede `FREEZE.json` itself.
**Rationale**: The current `SPEC_ARTIFACTS = ["fact_contract.schema.json", "closure_templates.yaml", "attacks.yaml", "access_profile.md", "margins.yaml", "witness_rule.md", "preregistration.md", "model_policy.yaml"]` will break when those files move and are renamed. The new contract is that `FREEZE.json` is *produced by* the freeze command and records the digests of the other four normative files (`protocol.yaml`, `templates.yaml`, `model_policy.yaml`, `fact.schema.json`). Replacing `CHECKSUMS.sha256` + `reports/spec-v1-freeze-receipt.json` with a single `FREEZE.json` at the root of `.factverify/` simplifies the freeze receipt and layout.
**Alternatives considered**: Keeping CHECKSUMS.sha256 as the digest record. Rejected — FREEZE.json is a richer structured artifact (also records revision, commit, timestamps, decisions, approvals) as specified in FV-SPEC-098.

---

## Finding 6: `protocol.yaml` consolidation is a design decision requiring Nathan's approval

**Decision (deferred)**: `protocol.yaml` consolidates the non-schema, non-template, non-policy normative content. Proposed mapping below — confirm before implementing.
**Rationale**: The five-file target layout does not specify exact content for `protocol.yaml`. The current spec directory has 8 files. The following mapping needs Nathan's confirmation:

| Current file | Target |
|---|---|
| `spec/fact_contract.schema.json` | `.factverify/fact.schema.json` (rename + schema update) |
| `spec/closure_templates.yaml` | `.factverify/templates.yaml` (rename) |
| `spec/model_policy.yaml` | `.factverify/model_policy.yaml` (move up one level) |
| `spec/attacks.yaml` | Content absorbed into `.factverify/protocol.yaml` |
| `spec/margins.yaml` | Content absorbed into `.factverify/protocol.yaml` |
| `spec/access_profile.md` | Content absorbed into `.factverify/protocol.yaml` |
| `spec/witness_rule.md` | Content absorbed into `.factverify/protocol.yaml` |
| `spec/preregistration.md` | Registration metadata → `FREEZE.json`; scientific rationale → `protocol.yaml` body |

`protocol.yaml` would be a structured YAML document with sections for each of attacks, margins, access_profile, and witness_rule. Its schema must be defined before implementation.
**Alternatives considered**: Keeping `attacks.yaml`, `margins.yaml`, etc. as separate top-level files. This would increase the count above 5 and violate FV-SPEC-098. The consolidation must happen.
**Action required**: Nathan must approve the `protocol.yaml` consolidation structure before the migration tool is written.

---

## Finding 7: Multiple source modules hardcode `.factverify/spec/` paths — full inventory required for FV-SPEC-111

**Decision**: Build the legacy-artifact inventory as the first implementation task.
**Rationale**: The following files reference the current spec path directly and must be updated atomically:
- `src/data/spec_readers.py`
- `src/eval/spec_load.py`, `src/eval/store.py`, `src/eval/run.py`
- `src/controls/spec_load.py`, `src/controls/run.py`
- `src/models/spec.py` (calls `spec_root / "models.yaml"` in `load_model_spec` — legacy function)
- `src/models/loader.py`
- `src/stats/io.py`, `src/stats/thresholds.py`, `src/stats/bootstrap.py`, `src/stats/report.py`
- `src/cache/store.py`
- `src/train/run.py`
- `tools/freeze.py`, `tools/witness_rule_validator.py`
- `tests/test_contract_schema.py`, `tests/test_model_config.py`, `tests/test_models_spec.py`
Additionally, `src/models/spec.py` still has the legacy `load_model_spec` function (reads `models.yaml`) — this must be deleted as part of FV-SPEC-111.
**Alternatives considered**: Leaving legacy functions in place with deprecation warnings. Rejected per FV-SPEC-111 (zero unallowlisted legacy interfaces after cutover).

---

## Finding 8: D-71 and D-72 must be added to `config/decisions/catalog.yaml` (Constitution Principle 14)

**Decision**: Add both decisions with semantic keys as part of this implementation.
**Rationale**: The blocking decisions for this ticket (D-71: artifact namespace boundary, D-72: identity authority) are resolved but not yet in the decision catalog. Per Constitution Principle 14, new code must use semantic keys. Proposed keys:
- D-71: `artifacts.namespace.boundary`
- D-72: `artifacts.identity.authority`
**Alternatives considered**: Using the bare `D-71` / `D-72` identifiers in new code. Rejected — Principle 14 requires semantic keys as the primary identifier in new code, diagnostics, and output records.

---

## Finding 9: The ledger currently lives at a path resolved by callers — must be re-anchored to `.factverify_internal/`

**Decision**: `src/ledger/api.py` must accept an explicit path (defaulting to `<internal_root>/ledger.sqlite`) rather than a hardcoded relative path. The layout resolver provides the default.
**Rationale**: `src/ledger/schema.py`'s `connect()` and `open_ledger()` take a `Path` argument — this is already correct. But call sites that construct the path must use the layout resolver rather than inferring from cwd. The `src/artifacts/layout.py` module will be the single authority for the internal root.

---

## Finding 10: `.factverify_internal/` structure — declare subdirectories explicitly

**Decision**: The layout resolver declares and creates the following subdirectories under `.factverify_internal/` on first access: `ledger.sqlite` (file), `runs/`, `cache/`, `checkpoints/`, `evidence/`, `results/`, `reports/`, `deviations/`, `tmp/`.
**Rationale**: FV-SPEC-100 specifies these subdirectories. They must be declared as the allowlist for the layout validator so that any path outside this set triggers a refusal.

---

## No external research required

All decisions are fully specified in the requirements document or resolvable from the codebase. No web search or external documentation needed. The only blocking open item is Finding 6 (protocol.yaml consolidation structure — requires Nathan's approval).
