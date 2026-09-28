# Research: P0-7 Pre-registration and Spec Freeze

## Codebase Patterns (observed in P0-1 through P0-6)

**Decision**: Follow the established validator-per-scope pattern exactly.  
**Rationale**: Every P0 task follows the same structure: a `tools/<scope>_validator.py` module with individual `check_fv_spec_<NNN>_<name>` functions imported directly by `tests/test_<scope>.py`. `tools/validate_spec.py` dispatches to each module via `--scope <scope-name>`. Diverging from this pattern would create inconsistency in the test suite and the CLI interface.  
**Alternatives considered**: A monolithic preregistration+freeze module — rejected because it would mix validation and write operations, complicating the read-only dry-run requirement.

---

## Non-circular Digest Design (FV-SPEC-086, §2 source-reconciliation note)

**Decision**: Three separate, non-self-referential identity mechanisms.  
**Rationale**:

1. **CHECKSUMS.sha256** — computed over all packaged spec artifacts excluding itself using `hashlib.sha256`. Written before the commit. Format: one `sha256:<hex>  <relative-path>` line per artifact (shasum-compatible). Excludes `CHECKSUMS.sha256` itself from its own entries.

2. **Contract payload digest** (embedded in `preregistration.md` frontmatter) — serialize the document's canonical payload (all normative fields, excluding `digest`, `frozen_at`, and `receipt_location`) as deterministic JSON (sorted keys, no trailing whitespace), then SHA-256 hash. This identifies the document content without self-reference.

3. **Freeze receipt** (`reports/spec-v1-freeze-receipt.json`) — generated *after* `git tag -a spec-v1` is created. The receipt records `tag_target_commit` obtained via `git rev-parse spec-v1^{}` (dereferences the annotated tag object to the commit it points to). The receipt itself is never included in CHECKSUMS; it is a post-commit attestation.

**Alternatives considered**: Embedding the commit hash inside `preregistration.md` before committing — rejected because a commit cannot know its own hash (circular). Handbook V22/V24 described this circular approach; the §2 source-reconciliation note explicitly resolves it in favour of the non-circular design above.

---

## Decision Register Format

**Decision**: YAML file at `.factverify/decisions/register.yaml` with structured entries keyed by D-ID.  
**Rationale**: Matches the YAML-first convention used for `attacks.yaml`, `closure_templates.yaml`, and `margins.yaml`. The validator reads this file to determine which decisions are open vs resolved. A decision is considered "resolved" when it has `status: resolved` and a non-empty `resolution` field. "Open" means `status: open` or `status: pending`. "Not applicable" requires `status: not_applicable` and a non-empty `reason` field.

**Schema per entry**:
```yaml
D-01:
  status: open | pending | resolved | not_applicable
  resolution: ""          # required when status == resolved
  reason: ""              # required when status == not_applicable
  blocked_specs: [FV-SPEC-082]
  owner: ""
```

**Alternatives considered**: SQLite decisions table — rejected for P0-7 (the ledger is for checkpoints, not spec decisions). JSON — rejected because YAML is more human-editable and consistent with the rest of the spec namespace.

---

## Milestone Manifest Format

**Decision**: YAML file at `.factverify/milestones/milestones.yaml`.  
**Rationale**: Three milestones (`spec-v1`, `thresholds-v1`, `protocol-v1`) with structured determination rules. A value is acceptable if it is either already resolved (carries a `value` or `git_tag` field) or carries a `staged_rule` block (which must include `determined_at_gate`, `inputs`, and `method` fields). A plain `null`, `"TBD"`, or an empty string is not acceptable.

**Schema**:
```yaml
spec-v1:
  description: "Design rules, evaluation protocol, fact schema, splits"
  git_tag: spec-v1
  staged_rule: null           # null because this IS the freeze being created
thresholds-v1:
  description: "FCR/FRR operating thresholds selected on calibration split"
  git_tag: null               # not yet
  staged_rule:
    determined_at_gate: P4-3
    inputs: [calibration_split_results]
    method: "Select threshold maximising F-score at FRR ≤ α on calibration set"
protocol-v1:
  description: "Post-ablation Stage B components after Gate 3"
  git_tag: null
  staged_rule:
    determined_at_gate: Gate-3
    inputs: [block2_ablation_results]
    method: "Retain components with independent failure-witness confirmation"
```

---

## Exposure Record Format

**Decision**: Markdown file with YAML frontmatter at `.factverify/exposure/exposure_record.md`, following the same pattern as `access_profile.md` and `witness_rule.md`.  
**Rationale**: Consistent with the existing P0-4 and P0-6 pattern (Markdown + YAML frontmatter + human-readable body). The frontmatter contains the structured fields the validator checks; the body provides narrative context for reviewers.

**Required frontmatter fields**:
```yaml
status: draft | needs-review | reviewed
review_date: ""            # ISO 8601, required when status == reviewed
reviewer: ""
registration_status: local-only | externally-archived
archive_evidence: ""       # required when registration_status == externally-archived
access_events: []          # list of {date, actor, scope, outcomes_inspected}
```

**Key validation rule**: If any `access_event` has `scope` containing `final_test` and `outcomes_inspected` is non-empty, and the frontmatter claims `"untouched"` for the final set, validation fails with a contradiction diagnostic.

