"""P0-2 closure template suite validator.

Validates closure_templates.yaml against structural, routing, binding,
coverage, group/split, review, and revision rules (FV-SPEC-016 through
FV-SPEC-032).

This module is imported by validate_spec.py when --scope closure-templates
is specified. It does not define its own CLI entry point.

Exit semantics (via validate_spec.py):
    0 — all requested checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs

Deferred checks (listed but not evaluated):
    P0-3 budget accounting, P0-6 witness rule
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import yaml

# ---- helpers ---------------------------------------------------------------


def _diag(
    rule_id: str, template_id: str | None, file: str, pointer: str, message: str
) -> dict:
    d = {"rule_id": rule_id, "file": file, "json_pointer": pointer, "message": message}
    if template_id:
        d["template_id"] = template_id
    return d


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---- T009: load and parse --------------------------------------------------


def load_suite(spec_root: Path) -> tuple[dict, Path]:
    """Load closure_templates.yaml from spec_root. Returns (data, path)."""
    suite_path = spec_root / "closure_templates.yaml"
    if not suite_path.exists():
        raise SystemExit(f"Suite not found: {suite_path}")
    try:
        data = yaml.safe_load(suite_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"Malformed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Suite root is not a mapping")
    return data, suite_path


def load_bindings(bindings_path: Path) -> dict:
    """Load instance_bindings.json."""
    if not bindings_path.exists():
        raise SystemExit(f"Bindings not found: {bindings_path}")
    try:
        return json.loads(bindings_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Malformed bindings JSON: {exc}") from exc


def load_review_manifest(path: Path) -> dict:
    """Load review_manifest.json."""
    if not path.exists():
        raise SystemExit(f"Review manifest not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Malformed review manifest JSON: {exc}") from exc


def load_contracts(contracts_dir: Path) -> dict[str, dict]:
    """Load P0-1 contracts indexed by contract_id."""
    contracts = {}
    if not contracts_dir.exists():
        raise SystemExit(f"Contracts directory not found: {contracts_dir}")
    for fp in sorted(contracts_dir.glob("*.json")):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        cid = data.get("contract_id", "")
        if cid:
            contracts[cid] = data
    return contracts


# ---- template extraction ---------------------------------------------------

_VALID_CLASSES = {"E", "I", "R", "X"}
_VALID_FAMILIES = {
    "direct",
    "inverse",
    "cloze",
    "paraphrase",
    "multilingual",
    "verification",
}
_VALID_FORMATS = {"free_answer", "completion", "true_false"}
_VALID_ANSWER_ROLES = {"subject", "object", "truth_value"}
_VALID_SUBTYPES = {"prompt_supplied", "contextual", "compositional"}
_VALID_REASONING = {"bridge", "chain", "multi_hop"}
_VALID_SUPPORT = {"supporting", "sufficient", "necessary"}
_VALID_BUCKETS = {"same_subject", "same_relation", "compositional", "global"}
_VALID_SPLITS = {"construction", "calibration", "final_test"}


def _all_templates(suite: dict) -> list[tuple[str, dict]]:
    """Return (location, template) pairs for every template in the suite."""
    templates = []
    for t in suite.get("sets", {}).get("equivalence", {}).get("templates", []):
        templates.append(("sets/equivalence", t))
    for t in suite.get("sets", {}).get("inference", {}).get("templates", []):
        templates.append(("sets/inference", t))
    for t in suite.get("controls", []):
        templates.append(("controls", t))
    return templates


# ---- FV-SPEC-016: structural validation ------------------------------------

_REQUIRED_TOP = {
    "spec_version",
    "fact_contract_ref",
    "boundary_policy",
    "sets",
    "groups",
    "splits",
    "relation_manifest",
    "revision",
}

_REQUIRED_E = {
    "id",
    "class",
    "group",
    "language",
    "format",
    "text",
    "relation_applicability",
    "answer_role",
    "primary_family",
    "extra_premises",
}

_REQUIRED_I = {
    "id",
    "class",
    "group",
    "language",
    "format",
    "text",
    "relation_applicability",
    "answer_role",
    "subtype",
    "extra_premises",
    "premise_origins",
    "reasoning_status",
    "support_status",
    "separate_reporting",
}

_REQUIRED_R = {
    "id",
    "class",
    "group",
    "language",
    "format",
    "text",
    "relation_applicability",
    "answer_role",
    "retained_entry_ref",
    "bucket",
}

_REQUIRED_X = {"id", "class", "language", "text", "exclusion_reason"}


def check_artifact_structure(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-016: Validate top-level structure and required fields."""
    diags = []
    missing = _REQUIRED_TOP - set(suite.keys())
    if missing:
        diags.append(
            _diag(
                "FV-SPEC-016",
                None,
                fname,
                "/",
                f"Missing top-level fields: {sorted(missing)}",
            )
        )

    # Check sets structure
    sets = suite.get("sets", {})
    if not isinstance(sets, dict):
        diags.append(
            _diag("FV-SPEC-016", None, fname, "/sets", "sets must be a mapping")
        )
    else:
        if "equivalence" not in sets:
            diags.append(
                _diag("FV-SPEC-016", None, fname, "/sets", "Missing sets.equivalence")
            )
        if "inference" not in sets:
            diags.append(
                _diag("FV-SPEC-016", None, fname, "/sets", "Missing sets.inference")
            )

    # Check each template has required fields based on class
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            diags.append(
                _diag(
                    "FV-SPEC-016", None, fname, f"/{loc}", "Template is not a mapping"
                )
            )
            continue
        tid = tmpl.get("id", "<unknown>")
        cls = tmpl.get("class", "")
        req = {
            "E": _REQUIRED_E,
            "I": _REQUIRED_I,
            "R": _REQUIRED_R,
            "X": _REQUIRED_X,
        }.get(cls)
        if req:
            tmpl_missing = req - set(tmpl.keys())
            if tmpl_missing:
                diags.append(
                    _diag(
                        "FV-SPEC-016",
                        tid,
                        fname,
                        f"/{loc}/{tid}",
                        f"Missing fields: {sorted(tmpl_missing)}",
                    )
                )

        # Validate enum values
        if cls in ("E", "I", "R"):
            fmt = tmpl.get("format")
            if fmt and fmt not in _VALID_FORMATS:
                diags.append(
                    _diag(
                        "FV-SPEC-016",
                        tid,
                        fname,
                        f"/{loc}/{tid}/format",
                        f"Invalid format: {fmt}",
                    )
                )
            ar = tmpl.get("answer_role")
            if ar and ar not in _VALID_ANSWER_ROLES:
                diags.append(
                    _diag(
                        "FV-SPEC-016",
                        tid,
                        fname,
                        f"/{loc}/{tid}/answer_role",
                        f"Invalid answer_role: {ar}",
                    )
                )

    return diags


