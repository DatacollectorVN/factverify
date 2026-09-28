# CLI Contract: models scope

## Invocation

```
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  [--strict] \
  [--report reports/p0-8-validation.json] \
  [--model-dir <path-to-local-model-directory>] \
  [--access-profile <path>] \
  [--downstream-report <path>]
```

## Options

| Option | Required | Default | Purpose |
|---|---|---|---|
| `--scope models` | yes | — | Activates the models validator |
| `--spec-root` | yes | — | Path to `.factverify/spec/`; must contain `models.yaml` |
| `--strict` | no | false | In strict mode, `DECISION_REQUIRED` values and open blocking decisions cause failure |
| `--report` | no | stdout summary only | Path for the structured JSON validation report |
| `--model-dir` | no | none | Local model directory to run offline digest check against (FV-SPEC-091); omit to skip |
| `--access-profile` | no | `<spec-root>/access_profile.md` | Override access profile path for FV-SPEC-092 |
| `--downstream-report` | no | none | Exclusion-gate report JSON to cross-check model-identity hash (FV-SPEC-094); omit for `pending` |

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | All checks pass (or all failures are `pending`) |
| 1 | One or more checks failed |
| 2 | Missing or malformed inputs (models.yaml absent, spec-root invalid) |

## Behaviour by Check

### FV-SPEC-089 (identity_completeness)
- Non-strict: warns on `DECISION_REQUIRED` values, does not fail.
- Strict: fails on any null, empty, or `DECISION_REQUIRED` value in a non-pending role entry.
- Pending role (`status: pending`): all sub-checks for that role are reported `pending`.

### FV-SPEC-090 (immutable_revision)
- Fails on any `model_revision` or `tokenizer_revision` that does not match `/^[0-9a-f]{40}$/`.
- `DECISION_REQUIRED` is caught by FV-SPEC-089 first; FV-SPEC-090 only runs on non-placeholder values.

### FV-SPEC-091 (file_digests)
- If `--model-dir` is absent: status is `pending`.
- If `--model-dir` is present: re-computes SHA-256 for every file listed in `files` dict; fails on any mismatch, missing file, or extra file.
- If `files` is empty `{}`: warns but does not fail (files not yet recorded).

### FV-SPEC-092 (access_profile_compat)
- Reads `access_profile.md` (from `--access-profile` or default).
- Checks each declared model's `licence` and `variant` against the profile's intervention channels.
- If `access_profile.md` is absent: status is `pending` (not fail).

### FV-SPEC-093 (identity_hash_definition)
- Computes the canonical identity hash for every resolved role entry.
- Reports the computed hashes in the JSON report under `identity_hashes`.
- Always passes if the inputs are present (it is a definition, not a constraint check).
- Pending if any required field (`repo_id`, `model_revision`, `tokenizer_revision`, `dtype`) is unresolved.

### FV-SPEC-094 (downstream_binding)
- If `--downstream-report` is absent: all downstream sub-checks are `pending`.
- If `--downstream-report` is present: parses its `model_identity_hash` field and compares against computed hash; fails on mismatch.
- Ledger and cache manifest checks are `pending` at P0-8 time (P2-5 and P2-7 not yet built).

### FV-SPEC-095 (amendment_protocol)
- If `CHECKSUMS.sha256` does not exist (spec not yet frozen): status is `pending`.
- If `CHECKSUMS.sha256` exists: computes SHA-256 of current `models.yaml` and compares against stored value. If they differ, checks `preregistration.md` for an amendment record referencing `models.yaml`. Fails if no amendment found.

## Example: Full validation after decisions resolve

```bash
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  --strict \
  --model-dir /path/to/downloaded/model \
  --report reports/p0-8-validation.json
```

## Example: Pre-decision structural check (non-strict)

```bash
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  --report reports/p0-8-validation.json
```

Expected exit code: 0 (all checks pending or passing at schema level).
