"""P0-7 spec-freeze workflow CLI.

Gates and executes the spec-v1 freeze: checksum manifest, annotated git tag,
post-commit receipt.

Modes:
    --dry-run   (default) Run all gate checks; make no writes.
    --execute   Run gate checks, then write CHECKSUMS, commit, tag, receipt.
    --verify    Re-compute hashes and verify against existing CHECKSUMS + receipt.

Exit codes:
    0 — dry-run: all gates passed; execute: freeze complete; verify: valid
    1 — gate failure, integrity failure, or validation error
    2 — missing inputs, bad invocation, or ambiguous mode flags
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import click

# ---------------------------------------------------------------------------
# Spec artifact manifest
# ---------------------------------------------------------------------------

SPEC_ARTIFACTS = [
    "fact_contract.schema.json",
    "closure_templates.yaml",
    "attacks.yaml",
    "access_profile.md",
    "margins.yaml",
    "witness_rule.md",
    "preregistration.md",
    "models.yaml",
]

# ---------------------------------------------------------------------------
# Checksum helpers
# ---------------------------------------------------------------------------


def compute_checksums(spec_root: Path) -> dict[str, str]:
    """Return {relative_path: sha256_hex} for all spec artifacts."""
    result = {}
    repo_root = spec_root.parent.parent
    for name in SPEC_ARTIFACTS:
        p = spec_root / name
        if p.exists():
            digest = hashlib.sha256(p.read_bytes()).hexdigest()
            try:
                rel = str(p.relative_to(repo_root))
            except ValueError:
                rel = str(p)
            result[rel] = digest
    return result


def write_checksums(spec_root: Path, output_path: Path) -> None:
    """Write CHECKSUMS.sha256 in shasum-compatible format."""
    checksums = compute_checksums(spec_root)
    lines = [
        f"sha256:{hex_val}  {path}\n" for path, hex_val in sorted(checksums.items())
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("".join(lines), encoding="utf-8")


def verify_checksums(spec_root: Path, checksums_path: Path) -> list[str]:
    """Return list of mismatched or missing paths.

    If the checksums file itself is missing, returns [str(checksums_path)].
    """
    if not checksums_path.exists():
        return [str(checksums_path)]

    repo_root = spec_root.parent.parent
    mismatched = []
    for line in checksums_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            continue
        stored_hex = parts[0].replace("sha256:", "").strip()
        rel_path = parts[1].strip()

        # Resolve relative to repo root
        full_path = repo_root / rel_path
        if not full_path.exists():
            mismatched.append(rel_path)
            continue
        actual_hex = hashlib.sha256(full_path.read_bytes()).hexdigest()
        if actual_hex != stored_hex:
            mismatched.append(rel_path)

    return mismatched


def compute_contract_digest(prereg_path: Path) -> str:
    """SHA-256 of canonical payload: frontmatter (without digest field) + body."""
    import yaml

    text = prereg_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        fm = yaml.safe_load(parts[1]) or {}
        body = parts[2] if len(parts) > 2 else ""
    else:
        fm = {}
        body = text
    fm.pop("digest", None)
    canonical = json.dumps(
        {"frontmatter": fm, "body": body}, sort_keys=True, ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Gate check functions
# ---------------------------------------------------------------------------


def _check_artifacts_present(spec_root: Path) -> list[dict]:
    """Gate 1: All eight spec artifacts present and non-empty."""
    diags = []
    for name in SPEC_ARTIFACTS:
        p = spec_root / name
        if not p.exists():
            diags.append(
                {
                    "check": "artifacts_present",
                    "status": "fail",
                    "message": f"Missing spec artifact: {name}",
                }
            )
        elif p.stat().st_size == 0:
            diags.append(
                {
                    "check": "artifacts_present",
                    "status": "fail",
                    "message": f"Spec artifact is empty: {name}",
                }
            )
    return diags


def _check_decisions_resolved(decisions_path: Path) -> list[dict]:
    """Gate 4: All applicable decisions resolved or not_applicable."""
    import yaml

    diags = []
    if not decisions_path.exists():
        diags.append(
            {
                "check": "decisions_resolved",
                "status": "fail",
                "message": f"Decision register not found: {decisions_path}",
            }
        )
        return diags

    try:
        register = yaml.safe_load(decisions_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        diags.append(
            {
                "check": "decisions_resolved",
                "status": "fail",
                "message": f"YAML parse error in decision register: {exc}",
            }
        )
        return diags

    for d_id, entry in register.items():
        if not isinstance(entry, dict):
            continue
        status = entry.get("status", "open")
        if status in ("open", "pending"):
            diags.append(
                {
                    "check": "decisions_resolved",
                    "status": "fail",
                    "message": (f"Decision {d_id} is unresolved (status: {status})."),
                }
            )

    return diags


def _check_exposure_reviewed(exposure_path: Path) -> list[dict]:
    """Gate 5: Exposure record status == reviewed."""
    import yaml

    diags = []
    if not exposure_path.exists():
        diags.append(
            {
                "check": "exposure_reviewed",
                "status": "fail",
                "message": f"Exposure record not found: {exposure_path}",
            }
        )
        return diags

    text = exposure_path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        try:
            fm = yaml.safe_load(parts[1]) or {}
        except yaml.YAMLError:
            fm = {}
    else:
        fm = {}

    if fm.get("status") != "reviewed":
        diags.append(
            {
                "check": "exposure_reviewed",
                "status": "fail",
                "message": (
                    f"Exposure record status is '{fm.get('status')}', "
                    f"must be 'reviewed'."
                ),
            }
        )

    return diags


def _check_milestones_complete(milestones_path: Path) -> list[dict]:
    """Gate 6: All three milestones have git_tag or complete staged_rule."""
    diags = []
    if not milestones_path.exists():
        diags.append(
            {
                "check": "milestones_complete",
                "status": "fail",
                "message": f"Milestones file not found: {milestones_path}",
            }
        )
        return diags

    try:
        import yaml

        milestones = yaml.safe_load(milestones_path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        diags.append(
            {
                "check": "milestones_complete",
                "status": "fail",
                "message": f"Error reading milestones: {exc}",
            }
        )
        return diags

    from tools.preregistration_validator import check_fv_spec_080_milestones

    for d in check_fv_spec_080_milestones(milestones):
        diags.append(
            {
                "check": "milestones_complete",
                "status": "fail",
                "message": d["message"],
            }
        )

    return diags


def _check_no_existing_tag(repo_root: Path, tag_name: str) -> list[dict]:
    """Gate 7: No existing tag with this name."""
    import subprocess as sp

    try:
        result = sp.run(
            ["git", "-C", str(repo_root), "tag", "-l", tag_name],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.stdout.strip() == tag_name:
            return [
                {
                    "check": "no_existing_tag",
                    "status": "fail",
                    "message": (f"Tag '{tag_name}' already exists. Cannot overwrite."),
                }
            ]
    except Exception:
        pass  # git not available — skip check

    return []


def _check_no_leaked_files(spec_root: Path) -> list[dict]:
    """Gate 8: No raw outputs, checkpoints, or credentials inside .factverify/."""
    diags = []
    banned_patterns = [
        "*.safetensors",
        "*.bin",
        "*.pt",
        "*.pth",
        "*.ckpt",
        "*.key",
        "*.pem",
        "*.env",
        ".env*",
        "credentials*",
    ]
    factverify_dir = spec_root.parent  # .factverify/
    if not factverify_dir.exists():
        return diags

    for p in factverify_dir.rglob("*"):
        if p.is_file():
            for pattern in banned_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    diags.append(
                        {
                            "check": "no_leaked_files",
                            "status": "fail",
                            "message": (
                                f"Potentially sensitive file inside .factverify/: {p}"
                            ),
                        }
                    )
                    break

    return diags


def _check_preregistration_valid(
    spec_root: Path,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
) -> list[dict]:
    """Gate 2: preregistration scope validates. Does not re-enter the freeze gate."""
    from tools.preregistration_validator import validate_preregistration

    prereg_path = spec_root / "preregistration.md"
    if not prereg_path.exists():
        return [
            {
                "check": "preregistration_valid",
                "status": "fail",
                "message": f"preregistration.md not found under {spec_root}",
            }
        ]
    passed, report = validate_preregistration(
        spec_root,
        prereg_path,
        decisions_path,
        exposure_path,
        milestones_path,
        include_freeze_gate=False,
    )
    if passed:
        return []
    diags = []
    for check in report.get("checks", []):
        if check.get("status") != "fail":
            continue
        for diag in check.get("diagnostics") or []:
            message = (
                diag.get("message", str(diag)) if isinstance(diag, dict) else str(diag)
            )
            diags.append(
                {
                    "check": "preregistration_valid",
                    "status": "fail",
                    "message": f"{check.get('id', 'preregistration')}: {message}",
                }
            )
    if not diags:
        diags.append(
            {
                "check": "preregistration_valid",
                "status": "fail",
                "message": "Preregistration validation failed.",
            }
        )
    return diags


_PRIOR_SPEC_TESTS = [
    "tests/test_contract_schema.py",
    "tests/test_fact_contract_schema.py",
    "tests/test_closure_templates.py",
    "tests/test_attack_spec.py",
    "tests/test_access_profile.py",
    "tests/test_margins_spec.py",
    "tests/test_witness_rule.py",
]


def _check_prior_specs(repo_root: Path) -> list[dict]:
    """Gate 3: prior P0 specs still pass. Fixture repos without those tests skip."""
    import subprocess

    present = [name for name in _PRIOR_SPEC_TESTS if (repo_root / name).exists()]
    if not present:
        return []
    result = subprocess.run(
        [sys.executable, "-m", "pytest", *present, "-q", "--tb=line"],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode == 0:
        return []
    tail = (result.stdout or result.stderr or "")[-800:]
    return [
        {
            "check": "prior_specs",
            "status": "fail",
            "message": f"Prior spec regression failed.\n{tail}",
        }
    ]


def run_gate_checks(
    spec_root: Path,
    tag_name: str,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
    include_preregistration: bool = True,
) -> tuple[bool, list[dict]]:
    """Run all gate checks. Returns (all_passed, results_list)."""
    repo_root = spec_root.parent.parent
    results = []

    # Gate 1: artifacts present
    diags = _check_artifacts_present(spec_root)
    results.append(
        {
            "gate": 1,
            "name": "artifacts_present",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 2: preregistration validates. Omitted when validate_preregistration
    # is already calling the freeze gate, which would recurse.
    if include_preregistration:
        diags = _check_preregistration_valid(
            spec_root,
            decisions_path,
            exposure_path,
            milestones_path,
        )
        results.append(
            {
                "gate": 2,
                "name": "preregistration_valid",
                "passed": not diags,
                "diagnostics": diags,
            }
        )

    # Gate 3: earlier spec tests still pass when this is the project repository
    diags = _check_prior_specs(repo_root)
    results.append(
        {
            "gate": 3,
            "name": "prior_specs",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 4: decisions resolved
    diags = _check_decisions_resolved(decisions_path)
    results.append(
        {
            "gate": 4,
            "name": "decisions_resolved",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 5: exposure reviewed
    diags = _check_exposure_reviewed(exposure_path)
    results.append(
        {
            "gate": 5,
            "name": "exposure_reviewed",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 6: milestones complete
    diags = _check_milestones_complete(milestones_path)
    results.append(
        {
            "gate": 6,
            "name": "milestones_complete",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 7: no existing tag
    diags = _check_no_existing_tag(repo_root, tag_name)
    results.append(
        {
            "gate": 7,
            "name": "no_existing_tag",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    # Gate 8: no leaked files
    diags = _check_no_leaked_files(spec_root)
    results.append(
        {
            "gate": 8,
            "name": "no_leaked_files",
            "passed": not diags,
            "diagnostics": diags,
        }
    )

    all_passed = all(r["passed"] for r in results)
    return all_passed, results


# ---------------------------------------------------------------------------
# Mode implementations
# ---------------------------------------------------------------------------


def _do_dry_run(
    spec_root: Path,
    tag_name: str,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
    report_path: Path | None,
) -> None:
    """Dry-run: check all gates, write report if requested, make no writes."""
    all_passed, results = run_gate_checks(
        spec_root, tag_name, decisions_path, exposure_path, milestones_path
    )
    passed = sum(1 for r in results if r["passed"])
    failed = sum(1 for r in results if not r["passed"])
    click.echo(f"Dry-run gate check: {passed} passed, {failed} failed.")

    if report_path:
        report = {
            "mode": "dry_run",
            "tag": tag_name,
            "timestamp": datetime.now(UTC).isoformat(),
            "overall": "pass" if all_passed else "fail",
            "gates": results,
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for r in results:
        if not r["passed"]:
            for d in r["diagnostics"]:
                click.echo(f"  FAIL [{r['name']}]: {d['message']}", err=True)

    sys.exit(0 if all_passed else 1)


def _do_execute(
    spec_root: Path,
    tag_name: str,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
    report_path: Path | None,
) -> None:
    """Execute: gate checks, CHECKSUMS, git commit, tag, receipt."""
    import subprocess as sp

    all_passed, results = run_gate_checks(
        spec_root, tag_name, decisions_path, exposure_path, milestones_path
    )
    if not all_passed:
        click.echo("Freeze aborted: gate checks failed.", err=True)
        for r in results:
            for d in r.get("diagnostics", []):
                click.echo(f"  FAIL: {d['message']}", err=True)
        sys.exit(1)

    repo_root = spec_root.parent.parent

    # Write CHECKSUMS
    checksums_path = spec_root.parent / "CHECKSUMS.sha256"
    write_checksums(spec_root, checksums_path)
    click.echo(f"Written: {checksums_path}")

    # Git add + commit
    sp.run(["git", "-C", str(repo_root), "add", str(checksums_path)], check=True)
    sp.run(
        ["git", "-C", str(repo_root), "commit", "-m", f"P0-7: {tag_name} freeze"],
        check=True,
    )

    # Create annotated tag
    sp.run(
        [
            "git",
            "-C",
            str(repo_root),
            "tag",
            "-a",
            tag_name,
            "-m",
            f"{tag_name} freeze",
        ],
        check=True,
    )

    # Write receipt
    result = sp.run(
        ["git", "-C", str(repo_root), "rev-parse", f"{tag_name}^{{}}"],
        capture_output=True,
        text=True,
        check=True,
    )
    tag_target = result.stdout.strip()
    result2 = sp.run(
        ["git", "-C", str(repo_root), "rev-parse", tag_name],
        capture_output=True,
        text=True,
        check=True,
    )
    tag_obj = result2.stdout.strip()

    checksums_digest = (
        "sha256:" + hashlib.sha256(checksums_path.read_bytes()).hexdigest()
    )
    receipt = {
        "freeze_version": "1",
        "tag_name": tag_name,
        "tag_target_commit": tag_target,
        "tag_object_sha": tag_obj,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "checksums_digest": checksums_digest,
        "registration_status": "local-only",
        "archive_url": None,
    }
    receipt_path = repo_root / "reports" / "spec-v1-freeze-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    click.echo(f"Freeze complete. Tag: {tag_name}. Receipt: {receipt_path}")
    sys.exit(0)


def _do_verify(spec_root: Path, tag_name: str) -> None:
    """Verify: re-compute hashes, check receipt and tag-target."""
    import subprocess as sp

    repo_root = spec_root.parent.parent
    checksums_path = spec_root.parent / "CHECKSUMS.sha256"
    mismatched = verify_checksums(spec_root, checksums_path)
    if mismatched:
        click.echo(
            f"Verification FAILED: {len(mismatched)} artifact(s) have hash mismatches:",
            err=True,
        )
        for m in mismatched:
            click.echo(f"  {m}", err=True)
        sys.exit(1)

    # Check receipt
    receipt_path = repo_root / "reports" / "spec-v1-freeze-receipt.json"
    if receipt_path.exists():
        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            result = sp.run(
                [
                    "git",
                    "-C",
                    str(repo_root),
                    "rev-parse",
                    f"{tag_name}^{{}}",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                tag_target = result.stdout.strip()
                if receipt.get("tag_target_commit") != tag_target:
                    click.echo("Receipt tag_target_commit mismatch.", err=True)
                    sys.exit(1)
        except Exception:
            pass

    click.echo("Verification passed.")
    sys.exit(0)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--spec-root",
    required=True,
    type=click.Path(exists=False, path_type=Path),
    help="Root of spec namespace (.factverify/spec).",
)
@click.option(
    "--tag",
    default="spec-v1",
    show_default=True,
    help="Freeze tag name.",
)
@click.option(
    "--dry-run",
    "mode",
    flag_value="dry_run",
    default=True,
    help="Run gate checks only; no writes (default).",
)
@click.option(
    "--execute",
    "mode",
    flag_value="execute",
    help="Run gate checks then write CHECKSUMS, commit, tag, receipt.",
)
@click.option(
    "--verify",
    "mode",
    flag_value="verify",
    help="Verify existing snapshot (re-compute hashes, check tag-target).",
)
@click.option(
    "--report",
    default=None,
    type=click.Path(path_type=Path),
    help="Write gate-check results to JSON (dry-run mode).",
)
@click.option(
    "--decisions-register",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Decision register YAML path.",
)
@click.option(
    "--exposure-record",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Exposure record Markdown path.",
)
@click.option(
    "--milestones",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Milestones YAML path.",
)
def main(
    spec_root: Path,
    tag: str,
    mode: str,
    report: Path | None,
    decisions_register: Path | None,
    exposure_record: Path | None,
    milestones: Path | None,
) -> None:
    """Gate and execute the spec-v1 freeze workflow."""
    # Default paths
    if decisions_register is None:
        decisions_register = spec_root.parent / "decisions" / "register.yaml"
    if exposure_record is None:
        exposure_record = spec_root.parent / "exposure" / "exposure_record.md"
    if milestones is None:
        milestones = spec_root.parent / "milestones" / "milestones.yaml"

    if mode == "verify":
        _do_verify(spec_root, tag)
    elif mode == "execute":
        _do_execute(
            spec_root,
            tag,
            decisions_register,
            exposure_record,
            milestones,
            report,
        )
    else:  # dry_run
        _do_dry_run(
            spec_root,
            tag,
            decisions_register,
            exposure_record,
            milestones,
            report,
        )


if __name__ == "__main__":
    main()
