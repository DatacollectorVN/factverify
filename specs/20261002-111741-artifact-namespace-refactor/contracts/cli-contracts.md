# CLI Contracts: FV-SPEC — Artifact Namespace Refactor

**Feature**: `20261002-111741-artifact-namespace-refactor`
**Date**: 2026-10-02

---

## `tools/validate_layout.py`

Validates both namespace roots against the declared allowlist.

```
Usage: python -m tools.validate_layout [OPTIONS]

Options:
  --spec-root PATH        Frozen spec root (default: .factverify/)
  --internal-root PATH    Runtime root (default: .factverify_internal/)
  --strict                Fail on any allowlist violation (default: on)
  --report PATH           Write JSON report to this path
  --help

Exit codes:
  0  All checks pass
  1  One or more violations found
  2  Configuration error (bad paths, missing roots)
```

**Checks performed**:
1. Two roots are distinct non-overlapping absolute paths (FV-SPEC-096).
2. No runtime artifact class under `spec_root` (FV-SPEC-097).
3. No `.factverify/spec/models.yaml` or `.factverify/models.yaml` present (FV-SPEC-098 §3).
4. Every path under `spec_root` is in the frozen-input allowlist (FV-SPEC-097).
5. No credentials or binary blobs under either root (C-6).

**Report format** (JSON):
```json
{
  "timestamp_utc": "...",
  "spec_root": "...",
  "internal_root": "...",
  "overall": "pass|fail",
  "violations": [
    {
      "check": "frozen_namespace_allowlist",
      "path": ".factverify/runs/...",
      "artifact_class": "run_manifest",
      "message": "runtime artifact class 'run_manifest' found under frozen spec root"
    }
  ]
}
```

---

## `tools/migrate_artifacts.py`

Migrates the legacy `.factverify/` tree to the new two-root layout.

```
Usage: python -m tools.migrate_artifacts [OPTIONS]

Options:
  --source PATH           Source .factverify/ root (default: .factverify/)
  --spec-root PATH        Target frozen spec root (default: .factverify/)
  --internal-root PATH    Target runtime root (default: .factverify_internal/)
  --dry-run               Emit mapping without writing (default)
  --execute               Run migration after confirming dry-run passes
  --report PATH           Write migration report JSON to this path (required)
  --help

Exit codes:
  0  Dry-run: mapping complete with zero unresolved items
     Execute: migration complete
  1  Dry-run: unresolved or colliding items found
     Execute: migration failed (source tree unchanged)
  2  Configuration error
```

**Guarantees**:
- Dry-run makes zero writes to disk.
- Execute is fail-closed: any error leaves the source tree in its pre-migration state.
- All Wikidata-backed fact triples receive FactVerify-native canonical IDs; Q/P references move to `external_refs[]`.
- `--report` is required in both modes.

---

## `src/artifacts/layout.py` (Python API)

```python
from src.artifacts.layout import LayoutRoots, ArtifactClass

# Resolve roots from environment / explicit overrides
roots = LayoutRoots.resolve(
    spec_root: Path | None = None,     # overrides FACTVERIFY_SPEC_ROOT
    internal_root: Path | None = None, # overrides FACTVERIFY_INTERNAL_ROOT
)

# Validate placement of a path
roots.assert_spec_path(path: Path) -> None        # raises if not under spec_root
roots.assert_internal_path(path: Path) -> None    # raises if not under internal_root
roots.classify(path: Path) -> ArtifactClass       # raises if unrecognized

# Resolve standard paths
roots.fact_dir(fact_id: str) -> Path              # <spec_root>/facts/<fact_id>/
roots.run_dir(run_id: str) -> Path                # <internal_root>/runs/<run_id>/
roots.ledger_path() -> Path                       # <internal_root>/ledger.sqlite
```

---

## `src/artifacts/preflight.py` (Python API)

```python
from src.artifacts.preflight import run_preflight, PreflightResult

result: PreflightResult = run_preflight(
    roots: LayoutRoots,
    fact_id: str,
    model_config_path: Path,       # explicit versioned config/models/*.yaml
    policy: ModelPolicy,           # loaded from <spec_root>/model_policy.yaml
    role: str,
)
# Raises PreflightError if any check fails (no run dir or ledger row committed)
# On success: returns PreflightResult with resolved hashes ready to write to run manifest
```

**Checks**:
1. `FREEZE.json` present and all content digests match on-disk files.
2. Fact case bundle manifest present with all digests matching sibling files.
3. Model config path exists, parses, role is not pending, all digests present.
4. Role is permitted by `model_policy.yaml`.

---

## `src/artifacts/store.py` (Python API)

```python
from src.artifacts.store import ArtifactStore

store = ArtifactStore(roots: LayoutRoots, ledger: sqlite3.Connection)

# Open a write transaction; registers artifact in ledger before returning path
with store.write(
    artifact_class: ArtifactClass,
    run_id: str,
    filename: str,
) as path:
    # write to path; transaction committed on __exit__
    ...

# Register an external blob
store.register_external_blob(
    ref: ExternalBlobRef,
    run_id: str,
) -> None

# Resolve a ledgered artifact for reading
store.resolve(artifact_class: ArtifactClass, digest: str) -> Path
# Raises UnledgeredArtifactError if not registered
```

---

## `src/artifacts/export.py` (Python API)

```python
from src.artifacts.export import export_snapshot, import_snapshot

export_snapshot(
    roots: LayoutRoots,
    ledger: sqlite3.Connection,
    scope: ExportScope,            # selected run IDs, fact IDs, date range
    output_path: Path,             # directory to write the snapshot into
) -> Path                          # path to manifest.json inside output

import_snapshot(
    snapshot_manifest: Path,       # path to exported manifest.json
    target_roots: LayoutRoots,     # destination layout
    target_ledger: sqlite3.Connection,
) -> ImportResult
```
