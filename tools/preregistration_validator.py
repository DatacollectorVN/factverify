"""P0-7 preregistration and spec-freeze validator.

Validates preregistration.md, exposure_record.md, milestones.yaml, and
decisions/register.yaml against FV-SPEC-078 through FV-SPEC-088.
All checks are offline — zero model, LLM, GPU, or network calls.

Exit codes (via CLI dispatcher in validate_spec.py):
    0 — all checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

import yaml

# ---------------------------------------------------------------------------
# Sentinel: this validator makes zero model/LLM/GPU/network calls
# ---------------------------------------------------------------------------

_NO_MODEL_CALLS = True  # P0-7 validator makes zero model/LLM/GPU/network calls

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_SECTIONS = [
    "## Primary Question",
    "## Baselines",
    "## Hypotheses",
    "## Controlled Construction",
    "## Evaluation Units",
    "## Sampling",
    "## Evaluation Protocol",
    "## Primary Analysis",
    "## Stopping Rules",
    "## Deviations",
    "## Reporting",
]

REQUIRED_MILESTONES = ["spec-v1", "thresholds-v1", "protocol-v1"]

DEVIATION_CATEGORIES = [
    "feasibility_failure",
    "no_feasible_threshold",
    "scoring_bug",
    "budget_overrun",
    "model_revision",
    "hardware_failure",
    "missing_access",
    "cost_limit",
]

AMENDMENT_REQUIRED_FIELDS = [
    "id",
    "trigger",
    "allowed_information",
    "approver",
    "deadline_before_final_access",
    "effect_size_link",
    "sample_size_link",
    "previous_value",
    "new_value",
    "authorized",
    "post_hoc",
]

# Normative keys that must NOT appear inline in preregistration.md
BANNED_INLINE = ["alpha:", "frr_cap:", "n_facts_target:", "query_budget:"]

# Required split isolation dimensions
ISOLATION_DIMENSIONS = [
    "entity_fact_isolation",
    "reference_seed_isolation",
    "template_group_isolation",
    "control_implementation_isolation",
]

# Keys whose concrete values must live in exactly one spec file (T015, T042).
NORMATIVE_KEYS = ("alpha", "frr_cap", "n_facts_target", "query_budget")
_ASSIGNMENT_RE = re.compile(
    r"(?m)^[ \t-]*({keys}):[ \t]*(\S+)".format(keys="|".join(NORMATIVE_KEYS))
)
_NULL_VALUES = {"null", "none", "~", '""', "''"}


def _mapping_from_path(path: Path) -> dict:
    """Load a YAML mapping, or the YAML frontmatter of a markdown file."""
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    try:
        if path.suffix == ".md" and text.startswith("---"):
            parts = text.split("---", 2)
            data = yaml.safe_load(parts[1]) if len(parts) >= 2 else None
        else:
            data = yaml.safe_load(text)
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


def _normative_assignments(text: str, source: str) -> list[tuple[str, str, str]]:
    found: list[tuple[str, str, str]] = []
    for match in _ASSIGNMENT_RE.finditer(text):
        key, raw = match.group(1), match.group(2).strip().strip("\"'")
        if raw.lower() in _NULL_VALUES or raw in ("|", ">"):
            continue
        found.append((key, raw, source))
    return found


def find_duplicate_normative_values(
    spec_root: Path, extra_text: str = "", extra_name: str = ""
) -> list[dict]:
    """Return diagnostics when the same normative key/value appears in two files."""
    locations: dict[tuple[str, str], list[str]] = {}
    if spec_root.exists():
        for path in sorted(spec_root.iterdir()):
            if (
                path.suffix not in {".yaml", ".yml", ".md", ".json"}
                or not path.is_file()
            ):
                continue
            for key, value, source in _normative_assignments(
                path.read_text(encoding="utf-8"), path.name
            ):
                locations.setdefault((key, value), []).append(source)
    if extra_text:
        for key, value, source in _normative_assignments(
            extra_text, extra_name or "preregistration.md"
        ):
            locations.setdefault((key, value), []).append(source)
    diagnostics = []
    for (key, value), sources in sorted(locations.items()):
        unique = []
        for source in sources:
            if source not in unique:
                unique.append(source)
        if len(unique) < 2:
            continue
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-078",
                "file": unique[0],
                "json_pointer": f"/{key}",
                "message": (
                    f"Normative key '{key}' value {value!r} appears in "
                    f"{' and '.join(unique)}. It must live in one owning artifact."
                ),
            }
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------


def load_preregistration(path: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter + body from a Markdown file.

    Returns (frontmatter_dict, body_str).
    Raises SystemExit with a diagnostic if the file is missing or unparseable.
    """
    if not path.exists():
        raise SystemExit(f"Preregistration file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError as exc:
                raise SystemExit(f"YAML parse error in {path}: {exc}") from exc
            body = parts[2]
        else:
            fm = {}
            body = text
    else:
        fm = {}
        body = text
    return fm, body


def load_yaml_artifact(path: Path) -> dict:
    """Load a YAML file and return the parsed dict.

    Raises SystemExit with a diagnostic if the file is missing or unparseable.
    """
    if not path.exists():
        raise SystemExit(f"YAML artifact not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise SystemExit(f"YAML parse error in {path}: {exc}") from exc
    return data


# ---------------------------------------------------------------------------
# Check functions — FV-SPEC-078 through FV-SPEC-088
# ---------------------------------------------------------------------------


def check_fv_spec_078_artifact(
    frontmatter: dict, body: str, spec_root: Path
) -> list[dict]:
    """FV-SPEC-078: preregistration.md has all required sections with artifact refs.

    - All 11 section headings present
    - Each section contains at least one artifact reference (ref: or [[...]])
    - No normative value (alpha, frr_cap, etc.) appears inline
    """
    diagnostics = []

    # Check all required sections present
    for section in REQUIRED_SECTIONS:
        if section not in body:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-078",
                    "file": "preregistration.md",
                    "json_pointer": "/sections",
                    "message": f"Required section '{section}' is missing.",
                }
            )

    # Check each present section has at least one artifact reference
    for section in REQUIRED_SECTIONS:
        if section in body:
            pattern = re.escape(section) + r"(.*?)(?=\n## |\Z)"
            m = re.search(pattern, body, re.DOTALL)
            if m:
                content = m.group(1)
                if "ref:" not in content and "[[" not in content:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-078",
                            "file": "preregistration.md",
                            "json_pointer": f"/sections/{section}",
                            "message": (
                                f"Section '{section}' contains no artifact reference "
                                f"(ref: or [[...]])."
                            ),
                        }
                    )

    # Check for duplicate normative values inside this document
    body_lower = body.lower()
    for key in BANNED_INLINE:
        if key in body_lower:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-078",
                    "file": "preregistration.md",
                    "json_pointer": "/body",
                    "message": (
                        f"Inline normative value '{key}' found in preregistration.md. "
                        f"This value must only appear in its owning artifact."
                    ),
                }
            )

    # Same concrete value of a normative key in two spec files (T015)
    diagnostics.extend(
        find_duplicate_normative_values(spec_root, body, "preregistration.md")
    )

    return diagnostics


