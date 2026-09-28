# Data Model: P0-7 Pre-registration and Spec Freeze

## Entities

### PreregistrationDocument

**File**: `.factverify/spec/preregistration.md`  
**Format**: Markdown with YAML frontmatter  
**Role**: Single normative source for study design commitments. Seventh and final spec artifact.

**Frontmatter fields**:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `status` | enum: `draft`, `needs-review`, `reviewed` | yes | Must be `reviewed` for strict gate |
| `version` | string (integer-as-string) | yes | Incremented on any content change |
| `digest` | string (`sha256:<hex>` or `""`) | yes | SHA-256 of canonical payload excluding this field |
| `receipt_location` | string (relative path) | yes | Where the freeze receipt will be written |
| `staged_milestones` | list of strings | yes | Must contain `spec-v1`, `thresholds-v1`, `protocol-v1` |
| `amendment_log` | list of AmendmentEntry | yes (empty list ok) | See AmendmentEntry below |
| `deviation_log` | list of DeviationEntry | yes (empty list ok) | Post-freeze deviations; empty at freeze time |
| `review_date` | ISO 8601 date string | conditional | Required when `status == reviewed` |
| `reviewer` | string | conditional | Required when `status == reviewed` |

**Required body sections** (validated by heading presence and artifact reference):

- `## Primary Question` — must reference `margins.yaml` for the primary endpoint
- `## Baselines` — must name both comparison baselines
- `## Hypotheses` — must reference `margins.yaml#hypothesis`
- `## Controlled Construction` — must reference `fact_contract.schema.json` and `closure_templates.yaml`
- `## Evaluation Units` — defines atomic fact as evaluation unit
- `## Sampling` — must reference `margins.yaml#n_facts_target` or staged rule
- `## Evaluation Protocol` — must reference `attacks.yaml`, `witness_rule.md`, `access_profile.md`
- `## Primary Analysis` — must reference `margins.yaml` for FRR cap, budgets, weighting
- `## Stopping Rules` — must enumerate all eight deviation event categories
- `## Deviations` — must declare the amendment protocol reference
- `## Reporting` — must enumerate confirmatory vs exploratory labelling rules

**Validation rules**:
- Each authoritative value (α, query budget, scorer policy) appears in exactly one artifact; any duplicate causes a conflict diagnostic.
- All section headings present; missing section → non-zero exit naming the section.
- `digest` field: if non-empty, must match SHA-256 of canonical payload (sections above, in defined order, with `digest` field omitted).

---

### MilestoneManifest

**File**: `.factverify/milestones/milestones.yaml`  
**Format**: YAML  
**Role**: Declares the three freeze milestones and their determination rules.

**Schema**:

```yaml
<milestone-name>:
  description: string          # human-readable purpose
  git_tag: string | null       # set once the tag exists
  staged_rule:                 # required if git_tag is null; must be null if git_tag is set
    determined_at_gate: string # gate ID (e.g., P4-3, Gate-3)
    inputs: [string]           # upstream artifact or result identifiers
    method: string             # non-empty description of determination procedure
```

**Valid milestone names**: `spec-v1`, `thresholds-v1`, `protocol-v1`

**Validation rules**:
- All three milestone names present.
- For each milestone: either `git_tag` is non-null, or `staged_rule` is present with all three sub-fields non-empty.
- A plain `null`, empty string, or literal `TBD` in any normative field → fail.

---

### ExposureRecord

**File**: `.factverify/exposure/exposure_record.md`  
**Format**: Markdown with YAML frontmatter  
**Role**: Dated, reviewed record of all data-access events and current registration status.

**Frontmatter fields**:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `status` | enum: `draft`, `needs-review`, `reviewed` | yes | Must be `reviewed` for strict gate |
| `review_date` | ISO 8601 date string | conditional | Required when `status == reviewed` |
| `reviewer` | string | conditional | Required when `status == reviewed` |
| `registration_status` | enum: `local-only`, `externally-archived` | yes | |
| `archive_evidence` | string (URL or path) | conditional | Required when `registration_status == externally-archived` |
| `access_events` | list of AccessEvent | yes (empty list ok) | |

**AccessEvent sub-schema**:

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `date` | ISO 8601 date string | yes | |
| `actor` | string | yes | |
| `scope` | string | yes | e.g., `"development"`, `"pilot"`, `"final_test"` |
| `outcomes_inspected` | list of strings | yes (empty list ok) | Metric names or result file paths |

**Validation rules**:
- If any `access_event` has `scope` containing `final_test` and `outcomes_inspected` is non-empty → contradiction with "untouched" claims.
- `registration_status == externally-archived` requires non-empty `archive_evidence`.
- `registration_status == local-only` with a non-empty external URL in `archive_evidence` → fail (inconsistency).

---

### DecisionRegister

**File**: `.factverify/decisions/register.yaml`  
**Format**: YAML  
**Role**: Canonical list of all design decisions (D-IDs); the strict freeze gate requires all applicable decisions to be resolved or explicitly marked not-applicable.

**Schema per entry**:

```yaml
D-01:
  status: open | pending | resolved | not_applicable
  resolution: string     # required (non-empty) when status == resolved
  reason: string         # required (non-empty) when status == not_applicable
  blocked_specs: [string]  # list of FV-SPEC-NNN IDs this blocks
  owner: string
  notes: string          # optional
```

