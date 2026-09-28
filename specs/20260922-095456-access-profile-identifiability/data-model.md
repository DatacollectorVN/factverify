# Data Model: P0-4 Access Profile and the Identifiability Limit

**Feature**: `20260922-095456-access-profile-identifiability`
**Created**: 2026-09-22
**Source**: [spec.md](spec.md), [research.md](research.md)

---

## Entity: Access Profile

**Artifact**: `.factverify/spec/access_profile.md` (YAML frontmatter + Markdown body)
**Purpose**: Single authoritative contract declaring observation boundary, capabilities, roles, permitted sources, intervention rules, and handling policies for all evaluator systems.

### Frontmatter Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `version` | string (semver) | yes | Artifact revision, e.g. `"1.0.0"` |
| `profile` | enum `A\|B\|C` | yes | Summary profile letter (shorthand only — per-system capabilities are authoritative) |
| `measurement_point` | string | yes | Where the observation tap sits (e.g. `"serving_pipeline_output"`) |
| `score_scope` | mapping | conditional (B/C) | `type` (`pre_mask`/`post_mask`), `vocabulary` (`full`/`top_k`), `top_k_value` (int, if top_k) |
| `systems` | mapping | yes | Per-system capability declarations (see Capability Declaration) |
| `roles` | list of mapping | yes | Each entry: `role_id`, `role_type` (`evaluator`/`operator`/`auditor`), `permitted_actions` |
| `permitted_sources` | list of string | yes | Enumerated allowed input/artifact sources |
| `interventions` | list of mapping | no | Intervention permissions (see Intervention Permission) |
| `historical_access` | list of mapping | no | Each entry: `artifact_id`, `artifact_type`, `source`, `attribution` |
| `handling_policies` | mapping | yes | Keys: `non_identifiable`, `incomplete` — each maps to a reporting-rule reference |
| `budget_ref` | string (path) | yes | Relative path to P0-3 `attacks.yaml` |
| `claim_refs` | list of string | no | Relative paths to claim template files |
| `blocking_decisions` | list of mapping | yes | Each: `decision_id`, `status` (`open`/`resolved`), `resolution` (if resolved) |
| `provenance_refs` | list of string | yes | Relative paths to capability/provenance manifests |
| `identifiability_refs` | list of string | no | Relative paths to identifiability justification records |

### Markdown Body Sections

| Section | Required | Content |
|---------|----------|---------|
| Observation Boundary | yes | Prose description of what each evaluator can see at the serving boundary |
| Provenance Procedure | yes | Reviewed protocol: tap location, intervening processors, model/tokenizer identity, evidence source |
| Identifiability Argument | conditional | Required if any `identifiability_refs` are declared; summary of justification |
| Limitations | yes | Known restrictions, unverified boundaries, deferred checks |

### Validation Rules

- All `systems` entries must have a corresponding manifest in `provenance_refs`
- `profile` letter must be consistent with the highest declared capability across systems
- `score_scope` required if any system declares B or C capabilities
- `budget_ref` must resolve to an existing file
- `blocking_decisions` must include D-13, D-14, D-27, D-28, D-29, D-31

---

## Entity: Capability Declaration

**Location**: Nested under `systems.<system_id>` in access_profile.md frontmatter
**Purpose**: Per-system record of what is observable at the actual serving-pipeline boundary.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `system_id` | string | yes | Unique identifier (e.g. `"base_model"`, `"candidate"`, `"reference"`) |
| `profile_letter` | enum `A\|B\|C` | yes | System-level profile |
| `capabilities` | mapping | yes | See sub-fields below |
| `capabilities.text` | state | yes | `declared\|verified\|unavailable\|unverified` |
| `capabilities.scores` | state | yes | Same four-value enum |
| `capabilities.internals` | state | yes | Same four-value enum |
| `capabilities.candidate_scoring` | state | yes | Same four-value enum |
| `capabilities.controllable_decoding` | state | yes | Same four-value enum |
| `manifest_ref` | string (path) | yes | Relative path to capability/provenance manifest JSON |
| `verification_state` | enum | yes | `unverified\|partial\|verified` |
| `provider_transformations` | list of string | no | Post-processing applied by provider (e.g. `["top_k_filtering", "log_prob_masking"]`) |

### Validation Rules

- `profile_letter` A: `scores` and `internals` must be `unavailable`
- `profile_letter` B: `internals` must be `unavailable`; `scores` must not be `unavailable`
- `profile_letter` C: no restrictions on individual capabilities
- If `scores` is `declared` or `verified` and provider applies post-masking, `score_scope.type` must be `post_mask`
- `manifest_ref` must resolve to an existing JSON file

### State Vocabulary

| State | Meaning |
|-------|---------|
| `declared` | Provider claims this capability; not yet confirmed by evaluator |
| `verified` | Evaluator has confirmed the capability matches the actual boundary |
| `unavailable` | Capability is not available at this access level |
| `unverified` | Declared but evaluation team has not yet checked |