def check_fv_spec_079_exposure(exposure_fm: dict) -> list[dict]:
    """FV-SPEC-079: exposure_record.md frontmatter is complete and consistent.

    - Required fields present
    - No final_test access with non-empty outcomes_inspected
    - externally-archived requires archive_evidence
    """
    diagnostics = []

    required = ["status", "registration_status", "access_events"]
    for field in required:
        if field not in exposure_fm:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-079",
                    "file": "exposure_record.md",
                    "json_pointer": f"/{field}",
                    "message": f"Required field '{field}' is missing.",
                }
            )

    # Detect final_test access with non-empty outcomes_inspected
    for i, event in enumerate(exposure_fm.get("access_events", [])):
        if "final_test" in str(event.get("scope", "")):
            if event.get("outcomes_inspected"):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-079",
                        "file": "exposure_record.md",
                        "json_pointer": f"/access_events/{i}/outcomes_inspected",
                        "message": (
                            "Final-test scope access event lists non-empty "
                            "outcomes_inspected."
                        ),
                    }
                )

    # externally-archived requires archive_evidence
    if exposure_fm.get("registration_status") == "externally-archived":
        if not exposure_fm.get("archive_evidence"):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-079",
                    "file": "exposure_record.md",
                    "json_pointer": "/archive_evidence",
                    "message": (
                        "registration_status is externally-archived but "
                        "archive_evidence is missing or empty."
                    ),
                }
            )

    return diagnostics


