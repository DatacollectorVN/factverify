# Quickstart: FV-SPEC — Artifact Namespace Refactor

**Feature**: `20261002-111741-artifact-namespace-refactor`
**Date**: 2026-10-02

---

## Overview

This refactor restructures FactVerify's storage into two namespaces:
- **`.factverify/`** — frozen inputs (spec, fact cases). Immutable after freeze.
- **`.factverify_internal/`** — runtime outputs (runs, ledger, cache). Append-only.

It also makes FactVerify-native IDs the canonical identity of every fact, entity and relation (removing Wikidata as a mandatory dependency).

---

## Developer workflow after cutover

### 1. Validate the layout

```bash
# Check that both roots are clean
uv run python -m tools.validate_layout

# With explicit roots (for CI)
uv run python -m tools.validate_layout \
  --spec-root .factverify/ \
  --internal-root .factverify_internal/ \
  --report reports/layout-check.json
```

### 2. Run the migration (dry-run first, always)

```bash
# Dry-run: see what would change without writing
uv run python -m tools.migrate_artifacts \
  --dry-run \
  --report reports/migration-dry-run.json

# Execute after reviewing the report
uv run python -m tools.migrate_artifacts \
  --execute \
  --report reports/migration-execute.json
```

### 3. Open a run with preflight guard

```python
from pathlib import Path
from src.artifacts.layout import LayoutRoots
from src.artifacts.preflight import run_preflight
from src.models.spec import load_model_policy, load_model_configuration, resolve_role

roots = LayoutRoots.resolve()
policy = load_model_policy(roots.spec_root)
config = load_model_configuration(Path("config/models/block0-debug-pythia-410m.yaml"))
role = resolve_role(policy, config, "controlled_fact_base")

result = run_preflight(
    roots=roots,
    fact_id="factverify:fact:hanoi_capital_of_vietnam",
    model_config_path=Path("config/models/block0-debug-pythia-410m.yaml"),
    policy=policy,
    role="controlled_fact_base",
)
# result.run_id, result.config_hash, etc. are ready to write to run manifest
```

### 4. Write a contract with FactVerify-native IDs

```json
{
  "schema_version": "1.1.0",
  "contract_id": "factverify:contract:hanoi_capital_of_vietnam:v1",
  "fact_id": "factverify:fact:hanoi_capital_of_vietnam",
  "triple": {
    "subject": {
      "id": "factverify:entity:hanoi",
      "label": "Hà Nội",
      "external_refs": [{"scheme": "wikidata", "external_id": "Q1858"}]
    },
    "relation": {
      "id": "factverify:relation:capital-of",
      "label": "capital of",
      "external_refs": [{"scheme": "wikidata", "external_id": "P1376"}]
    },
    "object": {
      "id": "factverify:entity:vietnam",
      "label": "Vietnam",
      "external_refs": [{"scheme": "wikidata", "external_id": "Q881"}]
    }
  }
}
```

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `FACTVERIFY_SPEC_ROOT` | `.factverify/` | Frozen spec root path |
| `FACTVERIFY_INTERNAL_ROOT` | `.factverify_internal/` | Runtime root path |

Override at runtime via `--spec-root` / `--internal-root` CLI flags on all entry points.

---

## What changed from the old layout

| Old path | New path | Notes |
|---|---|---|
| `.factverify/spec/fact_contract.schema.json` | `.factverify/fact.schema.json` | Schema updated: native IDs only, `external_refs[]` added |
| `.factverify/spec/closure_templates.yaml` | `.factverify/templates.yaml` | Rename only |
| `.factverify/spec/model_policy.yaml` | `.factverify/model_policy.yaml` | Move up one level |
| `.factverify/spec/attacks.yaml` + others | `.factverify/protocol.yaml` | Consolidated (see research.md Finding 6) |
| `.factverify/contracts/*.json` | `.factverify/facts/<fact_id>/contract.json` | Identity migration + bundle structure |
| `.factverify/spec/models.yaml` | _(deleted)_ | Replaced by `config/models/*.yaml` selections |
| `ledger.sqlite` _(various locations)_ | `.factverify_internal/ledger.sqlite` | Single authoritative location |
| `results/`, `reports/` _(repo root)_ | `.factverify_internal/results/`, `reports/` | Runtime-output root |
