"""Run bundle management (FV-SPEC-102)."""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.artifacts.layout import LayoutRoots
from src.artifacts.preflight import PreflightResult


class RunBundleError(Exception):
    """Raised when a run bundle is invalid or integrity fails."""


@dataclass
class RunManifest:
    run_id: str
    fact_id: str
    role: str
    method: str
    seed: int
    split: str
    protocol_revision: str
    code_commit: str
    model_config_id: str
    model_config_digest: str
    model_identity_hash: str
    config_hash: str
    opened_at: str
    status: str  # "open" | "finalized" | "failed"


def open_run(
    roots: LayoutRoots,
    preflight: PreflightResult,
    role: str,
    method: str,
    seed: int,
    split: str,
    code_commit: str,
    model_config_path: Path,
) -> tuple[str, Path]:
    """Create run directory and write manifest. Returns (run_id, run_dir)."""
    run_id = uuid.uuid4().hex
    run_dir = roots.run_dir(run_id)
    run_dir.mkdir(parents=True, exist_ok=False)

    manifest = RunManifest(
        run_id=run_id,
        fact_id=preflight.fact_id,
        role=role,
        method=method,
        seed=seed,
        split=split,
        protocol_revision=preflight.protocol_revision,
        code_commit=code_commit,
        model_config_id=preflight.model_config_id,
        model_config_digest=preflight.model_config_digest,
        model_identity_hash=preflight.model_identity_hash,
        config_hash=preflight.config_hash,
        opened_at=datetime.now(UTC).isoformat(),
        status="open",
    )

    # Write frozen config copy
    frozen_config = run_dir / "config.yaml"
    frozen_config.write_bytes(model_config_path.read_bytes())

    # Write manifest
    _write_manifest(run_dir / "manifest.json", manifest)

    return run_id, run_dir


def finalize_run(run_dir: Path) -> dict[str, str]:
    """Compute artifact digests and write artifacts.json. Returns digest map."""
    # Update manifest status first so the digest reflects the final state
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_data["status"] = "finalized"
        manifest_path.write_text(
            json.dumps(manifest_data, indent=2) + "\n",
            encoding="utf-8",
        )

    # Now compute digests of all files in their final state
    artifact_files = list(run_dir.iterdir())
    digests: dict[str, str] = {}
    for artifact in artifact_files:
        if artifact.name == "artifacts.json":
            continue
        if artifact.is_file():
            digest = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
            digests[artifact.name] = digest

    artifacts_path = run_dir / "artifacts.json"
    artifacts_path.write_text(
        json.dumps(digests, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    return digests


def verify_run_integrity(run_dir: Path) -> list[str]:
    """Verify all files match their recorded digests. Returns list of failures."""
    artifacts_path = run_dir / "artifacts.json"
    if not artifacts_path.exists():
        return ["artifacts.json missing — run not finalized"]

    recorded: dict[str, str] = json.loads(artifacts_path.read_text(encoding="utf-8"))
    failures = []
    for filename, expected in recorded.items():
        path = run_dir / filename
        if not path.exists():
            failures.append(f"{filename}: missing")
            continue
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            failures.append(f"{filename}: expected {expected}, got {actual}")
    return failures


def _write_manifest(path: Path, manifest: RunManifest) -> None:
    data = {
        "run_id": manifest.run_id,
        "fact_id": manifest.fact_id,
        "role": manifest.role,
        "method": manifest.method,
        "seed": manifest.seed,
        "split": manifest.split,
        "protocol_revision": manifest.protocol_revision,
        "code_commit": manifest.code_commit,
        "model_config_id": manifest.model_config_id,
        "model_config_digest": manifest.model_config_digest,
        "model_identity_hash": manifest.model_identity_hash,
        "config_hash": manifest.config_hash,
        "opened_at": manifest.opened_at,
        "status": manifest.status,
    }
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
