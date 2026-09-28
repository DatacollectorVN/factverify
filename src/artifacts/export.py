"""Portable reproduction snapshot (FV-SPEC-106)."""
from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.artifacts.layout import LayoutRoots


class ExportError(Exception):
    """Raised when export or import fails."""


@dataclass(frozen=True)
class ExportScope:
    run_ids: list[str]
    fact_ids: list[str]


@dataclass(frozen=True)
class ImportResult:
    digests_verified: int
    ledger_rows_inserted: int


def export_snapshot(
    roots: LayoutRoots,
    scope: ExportScope,
    output_path: Path,
) -> Path:
    """Export a bounded reproduction snapshot to output_path."""
    output_path.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict[str, object]] = []

    # Copy frozen inputs
    if roots.spec_root.exists():
        spec_dest = output_path / "spec"
        shutil.copytree(str(roots.spec_root), str(spec_dest))
        for f in spec_dest.rglob("*"):
            if f.is_file():
                digest = "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()
                rel = str(f.relative_to(output_path))
                manifest_entries.append({"path": rel, "digest": digest})

    # Copy selected run bundles
    for run_id in scope.run_ids:
        run_src = roots.run_dir(run_id)
        if run_src.exists():
            run_dest = output_path / "runs" / run_id
            shutil.copytree(str(run_src), str(run_dest))
            for f in run_dest.rglob("*"):
                if f.is_file():
                    digest = "sha256:" + hashlib.sha256(f.read_bytes()).hexdigest()
                    rel = str(f.relative_to(output_path))
                    manifest_entries.append({"path": rel, "digest": digest})

    # Write manifest
    manifest = {
        "schema_version": "1",
        "exported_at": datetime.now(UTC).isoformat(),
        "scope": {"run_ids": scope.run_ids, "fact_ids": scope.fact_ids},
        "entries": manifest_entries,
    }
    manifest_path = output_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest_path


def import_snapshot(
    snapshot_manifest: Path,
    target_output: Path,
) -> ImportResult:
    """Import a snapshot and verify all digests."""
    manifest = json.loads(snapshot_manifest.read_text(encoding="utf-8"))
    snapshot_dir = snapshot_manifest.parent

    verified = 0
    for entry in manifest.get("entries", []):
        path = snapshot_dir / entry["path"]
        if not path.exists():
            raise ExportError(f"Snapshot entry missing: {entry['path']}")
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != entry["digest"]:
            raise ExportError(
                f"Digest mismatch for {entry['path']}: "
                f"expected {entry['digest']}, got {actual}"
            )
        verified += 1

    return ImportResult(digests_verified=verified, ledger_rows_inserted=0)