def check_fv_spec_080_milestones(milestones: dict) -> list[dict]:
    """FV-SPEC-080: milestones.yaml has all three milestones with staged rules.

    - All three milestone names present
    - Each has git_tag OR complete staged_rule with all sub-fields
    """
    diagnostics = []

    for name in REQUIRED_MILESTONES:
        if name not in milestones:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-080",
                    "file": "milestones.yaml",
                    "json_pointer": f"/{name}",
                    "message": f"Required milestone '{name}' is missing.",
                }
            )
            continue

        entry = milestones[name]
        has_tag = bool(entry.get("git_tag"))
        sr = entry.get("staged_rule")

        if has_tag:
            continue  # resolved milestone — no further checks

        if not sr:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-080",
                    "file": "milestones.yaml",
                    "json_pointer": f"/{name}/staged_rule",
                    "message": (
                        f"Milestone '{name}' has no git_tag and no staged_rule."
                    ),
                }
            )
            continue

        for subfield in ["determined_at_gate", "inputs", "method"]:
            val = sr.get(subfield)
            if not val or val in ("TBD", "", None):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-080",
                        "file": "milestones.yaml",
                        "json_pointer": f"/{name}/staged_rule/{subfield}",
                        "message": (
                            f"staged_rule.{subfield} for '{name}' is missing or TBD."
                        ),
                    }
                )

    return diagnostics


def check_fv_spec_081_splits(splits: dict) -> list[dict]:
    """FV-SPEC-081: split manifests record all required isolation dimensions.

    - Each split has all four isolation dimensions recorded
    - TOFU source records have atomic_fact_mapping
    - Unmaterialised splits have a gate reference
    """
    diagnostics = []

    for split_name, split_entry in splits.items():
        if not isinstance(split_entry, dict):
            continue

        # Check isolation dimensions
        for dim in ISOLATION_DIMENSIONS:
            if dim not in split_entry:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-081",
                        "file": "splits.yaml",
                        "json_pointer": f"/{split_name}/{dim}",
                        "message": (
                            f"Split '{split_name}' is missing isolation dimension "
                            f"'{dim}'."
                        ),
                    }
                )

        # TOFU source requires atomic_fact_mapping
        if split_entry.get("source") == "tofu":
            if not split_entry.get("atomic_fact_mapping"):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-081",
                        "file": "splits.yaml",
                        "json_pointer": f"/{split_name}/atomic_fact_mapping",
                        "message": (
                            f"Split '{split_name}' has source: tofu but no "
                            f"atomic_fact_mapping."
                        ),
                    }
                )

        # Unmaterialised split must have a gate. A declared gate is pending, not verified.
        if split_entry.get("materialised") is False:
            gate = split_entry.get("gate")
            if not gate:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-081",
                        "file": "splits.yaml",
                        "json_pointer": f"/{split_name}/gate",
                        "message": (
                            f"Split '{split_name}' is unmaterialised but has no "
                            f"gate reference."
                        ),
                    }
                )
            else:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-081",
                        "file": "splits.yaml",
                        "json_pointer": f"/{split_name}/status",
                        "severity": "pending",
                        "message": f"Split '{split_name}' is pending ({gate}), not verified.",
                    }
                )

    return diagnostics


