"""Run preflight guard (FV-SPEC-104, FV-SPEC-110)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.artifacts.layout import LayoutRoots
from src.data.fact_bundle import BundleError, load_bundle
from src.models.spec import (
    ModelPolicy,
    load_model_configuration,
    resolve_role,
)


class PreflightError(Exception):
    """Raised when any preflight check fails. No run dir or ledger row is written."""


@dataclass(frozen=True)
class PreflightResult:
    spec_root_digest: str
    fact_manifest_digest: str
    model_config_id: str
    model_config_digest: str
    model_identity_hash: str
    model_revision: str
    fact_id: str
    protocol_revision: str
    config_hash: str


def run_preflight(
    roots: LayoutRoots,
    fact_id: str,
    model_config_path: Path,
    policy: ModelPolicy | None,
    role: str,
) -> PreflightResult:
    """Verify frozen inputs before opening any run. Raises PreflightError on failure."""

    # 1. Verify FREEZE.json exists and content_digests match
    freeze_path = roots.spec_root / "FREEZE.json"
    if not freeze_path.exists():
        raise PreflightError(
            f"FREEZE.json not found at {freeze_path}. "
            "Run tools/freeze.py --execute to create it."
        )

    try:
        freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise PreflightError(f"Cannot read FREEZE.json: {exc}") from exc

    content_digests: dict[str, str] = freeze.get("content_digests", {})
    for rel_path, expected_digest in content_digests.items():
        artifact = (
            roots.spec_root / rel_path
            if not Path(rel_path).is_absolute()
            else Path(rel_path)
        )
        if not artifact.exists():
            raise PreflightError(f"Normative artifact missing: {artifact}")
        actual = "sha256:" + hashlib.sha256(artifact.read_bytes()).hexdigest()
        if actual != expected_digest:
            raise PreflightError(
                f"Digest mismatch for {rel_path}: "
                f"expected {expected_digest}, got {actual}"
            )

    spec_root_digest = "sha256:" + hashlib.sha256(freeze_path.read_bytes()).hexdigest()

    # 2. Load and validate fact bundle
    try:
        bundle = load_bundle(roots, fact_id)
    except BundleError as exc:
        raise PreflightError(f"Fact bundle for {fact_id!r} failed: {exc}") from exc

    fact_manifest_digest = _compute_bundle_digest(roots, fact_id)

    # 3. Load and resolve model config
    if not model_config_path.exists():
        raise PreflightError(f"Model config not found: {model_config_path}")

    try:
        config = load_model_configuration(model_config_path)
    except Exception as exc:
        raise PreflightError(
            f"Cannot load model config {model_config_path}: {exc}"
        ) from exc

    if policy is not None:
        try:
            resolved = resolve_role(policy, config, role)
        except Exception as exc:
            raise PreflightError(f"Role {role!r} resolution failed: {exc}") from exc

        model_config_digest = (
            "sha256:" + hashlib.sha256(model_config_path.read_bytes()).hexdigest()
        )
        config_hash = model_config_digest

        return PreflightResult(
            spec_root_digest=spec_root_digest,
            fact_manifest_digest=fact_manifest_digest,
            model_config_id=resolved.config_id,
            model_config_digest=model_config_digest,
            model_identity_hash=resolved.model_revision,
            model_revision=resolved.model_revision,
            fact_id=bundle.fact_id,
            protocol_revision=bundle.protocol_revision,
            config_hash=config_hash,
        )
    else:
        # No policy: use config_id directly from config
        model_config_digest = (
            "sha256:" + hashlib.sha256(model_config_path.read_bytes()).hexdigest()
        )
        config_hash = model_config_digest

        return PreflightResult(
            spec_root_digest=spec_root_digest,
            fact_manifest_digest=fact_manifest_digest,
            model_config_id=config.config_id,
            model_config_digest=model_config_digest,
            model_identity_hash="",
            model_revision="",
            fact_id=bundle.fact_id,
            protocol_revision=bundle.protocol_revision,
            config_hash=config_hash,
        )


def _compute_bundle_digest(roots: LayoutRoots, fact_id: str) -> str:
    bundle_dir = roots.fact_dir(fact_id)
    manifest_path = bundle_dir / "manifest.json"
    return "sha256:" + hashlib.sha256(manifest_path.read_bytes()).hexdigest()
