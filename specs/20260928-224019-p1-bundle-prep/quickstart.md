# Quickstart: P1 Fact Bundle Preparation

**Feature**: 20260928-224019-p1-bundle-prep

Run the three scripts in order. Each is CPU-only (no GPU, no model weights needed) except the entailment screen in P1-4 which calls the Anthropic API.

---

## Prerequisites

- `data/controlled/facts.jsonl` exists with ≥16 accepted facts (`contract_status: draft`, gate verdict `pass` from P1-2 once that runs — for now, all draft facts are treated as candidates).
- TOFU dataset at the pinned path: `~/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68/`
- `uv sync` completed.
- `ANTHROPIC_API_KEY` set (needed only for P1-4 entailment screen).

---

## Step 1 — Build source bundles (P1-3)

```bash
uv run python scripts/build_bundles.py build \
  --facts       data/controlled/facts.jsonl \
  --mentions    data/tofu_derived/mentions.jsonl \
  --source      ~/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68 \
  --spec-root   .factverify/spec \
  --out         data/controlled/sources/ \
  --leaveout    data/controlled/leaveout/ \
  --transforms  data/tofu_derived/transformations.jsonl
```

**Outputs**:
- `data/controlled/sources/records.jsonl` — all training records
- `data/controlled/sources/index.jsonl` — record → fact IDs index
- `data/controlled/sources/bundles/<fact_id>.json` — one bundle per accepted fact
- `data/controlled/leaveout/<fact_id>.json` — one leave-out manifest per fact

**Expected output** (Block 0 pilot, ~35 facts):
```
Built 35 bundles | 0 below direction minimum | 0 multi-fact exclusions | Written: data/controlled/sources/
Leave-out manifests: 35 written to data/controlled/leaveout/
```

---

## Step 2 — Fill locality neighbourhoods (P1-5)

```bash
uv run python scripts/build_neighbourhoods.py build \
  --facts       data/controlled/facts.jsonl \
  --index       data/controlled/sources/index.jsonl \
  --leaveout    data/controlled/leaveout/ \
  --source      ~/.cache/huggingface/hub/datasets--locuslab--TOFU/snapshots/324592d84ae4f482ac7249b9285c2ecdb53e3a68 \
  --out         data/controlled/neighbourhoods.jsonl
```

**Outputs**:
- `data/controlled/neighbourhoods.jsonl` — neighbourhood items, all stubs replaced

**Expected output**:
```
35 facts processed | 0 stubs remaining | 0 below bucket minimum
Written: data/controlled/neighbourhoods.jsonl
```

---

## Step 3 — Entailment audit (P1-4)

```bash
uv run python scripts/entailment_audit.py audit \
  --facts     data/controlled/facts.jsonl \
  --leaveout  data/controlled/leaveout/ \
  --index     data/controlled/sources/index.jsonl \
  --spec-root .factverify/spec \
  --out       results/entailment_audit.jsonl \
  --report    reports/entailment_audit.md \
  --sample-fraction 0.10 \
  --sample-min 5 \
  --sample-max 20
```

**Outputs**:
- `results/entailment_audit.jsonl` — per (unit, record) classification
- `reports/entailment_audit.md` — human-readable summary with flagged records

**Expected output**:
```
35 units audited | N records total | M flagged (exact: K, entailment: L)
Sample: P unflagged records reviewed
Confirmed failures: 0  (or: N → remediate before Phase 3)
Written: results/entailment_audit.jsonl | reports/entailment_audit.md
```

If confirmed failures > 0, rewrite or exclude the affected facts, then re-run the audit.

---

## Verify

```bash
make test  # runs tests/test_bundles.py, test_neighbourhoods.py, test_entailment_audit.py
make lint  # ruff check + ruff format --check
```

All must pass before Phase 3 (Block 0 pilot training) begins.

---

## Makefile targets (to be added)

```makefile
## P1-3: Build source bundles and leave-out manifests
build-bundles:
    uv run python scripts/build_bundles.py build \
      --facts data/controlled/facts.jsonl \
      --mentions data/tofu_derived/mentions.jsonl \
      --source $(TOFU_PATH) \
      --spec-root .factverify/spec \
      --out data/controlled/sources/ \
      --leaveout data/controlled/leaveout/ \
      --transforms data/tofu_derived/transformations.jsonl

## P1-5: Fill compositional and global neighbourhood stubs
build-neighbourhoods:
    uv run python scripts/build_neighbourhoods.py build \
      --facts data/controlled/facts.jsonl \
      --index data/controlled/sources/index.jsonl \
      --leaveout data/controlled/leaveout/ \
      --source $(TOFU_PATH) \
      --out data/controlled/neighbourhoods.jsonl

## P1-4: Entailment audit (requires ANTHROPIC_API_KEY for entailment screen)
entailment-audit:
    uv run python scripts/entailment_audit.py audit \
      --facts data/controlled/facts.jsonl \
      --leaveout data/controlled/leaveout/ \
      --index data/controlled/sources/index.jsonl \
      --spec-root .factverify/spec \
      --out results/entailment_audit.jsonl \
      --report reports/entailment_audit.md
```
