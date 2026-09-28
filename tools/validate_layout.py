"""Layout validator for FactVerify two-root namespace (FV-SPEC-097, 098, 100).

CLI interface:
  python -m tools.validate_layout [--spec-root PATH] [--internal-root PATH]
      [--strict] [--report PATH]

Exit codes:
  0 — pass
  1 — violations found
  2 — config error
"""
from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.artifacts.layout import LayoutError, LayoutRoots

_CREDENTIAL_PATTERNS = frozenset({
    ".key", ".pem", ".env", ".crt", ".p12", ".pfx",
    ".safetensors", ".bin", ".pt",
})

_CREDENTIAL_NAME_PATTERNS = frozenset({
    "credentials", "secret", "token", "password",
})

# Retired files that should no longer exist under spec root
_RETIRED_SPEC_FILES = frozenset({
    "spec/models.yaml",
    "models.yaml",
    "fact_contract.schema.json",
    "access_profile.md",
    "attacks.yaml",
    "margins.yaml",
    "preregistration.md",
    "witness_rule.md",
})

# Retired directories — no content from these should remain under spec root
_RETIRED_SPEC_DIRS = frozenset({
    "spec",
    "contracts",
    "access",
    "attacks",
    "closure",
    "decisions",
    "exposure",
    "margins",
    "milestones",
    "witness",
})


def _is_credential_blob(path: Path) -> bool:
    """Return True if this path looks like a credential or large binary blob."""
    suffix = path.suffix.lower()
    if suffix in _CREDENTIAL_PATTERNS:
        return True
    stem = path.stem.lower()
    for pattern in _CREDENTIAL_NAME_PATTERNS:
        if pattern in stem:
            return True
    return False


def validate_layout(
    spec_root: Path | None = None,
    internal_root: Path | None = None,
    *,
    strict: bool = True,
) -> dict[str, Any]:
    """Validate the two-root namespace. Returns a report dict."""
    violations: list[dict[str, str]] = []

    # 1. Resolve roots — fails if identical or nested
    try:
        roots = LayoutRoots.resolve(spec_root=spec_root, internal_root=internal_root)
    except LayoutError as exc:
        return {
            "timestamp_utc": datetime.now(UTC).isoformat(),
            "spec_root": str(spec_root),
            "internal_root": str(internal_root),
            "overall": "fail",
            "violations": [
                {
                    "check": "root_separation",
                    "path": "",
                    "artifact_class": "",
                    "message": f"Root validation failed: {exc}",
                }
            ],
        }

    resolved_spec = roots.spec_root
    resolved_internal = roots.internal_root

    # 2. Check for retired files (FV-SPEC-098 §3)
    for retired_rel in _RETIRED_SPEC_FILES:
        retired_path = resolved_spec / retired_rel
        if retired_path.exists():
            violations.append({
                "check": "retired_file",
                "path": str(retired_path),
                "artifact_class": "",
                "message": (
                    f"Retired file found: {retired_rel}. "
                    f"This file has been consolidated or superseded. "
                    f"See FV-SPEC-098 and FV-SPEC-111."
                ),
            })

    # 3. Check for retired directories (FV-SPEC-111)
    for retired_dir in _RETIRED_SPEC_DIRS:
        retired_path = resolved_spec / retired_dir
        if retired_path.exists() and retired_path.is_dir():
            violations.append({
                "check": "retired_directory",
                "path": str(retired_path),
                "artifact_class": retired_dir,
                "message": (
                    f"Retired directory found: {retired_dir}/. "
                    f"Legacy directories must not remain under the frozen spec root. "
                    f"See FV-SPEC-111."
                ),
            })

    # 4. Scan spec_root for runtime artifacts (FV-SPEC-097)
    if resolved_spec.exists():
        for path in sorted(resolved_spec.rglob("*")):
            if not path.is_file():
                continue

            # Check for credential/binary blobs
            if _is_credential_blob(path):
                violations.append({
                    "check": "credential_blob",
                    "path": str(path),
                    "artifact_class": "",
                    "message": (
                        f"Credential or binary blob found under frozen spec root: {path}. "
                        "These must not appear in the spec root."
                    ),
                })
                continue

            # Check if the file is under a retired directory
            rel = path.relative_to(resolved_spec)
            if rel.parts and rel.parts[0] in _RETIRED_SPEC_DIRS:
                # Already flagged at directory level; skip individual files
                continue

            # Classify the path — LayoutError means it's not in the allowlist
            try:
                artifact_class = roots.classify(path)
            except LayoutError:
                # Check for known runtime subdirectories
                runtime_dirs = {
                    "runs", "checkpoints", "evidence", "results",
                    "reports", "cache", "tmp", "deviations",
                }
                if rel.parts and rel.parts[0] in runtime_dirs:
                    violations.append({
                        "check": "frozen_namespace_allowlist",
                        "path": str(path),
                        "artifact_class": rel.parts[0],
                        "message": (
                            f"Runtime artifact directory '{rel.parts[0]}' found under frozen spec root. "
                            "Runtime artifacts must go under the internal root."
                        ),
                    })
                continue

            # If it classified as a runtime class, it's a violation
            if roots.is_runtime_class(artifact_class):
                violations.append({
                    "check": "frozen_namespace_allowlist",
                    "path": str(path),
                    "artifact_class": artifact_class.value,
                    "message": (
                        f"Runtime artifact class '{artifact_class.value}' found under frozen spec root. "
                        "Runtime artifacts must go under the internal root."
                    ),
                })

    overall = "fail" if violations else "pass"

    return {
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "spec_root": str(resolved_spec),
        "internal_root": str(resolved_internal),
        "overall": overall,
        "violations": violations,
    }


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m tools.validate_layout",
        description="Validate FactVerify two-root namespace.",
    )
    parser.add_argument(
        "--spec-root",
        type=Path,
        default=None,
        help="Frozen spec root (default: FACTVERIFY_SPEC_ROOT env or .factverify)",
    )
    parser.add_argument(
        "--internal-root",
        type=Path,
        default=None,
        help="Runtime internal root (default: FACTVERIFY_INTERNAL_ROOT env or .factverify_internal)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        default=True,
        help="Strict mode (default: on)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Path to write the JSON report",
    )

    args = parser.parse_args(argv)

    report = validate_layout(
        spec_root=args.spec_root,
        internal_root=args.internal_root,
        strict=args.strict,
    )

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )

    overall = report["overall"]
    n_violations = len(report["violations"])

    if n_violations > 0:
        print(f"Layout validation: {overall}. {n_violations} violation(s):", flush=True)
        for v in report["violations"]:
            print(f"  [{v['check']}] {v['path']}: {v['message']}", flush=True)
    else:
        print(f"Layout validation: {overall}.", flush=True)

    return 0 if overall == "pass" else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
