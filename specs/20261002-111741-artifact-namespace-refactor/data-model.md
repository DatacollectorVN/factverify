# Data Model: FV-SPEC — Artifact Namespace Refactor

**Feature**: `20261002-111741-artifact-namespace-refactor`
**Date**: 2026-10-02

---

## Entities

### LayoutRoots

The single authority for resolving the two namespace roots. Created once at process startup from environment variables and/or CLI flags.

| Field | Type | Constraint |
|---|---|---|
| `spec_root` | `Path` (absolute) | Resolved from `FACTVERIFY_SPEC_ROOT` env var or `--spec-root` flag; default `.factverify/` |
| `internal_root` | `Path` (absolute) | Resolved from `FACTVERIFY_INTERNAL_ROOT` env var or `--internal-root` flag; default `.factverify_internal/` |

**Validation rules**:
- Both paths must be distinct absolute paths.
- Neither may be a prefix of the other (no nesting).
- After initialization, code must not re-infer roots from `cwd`.

**Defined in**: `src/artifacts/layout.py::LayoutRoots`

---

### ArtifactClass

An enumeration of all recognized artifact classes, used by the namespace validator and store to route writes and check placements.

**Frozen-input classes** (permitted only under `spec_root`):

| Value | Location | Description |
|---|---|---|
| `protocol` | `<spec_root>/protocol.yaml` | Consolidated normative spec document |
| `templates` | `<spec_root>/templates.yaml` | Closure template suite |
| `model_policy` | `<spec_root>/model_policy.yaml` | Frozen model-role policy |
| `fact_schema` | `<spec_root>/fact.schema.json` | JSON Schema for fact contracts |
| `freeze_receipt` | `<spec_root>/FREEZE.json` | Freeze receipt with content digests |
| `fact_contract` | `<spec_root>/facts/<fact_id>/contract.json` | Per-fact contract |
| `fact_sources` | `<spec_root>/facts/<fact_id>/sources.jsonl` | Per-fact provenance |
| `fact_neighbourhood` | `<spec_root>/facts/<fact_id>/neighbourhood.jsonl` | Per-fact retain neighbourhood |
| `fact_prompts` | `<spec_root>/facts/<fact_id>/prompts.jsonl` | Per-fact executable queries |
| `fact_manifest` | `<spec_root>/facts/<fact_id>/manifest.json` | Per-fact bundle manifest |

**Runtime classes** (permitted only under `internal_root`):

| Value | Subdirectory | Description |
|---|---|---|
| `ledger` | `ledger.sqlite` | Transaction authority |
| `run_manifest` | `runs/<run_id>/manifest.json` | Run identity and provenance binding |
| `run_config` | `runs/<run_id>/config.yaml` | Frozen run config snapshot |
| `run_events` | `runs/<run_id>/events.jsonl` | Append-only event stream |
| `run_metrics` | `runs/<run_id>/metrics.jsonl` | Metric stream |
| `run_verdict` | `runs/<run_id>/verdict.json` | Final verdict |
| `run_artifact_manifest` | `runs/<run_id>/artifacts.json` | Artifact manifest (digest list) |
| `checkpoint` | `checkpoints/` | Model weight checkpoint |
| `generation` | `evidence/<run_id>/` | Model generation output |
| `score` | `evidence/<run_id>/` | Metric score record |
| `witness` | `evidence/<run_id>/` | Confirmed failure witness |
| `result` | `results/` | Derived result (regenerable) |
| `report` | `reports/` | Derived report (regenerable) |
| `deviation` | `deviations/` | Post-freeze deviation record |
| `cache_shard` | `cache/` | Generation cache shard |
| `external_blob` | _(declared, stored elsewhere)_ | Large artifact with content-addressed reference |
| `temporary` | `tmp/` | Disposable intermediate file |

**Defined in**: `src/artifacts/layout.py::ArtifactClass`

---

### FreezeReceipt (FREEZE.json)

Stored at `<spec_root>/FREEZE.json`. Replaces `CHECKSUMS.sha256` and `reports/spec-v1-freeze-receipt.json`.

| Field | Type | Description |
|---|---|---|
| `schema_version` | `str` | `"1"` |
| `spec_version` | `str` | e.g. `"spec-v1"` |
| `commit` | `str` | 40-char hex git commit hash |
| `timestamp_utc` | `str` | ISO 8601 datetime |
| `decisions` | `dict[str, str]` | `{semantic_key: resolved_value}` for all blocking decisions |
| `approvals` | `list[ApprovalEntry]` | Cross-references to approval artifacts |
| `content_digests` | `dict[str, str]` | `{relative_path: "sha256:hex"}` for the other 4 normative artifacts |

**Defined in**: `src/artifacts/layout.py::FreezeReceipt` + `tools/freeze.py`

---

### FactCaseBundle

A five-file directory at `<spec_root>/facts/<fact_id>/`. Immutable after fact freeze.

