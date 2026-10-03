"""Fact case bundle loader and manifest writer (FV-SPEC-099)."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.artifacts.layout import LayoutRoots


class BundleError(Exception):
    """Raised when a fact bundle is incomplete or has digest mismatches."""


@dataclass(frozen=True)
class FactCaseManifest:
    fact_id: str
    split: str
    protocol_revision: str
    digests: dict[str, str]  # filename -> "sha256:hex"


_BUNDLE_FILES = (
    "contract.json", "sources.jsonl", "neighbourhood.jsonl", "prompts.jsonl"
)


def load_bundle(roots: LayoutRoots, fact_id: str) -> FactCaseManifest:
    """Load and validate a fact case bundle. Raises BundleError on any failure."""
    bundle_dir = roots.fact_dir(fact_id)
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.exists():
        raise BundleError(f"manifest.json missing in {bundle_dir}")

    try:
        manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise BundleError(f"cannot read manifest.json: {exc}") from exc

    required = ("fact_id", "split", "protocol_revision", "digests")
    for field in required:
        if field not in manifest_data:
            raise BundleError(f"manifest.json missing field: {field!r}")

    # Reject model selection in manifest
    if "model_config" in manifest_data or "model_config_id" in manifest_data:
        raise BundleError("manifest.json must not bind a model selection")

    digests: dict[str, str] = manifest_data["digests"]

    # Verify all sibling files exist and match their digests
    for filename in _BUNDLE_FILES:
        sibling = bundle_dir / filename
        if not sibling.exists():
            raise BundleError(f"bundle file missing: {filename}")
        if filename not in digests:
            raise BundleError(f"digest missing for {filename} in manifest")
        expected = digests[filename]
        actual = "sha256:" + _sha256_hex(sibling)
        if actual != expected:
            raise BundleError(
                f"digest mismatch for {filename}: expected {expected}, got {actual}"
            )

    return FactCaseManifest(
        fact_id=str(manifest_data["fact_id"]),
        split=str(manifest_data["split"]),
        protocol_revision=str(manifest_data["protocol_revision"]),
        digests=digests,
    )


def write_manifest(
    bundle_dir: Path,
    fact_id: str,
    split: str,
    protocol_revision: str,
) -> FactCaseManifest:
    """Compute digests of sibling files and write manifest.json."""
    digests: dict[str, str] = {}
    for filename in _BUNDLE_FILES:
        sibling = bundle_dir / filename
        if not sibling.exists():
            raise BundleError(f"cannot write manifest: {filename} is missing")
        digests[filename] = "sha256:" + _sha256_hex(sibling)

    manifest = FactCaseManifest(
        fact_id=fact_id,
        split=split,
        protocol_revision=protocol_revision,
        digests=digests,
    )
    manifest_path = bundle_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps({
            "fact_id": fact_id,
            "split": split,
            "protocol_revision": protocol_revision,
            "digests": digests,
        }, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return manifest


def _sha256_hex(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