---

## Entity: Provenance Procedure

**Location**: Markdown body of `access_profile.md` + referenced manifest JSON
**Purpose**: Reviewed protocol identifying the measurement tap, intervening processors, model/tokenizer identity, and evidence source.

### Manifest Fields (JSON in `.factverify/access/capability_manifests/`)

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `manifest_id` | string | yes | Unique identifier |
| `system_id` | string | yes | Must match a system in `access_profile.md` |
| `tap_location` | string | yes | Where observations are collected |
| `intervening_processors` | list of string | yes | Processing between model output and observation point |
| `model_identity` | mapping | yes | `name`, `version`, `hash` (SHA-256) |
| `tokenizer_identity` | mapping | yes | `name`, `version`, `hash` (SHA-256) |
| `decoding_manifest` | mapping | no | Temperature, top_p, top_k, repetition_penalty, etc. |
| `evidence_source` | string | yes | How capability was verified (e.g. `"api_documentation"`, `"direct_test"`, `"provider_attestation"`) |
| `reviewer_id` | string | yes | Who reviewed this procedure |
| `review_date` | string (ISO 8601) | yes | When last reviewed |
| `artifact_hash` | string (SHA-256) | no | Hash of the referenced artifact if applicable |

### Validation Rules

- `system_id` must match an entry in `access_profile.md` `systems`
- `model_identity.hash` must be a valid SHA-256 hex string (64 chars)
- `reviewer_id` must be non-empty
- `review_date` must be valid ISO 8601

---

## Entity: Intervention Permission

**Location**: `interventions` list in access_profile.md frontmatter
**Purpose**: Role-separated record of approved modifications, independent of observation profile.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `action` | string | yes | What modification is permitted (e.g. `"export_checkpoint"`, `"fine_tune"`, `"tokenizer_change"`) |
| `actor_role` | string | yes | Must reference a `role_id` from `roles` |
| `approved_recipes` | list of string | yes | References to approved procedure documents |
| `artifact_lineage` | string | yes | How to trace the modification's provenance |
| `requires_capabilities` | list of string | no | Capabilities the actor must have for this action |

### Validation Rules

- `actor_role` must match a declared `role_id` in `roles`
- `approved_recipes` must be non-empty (no blank-check interventions)
- An action referencing capabilities beyond the actor's system profile is rejected

---

## Entity: Threat-Model Manifest

**Location**: Embedded in access_profile.md frontmatter under `permitted_sources` and `historical_access`
**Purpose**: Declaration of all permitted input sources, external information, historical artifacts, allowed actors, and resource references.

### Validation Rules

- Every source in `permitted_sources` must be a recognized category or explicit URL/path
- `historical_access` entries must have non-empty `attribution`
- Recovery from a pre-unlearning checkpoint must be separately attributed to that artifact
- Undeclared sources fail validation

---

## Entity: Identifiability Justification

**Location**: `.factverify/access/identifiability/<justification_id>.json`
**Purpose**: Scoped, reviewed argument for structural non-identifiability under declared observation regime.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `justification_id` | string | yes | Unique identifier |
| `revision` | string (semver) | yes | Bound to access_profile version |
| `system_pair` | list of 2 strings | yes | The two system_ids being compared |
| `observation_boundary` | string | yes | What the observer can see (must match profile) |
| `permitted_queries` | list of string | yes | Query types the argument covers |
| `historical_access` | list of string | yes | Historical information available to observer |
| `argument_type` | enum | yes | `constructive` (synthetic simulator) or `empirical` (observed matching) |
| `argument_summary` | string | yes | Prose summary of the justification |
| `reviewer_id` | string | yes | Who reviewed |
| `review_date` | string (ISO 8601) | yes | When reviewed |
| `limitations` | list of string | yes | Known scope restrictions |

### Validation Rules

- `system_pair` entries must both exist in `access_profile.md` `systems`
- `revision` must match or be compatible with the access_profile `version`
- `argument_type: empirical` requires `limitations` to note that finite observations do not prove universal equivalence
- `argument_type: constructive` requires `system_pair` to reference synthetic/controlled systems
- `reviewer_id` must be non-empty
- One matching refusal does not establish non-identifiability

---

## Entity: Status Contract

**Location**: Conceptual — enforced by validator logic, declared in access_profile.md `handling_policies`
**Purpose**: Four distinct outcome statuses with no silent promotion.

### Status Enum

| Status | Evidence Required | Description |
|--------|------------------|-------------|
| `confirmed_recovery` | P0-6 witness rule evidence | Knowledge was recovered despite unlearning claim |
| `conformance` | Complete bounded acceptance across all enabled channels | System passes all tests within declared scope |
| `non_identifiable` | Scoped identifiability justification (reviewed) | System pair cannot be distinguished under observation regime |
| `incomplete` | (default) Missing or uncertain required evidence | Any gap in evidence; never silently promoted |