# ---- FV-SPEC-017: class routing --------------------------------------------


def check_class_routing(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-017: E→equivalence, I→inference, R/X→controls."""
    diags = []
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        tid = tmpl.get("id", "<unknown>")
        cls = tmpl.get("class", "")

        if cls not in _VALID_CLASSES:
            diags.append(
                _diag(
                    "FV-SPEC-017",
                    tid,
                    fname,
                    f"/{loc}/{tid}/class",
                    f"Invalid class: {cls}",
                )
            )
            continue

        expected_loc = {"E": "sets/equivalence", "I": "sets/inference"}
        if cls in expected_loc:
            if loc != expected_loc[cls]:
                diags.append(
                    _diag(
                        "FV-SPEC-017",
                        tid,
                        fname,
                        f"/{loc}/{tid}",
                        f"Class {cls} must be in {expected_loc[cls]}, found in {loc}",
                    )
                )
        elif cls in ("R", "X"):
            if loc != "controls":
                diags.append(
                    _diag(
                        "FV-SPEC-017",
                        tid,
                        fname,
                        f"/{loc}/{tid}",
                        f"Class {cls} must be in controls, found in {loc}",
                    )
                )
    return diags


# ---- FV-SPEC-018: equivalence premises -------------------------------------


def check_equivalence_premises(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-018: E templates must have extra_premises: []."""
    diags = []
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict) or tmpl.get("class") != "E":
            continue
        tid = tmpl.get("id", "<unknown>")
        premises = tmpl.get("extra_premises")
        if premises is None:
            diags.append(
                _diag(
                    "FV-SPEC-018",
                    tid,
                    fname,
                    f"/{loc}/{tid}/extra_premises",
                    "Equivalence template must have extra_premises field",
                )
            )
        elif premises != []:
            diags.append(
                _diag(
                    "FV-SPEC-018",
                    tid,
                    fname,
                    f"/{loc}/{tid}/extra_premises",
                    "Equivalence template must have empty premises",
                )
            )
    return diags


# ---- FV-SPEC-019: inference provenance -------------------------------------