**Validation rules**:
- `status == resolved` requires non-empty `resolution`.
- `status == not_applicable` requires non-empty `reason`.
- `status == open` or `status == pending` → the freeze gate counts this as unresolved.
- Any D-ID listed in a `FV-SPEC-NNN` `blocked_by` field that does not appear in the register → missing decision diagnostic.

---

### AmendmentEntry (inline in preregistration.md `amendment_log`)

| Field | Type | Required | Notes |
|-------|------|----------|-------|
| `id` | string (e.g., `AMD-001`) | yes | Unique within the log |
| `trigger` | string | yes | Description of what condition may trigger the amendment |
| `allowed_information` | string | yes | What data may inform the amendment decision |
| `approver` | string | yes | Named role or person |
| `deadline_before_final_access` | ISO 8601 date string | yes | Hard deadline |
| `effect_size_link` | string | yes | Reference to the artifact field that would change |
| `sample_size_link` | string | yes | Reference to the artifact field that would change |
| `previous_value` | string | yes | Normative value before amendment |
| `new_value` | string | yes | `"TBD"` is acceptable here (not for normative spec fields) |
| `authorized` | boolean | yes | `false` until formally approved |
| `post_hoc` | boolean | yes | `true` means triggered after final-test access — causes validation failure |

---

### ChecksumManifest

**File**: `.factverify/CHECKSUMS.sha256`  
**Format**: Plain text (shasum-compatible)  
**Role**: Byte-level integrity record for all packaged spec artifacts. Written by `freeze.py`, verified by `freeze.py --verify`.

**Format** (one line per artifact):
```
sha256:<64-char-hex>  .factverify/spec/fact_contract.schema.json
sha256:<64-char-hex>  .factverify/spec/closure_templates.yaml
sha256:<64-char-hex>  .factverify/spec/attacks.yaml
sha256:<64-char-hex>  .factverify/spec/access_profile.md
sha256:<64-char-hex>  .factverify/spec/margins.yaml
sha256:<64-char-hex>  .factverify/spec/witness_rule.md
sha256:<64-char-hex>  .factverify/spec/preregistration.md
```

**Excluded**: `.factverify/CHECKSUMS.sha256` itself (not self-referential).

**Validation rules**:
- Each artifact path resolves to an existing file.
- Re-computed SHA-256 matches the stored hex for every entry.
- Any new file in `.factverify/spec/` not present in the manifest → warning (unexpected artifact).

---

### FreezeReceipt

**File**: `reports/spec-v1-freeze-receipt.json`  
**Format**: JSON  
**Role**: Post-commit attestation. Generated after the tag is created; records the tag-target commit.

**Schema**:

```json
{
  "freeze_version": "1",
  "tag_name": "spec-v1",
  "tag_target_commit": "<40-char-sha>",
  "tag_object_sha": "<40-char-sha>",
  "timestamp_utc": "<ISO 8601>",
  "checksums_digest": "sha256:<hex-of-CHECKSUMS.sha256>",
  "registration_status": "local-only | externally-archived",
  "archive_url": null
}
```

**Validation rules** (in `freeze.py --verify`):
- `tag_target_commit` must match `git rev-parse <tag_name>^{}`.
- `checksums_digest` must match SHA-256 of the current `CHECKSUMS.sha256` file.
- Receipt file itself is never included in `CHECKSUMS.sha256`.

---

### ReadinessReport

**File**: `reports/p0-7-validation.json`  
**Format**: JSON  
**Role**: Machine-readable output of `validate_spec.py --scope preregistration`.

**Schema**:

```json
{
  "scope": "preregistration",
  "spec_root": "<path>",
  "timestamp": "<ISO 8601>",
  "strict": true | false,
  "overall_status": "pass | fail",
  "checks": [
    {
      "id": "FV-SPEC-078",
      "name": "artifact",
      "status": "pass | fail | deferred",
      "diagnostics": []
    }
  ],
  "open_decisions": ["D-44", "D-45"],
  "staged_obligations": [
    {"milestone": "thresholds-v1", "status": "pending", "gate": "P4-3"}
  ],
  "input_digests": {
    "preregistration.md": "sha256:<hex>",
    "register.yaml": "sha256:<hex>"
  }
}
```

---

## State Transitions

### Preregistration document lifecycle

```
draft → needs-review → reviewed → [frozen at spec-v1 tag]
```

- `draft`: work in progress; validator runs but strict mode fails
- `needs-review`: ready for supervisor/reviewer sign-off
- `reviewed`: approved; required for `freeze.py` gate to pass
- frozen: `spec-v1` tag created; any further edit requires an amendment entry and a new tag

### Decision register entry lifecycle

```
open → pending → resolved
              ↘ not_applicable
```

- `open`: not yet addressed
- `pending`: under discussion, blocked on external input
- `resolved`: `resolution` field populated; freeze gate accepts
- `not_applicable`: `reason` field populated; freeze gate accepts

### Freeze workflow state

```
(clean repo) → dry-run checks → [all pass] → execute → commit → tag → receipt
                              ↘ [any fail] → diagnostic report, exit non-zero
```

- Dry-run: read-only; produces only a console/report output
- Execute: requires all gate checks to pass; writes CHECKSUMS, commits, tags, writes receipt
- Verify: reads existing CHECKSUMS and receipt; re-computes hashes; checks tag-target