### Validation Rules

- No automatic transition between statuses
- Missing raw score → `incomplete`, not `non_identifiable`
- Known control label alone → not a fabricated witness
- Completed test without confirmed witness → `incomplete`, not `conformance`
- Each status is a lookup-table assignment based on evidence, not a state machine

---

## Entity: Claim Template

**Location**: `.factverify/access/claim_templates/<template_id>.json`
**Purpose**: Profile-scoped, stage-labelled template declaring what evidence supports what conclusion.

### Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `template_id` | string | yes | Unique identifier |
| `profile` | enum `A\|B\|C` | yes | Must match access_profile profile |
| `stage` | enum `A\|B` | yes | Stage A (controlled) or Stage B (pretrained) |
| `completed_tests` | list of string | yes | Which tests support this claim |
| `permitted_interventions` | list of string | no | Which interventions were used |
| `budget_ref` | string (path) | yes | Reference to budget allocation |
| `reference_condition` | string | conditional | Required for claims involving reference models |
| `claim_text` | string | yes | The actual claim statement |
| `limitations` | list of string | yes | Scope restrictions |
| `reviewer_id` | string | yes | Who approved |
| `review_date` | string (ISO 8601) | yes | When approved |

### Validation Rules

- `profile` must match the access_profile's declared level
- Profile A claims must include an output-simulation limitation in `limitations`
- `stage` B claims cannot inherit Stage A causal references
- Universal erasure language in `claim_text` → rejection
- `budget_ref` must resolve to a valid budget allocation
- `reviewer_id` must be non-empty

---

## Entity: Capability/Provenance Manifest

**Location**: `.factverify/access/capability_manifests/<manifest_id>.json`
**Purpose**: Per-system referenced record binding artifact hashes to declared capabilities and measurement evidence.

(Fields defined under Provenance Procedure above — same JSON structure.)

---

## Entity: Validation Report

**Location**: `reports/p0-4-validation.json` (or path from `--report` CLI flag)
**Purpose**: Machine-readable output of the validation pass.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `report_id` | string | Generated UUID |
| `timestamp` | string (ISO 8601) | When validation ran |
| `spec_root` | string | Path to spec root |
| `scope` | string | `"access-profile"` |
| `strict` | boolean | Whether strict mode was enabled |
| `profile_version` | string | Version from access_profile.md |
| `checks` | list of mapping | Each: `rule_id` (FV-SPEC-047–056), `status` (`pass\|fail\|deferred\|skipped`), `diagnostics` (list of strings) |
| `capabilities` | mapping | Summary of declared capabilities per system |
| `permission_conflicts` | list of mapping | Any observation/intervention mismatches |
| `review_state` | mapping | Provenance review status per system |
| `cross_file_checks` | list of mapping | Each: `target`, `resolved` (bool), `digest_match` (bool or null) |
| `input_digests` | mapping | SHA-256 of each input file |
| `deferred_checks` | list of string | Checks deferred to future P0-x tasks |
| `baseline_comparison` | mapping or null | If `--baseline-suite` used: `changed_fields`, `revision_match` |
| `overall` | enum `pass\|fail` | Aggregate result |

---

## Entity: Review Manifest

**Location**: `.factverify/access/review_manifest.json`
**Purpose**: Tracks review records for provenance procedures, identifiability justifications, and claim templates.

### Fields

| Field | Type | Description |
|-------|------|-------------|
| `reviews` | list of mapping | Each: `artifact_id`, `artifact_type`, `reviewer_id`, `review_date`, `status` (`current\|expired\|pending`) |

### Validation Rules

- Every referenced manifest, justification, and claim template should have a corresponding review entry
- `expired` reviews trigger warnings; `pending` reviews block strict-mode validation

---

## Cross-Entity Relationships

```
access_profile.md
├── systems.<id> ──────────► capability_manifests/<manifest_id>.json
│   └── manifest_ref
├── interventions[].actor_role ──► roles[].role_id
├── budget_ref ────────────► .factverify/spec/attacks.yaml (P0-3)
├── claim_refs[] ──────────► claim_templates/<template_id>.json
├── identifiability_refs[] ► identifiability/<justification_id>.json
├── provenance_refs[] ─────► capability_manifests/<manifest_id>.json
├── handling_policies ─────► cross-check with P0-5 margins, P0-6 witness
└── blocking_decisions[] ──► decision registry (D-13..D-31)

identifiability/<id>.json
├── system_pair[] ─────────► access_profile systems.<id>
└── revision ──────────────► access_profile version

claim_templates/<id>.json
├── profile ───────────────► access_profile profile
├── budget_ref ────────────► attacks.yaml budget allocation
└── completed_tests[] ────► test identifiers from P0-6

review_manifest.json
└── reviews[].artifact_id ─► manifests, justifications, claim templates
```