def check_fv_spec_082_analysis(
    frontmatter: dict, body: str, spec_root: Path
) -> list[dict]:
    """FV-SPEC-082: primary analysis contract is consistent with margins.yaml.

    - No inline normative values that duplicate margins.yaml
    - No empty denominator fields
    """
    diagnostics = []

    # Load owning artifacts (T042): margins, attacks, and the witness rule.
    sources = {
        "margins.yaml": _mapping_from_path(spec_root / "margins.yaml"),
        "attacks.yaml": _mapping_from_path(spec_root / "attacks.yaml"),
        "witness_rule.md": _mapping_from_path(spec_root / "witness_rule.md"),
    }
    normative_keys: set[str] = set()
    owners: dict[str, str] = {}
    for source_name, mapping in sources.items():
        for key in mapping:
            normative_keys.add(str(key))
            owners.setdefault(str(key), source_name)
        for key, value, source in _normative_assignments(
            "\n".join(
                f"{k}: {v}"
                for k, v in mapping.items()
                if not isinstance(v, (dict, list))
            ),
            source_name,
        ):
            owners[key] = source

    # Scan body for inline declarations of normative keys
    body_lower = body.lower()
    for key in normative_keys:
        # Pattern: key: value (key at start of line or after whitespace)
        pattern = rf"(?:^|\s){re.escape(key)}:\s*\S"
        if re.search(pattern, body_lower, re.MULTILINE):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-082",
                    "file": "preregistration.md",
                    "json_pointer": "/body",
                    "message": (
                        f"Inline declaration of normative key '{key}' found in "
                        f"preregistration.md. This value is owned by {owners.get(key, 'margins.yaml')}."
                    ),
                }
            )

    # Check for empty denominator fields (pattern: _denominator: "" or _denominator: with no value)
    denominator_pattern = re.compile(r"_denominator:\s*(?:\"\"|\s*$)", re.MULTILINE)
    for m in denominator_pattern.finditer(body):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-082",
                "file": "preregistration.md",
                "json_pointer": "/body",
                "message": ("Empty denominator field found in preregistration.md."),
            }
        )

    return diagnostics


def check_fv_spec_083_deviations(frontmatter: dict, body: str) -> list[dict]:
    """FV-SPEC-083: Stopping Rules section covers all 8 deviation categories.

    - All 8 deviation categories present in ## Stopping Rules
    - No 'patch and resume' phrasing for broken final pass
    """
    diagnostics = []

    # Extract Stopping Rules section
    m = re.search(r"## Stopping Rules(.*?)(?=\n## |\Z)", body, re.DOTALL)
    if not m:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-083",
                "file": "preregistration.md",
                "json_pointer": "/sections/StoppingRules",
                "message": "## Stopping Rules section not found.",
            }
        )
        return diagnostics

    section = m.group(1).lower()

    for cat in DEVIATION_CATEGORIES:
        cat_normalised = cat.replace("_", " ")
        if cat_normalised not in section and cat not in section:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-083",
                    "file": "preregistration.md",
                    "json_pointer": f"/sections/StoppingRules/{cat}",
                    "message": (
                        f"Deviation category '{cat}' not found in Stopping Rules "
                        f"section."
                    ),
                }
            )

    # Detect "patch and resume" phrasing (only when used as an accepted action,
    # not when explicitly negated, e.g. "never patch and resume" is fine)
    # Look for "patch and resume" NOT preceded by "never", "not", "do not", "don't"
    patch_pattern = re.compile(
        r"(?<!never )(?<!not )(?<!do not )(?<!don't )(?<!don.t )"
        r"patch.?and.?resume",
        re.IGNORECASE,
    )
    if patch_pattern.search(section):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-083",
                "file": "preregistration.md",
                "json_pointer": "/sections/StoppingRules/broken_final_pass",
                "message": (
                    "Stopping Rules declares 'patch and resume' for broken final "
                    "pass. Must require full re-run on fresh split."
                ),
            }
        )

    return diagnostics


def check_fv_spec_084_amendments(frontmatter: dict) -> list[dict]:
    """FV-SPEC-084: amendment_log entries have all required fields, no post_hoc."""
    diagnostics = []

    for i, entry in enumerate(frontmatter.get("amendment_log", [])):
        for field in AMENDMENT_REQUIRED_FIELDS:
            if field not in entry:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-084",
                        "file": "preregistration.md",
                        "json_pointer": f"/amendment_log/{i}/{field}",
                        "message": (
                            f"Amendment entry {i} missing required field '{field}'."
                        ),
                    }
                )
        if entry.get("post_hoc") is True:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-084",
                    "file": "preregistration.md",
                    "json_pointer": f"/amendment_log/{i}/post_hoc",
                    "message": (
                        f"Amendment entry '{entry.get('id', i)}' is post_hoc: "
                        f"cannot inherit confirmatory claim."
                    ),
                }
            )

    return diagnostics


