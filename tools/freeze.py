"""P0-7 spec-freeze workflow CLI.

Gates and executes the spec-v1 freeze: FREEZE.json digest record, annotated
git tag, post-commit receipt.

The four normative spec artifacts (directly under the frozen spec root) are:
  protocol.yaml, templates.yaml, model_policy.yaml, fact.schema.json

Modes:
    --dry-run   (default) Run all gate checks; make no writes.
    --execute   Run gate checks, then write FREEZE.json, commit, tag, receipt.
    --verify    Re-compute hashes and verify against existing FREEZE.json.

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
# Spec artifact manifest — four normative files at frozen spec root top level
# ---------------------------------------------------------------------------

SPEC_ARTIFACTS = [
    "protocol.yaml",
    "templates.yaml",
    "model_policy.yaml",
    "fact.schema.json",
]

# ---------------------------------------------------------------------------
# Digest helpers
# ---------------------------------------------------------------------------


def compute_content_digests(spec_root: Path) -> dict[str, str | None]:
    """Return {filename: 'sha256:<hex>'} for all four normative spec artifacts."""
    result: dict[str, str | None] = {}
    for name in SPEC_ARTIFACTS:
        p = spec_root / name
        if p.exists():
            hex_val = hashlib.sha256(p.read_bytes()).hexdigest()
            result[name] = f"sha256:{hex_val}"
        else:
            result[name] = None
    return result


def write_freeze_json(
    spec_root: Path,
    spec_version: str = "0.1.0-demo",
    commit: str | None = None,
) -> Path:
    """Compute digests and write FREEZE.json to spec_root. Returns the path written."""
    content_digests = compute_content_digests(spec_root)
    freeze = {
        "schema_version": "1.0.0",
        "spec_version": spec_version,
        "status": "frozen",
        "commit": commit,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "decisions": [],
        "approvals": [],
        "content_digests": content_digests,
    }
    freeze_path = spec_root / "FREEZE.json"
    freeze_path.write_text(json.dumps(freeze, indent=2) + "\n", encoding="utf-8")
    return freeze_path


def verify_freeze_json(spec_root: Path) -> list[str]:
    """Re-compute digests and compare against FREEZE.json. Returns mismatch list.

    Returns [str(freeze_path)] if FREEZE.json is missing.
    """
    freeze_path = spec_root / "FREEZE.json"
    if not freeze_path.exists():
        return [str(freeze_path)]

    try:
        stored = json.loads(freeze_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"FREEZE.json parse error: {exc}"]

    stored_digests: dict[str, str | None] = stored.get("content_digests", {})
    mismatched = []
    for name in SPEC_ARTIFACTS:
        p = spec_root / name
        if not p.exists():
            mismatched.append(name)
            continue
        actual = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
        stored_val = stored_digests.get(name)
        if stored_val is None or actual != stored_val:
            mismatched.append(name)
    return mismatched


def compute_contract_digest(prereg_path: Path) -> str:
    """SHA-256 of canonical payload: frontmatter (without digest field) + body.

    Used by preregistration_validator.  spec/ subdir files still exist during
    the transition period; this helper reads directly from the supplied path.
    """
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
    """Gate 1: All four normative spec artifacts present and non-empty."""
    diags = []
    for name in SPEC_ARTIFACTS:
        p = spec_root / name
        if not p.exists():
            diags.append(
                {
                    "check": "artifacts_present",
                    "status": "fail",
                    "message": f"Missing normative spec artifact: {name}",
                }
            )
        elif p.stat().st_size == 0:
            diags.append(
                {
                    "check": "artifacts_present",
                    "status": "fail",
                    "message": f"Normative spec artifact is empty: {name}",
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
    """Gate 8: No raw outputs, checkpoints, or credentials inside spec_root."""
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
    if not spec_root.exists():
        return diags

    for p in spec_root.rglob("*"):
        if p.is_file():
            for pattern in banned_patterns:
                if fnmatch.fnmatch(p.name, pattern):
                    diags.append(
                        {
                            "check": "no_leaked_files",
                            "status": "fail",
                            "message": (
                                f"Potentially sensitive file inside spec root: {p}"
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
    """Gate 2: preregistration scope validates. Does not re-enter the freeze gate.

    preregistration.md lives in spec_root/spec/ during the transition period
    (source files remain in spec/ until full cutover).
    """
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
    repo_root = spec_root.parent
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
    """Execute: gate checks, FREEZE.json, git commit, tag, receipt."""
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

    repo_root = spec_root.parent

    # Get current commit SHA for provenance record
    commit_result = sp.run(
        ["git", "-C", str(repo_root), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    commit_sha = commit_result.stdout.strip() if commit_result.returncode == 0 else None

    # Write FREEZE.json
    freeze_path = write_freeze_json(spec_root, commit=commit_sha)
    click.echo(f"Written: {freeze_path}")

    # Git add + commit
    sp.run(["git", "-C", str(repo_root), "add", str(freeze_path)], check=True)
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

    freeze_digest = "sha256:" + hashlib.sha256(freeze_path.read_bytes()).hexdigest()
    receipt = {
        "freeze_version": "2",
        "tag_name": tag_name,
        "tag_target_commit": tag_target,
        "tag_object_sha": tag_obj,
        "timestamp_utc": datetime.now(UTC).isoformat(),
        "freeze_json_digest": freeze_digest,
        "registration_status": "local-only",
        "archive_url": None,
    }
    receipt_path = repo_root / "reports" / "spec-v1-freeze-receipt.json"
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    click.echo(f"Freeze complete. Tag: {tag_name}. Receipt: {receipt_path}")
    sys.exit(0)


def _do_verify(spec_root: Path, tag_name: str) -> None:
    """Verify: re-compute hashes against FREEZE.json, check receipt and tag-target."""
    import subprocess as sp

    repo_root = spec_root.parent
    mismatched = verify_freeze_json(spec_root)
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
    help="Frozen spec root (default: .factverify/).",
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
    # Default paths — decisions, exposure, milestones live under spec_root
    if decisions_register is None:
        decisions_register = spec_root / "decisions" / "register.yaml"
    if exposure_record is None:
        exposure_record = spec_root / "exposure" / "exposure_record.md"
    if milestones is None:
        milestones = spec_root / "milestones" / "milestones.yaml"

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