---

## Preregistration Document Format

**Decision**: Markdown file with YAML frontmatter at `.factverify/spec/preregistration.md`, consistent with `access_profile.md` and `witness_rule.md`.

**Required top-level sections** (validated by heading presence):
- `## Primary Question`
- `## Baselines`
- `## Hypotheses`
- `## Controlled Construction`
- `## Evaluation Units`
- `## Sampling`
- `## Evaluation Protocol`
- `## Primary Analysis`
- `## Stopping Rules`
- `## Deviations`
- `## Reporting`

Each section must contain an explicit artifact reference (`ref:` citation or `[[...]]` wikilink) — not an inline literal value for any normative quantity.

**Required frontmatter fields**:
```yaml
status: draft | needs-review | reviewed
version: "1"
digest: ""                 # SHA-256 of canonical payload (excluding this field)
receipt_location: reports/spec-v1-freeze-receipt.json
staged_milestones: [spec-v1, thresholds-v1, protocol-v1]
amendment_log: []
deviation_log: []
```

---

## freeze.py Architecture

**Decision**: Standalone CLI at `tools/freeze.py` using `click`, separate from `validate_spec.py`.  
**Rationale**: The freeze tool performs write operations (CHECKSUMS.sha256, git tag, receipt file), which must be explicitly separated from the read-only validator. The `--dry-run` flag makes the tool read-only. The `--verify` flag re-checks an existing snapshot.

**Modes**:
- `--dry-run` (default): Run all gate checks and report; make no writes and no git operations.
- `--execute`: Run gate checks, then write CHECKSUMS, commit, create annotated tag, write receipt.
- `--verify`: Read CHECKSUMS.sha256 and receipt; check all hashes; verify tag-target matches receipt.

**Gate check sequence** (in `--execute` mode; `--dry-run` runs the same checks without acting):
1. All seven spec artifacts present and non-empty.
2. `preregistration.md` passes `--scope preregistration --strict` validation.
3. All prior SPEC scopes pass their validators (regression: `--scope fact-contract`, `--scope closure-templates`, etc.).
4. Decision register: all applicable decisions resolved or marked not-applicable with reason.
5. Exposure record reviewed (`status: reviewed`).
6. Milestone manifest: all three milestones have either a `git_tag` or a `staged_rule` with all required fields.
7. No existing `spec-v1` tag (to prevent overwrite).
8. No raw model outputs, checkpoints, or credentials inside `.factverify/`.

**Tag-target commit extraction**:
```python
import subprocess
result = subprocess.run(
    ["git", "rev-parse", f"{tag_name}^{{}}"],
    capture_output=True, text=True, check=True
)
tag_target_commit = result.stdout.strip()
```

---

## Test Fixture Strategy (temporary-repository pattern)

**Decision**: Use pytest's `tmp_path` fixture plus `subprocess.run(["git", "init"])` for temporary repository fixtures in freeze tests.  
**Rationale**: This is the safest pattern for testing git operations — it avoids any interaction with the live study repository. Each test that exercises `freeze.py --execute` creates its own isolated git repo, populates it with the minimum required fixtures, and asserts the output state.

**Pattern** (matches existing `tempfile`-based tests in `test_witness_rule.py`):
```python
@pytest.fixture()
def freeze_repo(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.email", "test@test"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "config", "user.name", "Test"], check=True)
    # populate .factverify/spec/ with minimal valid fixtures
    # ...
    return tmp_path
```

**Non-mutating tests** (FV-SPEC-078 through FV-SPEC-085, FV-SPEC-087 structural checks): use the existing `tests/fixtures/preregistration/valid/` and `invalid/` fixture directories, consistent with the P0-1 through P0-6 pattern. No temporary git repo needed.

---

## Scope Addition to validate_spec.py

**Decision**: Add `"preregistration"` to `SUPPORTED_SCOPES` and add a `_run_preregistration_validation()` dispatch in `validate_spec.py`.  
**Rationale**: Consistent with the existing dispatch pattern for `closure-templates`, `attacks`, `access-profile`, `margins`, and `witness-rule`. The new options needed:
- `--preregistration` (path to `preregistration.md`)
- `--decisions-register` (path to decision register YAML)
- `--exposure-record` (path to exposure record MD)
- `--milestones` (path to milestones YAML)

All new options are optional (with sensible defaults derived from `--spec-root`) and unused for other scopes.

---

## Amendment Record Location

**Decision**: Amendment records live as entries in the `amendment_log` list in `preregistration.md` frontmatter (not as separate files).  
**Rationale**: Keeps all amendment history in the versioned preregistration document itself. Each amendment entry is a structured YAML object:
```yaml
- id: "AMD-001"
  trigger: "Pilot alpha amendment window"
  allowed_information: "Block 0 feasibility results only"
  approver: "Supervisor"
  deadline_before_final_access: "2027-03-01"
  effect_size_link: "margins.yaml#practical_effect_size"
  sample_size_link: "margins.yaml#n_facts_target"
  previous_value: "alpha: 0.05"
  new_value: "alpha: TBD"
  authorized: false    # becomes true when approved
  post_hoc: false      # set to true if triggered after final-test access
```

The validator checks: all required fields present, `post_hoc: false`, `authorized: true` (or explicitly declared as pending with a deadline).