| File | Format | Content |
|---|---|---|
| `contract.json` | JSON | Full fact contract (FV-SPEC-108 IDs) |
| `sources.jsonl` | JSONL | Provenance records for the fact |
| `neighbourhood.jsonl` | JSONL | Retain neighbourhood probes |
| `prompts.jsonl` | JSONL | Executable query suite |
| `manifest.json` | JSON | Bundle manifest (see `FactCaseManifest`) |

**Defined in**: `src/data/fact_bundle.py` (new)

---

### FactCaseManifest

Stored as `manifest.json` inside a fact case bundle.

| Field | Type | Constraint |
|---|---|---|
| `fact_id` | `str` | `factverify:fact:<local-id>` |
| `split` | `str` | `"calibration"` or `"test"` |
| `protocol_revision` | `str` | e.g. `"spec-v1"` |
| `digests` | `dict[str, str]` | `{filename: "sha256:hex"}` for the other 4 bundle files |

**Validation**: All 4 sibling files must be present with matching digests before a run opens. No model selection in the manifest.

**Defined in**: `src/data/fact_bundle.py`

---

### RunBundle

A directory at `<internal_root>/runs/<run_id>/`. The run manifest is written at run open; all other files are appended during execution.

**run manifest fields** (all required):

| Field | Type |
|---|---|
| `run_id` | `str` (UUID) |
| `fact_id` | `str` (`factverify:fact:…`) |
| `role` | `str` (study role) |
| `method` | `str` (unlearning method) |
| `seed` | `int` |
| `split` | `str` |
| `protocol_revision` | `str` |
| `code_commit` | `str` (40-char hex) |
| `model_config_id` | `str` |
| `model_config_digest` | `str` (`sha256:hex`) |
| `model_identity_hash` | `str` |
| `config_hash` | `str` (`sha256:hex`) |
| `opened_at` | `str` (ISO 8601) |
| `status` | `str` (`open` \| `finalized` \| `failed`) |

**Defined in**: `src/artifacts/run_bundle.py`

---

### ExternalBlobRef

A content-addressed pointer registered in both the ledger and the run artifact manifest for artifacts stored outside `.factverify_internal/`.

| Field | Type | Constraint |
|---|---|---|
| `uri` | `str` | Non-empty URI (local path or remote) |
| `byte_size` | `int` | > 0 |
| `content_digest` | `str` | `sha256:` + 64 hex chars |
| `producer_run_id` | `str` | UUID of the run that produced the blob |

**Validation**: All four fields required for registration; any missing field blocks registration and reproduction.

**Defined in**: `src/artifacts/refs.py::ExternalBlobRef`

---

### FactVerifyNativeId

A validated project-internal identifier.

**Canonical forms**:

| Form | Pattern | Example |
|---|---|---|
| Fact | `factverify:fact:[a-z0-9][a-z0-9_-]*` | `factverify:fact:hanoi_capital_of_vietnam` |
| Contract version | `factverify:contract:[a-z0-9][a-z0-9_-]*:v[1-9][0-9]*` | `factverify:contract:hanoi_capital_of_vietnam:v1` |
| Entity | `factverify:entity:[a-z0-9][a-z0-9_-]*` | `factverify:entity:hanoi` |
| Relation | `factverify:relation:[a-z0-9][a-z0-9_-]*` | `factverify:relation:capital-of` |

**Rules**:
- `<local-id>` is stable after freeze; label or external mapping changes do not change it.
- Contract `<local-id>` must equal the fact `<local-id>`.
- Not derived from Q/P numbers or display labels.

---

### Updated EntityRef (in `fact.schema.json`)

Replaces the current `entityRef` definition. The `source` required field is removed; `external_refs[]` is optional.

| Field | Required | Description |
|---|---|---|
| `id` | Yes | `factverify:entity:<local-id>` only |
| `label` | Yes | Human-readable label (non-empty) |
| `external_refs` | No | Array of `ExternalRef` entries |

**Defined in**: `.factverify/fact.schema.json` `$defs.entityRef`

---

### Updated RelationRef (in `fact.schema.json`)

Same change as `entityRef` but for relations.

| Field | Required | Description |
|---|---|---|
| `id` | Yes | `factverify:relation:<local-id>` only |
| `label` | Yes | Human-readable label (non-empty) |
| `external_refs` | No | Array of `ExternalRef` entries |

**Defined in**: `.factverify/fact.schema.json` `$defs.relationRef`

---

### ExternalRef (in `fact.schema.json`)

An optional entry in `external_refs[]` on an entity or relation.

| Field | Required | Type | Description |
|---|---|---|---|
| `scheme` | Yes | `str` | Authority name (e.g. `"wikidata"`, `"geonames"`) |
| `external_id` | Yes | `str` | ID within that authority (e.g. `"Q1858"`, `"P1376"`) |
| `url` | No | `str` (URI) | Canonical URL for the record |
| `retrieved_at` | No | `str` (date) | ISO 8601 date of retrieval |
| `verified_by` | No | `str` | Reviewer name or tool |