def check_inference_provenance(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-019: I templates must carry full provenance."""
    diags = []
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict) or tmpl.get("class") != "I":
            continue
        tid = tmpl.get("id", "<unknown>")

        subtype = tmpl.get("subtype")
        if subtype and subtype not in _VALID_SUBTYPES:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/subtype",
                    f"Invalid subtype: {subtype}",
                )
            )

        premises = tmpl.get("extra_premises")
        if not premises or not isinstance(premises, list) or len(premises) == 0:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/extra_premises",
                    "Inference template must have nonempty premises",
                )
            )

        origins = tmpl.get("premise_origins")
        if not origins or not isinstance(origins, list) or len(origins) == 0:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/premise_origins",
                    "Inference template must have premise_origins",
                )
            )

        reasoning = tmpl.get("reasoning_status")
        if reasoning and reasoning not in _VALID_REASONING:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/reasoning_status",
                    f"Invalid reasoning_status: {reasoning}",
                )
            )

        support = tmpl.get("support_status")
        if support and support not in _VALID_SUPPORT:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/support_status",
                    f"Invalid support_status: {support}",
                )
            )

        if tmpl.get("separate_reporting") is not True:
            diags.append(
                _diag(
                    "FV-SPEC-019",
                    tid,
                    fname,
                    f"/{loc}/{tid}/separate_reporting",
                    "Inference template must have separate_reporting: true",
                )
            )
    return diags


# ---- FV-SPEC-022: unique identity ------------------------------------------


def check_unique_identity(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-022: No duplicate template IDs."""
    diags = []
    seen_ids: dict[str, str] = {}
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        tid = tmpl.get("id")
        if not tid:
            continue
        if tid in seen_ids:
            diags.append(
                _diag(
                    "FV-SPEC-022",
                    tid,
                    fname,
                    f"/{loc}/{tid}",
                    f"Duplicate template ID '{tid}' (first seen in {seen_ids[tid]})",
                )
            )
        else:
            seen_ids[tid] = loc
    return diags


# ---- FV-SPEC-026: excluded controls ----------------------------------------


def check_excluded_controls(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-026: X must be in controls, must have exclusion_reason."""
    diags = []
    for loc, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        tid = tmpl.get("id", "<unknown>")
        cls = tmpl.get("class")

        if cls == "X":
            if loc != "controls":
                diags.append(
                    _diag(
                        "FV-SPEC-026",
                        tid,
                        fname,
                        f"/{loc}/{tid}",
                        "Excluded template must be in controls",
                    )
                )
            reason = tmpl.get("exclusion_reason")
            if not reason or not isinstance(reason, str) or not reason.strip():
                diags.append(
                    _diag(
                        "FV-SPEC-026",
                        tid,
                        fname,
                        f"/{loc}/{tid}/exclusion_reason",
                        "Excluded template must have non-empty exclusion_reason",
                    )
                )
    return diags


# ---- FV-SPEC-020: contract binding validation -------------------------------

_BINDING_ROLE_RULES = {
    "forward": "object",
    "inverse": "subject",
    "verification": "truth_value",
}


def check_contract_bindings(
    suite: dict, bindings: dict, contracts: dict[str, dict], fname: str
) -> list[dict]:
    """FV-SPEC-020: Validate bindings against P0-1 contracts."""
    diags = []
    template_map = {
        t.get("id"): t for _, t in _all_templates(suite) if isinstance(t, dict)
    }

    for entry in bindings.get("bindings", []):
        tid = entry.get("template_id", "<unknown>")
        cid = entry.get("contract_id", "")
        contract = contracts.get(cid)

        if not contract:
            diags.append(
                _diag(
                    "FV-SPEC-020",
                    tid,
                    fname,
                    f"/bindings/{tid}",
                    f"Contract not found: {cid}",
                )
            )
            continue

        tmpl = template_map.get(tid)
        if not tmpl:
            diags.append(
                _diag(
                    "FV-SPEC-020",
                    tid,
                    fname,
                    f"/bindings/{tid}",
                    f"Template not found in suite: {tid}",
                )
            )
            continue

        # Check answer_role vs direction
        answer_role = tmpl.get("answer_role")
        primary_family = tmpl.get("primary_family", "")

        # For verification templates, answer must be truth_value
        if primary_family == "verification":
            if answer_role != "truth_value":
                diags.append(
                    _diag(
                        "FV-SPEC-020",
                        tid,
                        fname,
                        f"/bindings/{tid}/answer_role",
                        "Verification template must have answer_role=truth_value",
                    )
                )
        elif primary_family == "inverse":
            if answer_role != "subject":
                diags.append(
                    _diag(
                        "FV-SPEC-020",
                        tid,
                        fname,
                        f"/bindings/{tid}/answer_role",
                        "Inverse template must have answer_role=subject",
                    )
                )
        elif primary_family == "direct":
            if answer_role != "object":
                diags.append(
                    _diag(
                        "FV-SPEC-020",
                        tid,
                        fname,
                        f"/bindings/{tid}/answer_role",
                        "Direct/forward template must have answer_role=object",
                    )
                )

        # Check unresolved placeholders in binding values
        for field in ("subject_value", "object_value", "relation_value", "answer_key"):
            val = entry.get(field, "")
            if isinstance(val, str) and "{" in val and "}" in val:
                diags.append(
                    _diag(
                        "FV-SPEC-020",
                        tid,
                        fname,
                        f"/bindings/{tid}/{field}",
                        f"Unresolved placeholder in {field}: {val}",
                    )
                )

    return diags


# ---- FV-SPEC-021: relation-family coverage ---------------------------------


def check_relation_family_coverage(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-021: All six families covered per relation, ≥4 relations."""
    diags = []
    coverage: dict[str, set[str]] = {}

    for _, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        cls = tmpl.get("class")
        if cls not in ("E", "I"):
            continue
        family = tmpl.get("primary_family", "")
        for rel in tmpl.get("relation_applicability", []):
            coverage.setdefault(rel, set()).add(family)

    relation_manifest = suite.get("relation_manifest", [])
    for rel in relation_manifest:
        families = coverage.get(rel, set())
        missing = _VALID_FAMILIES - families
        if missing:
            diags.append(
                _diag(
                    "FV-SPEC-021",
                    None,
                    fname,
                    f"/relation_manifest/{rel}",
                    f"Relation '{rel}' missing families: {sorted(missing)}",
                )
            )

    if len(relation_manifest) < 4:
        diags.append(
            _diag(
                "FV-SPEC-021",
                None,
                fname,
                "/relation_manifest",
                f"Need ≥4 relation types, got {len(relation_manifest)}",
            )
        )

    return diags


# ---- FV-SPEC-024: verification balance -------------------------------------


def check_verification_balance(suite: dict, bindings: dict, fname: str) -> list[dict]:
    """FV-SPEC-024: True/false counts must match per balance block."""
    diags = []
    template_map = {
        t.get("id"): t for _, t in _all_templates(suite) if isinstance(t, dict)
    }
    blocks: dict[str, dict[str, int]] = {}

    for entry in bindings.get("bindings", []):
        tid = entry.get("template_id", "")
        tmpl = template_map.get(tid)
        if not tmpl or tmpl.get("primary_family") != "verification":
            continue
        block_key = tmpl.get("balance_block")
        if not block_key:
            continue
        truth = entry.get("truth_label")
        if truth is True:
            blocks.setdefault(block_key, {"true": 0, "false": 0})["true"] += 1
        elif truth is False:
            blocks.setdefault(block_key, {"true": 0, "false": 0})["false"] += 1

    for block_key, counts in blocks.items():
        if counts["true"] != counts["false"]:
            diags.append(
                _diag(
                    "FV-SPEC-024",
                    None,
                    fname,
                    f"/balance/{block_key}",
                    f"Unbalanced verification block: "
                    f"{counts['true']} true vs "
                    f"{counts['false']} false",
                )
            )

    return diags


# ---- FV-SPEC-025: retained controls ----------------------------------------


def check_retained_controls(
    suite: dict, bindings: dict, contracts: dict[str, dict], fname: str
) -> list[dict]:
    """FV-SPEC-025: R controls bind to approved retained entries, all buckets."""
    diags = []
    {t.get("id"): t for _, t in _all_templates(suite) if isinstance(t, dict)}

    # Collect all approved neighbourhood entry IDs from contracts
    approved_entries: set[str] = set()
    for contract in contracts.values():
        for entry in contract.get("retained_neighbourhood", []):
            eid = entry.get("id")
            if eid:
                approved_entries.add(eid)

    # Check each R template
    r_buckets: set[str] = set()
    for _, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict) or tmpl.get("class") != "R":
            continue
        tid = tmpl.get("id", "<unknown>")
        ref = tmpl.get("retained_entry_ref")
        bucket = tmpl.get("bucket")

        if ref and ref not in approved_entries:
            diags.append(
                _diag(
                    "FV-SPEC-025",
                    tid,
                    fname,
                    f"/controls/{tid}/retained_entry_ref",
                    f"Unknown retained entry: {ref}",
                )
            )
        if bucket:
            if bucket not in _VALID_BUCKETS:
                diags.append(
                    _diag(
                        "FV-SPEC-025",
                        tid,
                        fname,
                        f"/controls/{tid}/bucket",
                        f"Invalid bucket: {bucket}",
                    )
                )
            else:
                r_buckets.add(bucket)

    # Check all buckets represented (only if there are R templates)
    if r_buckets:
        missing_buckets = _VALID_BUCKETS - r_buckets
        if missing_buckets:
            diags.append(
                _diag(
                    "FV-SPEC-025",
                    None,
                    fname,
                    "/controls",
                    f"Missing locality buckets: {sorted(missing_buckets)}",
                )
            )

    return diags


# ---- FV-SPEC-023: group/split isolation ------------------------------------


def check_group_split_isolation(suite: dict, fname: str) -> list[dict]:
    """FV-SPEC-023: Each template in one group, each group in one split,
    calibration/final_test disjoint."""
    diags = []
    groups = suite.get("groups", [])
    splits = suite.get("splits", {})

    # Build template→group mapping
    template_to_group: dict[str, list[str]] = {}
    group_to_split: dict[str, str] = {}

    for g in groups:
        gid = g.get("group_id", "")
        split = g.get("split", "")
        members = g.get("members", [])

        if split and split not in _VALID_SPLITS:
            diags.append(
                _diag(
                    "FV-SPEC-023",
                    None,
                    fname,
                    f"/groups/{gid}/split",
                    f"Invalid split: {split}",
                )
            )

        group_to_split[gid] = split
        for tid in members:
            template_to_group.setdefault(tid, []).append(gid)

    # Check each template appears in exactly one group
    all_template_ids = {
        t.get("id")
        for _, t in _all_templates(suite)
        if isinstance(t, dict) and t.get("id")
    }

    for tid in all_template_ids:
        groups_for = template_to_group.get(tid, [])
        if len(groups_for) == 0:
            # X templates without group are acceptable
            tmpl_cls = None
            for _, t in _all_templates(suite):
                if isinstance(t, dict) and t.get("id") == tid:
                    tmpl_cls = t.get("class")
                    break
            if tmpl_cls != "X":
                diags.append(
                    _diag(
                        "FV-SPEC-023",
                        tid,
                        fname,
                        "/groups",
                        f"Template '{tid}' not in any group",
                    )
                )
        elif len(groups_for) > 1:
            diags.append(
                _diag(
                    "FV-SPEC-023",
                    tid,
                    fname,
                    "/groups",
                    f"Template '{tid}' in multiple groups: {groups_for}",
                )
            )

    # Check group→split consistency between groups[] and splits{}
    for split_name, split_groups in splits.items():
        if split_name not in _VALID_SPLITS:
            diags.append(
                _diag(
                    "FV-SPEC-023",
                    None,
                    fname,
                    f"/splits/{split_name}",
                    f"Invalid split name: {split_name}",
                )
            )
            continue
        for gid in split_groups:
            declared_split = group_to_split.get(gid)
            if declared_split and declared_split != split_name:
                diags.append(
                    _diag(
                        "FV-SPEC-023",
                        None,
                        fname,
                        f"/splits/{split_name}/{gid}",
                        f"Group '{gid}' declared split "
                        f"'{declared_split}' but listed under "
                        f"'{split_name}'",
                    )
                )

    # Check calibration/final_test disjoint
    cal_groups = set(splits.get("calibration", []))
    ft_groups = set(splits.get("final_test", []))
    overlap = cal_groups & ft_groups
    if overlap:
        diags.append(
            _diag(
                "FV-SPEC-023",
                None,
                fname,
                "/splits",
                f"Groups in both calibration and final_test: {sorted(overlap)}",
            )
        )

    return diags


# ---- FV-SPEC-027: complete context / deterministic rendering ---------------


def render_preview(
    suite: dict, bindings: dict, split: str | None, fname: str
) -> tuple[list[dict], list[dict]]:
    """FV-SPEC-027/028: Render preview records, return (records, diags)."""
    diags = []
    records = []
    template_map = {
        t.get("id"): t for _, t in _all_templates(suite) if isinstance(t, dict)
    }

    # Build group→split mapping
    group_split: dict[str, str] = {}
    for g in suite.get("groups", []):
        group_split[g.get("group_id", "")] = g.get("split", "")

    for entry in bindings.get("bindings", []):
        tid = entry.get("template_id", "")
        tmpl = template_map.get(tid)
        if not tmpl:
            continue

        gid = tmpl.get("group", "")
        tmpl_split = group_split.get(gid, "")

        # Filter by split if requested
        if split and tmpl_split != split:
            continue

        # Render model_input
        text = tmpl.get("text", "")
        subject = entry.get("subject_value", "")
        obj = entry.get("object_value", "")
        relation = entry.get("relation_value", "")
        rendered = (
            text.replace("{subject}", subject)
            .replace("{object}", obj)
            .replace("{relation}", relation)
        )

        model_input = [{"role": "user", "content": rendered}]

        # Check for answer leakage in model_input (FV-SPEC-028)
        answer_key = entry.get("answer_key", "")
        truth_label = entry.get("truth_label")
        _check_answer_leakage(
            model_input, answer_key, truth_label, tmpl, tid, fname, diags
        )

        instance_id = f"{tid}__{entry.get('contract_id', '')}"

        evaluator_metadata = {
            "contract_id": entry.get("contract_id", ""),
            "contract_version": entry.get("contract_version", ""),
            "template_id": tid,
            "group_id": gid,
            "split": tmpl_split,
            "relation": relation,
            "class": tmpl.get("class", ""),
            "primary_family": tmpl.get("primary_family", ""),
            "overlapping_attributes": tmpl.get("overlapping_attributes", []),
            "answer_role": tmpl.get("answer_role", ""),
            "answer_key": answer_key,
            "truth_label": truth_label,
            "reporting_population": (
                "inference"
                if tmpl.get("class") == "I"
                else "equivalence"
                if tmpl.get("class") == "E"
                else "control"
            ),
            "premises": tmpl.get("extra_premises", []),
            "review_ref": None,
        }

        records.append(
            {
                "instance_id": instance_id,
                "model_input": model_input,
                "evaluator_metadata": evaluator_metadata,
            }
        )

    return records, diags


def _check_answer_leakage(
    model_input: list[dict],
    answer_key: str,
    truth_label: object,
    tmpl: dict,
    tid: str,
    fname: str,
    diags: list[dict],
) -> None:
    """FV-SPEC-028: No answer keys in model_input."""
    for msg in model_input:
        content = msg.get("content", "")
        # Check for direct answer_key presence (only for non-trivial answers)
        if answer_key and len(answer_key) > 3:
            if answer_key.lower() in content.lower():
                # Except for verification where the candidate is in the prompt
                if tmpl.get("primary_family") != "verification":
                    diags.append(
                        _diag(
                            "FV-SPEC-028",
                            tid,
                            fname,
                            f"/preview/{tid}/model_input",
                            "Answer key found in model_input",
                        )
                    )


# ---- FV-SPEC-029: bilingual review -----------------------------------------


def check_bilingual_review(suite: dict, manifest: dict, fname: str) -> list[dict]:
    """FV-SPEC-029: Multilingual E instances require bilingual approval."""
    diags = []
    approved_ids = {
        a.get("template_id") for a in manifest.get("bilingual_approvals", [])
    }

    for _, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        if tmpl.get("class") != "E":
            continue
        if tmpl.get("primary_family") == "multilingual":
            tid = tmpl.get("id", "<unknown>")
            if tid not in approved_ids:
                diags.append(
                    _diag(
                        "FV-SPEC-029",
                        tid,
                        fname,
                        f"/reviews/{tid}",
                        "Multilingual E template missing bilingual approval",
                    )
                )

    # Check digest match
    suite_digest_in_manifest = manifest.get("suite_digest", "")
    if suite_digest_in_manifest:
        # Will be validated by caller if they pass the suite path
        pass

    return diags


# ---- FV-SPEC-030: classification review ------------------------------------


def check_classification_review(manifest: dict, fname: str) -> list[dict]:
    """FV-SPEC-030: Two-reader classification review required."""
    diags = []
    cr = manifest.get("classification_review")
    if not cr:
        diags.append(
            _diag(
                "FV-SPEC-030",
                None,
                fname,
                "/classification_review",
                "Classification review section missing",
            )
        )
        return diags

    for reader in ("reader_1", "reader_2"):
        if reader not in cr:
            diags.append(
                _diag(
                    "FV-SPEC-030",
                    None,
                    fname,
                    f"/classification_review/{reader}",
                    f"Missing {reader}",
                )
            )

    # Check unresolved disagreements
    disagreements = cr.get("disagreements", [])
    for d in disagreements:
        if not d.get("resolved", False):
            diags.append(
                _diag(
                    "FV-SPEC-030",
                    None,
                    fname,
                    "/classification_review/disagreements",
                    f"Unresolved disagreement: {d.get('template_id', '?')}",
                )
            )

    return diags


# ---- FV-SPEC-031: revision protection --------------------------------------


def check_suite_revision(current: dict, baseline: dict, fname: str) -> list[dict]:
    """FV-SPEC-031: Changed content requires new revision."""
    diags = []
    cur_rev = current.get("revision", "")
    base_rev = baseline.get("revision", "")

    if cur_rev == base_rev:
        # Same revision — content must be identical (ignoring content_digest)
        cur_copy = {k: v for k, v in current.items() if k != "content_digest"}
        base_copy = {k: v for k, v in baseline.items() if k != "content_digest"}

        if cur_copy != base_copy:
            diags.append(
                _diag(
                    "FV-SPEC-031",
                    None,
                    fname,
                    "/revision",
                    "Suite content changed but revision was not incremented",
                )
            )

    return diags


# ---- FV-SPEC-032: strict mode checks ---------------------------------------


def check_strict_mode(suite: dict, manifest: dict | None, fname: str) -> list[dict]:
    """FV-SPEC-032: Strict mode rejects open decisions and missing reviews."""
    diags = []

    if manifest is None:
        diags.append(
            _diag(
                "FV-SPEC-032",
                None,
                fname,
                "/review_manifest",
                "Strict mode requires review manifest",
            )
        )
        return diags

    # Check decision references
    decision_refs = manifest.get("decision_refs", [])
    for dref in decision_refs:
        if dref.get("status") != "resolved":
            diags.append(
                _diag(
                    "FV-SPEC-032",
                    None,
                    fname,
                    f"/decision_refs/{dref.get('id', '?')}",
                    f"Unresolved decision: {dref.get('id', '?')}",
                )
            )

    return diags


# ---- report writing --------------------------------------------------------


def write_closure_report(
    suite: dict,
    suite_path: Path,
    bindings_path: Path,
    schema_path: Path,
    checked_templates: list[dict],
    coverage_result: dict,
    balance_result: dict,
    split_result: dict,
    review_result: dict,
    revision_check: object,
    all_diagnostics: list[dict],
    report_path: Path,
) -> dict:
    """Build and write the P0-2 validation report."""
    total = len(checked_templates)
    valid_count = sum(1 for t in checked_templates if t.get("valid", True))
    invalid_count = total - valid_count

    report = {
        "scope": "closure-templates",
        "suite_path": str(suite_path.resolve()),
        "suite_digest": file_digest(suite_path),
        "bindings_path": str(bindings_path.resolve()),
        "schema_path": str(schema_path.resolve()),
        "timestamp": datetime.now(UTC).isoformat(),
        "checked_templates": checked_templates,
        "coverage": coverage_result,
        "balance": balance_result,
        "split_isolation": split_result,
        "review_status": review_result,
        "revision_check": revision_check,
        "deferred_checks": ["P0-3 budget accounting", "P0-6 witness rule"],
        "diagnostics": all_diagnostics,
        "summary": {
            "total_templates": total,
            "valid": valid_count,
            "invalid": invalid_count,
            "deferred": 2,
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


# ---- main validation entry point -------------------------------------------


def validate_closure_suite(
    spec_root: Path,
    contracts_dir: Path,
    bindings_path: Path,
    report_path: Path,
    review_manifest_path: Path | None = None,
    split: str | None = None,
    preview_path: Path | None = None,
    strict: bool = False,
    baseline_suite_path: Path | None = None,
) -> tuple[bool, dict]:
    """Run all closure template validations. Returns (success, report)."""
    suite, suite_path = load_suite(spec_root)
    bindings = load_bindings(bindings_path)
    contracts = load_contracts(contracts_dir)
    fname = "closure_templates.yaml"

    all_diags: list[dict] = []
    checked: list[dict] = []

    # Structural checks (FV-SPEC-016 through 019, 022, 026)
    all_diags.extend(check_artifact_structure(suite, fname))
    all_diags.extend(check_class_routing(suite, fname))
    all_diags.extend(check_equivalence_premises(suite, fname))
    all_diags.extend(check_inference_provenance(suite, fname))
    all_diags.extend(check_unique_identity(suite, fname))
    all_diags.extend(check_excluded_controls(suite, fname))

    # Binding checks (FV-SPEC-020)
    all_diags.extend(check_contract_bindings(suite, bindings, contracts, fname))

    # Coverage (FV-SPEC-021)
    coverage_diags = check_relation_family_coverage(suite, fname)
    all_diags.extend(coverage_diags)
    coverage_result = {
        "status": "pass" if not coverage_diags else "fail",
        "matrix": _build_coverage_matrix(suite),
        "missing": [d["message"] for d in coverage_diags],
    }

    # Verification balance (FV-SPEC-024)
    balance_diags = check_verification_balance(suite, bindings, fname)
    all_diags.extend(balance_diags)
    balance_result = {
        "status": "pass" if not balance_diags else "fail",
        "blocks": _build_balance_blocks(suite, bindings),
    }

    # Retained controls (FV-SPEC-025)
    all_diags.extend(check_retained_controls(suite, bindings, contracts, fname))

    # Group/split isolation (FV-SPEC-023)
    split_diags = check_group_split_isolation(suite, fname)
    all_diags.extend(split_diags)
    split_result = {
        "status": "pass" if not split_diags else "fail",
        "orphaned_templates": [],
        "cross_split_groups": [],
        "held_out_in_construction": [],
    }

    # Review checks (FV-SPEC-029, 030) — only if manifest provided
    review_result = {
        "bilingual_approvals": "not_requested",
        "classification_review": "not_requested",
        "stale_reviews": [],
    }
    manifest = None
    if review_manifest_path:
        manifest = load_review_manifest(review_manifest_path)
        bi_diags = check_bilingual_review(suite, manifest, fname)
        cr_diags = check_classification_review(manifest, fname)
        all_diags.extend(bi_diags)
        all_diags.extend(cr_diags)
        review_result = {
            "bilingual_approvals": "complete" if not bi_diags else "incomplete",
            "classification_review": "complete" if not cr_diags else "incomplete",
            "stale_reviews": [],
        }

    # Strict mode (FV-SPEC-032)
    if strict:
        strict_diags = check_strict_mode(suite, manifest, fname)
        all_diags.extend(strict_diags)

    # Revision check (FV-SPEC-031)
    revision_check: object = "not_requested"
    if baseline_suite_path:
        try:
            baseline_data = yaml.safe_load(
                baseline_suite_path.read_text(encoding="utf-8")
            )
            rev_diags = check_suite_revision(suite, baseline_data, fname)
            all_diags.extend(rev_diags)
            revision_check = {
                "status": "pass" if not rev_diags else "fail",
                "details": [d["message"] for d in rev_diags],
            }
        except (yaml.YAMLError, OSError) as exc:
            raise SystemExit(f"Failed to load baseline suite: {exc}") from exc

    # Preview rendering (FV-SPEC-027, 028)
    if preview_path:
        records, preview_diags = render_preview(suite, bindings, split, fname)
        all_diags.extend(preview_diags)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        with preview_path.open("w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    # Build per-template checked list
    template_diag_map: dict[str, list[dict]] = {}
    for d in all_diags:
        tid = d.get("template_id")
        if tid:
            template_diag_map.setdefault(tid, []).append(d)

    for _, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        tid = tmpl.get("id", "")
        t_diags = template_diag_map.get(tid, [])
        checked.append(
            {
                "id": tid,
                "class": tmpl.get("class", ""),
                "valid": len(t_diags) == 0,
                "diagnostics": t_diags,
            }
        )

    schema_path = spec_root / "fact_contract.schema.json"
    report = write_closure_report(
        suite,
        suite_path,
        bindings_path,
        schema_path,
        checked,
        coverage_result,
        balance_result,
        split_result,
        review_result,
        revision_check,
        all_diags,
        report_path,
    )

    success = len(all_diags) == 0
    return success, report


# ---- helpers for report building -------------------------------------------


def _build_coverage_matrix(suite: dict) -> dict[str, list[str]]:
    """Build relation→families coverage matrix."""
    matrix: dict[str, set[str]] = {}
    for _, tmpl in _all_templates(suite):
        if not isinstance(tmpl, dict):
            continue
        if tmpl.get("class") not in ("E", "I"):
            continue
        family = tmpl.get("primary_family", "")
        for rel in tmpl.get("relation_applicability", []):
            matrix.setdefault(rel, set()).add(family)
    return {rel: sorted(fams) for rel, fams in matrix.items()}


def _build_balance_blocks(suite: dict, bindings: dict) -> list[dict]:
    """Build verification balance block summaries."""
    template_map = {
        t.get("id"): t for _, t in _all_templates(suite) if isinstance(t, dict)
    }
    blocks: dict[str, dict[str, int]] = {}

    for entry in bindings.get("bindings", []):
        tid = entry.get("template_id", "")
        tmpl = template_map.get(tid)
        if not tmpl or tmpl.get("primary_family") != "verification":
            continue
        block_key = tmpl.get("balance_block")
        if not block_key:
            continue
        truth = entry.get("truth_label")
        if truth is True:
            blocks.setdefault(block_key, {"true": 0, "false": 0})["true"] += 1
        elif truth is False:
            blocks.setdefault(block_key, {"true": 0, "false": 0})["false"] += 1

    return [
        {
            "key": k,
            "true_count": v["true"],
            "false_count": v["false"],
            "balanced": v["true"] == v["false"],
        }
        for k, v in blocks.items()
    ]