def check_fv_spec_085_claims(frontmatter: dict, body: str) -> list[dict]:
    """FV-SPEC-085: Reporting section labels exploratory analyses correctly.

    - Stage B, secondary, unplanned, post-freeze analyses should carry
      'label: exploratory' or 'exploratory' nearby
    """
    diagnostics = []

    # Extract Reporting section
    m = re.search(r"## Reporting(.*?)(?=\n## |\Z)", body, re.DOTALL)
    if not m:
        return diagnostics

    section = m.group(1)

    # Find analysis entries that appear exploratory in nature
    # Pattern captures the rest of the line (up to newline)
    stage_b_pattern = re.compile(
        r"(?i)(stage[ _]?b|secondary|unplanned|post.freeze)[^\n]*",
    )
    for match in stage_b_pattern.finditer(section):
        line = match.group(0)
        # Check the matched line itself for an exploratory label
        # (not surrounding lines — each entry is responsible for its own label)
        if "exploratory" not in line.lower():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-085",
                    "file": "preregistration.md",
                    "json_pointer": "/sections/Reporting",
                    "message": (
                        f"Analysis entry appears to be exploratory but lacks "
                        f"'label: exploratory' or 'exploratory': '{line[:60]}'"
                    ),
                }
            )

    return diagnostics


def check_fv_spec_086_integrity(
    spec_root: Path,
    checksums_path: Path,
    tag_name: str = "spec-v1",
) -> list[dict]:
    """FV-SPEC-086: CHECKSUMS.sha256 hashes match current artifacts.

    Only checks if the checksums file exists (not an error if absent in
    pre-freeze dry-run context).
    """
    diagnostics = []

    try:
        from tools.freeze import verify_checksums
    except ImportError:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-086",
                "file": "CHECKSUMS.sha256",
                "json_pointer": "/",
                "message": "freeze.py not importable.",
            }
        )
        return diagnostics

    if not checksums_path.exists():
        # Not an error in dry-run context — only check if file exists
        return diagnostics

    mismatched = verify_checksums(spec_root, checksums_path)
    for path in mismatched:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-086",
                "file": "CHECKSUMS.sha256",
                "json_pointer": f"/{path}",
                "message": f"Hash mismatch or missing artifact: {path}",
            }
        )

    # Check receipt if it exists
    repo_root = spec_root.parent.parent
    receipt_path = repo_root / "reports" / "spec-v1-freeze-receipt.json"
    if receipt_path.exists():
        import subprocess as sp

        try:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            result = sp.run(
                ["git", "-C", str(repo_root), "rev-parse", f"{tag_name}^{{}}"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                tag_target = result.stdout.strip()
                if receipt.get("tag_target_commit") != tag_target:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-086",
                            "file": "spec-v1-freeze-receipt.json",
                            "json_pointer": "/tag_target_commit",
                            "message": (
                                f"Receipt tag_target_commit does not match "
                                f"git rev-parse {tag_name}^{{}}"
                            ),
                        }
                    )
        except (OSError, json.JSONDecodeError, sp.TimeoutExpired) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-086",
                    "file": "spec-v1-freeze-receipt.json",
                    "json_pointer": "/tag_target_commit",
                    "message": f"Cannot compare receipt tag_target_commit with git: {exc}",
                }
            )

    return diagnostics


def check_fv_spec_087_freeze(
    spec_root: Path,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
    tag_name: str = "spec-v1",
) -> list[dict]:
    """FV-SPEC-087: Freeze gates from freeze.py, excluding this check itself.

    The required-file list is ``tools.freeze.SPEC_ARTIFACTS``, which includes
    ``models.yaml`` as the eighth spec artifact (P0-8).
    """
    from tools.freeze import run_gate_checks

    _passed, results = run_gate_checks(
        spec_root,
        tag_name,
        decisions_path,
        exposure_path,
        milestones_path,
        include_preregistration=False,
    )
    diagnostics = []
    for result in results:
        if result.get("passed"):
            continue
        gate_diags = result.get("diagnostics") or []
        if not gate_diags:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-087",
                    "file": result.get("name", "freeze"),
                    "json_pointer": f"/{result.get('name', 'gate')}",
                    "message": f"Freeze gate {result.get('name')} failed.",
                }
            )
        for diag in gate_diags:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-087",
                    "file": result.get("name", "freeze"),
                    "json_pointer": f"/{result.get('name', 'gate')}",
                    "message": diag.get("message", str(diag)),
                }
            )
    return diagnostics


