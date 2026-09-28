# CLI Interface Contract: P0-7 Validate and Freeze Tools

## validate_spec.py — preregistration scope (extension)

### Invocation

```
python tools/validate_spec.py \
  --scope preregistration \
  --spec-root .factverify/spec \
  --preregistration .factverify/spec/preregistration.md \
  --decisions-register .factverify/decisions/register.yaml \
  --exposure-record .factverify/exposure/exposure_record.md \
  --milestones .factverify/milestones/milestones.yaml \
  [--strict] \
  --report reports/p0-7-validation.json
```

### New options (unused by other scopes)

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--preregistration PATH` | path | `<spec-root>/preregistration.md` | Preregistration document |
| `--decisions-register PATH` | path | `.factverify/decisions/register.yaml` | Decision register |
| `--exposure-record PATH` | path | `.factverify/exposure/exposure_record.md` | Exposure record |
| `--milestones PATH` | path | `.factverify/milestones/milestones.yaml` | Milestone manifest |

The `--strict` flag (already present) additionally requires: all decisions resolved/not-applicable, all sections reviewed, no pending obligations for current-phase normative fields.

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | All checks passed |
| 1 | One or more validation failures |
| 2 | Missing or malformed inputs (bad path, unreadable file, bad invocation) |

### Output

Writes `reports/p0-7-validation.json` (ReadinessReport schema — see data-model.md).  
Prints summary to stdout: `Preregistration validation: N passed, M failed, K deferred.`

---

## freeze.py — new tool

### Invocation

```
# Dry run (default, read-only)
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --dry-run \
  --report reports/p0-7-validation.json

# Execute (writes checksums, commits, tags, writes receipt)
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --execute \
  --report reports/p0-7-validation.json

# Verify existing snapshot
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --verify
```

### Options

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--spec-root PATH` | path (required) | — | Root of spec namespace |
| `--tag TAG` | string | `spec-v1` | Name of the freeze tag to create or verify |
| `--dry-run` | flag | (default mode) | Run all gate checks; make no writes |
| `--execute` | flag | — | Run gate checks, then write CHECKSUMS, commit, tag, write receipt |
| `--verify` | flag | — | Verify an existing snapshot (re-compute hashes, check tag-target) |
| `--report PATH` | path | `None` | Write gate-check results to JSON |
| `--decisions-register PATH` | path | `.factverify/decisions/register.yaml` | |
| `--exposure-record PATH` | path | `.factverify/exposure/exposure_record.md` | |
| `--milestones PATH` | path | `.factverify/milestones/milestones.yaml` | |

Exactly one of `--dry-run`, `--execute`, or `--verify` must be provided (mutual exclusion enforced at startup).

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Dry run: all gates passed; Execute: freeze complete; Verify: snapshot valid |
| 1 | Gate failure, integrity failure, or validation error (named in diagnostics) |
| 2 | Missing inputs, bad invocation, or ambiguous mode flags |

### Writes (--execute only)

| File | When written |
|------|-------------|
| `.factverify/CHECKSUMS.sha256` | Before the git commit |
| `reports/spec-v1-freeze-receipt.json` | After `git tag -a spec-v1` |

### Guarantees

- `--dry-run` makes **no** filesystem writes and **no** git operations.
- `--execute` refuses to run if a tag named `--tag` already exists.
- `--execute` refuses to run if any gate check fails.
- `--verify` makes **no** writes; only reads and re-computes.
- No network calls in any mode.

---

## Diagnostic format (shared across both tools)

Each diagnostic entry in the JSON report follows the existing project convention:

```json
{
  "rule_id": "FV-SPEC-079",
  "file": ".factverify/exposure/exposure_record.md",
  "json_pointer": "/access_events/0/outcomes_inspected",
  "message": "Final-test access event lists inspected outcomes but registration claims 'untouched'."
}
```

`rule_id` maps to the FV-SPEC-NNN identifier from the requirements document.
