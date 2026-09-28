# Quickstart: Base Model Selection and Pinning (P0-8)

## Prerequisites

- Python 3.11 + uv (same as rest of project)
- Existing spec files in `.factverify/spec/` (P0-1 through P0-7 complete)
- `tools/validate_spec.py` and `tools/freeze.py` already present

## Step 1: Run the structural validator (pre-decision)

```bash
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  --report reports/p0-8-validation.json
```

Expected: exit 0; all checks `pending` (no decisions resolved yet).

## Step 2: After D-46 and D-49 resolve — fill the spec

Edit `.factverify/spec/models.yaml`:
1. Replace `DECISION_REQUIRED` values in `blocks_0_2` with the chosen model's details.
2. Set `block_3_confirmation.deadline` if D-47 has a target date.
3. Leave `files: {}` until the model is downloaded.

Re-run validation in strict mode:
```bash
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  --strict \
  --report reports/p0-8-validation.json
```

Expected: FV-SPEC-089 and FV-SPEC-090 pass; FV-SPEC-091 still `pending` (no model dir).

## Step 3: After downloading the model — record file digests

The `src/models/` module (P2-0) will compute and write `files` entries. To record manually:

```bash
# Example — replace with the actual model path
python -c "
import hashlib, json
from pathlib import Path
model_dir = Path('/path/to/model')
digests = {
    p.name: 'sha256:' + hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(model_dir.rglob('*')) if p.is_file()
}
print(json.dumps(digests, indent=2))
"
```

Copy the output into `.factverify/spec/models.yaml` under `files:`.

Then re-run with `--model-dir`:
```bash
python tools/validate_spec.py \
  --scope models \
  --spec-root .factverify/spec \
  --strict \
  --model-dir /path/to/model \
  --report reports/p0-8-validation.json
```

Expected: FV-SPEC-089, FV-SPEC-090, FV-SPEC-091 pass.

## Step 4: Run tests

```bash
uv run pytest tests/test_models_spec.py -v
```

All 7 tests (one per FV-SPEC-089 through FV-SPEC-095) must be green.

## Step 5: Freeze check

Once all upstream P0 tasks are done and you are ready to freeze:

```bash
python tools/freeze.py --spec-root .factverify/spec --dry-run
```

`models.yaml` is now included in the freeze artifact list (eighth artifact).
