# Data Model: P0-1 Atomic-Fact Contract Schema

**Feature**: `20260921-211249-fact-contract-schema`
**Date**: 2026-09-21

## Core Entities

### AtomicFactContract (JSON document)

The root entity. One file per fact, stored at `.factverify/contracts/`.

| Field | Type | Required | Source |
|-------|------|----------|--------|
| `schema_version` | const `"1.0.0"` | yes | schema |
| `contract_id` | string (pattern) | yes | schema |
| `fact_id` | string (pattern) | yes | schema |
| `contract_status` | enum | no | schema |
| `fact_type` | enum | no | schema |
| `evidence_regime` | object | no | schema |
| `triple` | TripleSpec | yes | schema |
| `canonical_statement` | StatementSpec | no | schema |
| `aliases` | AliasSet | yes | schema |
| `equivalent_directions` | DirectionSpec[] | yes | schema |
| `entity_resolution` | EntityResolutionSpec | no | schema |
| `normalization` | NormalizationSpec | no | schema |
| `deletion_scope` | DeletionScopeSpec | no | schema |
| `retained_neighbourhood` | NeighbourSpec[] | yes | schema |
| `clue_boundary` | ClueBoundarySpec | yes | schema |
| `reference_policy` | ReferencePolicySpec | no | schema |
| `freeze_policy` | FreezePolicySpec | no | schema |

**Identity rules**:
- `fact_id` format: `factverify:fact:{fact_key}` where `fact_key` = `wd-Q{s}-P{r}-Q{o}` (Wikidata) or `{slug}` (project-local)
- `contract_id` format: `factverify:contract:{fact_key}:v{N}` — `fact_key` MUST match `fact_id`
- `contract_id` version `v{N}` MUST increment on semantic changes; `fact_id` remains stable

### TripleSpec

| Field | Type | Required |
|-------|------|----------|
| `subject` | EntityRef | yes |
| `relation` | RelationRef | yes |
| `object` | EntityRef | yes |

### EntityRef

| Field | Type | Required |
|-------|------|----------|
| `id` | string (QID or project-local pattern) | yes |
| `label` | string (non-empty) | yes |
| `source` | enum: `wikidata`, `factverify_internal` | yes |
| `source_url` | URI | no |

### RelationRef

| Field | Type | Required |
|-------|------|----------|
| `id` | string (PID or project-local pattern) | yes |
| `label` | string (non-empty) | yes |
| `source` | enum: `wikidata`, `factverify_internal` | yes |
| `source_url` | URI | no |

### AliasSet

| Field | Type | Required |
|-------|------|----------|
| `subject` | AliasEntry[] (min 1) | yes |
| `relation` | RelationAliasEntry[] (min 1) | yes |
| `object` | AliasEntry[] (min 1) | yes |

### AliasEntry

| Field | Type | Required |
|-------|------|----------|
| `text` | string (non-empty) | yes |
| `language` | BCP 47 tag | yes |
| `alias_type` | enum: canonical, alternate_name, transliteration, disambiguated_name | yes |
| `source` | enum: wikidata, authority_source, manual_adjudication | no |
| `source_url` | URI | no |

### RelationAliasEntry

| Field | Type | Required |
|-------|------|----------|
| `text` | string (non-empty) | yes |
| `language` | BCP 47 tag | yes |
| `argument_order` | enum: subject_relation_object, object_inverse_relation_subject | yes |

### DirectionSpec

| Field | Type | Required |
|-------|------|----------|
| `direction` | enum: forward, inverse, verification | yes |
| `given` | enum: subject, object, triple | yes |
| `answer` | enum: object, subject, truth_value | yes |
| `language` | BCP 47 tag | no |
| `statement_pattern` | string | no |

**Consistency rules** (enforced by validator, not schema):
- forward → given=subject, answer=object
- inverse → given=object, answer=subject
- verification → given=triple, answer=truth_value

### NeighbourSpec

| Field | Type | Required |
|-------|------|----------|
| `id` | string (`retain:` prefix) | yes |
| `bucket` | enum: same_subject, same_relation, compositional, global | yes |
| `statement` | string (non-empty) | yes |
| `language` | BCP 47 tag | no |
| `expected_answers` | string[] (min 1) | no |

**Coverage rule**: Array MUST contain at least one item per bucket (4 minimum, enforced by schema `contains` + `allOf`).

### ClueBoundarySpec

| Field | Type | Required |
|-------|------|----------|
| `equivalent_rule` | string (non-empty) | yes |
| `clue_bearing_rule` | string (non-empty) | yes |
| `ambiguous_policy` | enum: adjudicate_before_freeze_else_exploratory, exclude_from_confirmatory_analysis | yes |

## Relationships

```
AtomicFactContract
├── triple: TripleSpec
│   ├── subject: EntityRef
│   ├── relation: RelationRef
│   └── object: EntityRef
├── aliases: AliasSet
│   ├── subject: AliasEntry[]
│   ├── relation: RelationAliasEntry[]
│   └── object: AliasEntry[]
├── equivalent_directions: DirectionSpec[]
├── retained_neighbourhood: NeighbourSpec[]
└── clue_boundary: ClueBoundarySpec
```

## Validation Report (output entity)

| Field | Type | Description |
|-------|------|-------------|
| `scope` | string | Always `"fact-contract"` for P0-1 |
| `schema_path` | string | Resolved path to schema file |
| `schema_digest` | string | SHA-256 of schema file |
| `checked_files` | object[] | Per-file validity and diagnostics |
| `revision_check` | object/string | Baseline comparison result or `"not_requested"` |
| `diagnostics` | object[] | Rule ID, file, JSON pointer, message |