**Validation**:
- No two entities may share the same `(scheme, external_id)` pair.
- Malformed entries fail strict validation without rewriting any local ID.

**Defined in**: `.factverify/fact.schema.json` `$defs.externalRef`

---

### MigrationReport

Output of `tools/migrate_artifacts.py`. Written as JSON.

| Field | Type | Description |
|---|---|---|
| `timestamp_utc` | `str` | ISO 8601 |
| `mode` | `str` | `"dry_run"` or `"execute"` |
| `source_root` | `str` | Absolute path to old `.factverify/` |
| `target_spec_root` | `str` | Absolute path to new `.factverify/` |
| `target_internal_root` | `str` | Absolute path to `.factverify_internal/` |
| `entries` | `list[MigrationEntry]` | One entry per source artifact |
| `collisions` | `list[str]` | Old paths with conflicting new paths |
| `unresolved` | `list[str]` | Source paths with no determined action |
| `overall` | `str` | `"pass"` if zero unresolved, zero collisions; else `"fail"` |

**MigrationEntry fields**:

| Field | Type |
|---|---|
| `source_path` | `str` |
| `target_path` | `str` or `null` |
| `action` | `str`: `"rename"`, `"move"`, `"consolidate"`, `"delete"`, `"archive"` |
| `old_id` | `str` or `null` |
| `new_id` | `str` or `null` |
| `external_refs_added` | `list[dict]` |
| `notes` | `str` |

---

## Entity relationships

```
LayoutRoots
├── spec_root/
│   ├── protocol.yaml                   (ArtifactClass.protocol)
│   ├── templates.yaml                  (ArtifactClass.templates)
│   ├── model_policy.yaml               (ArtifactClass.model_policy)
│   ├── fact.schema.json                (ArtifactClass.fact_schema)
│   ├── FREEZE.json ──────────────────► FreezeReceipt
│   │   └── .content_digests ─────────► SHA-256 of other 4 normative artifacts
│   └── facts/
│       └── <fact_id>/                  FactCaseBundle
│           ├── contract.json           (triple uses FactVerifyNativeId,
│           │                            external mappings in ExternalRef)
│           ├── sources.jsonl
│           ├── neighbourhood.jsonl
│           ├── prompts.jsonl
│           └── manifest.json ────────► FactCaseManifest
│               └── .digests ─────────► SHA-256 of other 4 bundle files
└── internal_root/
    ├── ledger.sqlite                   (transaction authority)
    └── runs/
        └── <run_id>/                   RunBundle
            ├── manifest.json ────────► references fact_id, model_config_id,
            │                            protocol_revision, code_commit
            ├── config.yaml            (frozen copy of config/models/*.yaml)
            ├── events.jsonl
            ├── metrics.jsonl
            ├── verdict.json
            └── artifacts.json ───────► contains ExternalBlobRef entries
                                        for large artifacts stored elsewhere

config/models/<model-config-id>.yaml   (source input; snapshotted per run)
```

---

## State transitions

### Fact lifecycle

```
declared → bundle_complete → fact_frozen → run_open (read-only thereafter)
```

A run may not open until `fact_frozen`. The bundle manifest's digests are compared at run open (FV-SPEC-099, 104).

### Run lifecycle

```
preflight_pass → open → in_progress → finalized  (or → failed)
```

- `open`: run directory created, manifest written, ledger row committed.
- `finalized`: all files present and matching artifact manifest digests.
- `failed`: no partial state retained; directory is cleaned up.

### Artifact registration lifecycle

```
written_to_disk → ledger_registered → eligible_for_analysis
```

A file on disk without a ledger row is never eligible for analysis (FV-SPEC-101).

---

## Schema changes summary

### `fact.schema.json` (renamed from `fact_contract.schema.json`)

| Location | Old | New |
|---|---|---|
| `$id` | `fact_contract.schema.json` | `fact.schema.json` |
| `contract_id.pattern` | allows `wd-Q…-P…-Q…` | `factverify:contract:<local-id>:v<N>` only |
| `fact_id.pattern` | allows `wd-Q…-P…-Q…` | `factverify:fact:<local-id>` only |
| `$defs.entityRef.required` | `["id", "label", "source"]` | `["id", "label"]` |
| `$defs.entityRef.properties.id.pattern` | allows `wikidata:Q…` | `factverify:entity:…` only |
| `$defs.entityRef.properties.source` | required enum | removed |
| `$defs.entityRef.properties.external_refs` | absent | optional `array` of `externalRef` |
| `$defs.relationRef` | same changes as entityRef | same changes |
| `$defs.entityResolutionSpec` | present (wikidata-centric) | removed (replaced by `external_refs`) |
| `$defs.externalRef` | absent | new `$def` |
