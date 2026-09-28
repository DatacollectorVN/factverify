# Quickstart: P0-7 Pre-registration and Spec Freeze

## Prerequisites

All prior spec artifacts must exist and pass validation:

```bash
# Verify P0-1 through P0-6 are green
python tools/validate_spec.py --scope fact-contract --spec-root .factverify/spec --contracts .factverify/contracts --report reports/p0-1-validation.json
python tools/validate_spec.py --scope closure-templates --spec-root .factverify/spec --contracts .factverify/closure --bindings .factverify/closure/instance_bindings.json --report reports/p0-2-validation.json
python tools/validate_spec.py --scope attacks --spec-root .factverify/spec --contracts .factverify/attacks --report reports/p0-3-validation.json
python tools/validate_spec.py --scope access-profile --spec-root .factverify/spec --report reports/p0-4-validation.json
python tools/validate_spec.py --scope margins --spec-root .factverify/spec --report reports/p0-5-validation.json
python tools/validate_spec.py --scope witness-rule --spec-root .factverify/spec --report reports/p0-6-validation.json
```

## Step 1 — Populate required input files

Create and populate the three new input artifacts:

```
.factverify/decisions/register.yaml       # decision register (all D-IDs)
.factverify/milestones/milestones.yaml    # three milestone entries
.factverify/exposure/exposure_record.md   # exposure record with YAML frontmatter
.factverify/spec/preregistration.md       # study commitment document
```

See `data-model.md` for the schema of each file.

## Step 2 — Validate (non-strict, iterative)

```bash
python tools/validate_spec.py \
  --scope preregistration \
  --spec-root .factverify/spec \
  --report reports/p0-7-validation.json
```

Fix any diagnostics reported. Repeat until exit code is 0.

## Step 3 — Validate (strict — freeze readiness)

```bash
python tools/validate_spec.py \
  --scope preregistration \
  --spec-root .factverify/spec \
  --strict \
  --report reports/p0-7-validation.json
```

Strict mode additionally requires:
- All applicable decisions in `register.yaml` are `resolved` or `not_applicable`.
- Exposure record `status: reviewed`.
- Preregistration `status: reviewed`.

## Step 4 — Dry-run freeze (read-only gate check)

```bash
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --dry-run \
  --report reports/p0-7-validation.json
```

This runs all eight freeze gate checks and reports results without writing anything.

## Step 5 — Execute freeze (write CHECKSUMS, commit, tag, receipt)

**Only perform this step when all gates are green and supervisor approval is in hand.**

```bash
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --execute
```

This will:
1. Re-run all gate checks (fails immediately if any fail).
2. Write `.factverify/CHECKSUMS.sha256`.
3. `git add .factverify/CHECKSUMS.sha256` and commit with message `P0-7: spec-v1 freeze`.
4. Create annotated tag: `git tag -a spec-v1 -m "spec-v1 freeze"`.
5. Write `reports/spec-v1-freeze-receipt.json` (capturing `git rev-parse spec-v1^{}`).

## Step 6 — Verify the snapshot

```bash
python tools/freeze.py \
  --spec-root .factverify/spec \
  --tag spec-v1 \
  --verify
```

Exit 0 = all artifact hashes match and receipt is consistent with the tag.

## Running the test suite

```bash
pytest tests/test_preregistration_freeze.py -v
```

All 11 hooks must pass. The suite is offline-only (no network, no GPU, no model calls).

## What NOT to do after the freeze

- Do not edit any file under `.factverify/spec/` without creating a new git tag and adding an amendment entry to `preregistration.md`.
- Do not move or force-overwrite the `spec-v1` tag.
- Do not re-run `freeze.py --execute` against the same tag name (it will refuse).
- Do not tune thresholds or select parameters based on final-test outcomes (see constitution §2–3).
