"""P0-1 atomic-fact contract validator.

Validates JSON contract files against the fact_contract.schema.json schema
and performs supplemental consistency checks not expressible in JSON Schema.

Exit codes:
    0 — all checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs (schema, empty contracts dir, bad invocation)
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

import click
from jsonschema import Draft202012Validator

# ---------------------------------------------------------------------------
# T008: Schema loading and meta-schema check
# ---------------------------------------------------------------------------

SUPPORTED_SCOPES = {
    "fact-contract",
    "closure-templates",
    "attacks",
    "access-profile",
    "margins",
    "witness-rule",
    "preregistration",
    "models",
}


def load_schema(spec_root: Path) -> dict:
    """Load and meta-validate the fact contract schema."""
    schema_path = spec_root / "fact_contract.schema.json"
    if not schema_path.exists():
        raise SystemExit(f"Schema not found: {schema_path}")
    text = schema_path.read_text(encoding="utf-8")
    schema = json.loads(text)
    try:
        Draft202012Validator.check_schema(schema)
    except Exception as exc:
        raise SystemExit(f"Schema fails meta-validation: {exc}") from exc
    return schema


def schema_digest(spec_root: Path) -> str:
    """SHA-256 hex digest of the schema file."""
    schema_path = spec_root / "fact_contract.schema.json"
    return "sha256:" + hashlib.sha256(schema_path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# T009: Contract directory scanning
# ---------------------------------------------------------------------------


def scan_contracts(contracts_dir: Path) -> list[Path]:
    """Enumerate *.json files in the contracts directory."""
    if not contracts_dir.exists() or not contracts_dir.is_dir():
        raise SystemExit(f"Contracts directory not found: {contracts_dir}")
    files = sorted(contracts_dir.glob("*.json"))
    if not files:
        raise SystemExit(f"No contracts found in: {contracts_dir}")
    return files


# ---------------------------------------------------------------------------
# T010: Per-contract JSON Schema validation
# ---------------------------------------------------------------------------


def validate_contract(
    contract: dict,
    schema: dict,
    file_name: str,
) -> list[dict]:
    """Validate a contract against the schema, return diagnostics."""
    validator = Draft202012Validator(schema)
    diagnostics = []
    for error in sorted(
        validator.iter_errors(contract), key=lambda e: list(e.absolute_path)
    ):
        pointer = (
            "/" + "/".join(str(p) for p in error.absolute_path)
            if error.absolute_path
            else "/"
        )
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-002",
                "file": file_name,
                "json_pointer": pointer,
                "message": error.message,
            }
        )
    return diagnostics


# ---------------------------------------------------------------------------
# T011: Identity consistency check (FV-SPEC-005)
# ---------------------------------------------------------------------------

_WD_FACT_RE = re.compile(
    r"^factverify:fact:(wd-Q(\d+)-P(\d+)-Q(\d+)|[a-z0-9]+(?:_[a-z0-9]+)*)$"
)
_WD_CONTRACT_RE = re.compile(
    r"^factverify:contract:(wd-Q(\d+)-P(\d+)-Q(\d+)|[a-z0-9]+(?:_[a-z0-9]+)*):v(\d+)$"
)


def check_identity_consistency(contract: dict, file_name: str) -> list[dict]:
    """Check that Q/P components in fact_id, contract_id, and triple IDs agree."""
    diagnostics = []
    fact_id = contract.get("fact_id", "")
    contract_id = contract.get("contract_id", "")

    fm = _WD_FACT_RE.match(fact_id)
    cm = _WD_CONTRACT_RE.match(contract_id)

    if not fm or not cm:
        return diagnostics  # syntax errors caught by schema validation

    fact_key = fm.group(1)
    contract_key = cm.group(1)

    if fact_key != contract_key:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-005",
                "file": file_name,
                "json_pointer": "/contract_id",
                "message": (
                    f"Fact key in contract_id ('{contract_key}') "
                    f"does not match fact_id key ('{fact_key}')."
                ),
            }
        )

    # For Wikidata-sourced facts, check triple component IDs match
    if fm.group(2):  # Wikidata pattern
        expected_subject_q = fm.group(2)
        expected_relation_p = fm.group(3)
        expected_object_q = fm.group(4)

        triple = contract.get("triple", {})
        subject_id = triple.get("subject", {}).get("id", "")
        relation_id = triple.get("relation", {}).get("id", "")
        object_id = triple.get("object", {}).get("id", "")

        if subject_id and subject_id != f"wikidata:Q{expected_subject_q}":
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-005",
                    "file": file_name,
                    "json_pointer": "/triple/subject/id",
                    "message": (
                        f"Subject ID '{subject_id}' does not match "
                        f"Q{expected_subject_q} from fact_id."
                    ),
                }
            )
        if relation_id and relation_id != f"wikidata:P{expected_relation_p}":
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-005",
                    "file": file_name,
                    "json_pointer": "/triple/relation/id",
                    "message": (
                        f"Relation ID '{relation_id}' does not match "
                        f"P{expected_relation_p} from fact_id."
                    ),
                }
            )
        if object_id and object_id != f"wikidata:Q{expected_object_q}":
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-005",
                    "file": file_name,
                    "json_pointer": "/triple/object/id",
                    "message": (
                        f"Object ID '{object_id}' does not match "
                        f"Q{expected_object_q} from fact_id."
                    ),
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# T012: Direction-role consistency check (FV-SPEC-007)
# ---------------------------------------------------------------------------

_DIRECTION_RULES = {
    "forward": ("subject", "object"),
    "inverse": ("object", "subject"),
    "verification": ("triple", "truth_value"),
}


def check_direction_roles(contract: dict, file_name: str) -> list[dict]:
    """Enforce forward→subject/object, inverse→object/subject, verification→triple/truth_value."""
    diagnostics = []
    for i, entry in enumerate(contract.get("equivalent_directions", [])):
        direction = entry.get("direction")
        given = entry.get("given")
        answer = entry.get("answer")
        expected = _DIRECTION_RULES.get(direction)
        if expected and (given, answer) != expected:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-007",
                    "file": file_name,
                    "json_pointer": f"/equivalent_directions/{i}",
                    "message": (
                        f"Direction '{direction}' requires given='{expected[0]}' "
                        f"and answer='{expected[1]}', got given='{given}' "
                        f"and answer='{answer}'."
                    ),
                }
            )
    return diagnostics


# ---------------------------------------------------------------------------
# T013: Diagnostic formatting (stable rule IDs)
# ---------------------------------------------------------------------------
# Diagnostics are already formatted with rule_id, file, json_pointer, message
# by each check function above. The rule_id mapping:
#   FV-SPEC-002 — schema validation errors (required fields, types, patterns)
#   FV-SPEC-005 — identity consistency
#   FV-SPEC-007 — direction-role consistency


# ---------------------------------------------------------------------------
# T014: JSON report writer
# ---------------------------------------------------------------------------


def write_report(
    scope: str,
    spec_root: Path,
    checked_files: list[dict],
    all_diagnostics: list[dict],
    report_path: Path,
    revision_check: object = "not_requested",
) -> dict:
    """Build and write the JSON validation report."""
    report = {
        "scope": scope,
        "schema_path": str((spec_root / "fact_contract.schema.json").resolve()),
        "schema_digest": schema_digest(spec_root),
        "timestamp": datetime.now(UTC).isoformat(),
        "checked_files": checked_files,
        "revision_check": revision_check,
        "diagnostics": all_diagnostics,
        "summary": {
            "total": len(checked_files),
            "valid": sum(1 for f in checked_files if f["valid"]),
            "invalid": sum(1 for f in checked_files if not f["valid"]),
        },
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


# ---------------------------------------------------------------------------
# T032-T034: Revision comparison (US2)
# ---------------------------------------------------------------------------


def load_baseline_contracts(baseline_dir: Path) -> dict[str, dict]:
    """Load baseline contracts indexed by fact key from contract_id."""
    if not baseline_dir.exists() or not baseline_dir.is_dir():
        raise SystemExit(f"Baseline directory not found: {baseline_dir}")
    baselines = {}
    for fp in sorted(baseline_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cid = data.get("contract_id", "")
        m = _WD_CONTRACT_RE.match(cid)
        if m:
            baselines[m.group(1)] = data
    return baselines


def _strip_freeze_fields(contract: dict) -> dict:
    """Return a copy with freeze_policy.frozen_at and content_sha256 removed."""
    out = json.loads(json.dumps(contract))  # deep copy
    fp = out.get("freeze_policy")
    if isinstance(fp, dict):
        fp.pop("frozen_at", None)
        fp.pop("content_sha256", None)
    return out


def _extract_version(contract_id: str) -> int | None:
    m = _WD_CONTRACT_RE.match(contract_id)
    if m:
        return int(m.group(5)) if m.group(5) else None
    return None


def check_revision(current: dict, baseline: dict, file_name: str) -> list[dict]:
    """Compare current contract against baseline for unauthorized changes."""
    diagnostics = []
    cur_stripped = _strip_freeze_fields(current)
    base_stripped = _strip_freeze_fields(baseline)

    if cur_stripped == base_stripped:
        return diagnostics  # identical — no revision needed

    cur_version = _extract_version(current.get("contract_id", ""))
    base_version = _extract_version(baseline.get("contract_id", ""))

    if cur_version is not None and base_version is not None:
        if cur_version <= base_version:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-013",
                    "file": file_name,
                    "json_pointer": "/contract_id",
                    "message": (
                        f"Contract content changed but version was not incremented "
                        f"(baseline v{base_version}, current v{cur_version})."
                    ),
                }
            )

    # Check if triple changed but fact_id stayed the same
    cur_triple = current.get("triple")
    base_triple = baseline.get("triple")
    if cur_triple != base_triple and current.get("fact_id") == baseline.get("fact_id"):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-013",
                "file": file_name,
                "json_pointer": "/triple",
                "message": "Triple changed but fact_id was not updated.",
            }
        )

    return diagnostics


def run_revision_checks(
    contracts_dir: Path,
    baseline_dir: Path,
    schema: dict,
) -> tuple[list[dict], object]:
    """Run revision comparison for all current contracts against baselines."""
    baselines = load_baseline_contracts(baseline_dir)
    all_diagnostics = []
    details = []

    for fp in sorted(contracts_dir.glob("*.json")):
        try:
            current = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cid = current.get("contract_id", "")
        m = _WD_CONTRACT_RE.match(cid)
        if not m:
            continue
        fact_key = m.group(1)
        baseline = baselines.get(fact_key)
        if baseline is None:
            details.append(
                {
                    "file": fp.name,
                    "status": "no_baseline",
                    "changed_fields": [],
                }
            )
            continue
        diags = check_revision(current, baseline, fp.name)
        all_diagnostics.extend(diags)
        details.append(
            {
                "file": fp.name,
                "status": "changed" if diags else "unchanged",
                "changed_fields": [d["json_pointer"] for d in diags],
            }
        )

    status = "pass" if not all_diagnostics else "fail"
    return all_diagnostics, {"status": status, "details": details}


# ---------------------------------------------------------------------------
# T015: CLI entry point
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--scope",
    required=True,
    help=(
        "Validation scope: fact-contract, closure-templates, attacks, "
        "access-profile, margins, witness-rule, preregistration, models."
    ),
)
@click.option(
    "--spec-root",
    required=True,
    type=click.Path(exists=False, path_type=Path),
    help="Path to the spec directory containing the schema.",
)
@click.option(
    "--contracts",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Directory of JSON contract files to validate "
    "(required for fact-contract, closure-templates, attacks).",
)
@click.option(
    "--report",
    default=None,
    type=click.Path(path_type=Path),
    help="Output path for the JSON validation report.",
)
@click.option(
    "--baseline-contracts",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Optional baseline directory for revision comparison (fact-contract).",
)
@click.option(
    "--bindings",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Instance bindings JSON (closure-templates).",
)
@click.option(
    "--review-manifest",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Review manifest JSON (closure-templates).",
)
@click.option(
    "--split",
    default=None,
    type=click.Choice(["construction", "calibration", "final_test"]),
    help="Filter preview to a specific split (closure-templates).",
)
@click.option(
    "--preview",
    default=None,
    type=click.Path(path_type=Path),
    help="Output preview JSONL path (closure-templates).",
)
@click.option(
    "--strict",
    is_flag=True,
    default=False,
    help="Require resolved decisions and current reviews (closure-templates).",
)
@click.option(
    "--baseline-suite",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Prior suite snapshot for revision check (closure-templates / attacks).",
)
@click.option(
    "--access-profile",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help=(
        "Access profile path. Attacks: channel permission check. "
        "Models: FV-SPEC-092 compatibility check."
    ),
)
@click.option(
    "--event-fixtures",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Event trace fixtures JSON for replay validation (attacks).",
)
@click.option(
    "--witness-rule",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Witness-rule routes for confirmation cross-check (attacks).",
)
@click.option(
    "--access-dir",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Path to .factverify/access/ directory (access-profile).",
)
@click.option(
    "--margins-dir",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Path to .factverify/margins/ directory (margins).",
)
@click.option(
    "--witness-dir",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Path to .factverify/witness/ directory (witness-rule).",
)
@click.option(
    "--preregistration",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Preregistration document path (preregistration scope).",
)
@click.option(
    "--decisions-register",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Decision register YAML path (preregistration scope).",
)
@click.option(
    "--exposure-record",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Exposure record Markdown path (preregistration scope).",
)
@click.option(
    "--milestones",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Milestones YAML path (preregistration scope).",
)
@click.option(
    "--model-dir",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Local model directory for offline digest check (models scope).",
)
@click.option(
    "--model-config",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Versioned model configuration to validate with the shared parser.",
)
@click.option(
    "--downstream-report",
    default=None,
    type=click.Path(exists=False, path_type=Path),
    help="Exclusion-gate report JSON for downstream binding check (models scope).",
)
def main(
    scope: str,
    spec_root: Path,
    contracts: Path,
    report: Path,
    baseline_contracts: Path | None,
    bindings: Path | None,
    review_manifest: Path | None,
    split: str | None,
    preview: Path | None,
    strict: bool,
    baseline_suite: Path | None,
    access_profile: Path | None,
    event_fixtures: Path | None,
    witness_rule: Path | None,
    access_dir: Path | None,
    margins_dir: Path | None,
    witness_dir: Path | None,
    preregistration: Path | None,
    decisions_register: Path | None,
    exposure_record: Path | None,
    milestones: Path | None,
    model_dir: Path | None,
    model_config: Path | None,
    downstream_report: Path | None,
) -> None:
    """Validate atomic-fact contracts, closure templates, attack specs, or margins."""
    if scope not in SUPPORTED_SCOPES:
        click.echo(f"Error: unsupported scope '{scope}'", err=True)
        sys.exit(2)

    if scope == "models":
        _run_models_validation(
            spec_root,
            report,
            model_dir,
            access_profile,
            downstream_report,
            strict,
            model_config,
        )
        return

    if scope == "preregistration":
        _run_preregistration_validation(
            spec_root,
            report,
            preregistration,
            decisions_register,
            exposure_record,
            milestones,
            strict,
        )
        return

    if scope == "witness-rule":
        _run_witness_rule_validation(
            spec_root,
            report,
            witness_dir,
            strict,
            baseline_suite,
        )
        return

    if scope == "margins":
        _run_margins_validation(
            spec_root,
            report,
            margins_dir,
            strict,
            baseline_suite,
        )
        return

    if scope == "access-profile":
        _run_access_profile_validation(
            spec_root,
            report,
            access_dir,
            strict,
            baseline_suite,
        )
        return

    if contracts is None:
        click.echo(
            f"Error: --contracts required for scope '{scope}'",
            err=True,
        )
        sys.exit(2)

    if scope == "attacks":
        _run_attack_validation(
            spec_root,
            contracts,
            report,
            access_profile,
            event_fixtures,
            witness_rule,
            strict,
            baseline_suite,
        )
        return

    if scope == "closure-templates":
        if report is None:
            click.echo(
                "Error: --report required for closure-templates scope",
                err=True,
            )
            sys.exit(2)
        _run_closure_validation(
            spec_root,
            contracts,
            report,
            bindings,
            review_manifest,
            split,
            preview,
            strict,
            baseline_suite,
        )
        return

    # --- fact-contract scope (unchanged P0-1 logic) ---
    if report is None:
        click.echo(
            "Error: --report required for fact-contract scope",
            err=True,
        )
        sys.exit(2)

    try:
        schema = load_schema(spec_root)
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    try:
        contract_files = scan_contracts(contracts)
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    checked_files = []
    all_diagnostics = []
    has_failures = False

    for fp in contract_files:
        file_name = fp.name
        try:
            contract = json.loads(fp.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            diag = {
                "rule_id": "FV-SPEC-002",
                "file": file_name,
                "json_pointer": "/",
                "message": f"Invalid JSON: {exc}",
            }
            checked_files.append(
                {"path": file_name, "valid": False, "diagnostics": [diag]}
            )
            all_diagnostics.append(diag)
            has_failures = True
            continue

        diags = validate_contract(contract, schema, file_name)
        diags.extend(check_identity_consistency(contract, file_name))
        diags.extend(check_direction_roles(contract, file_name))

        valid = len(diags) == 0
        if not valid:
            has_failures = True
        checked_files.append({"path": file_name, "valid": valid, "diagnostics": diags})
        all_diagnostics.extend(diags)

    revision_check: object = "not_requested"
    if baseline_contracts is not None:
        try:
            rev_diags, revision_check = run_revision_checks(
                contracts, baseline_contracts, schema
            )
            all_diagnostics.extend(rev_diags)
            if rev_diags:
                has_failures = True
        except SystemExit as exc:
            click.echo(f"Error: {exc}", err=True)
            sys.exit(2)

    write_report(
        scope, spec_root, checked_files, all_diagnostics, report, revision_check
    )

    summary_valid = sum(1 for f in checked_files if f["valid"])
    summary_invalid = sum(1 for f in checked_files if not f["valid"])
    click.echo(
        f"Validated {len(checked_files)} contract(s): "
        f"{summary_valid} valid, {summary_invalid} invalid."
    )
    if isinstance(revision_check, dict):
        click.echo(f"Revision check: {revision_check['status']}")

    sys.exit(1 if has_failures else 0)


def _run_closure_validation(
    spec_root: Path,
    contracts: Path,
    report: Path,
    bindings: Path | None,
    review_manifest: Path | None,
    split: str | None,
    preview: Path | None,
    strict: bool,
    baseline_suite: Path | None,
) -> None:
    """Dispatch to closure_validator for --scope closure-templates."""
    from tools.closure_validator import validate_closure_suite

    if bindings is None:
        click.echo("Error: --bindings required for closure-templates scope", err=True)
        sys.exit(2)

    try:
        success, rpt = validate_closure_suite(
            spec_root=spec_root,
            contracts_dir=contracts,
            bindings_path=bindings,
            report_path=report,
            review_manifest_path=review_manifest,
            split=split,
            preview_path=preview,
            strict=strict,
            baseline_suite_path=baseline_suite,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    summary = rpt.get("summary", {})
    click.echo(
        f"Validated {summary.get('total_templates', 0)} template(s): "
        f"{summary.get('valid', 0)} valid, "
        f"{summary.get('invalid', 0)} invalid."
    )
    if isinstance(rpt.get("revision_check"), dict):
        click.echo(f"Revision check: {rpt['revision_check']['status']}")

    sys.exit(0 if success else 1)


def _run_attack_validation(
    spec_root: Path,
    contracts: Path,
    report: Path,
    access_profile: Path | None,
    event_fixtures: Path | None,
    witness_rule: Path | None,
    strict: bool,
    baseline_suite: Path | None,
) -> None:
    """Dispatch to attack_validator for --scope attacks."""
    from tools.attack_validator import validate_attack_spec

    try:
        success, rpt = validate_attack_spec(
            spec_root=spec_root,
            contracts_dir=contracts,
            report_path=report,
            access_profile_path=access_profile,
            event_fixtures_path=event_fixtures,
            witness_rule_path=witness_rule,
            strict=strict,
            baseline_suite_path=baseline_suite,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    summary = rpt.get("summary", {})
    click.echo(
        f"Attack spec validation: "
        f"{summary.get('passed', 0)} passed, "
        f"{summary.get('failed', 0)} failed, "
        f"{summary.get('deferred', 0)} deferred."
    )
    if isinstance(rpt.get("revision_check"), dict):
        rev_status = rpt["revision_check"].get("status", "unknown")
        if rev_status != "not_requested":
            click.echo(f"Revision check: {rev_status}")

    sys.exit(0 if success else 1)


def _run_access_profile_validation(
    spec_root: Path,
    report: Path,
    access_dir: Path | None,
    strict: bool,
    baseline_suite: Path | None,
) -> None:
    """Dispatch to access_profile_validator for --scope access-profile."""
    from tools.access_profile_validator import validate_access_profile

    # Default access_dir to sibling of spec_root
    if access_dir is None:
        access_dir = spec_root.parent / "access"

    try:
        success, rpt = validate_access_profile(
            spec_root=spec_root,
            access_dir=access_dir,
            report_path=report,
            strict=strict,
            baseline_suite_path=baseline_suite,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    checks = rpt.get("checks", [])
    passed = sum(1 for c in checks if c.get("status") == "pass")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    deferred = sum(1 for c in checks if c.get("status") == "deferred")
    click.echo(
        f"Access profile validation: "
        f"{passed} passed, {failed} failed, {deferred} deferred."
    )
    bl = rpt.get("baseline_comparison")
    if isinstance(bl, dict) and bl.get("status") != "not_requested":
        click.echo(f"Baseline check: {bl['status']}")

    sys.exit(0 if success else 1)


def _run_witness_rule_validation(
    spec_root: Path,
    report: Path | None,
    witness_dir: Path | None,
    strict: bool,
    baseline_suite: Path | None,
) -> None:
    """Dispatch to witness_rule_validator for --scope witness-rule."""
    from tools.witness_rule_validator import validate_witness_rule

    if witness_dir is None:
        witness_dir = spec_root.parent / "witness"

    try:
        success, rpt = validate_witness_rule(
            spec_root=spec_root,
            witness_dir=witness_dir,
            report_path=report,
            strict=strict,
            baseline_suite_path=baseline_suite,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    checks = rpt.get("checks", [])
    passed = sum(1 for c in checks if c.get("status") == "pass")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    deferred = sum(1 for c in checks if c.get("status") == "deferred")
    click.echo(
        f"Witness rule validation: "
        f"{passed} passed, {failed} failed, {deferred} deferred."
    )
    bl = rpt.get("baseline_comparison")
    if isinstance(bl, dict) and bl.get("status") not in (None, "not_requested"):
        click.echo(f"Baseline check: {bl['status']}")

    sys.exit(0 if success else 1)


def _run_margins_validation(
    spec_root: Path,
    report: Path | None,
    margins_dir: Path | None,
    strict: bool,
    baseline_suite: Path | None,
) -> None:
    """Dispatch to margins_validator for --scope margins."""
    from tools.margins_validator import validate_margins

    if margins_dir is None:
        margins_dir = spec_root.parent / "margins"

    try:
        success, rpt = validate_margins(
            spec_root=spec_root,
            margins_dir=margins_dir,
            report_path=report,
            strict=strict,
            baseline_suite_path=baseline_suite,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    checks = rpt.get("checks", [])
    passed = sum(1 for c in checks if c.get("status") == "pass")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    deferred = sum(1 for c in checks if c.get("status") == "deferred")
    click.echo(
        f"Margins validation: {passed} passed, {failed} failed, {deferred} deferred."
    )
    bl = rpt.get("baseline_comparison")
    if isinstance(bl, dict) and bl.get("status") not in (None, "not_requested"):
        click.echo(f"Baseline check: {bl['status']}")

    sys.exit(0 if success else 1)


def _run_preregistration_validation(
    spec_root: Path,
    report: Path | None,
    preregistration: Path | None,
    decisions_register: Path | None,
    exposure_record: Path | None,
    milestones: Path | None,
    strict: bool,
) -> None:
    """Dispatch to preregistration_validator for --scope preregistration."""
    from tools.preregistration_validator import validate_preregistration

    # Default paths
    if preregistration is None:
        preregistration = spec_root / "preregistration.md"
    if decisions_register is None:
        decisions_register = spec_root.parent / "decisions" / "register.yaml"
    if exposure_record is None:
        exposure_record = spec_root.parent / "exposure" / "exposure_record.md"
    if milestones is None:
        milestones = spec_root.parent / "milestones" / "milestones.yaml"

    try:
        success, rpt = validate_preregistration(
            spec_root=spec_root,
            prereg_path=preregistration,
            decisions_path=decisions_register,
            exposure_path=exposure_record,
            milestones_path=milestones,
            strict=strict,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    if report:
        import json as json_mod

        report.parent.mkdir(parents=True, exist_ok=True)
        report.write_text(json_mod.dumps(rpt, indent=2) + "\n", encoding="utf-8")

    checks = rpt.get("checks", [])
    passed = sum(1 for c in checks if c.get("status") == "pass")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    deferred = sum(1 for c in checks if c.get("status") == "deferred")
    click.echo(
        f"Preregistration validation: {passed} passed, {failed} failed, {deferred} deferred."
    )

    sys.exit(0 if success else 1)


def _run_models_validation(
    spec_root: Path,
    report: Path | None,
    model_dir: Path | None,
    access_profile: Path | None,
    downstream_report: Path | None,
    strict: bool,
    model_config: Path | None = None,
) -> None:
    """Dispatch to models_validator for --scope models."""
    from tools.models_validator import validate_models_spec

    try:
        success, rpt = validate_models_spec(
            spec_root=spec_root,
            model_dir=model_dir,
            access_profile_path=access_profile,
            downstream_report_path=downstream_report,
            strict=strict,
            report_path=report,
            model_config=model_config,
        )
    except SystemExit as exc:
        click.echo(f"Error: {exc}", err=True)
        sys.exit(2)

    checks = rpt.get("checks", [])
    passed = sum(1 for c in checks if c.get("status") == "pass")
    failed = sum(1 for c in checks if c.get("status") == "fail")
    pending = sum(1 for c in checks if c.get("status") == "pending")
    click.echo(
        f"Models validation: {passed} passed, {failed} failed, {pending} pending."
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