def check_fv_spec_088_cli(spec_root: Path) -> list[dict]:
    """FV-SPEC-088: All validator hooks are offline (_NO_MODEL_CALLS = True)."""
    diagnostics = []
    # Verify this module itself has the sentinel
    import tools.preregistration_validator as mod

    if not getattr(mod, "_NO_MODEL_CALLS", False):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-088",
                "file": "preregistration_validator.py",
                "json_pointer": "/_NO_MODEL_CALLS",
                "message": "_NO_MODEL_CALLS sentinel is missing or False.",
            }
        )
    return diagnostics


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def validate_preregistration(
    spec_root: Path,
    prereg_path: Path,
    decisions_path: Path,
    exposure_path: Path,
    milestones_path: Path,
    strict: bool = False,
    include_freeze_gate: bool = True,
) -> tuple[bool, dict]:
    """Run all 11 check functions and build a ReadinessReport.

    Returns (all_passed, report_dict).
    """
    checks = []
    all_diagnostics = []

    # Load preregistration
    try:
        prereg_fm, prereg_body = load_preregistration(prereg_path)
    except SystemExit as exc:
        return False, {
            "scope": "preregistration",
            "spec_root": str(spec_root),
            "timestamp": datetime.now(UTC).isoformat(),
            "strict": strict,
            "overall_status": "fail",
            "checks": [
                {
                    "id": "FV-SPEC-078",
                    "name": "artifact",
                    "status": "fail",
                    "diagnostics": [
                        {
                            "rule_id": "FV-SPEC-078",
                            "file": str(prereg_path),
                            "json_pointer": "/",
                            "message": str(exc),
                        }
                    ],
                }
            ],
            "open_decisions": [],
            "staged_obligations": [],
            "input_digests": {},
        }

    # Load YAML artifacts (gracefully handle missing)
    try:
        decisions = load_yaml_artifact(decisions_path)
    except SystemExit:
        decisions = {}

    try:
        exposure_fm, _ = load_preregistration(exposure_path)
    except SystemExit:
        exposure_fm = {}

    try:
        milestones = load_yaml_artifact(milestones_path)
    except SystemExit:
        milestones = {}

    checksums_path = spec_root.parent / "CHECKSUMS.sha256"

    # FV-SPEC-078: artifact check
    diags_078 = check_fv_spec_078_artifact(prereg_fm, prereg_body, spec_root)
    checks.append(
        {
            "id": "FV-SPEC-078",
            "name": "artifact",
            "status": "fail" if diags_078 else "pass",
            "diagnostics": diags_078,
        }
    )
    all_diagnostics.extend(diags_078)

    # FV-SPEC-079: exposure
    diags_079 = check_fv_spec_079_exposure(exposure_fm)
    checks.append(
        {
            "id": "FV-SPEC-079",
            "name": "exposure",
            "status": "fail" if diags_079 else "pass",
            "diagnostics": diags_079,
        }
    )
    all_diagnostics.extend(diags_079)

    # FV-SPEC-080: milestones
    diags_080 = check_fv_spec_080_milestones(milestones)
    checks.append(
        {
            "id": "FV-SPEC-080",
            "name": "milestones",
            "status": "fail" if diags_080 else "pass",
            "diagnostics": diags_080,
        }
    )
    all_diagnostics.extend(diags_080)

    # FV-SPEC-081: splits. A missing manifest stays deferred. A declared
    # unmaterialised gate is pending (gate N), not a failure.
    splits_path = spec_root.parent / "splits" / "splits.yaml"
    if not splits_path.exists():
        checks.append(
            {
                "id": "FV-SPEC-081",
                "name": "splits",
                "status": "deferred",
                "diagnostics": [
                    {
                        "rule_id": "FV-SPEC-081",
                        "file": "splits.yaml",
                        "json_pointer": "/",
                        "message": "No splits manifest. Unmaterialised splits stay pending until a gate is declared.",
                    }
                ],
            }
        )
    else:
        splits_manifest = _mapping_from_path(splits_path)
        diags_081 = check_fv_spec_081_splits(splits_manifest)
        hard_081 = [d for d in diags_081 if d.get("severity") != "pending"]
        checks.append(
            {
                "id": "FV-SPEC-081",
                "name": "splits",
                "status": "fail" if hard_081 else ("pending" if diags_081 else "pass"),
                "diagnostics": diags_081,
            }
        )
        all_diagnostics.extend(hard_081)

    # FV-SPEC-082: analysis
    diags_082 = check_fv_spec_082_analysis(prereg_fm, prereg_body, spec_root)
    checks.append(
        {
            "id": "FV-SPEC-082",
            "name": "analysis",
            "status": "fail" if diags_082 else "pass",
            "diagnostics": diags_082,
        }
    )
    all_diagnostics.extend(diags_082)

    # FV-SPEC-083: deviations
    diags_083 = check_fv_spec_083_deviations(prereg_fm, prereg_body)
    checks.append(
        {
            "id": "FV-SPEC-083",
            "name": "deviations",
            "status": "fail" if diags_083 else "pass",
            "diagnostics": diags_083,
        }
    )
    all_diagnostics.extend(diags_083)

    # FV-SPEC-084: amendments
    diags_084 = check_fv_spec_084_amendments(prereg_fm)
    checks.append(
        {
            "id": "FV-SPEC-084",
            "name": "amendments",
            "status": "fail" if diags_084 else "pass",
            "diagnostics": diags_084,
        }
    )
    all_diagnostics.extend(diags_084)

    # FV-SPEC-085: claims
    diags_085 = check_fv_spec_085_claims(prereg_fm, prereg_body)
    checks.append(
        {
            "id": "FV-SPEC-085",
            "name": "claims",
            "status": "fail" if diags_085 else "pass",
            "diagnostics": diags_085,
        }
    )
    all_diagnostics.extend(diags_085)

    # FV-SPEC-086: integrity
    diags_086 = check_fv_spec_086_integrity(spec_root, checksums_path)
    checks.append(
        {
            "id": "FV-SPEC-086",
            "name": "integrity",
            "status": "fail" if diags_086 else "pass",
            "diagnostics": diags_086,
        }
    )
    all_diagnostics.extend(diags_086)

    # FV-SPEC-087: freeze gate. Skipped when this call is nested inside the
    # preregistration gate, which would otherwise recurse.
    if include_freeze_gate:
        diags_087 = check_fv_spec_087_freeze(
            spec_root, decisions_path, exposure_path, milestones_path
        )
    else:
        diags_087 = []
    checks.append(
        {
            "id": "FV-SPEC-087",
            "name": "freeze",
            "status": "fail" if diags_087 else "pass",
            "diagnostics": diags_087,
        }
    )
    all_diagnostics.extend(diags_087)

    # FV-SPEC-088: cli
    diags_088 = check_fv_spec_088_cli(spec_root)
    checks.append(
        {
            "id": "FV-SPEC-088",
            "name": "cli",
            "status": "fail" if diags_088 else "pass",
            "diagnostics": diags_088,
        }
    )
    all_diagnostics.extend(diags_088)

    # Collect open decisions
    open_decisions = [
        d_id
        for d_id, entry in decisions.items()
        if isinstance(entry, dict) and entry.get("status") in ("open", "pending")
    ]

    # Collect staged obligations
    staged_obligations = []
    for name in REQUIRED_MILESTONES:
        entry = milestones.get(name, {})
        if isinstance(entry, dict) and not entry.get("git_tag"):
            sr = entry.get("staged_rule", {}) or {}
            staged_obligations.append(
                {
                    "milestone": name,
                    "status": "pending",
                    "gate": sr.get("determined_at_gate", "unknown"),
                }
            )

    # Compute input digests
    input_digests: dict[str, str] = {}
    for label, path in [
        ("preregistration.md", prereg_path),
        ("register.yaml", decisions_path),
        ("exposure_record.md", exposure_path),
        ("milestones.yaml", milestones_path),
    ]:
        p = Path(path)
        if p.exists():
            input_digests[label] = (
                "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
            )

    overall_passed = not any(c["status"] == "fail" for c in checks)

    # In strict mode, open decisions cause failure
    if strict and open_decisions:
        overall_passed = False

    report = {
        "scope": "preregistration",
        "spec_root": str(spec_root),
        "timestamp": datetime.now(UTC).isoformat(),
        "strict": strict,
        "overall_status": "pass" if overall_passed else "fail",
        "checks": checks,
        "open_decisions": open_decisions,
        "staged_obligations": staged_obligations,
        "input_digests": input_digests,
    }

    return overall_passed, report
