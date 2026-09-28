# Research: P0-2 Closure Template Suite

**Feature**: `20260921-235511-closure-template-suite`
**Date**: 2026-09-21

## YAML Parsing and Validation Library

**Decision**: Use `pyyaml` (already in pyproject.toml) for YAML parsing. Use `jsonschema` for structural validation after converting YAML to dict.

**Rationale**: The closure artifact is YAML per the P0-2 study guide convention. PyYAML handles safe loading. After parsing, the same `jsonschema` Draft 2020-12 infrastructure from P0-1 validates the structure. This avoids introducing a YAML-native schema language (e.g., JSON Schema over YAML documents is standard practice).

**Alternatives considered**:
- `ruamel.yaml`: Preserves comments and round-trips, but unnecessary for read-only validation. Adds a dependency.
- `strictyaml`: Stronger typing but non-standard schema language; would split validation logic from the JSON Schema approach used by P0-1.

## Closure Artifact Format

**Decision**: Single `closure_templates.yaml` file with top-level keys: `spec_version`, `fact_contract_ref`, `boundary_policy`, `sets` (containing `equivalence` and `inference`), `controls`, `groups`, `splits`, and metadata references. Each template is a record within its set.

**Rationale**: Follows the P0-2 study guide §9 illustrative YAML structure. A single file keeps the suite atomic — no partial-load risk. The six families (direct, inverse, cloze, paraphrase, multilingual, verification) are attributes of templates, not separate collections, because families can overlap (e.g., Vietnamese cloze is both multilingual and cloze).

**Alternatives considered**:
- Multiple YAML files per family: More modular but breaks atomicity and complicates revision tracking. A suite change requires updating exactly one file.
- JSON format: Valid but less readable for human review. YAML aligns with the study guide convention and is friendlier for the template authoring workflow.

## Instance Binding Architecture

**Decision**: Separate `instance_bindings.json` file that maps template IDs to contract fields (aliases, answers, retained entries, distractors). Bindings are resolved at validation time, not embedded in the closure YAML.

**Rationale**: Separation of concerns — the closure artifact defines *what* to ask; bindings define *how* to instantiate it for a specific contract. This allows the same template to be bound to different contracts (Hà Nội vs fictional scientist). Bindings reference P0-1 contract fields (triple roles, aliases, retained_neighbourhood entries) and are validated against them.

**Alternatives considered**:
- Inline bindings in YAML: Simpler but couples template design to specific contracts. Would require duplicating templates for each contract.
- Binding as a separate YAML file: Acceptable, but JSON aligns with the P0-1 contract format and is easier to validate with jsonschema.

## Review Manifest Format

**Decision**: JSON manifest at `.factverify/closure/review_manifest.json` containing reviewer ID, date, revision hashes, per-instance labels, rationale, disagreements, adjudication results, bilingual approval flags, and decision references.

**Rationale**: Machine-readable for strict-mode validation. Tied to exact revisions via content digests so stale reviews are detected. Supports the two-reader workflow from P0-1 (extended for bilingual approval of multilingual E instances).

**Alternatives considered**:
- Markdown review file only: Human-readable but not machine-checkable for strict mode. The semantic review report (`reports/p0-2-semantic-review.md`) serves human review; the manifest serves automation.

## Preview Rendering Strategy

**Decision**: JSONL output where each line is a rendered instance containing `instance_id`, `model_input` (ordered message array), and `evaluator_metadata` (answer key, class, truth_label, premises, review references). Rendering is deterministic given fixed revisions and bindings.

**Rationale**: JSONL is append-friendly and can be inspected line by line. The model_input/evaluator_metadata split enforces FV-SPEC-028 (no answer leakage into model input) at the serialization level. Deterministic rendering (FV-SPEC-027, constraint C-1) is verified by comparing two runs.

**Alternatives considered**:
- JSON array: Entire preview in one file. Less memory-efficient for large suites and harder to inspect incrementally.
- CSV: Insufficient for nested message structures (multi-turn conversations, system prompts).

## Group/Split Assignment Strategy

**Decision**: Groups are declared in the closure artifact. Each group contains one or more near-duplicate template IDs. Each group is assigned to exactly one split (construction, calibration, final_test). Validation enforces: (1) every template belongs to exactly one group, (2) every group belongs to exactly one split, (3) calibration and final_test groups are disjoint.

**Rationale**: Per P0-2 §9.1 and handbook I6/V13, near-duplicates must stay grouped to prevent data leakage. The split assignment is at the group level, not the template level, because superficial rewrites of the same prompt must not appear in different splits.

**Alternatives considered**:
- Template-level split assignment: Simpler but fails to capture the near-duplicate grouping constraint. A researcher could accidentally split two paraphrases of the same prompt across calibration and final test.

## Scope Extension for validate_spec.py

**Decision**: Extend the existing `tools/validate_spec.py` CLI with `--scope closure-templates` rather than creating a new validator. Add closure-specific options (`--bindings`, `--review-manifest`, `--split`, `--preview`, `--strict`, `--baseline-suite`).

**Rationale**: Single entry point for all P0-x validation. Reuses the CLI framework (click), report format, and diagnostic structure from P0-1. The `--scope` flag already supports extensibility (P0-1 validates `fact-contract`; P0-2 adds `closure-templates`). Exit codes and report schema remain consistent.

**Alternatives considered**:
- Separate `tools/validate_closure.py`: Would duplicate CLI boilerplate, report writing, and diagnostic formatting. Also breaks the single-command validation story.

## Template Record Schema

**Decision**: Each template record carries: `id` (stable unique), `class` (E/I/R/X), `group` (group ID), `language` (BCP 47 tag), `format` (free_answer/completion/true_false), `text` (template with placeholders), `context_refs` (list of context template IDs for multi-turn), `relation_applicability` (list of relation types), `answer_role` (subject/object/truth_value), `premises` (list, empty for E), plus class-specific fields. E templates: `primary_family` + `overlapping_attributes`. I templates: `subtype`, `premise_origins`, `reasoning_status`, `support_status`, `separate_reporting`. R templates: `retained_entry_ref`, `bucket`. X templates: `exclusion_reason`, `diagnostic_role`.

**Rationale**: Directly maps to the "Required record content" section of FV-SPEC P0-2 §2. One template, one ID, one primary family addresses the overlapping-attribute problem (FV-SPEC-022). Class-specific fields enforce the routing rules (FV-SPEC-017) at the schema level.

## Verification Balance Enforcement

**Decision**: Balance is checked per block: (contract_id, relation_type, language, split). Within each block, the count of verification instances with `truth_label: true` must exactly equal the count with `truth_label: false`.

**Rationale**: Per FV-SPEC-024 and P0-2 §3.1, agreement with every proposition must not look like discrimination. Exact count matching per block is the simplest enforceable invariant. The oracle label is stored only in evaluator_metadata, never in model_input.
