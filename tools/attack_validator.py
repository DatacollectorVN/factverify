"""P0-3 attack specification validator.

Validates attacks.yaml against structural, allocation, accounting,
permission, confirmation, adaptive-policy, clue-audit, transformation,
relearning, cost-report, and revision-protection rules
(FV-SPEC-034 through FV-SPEC-046).

This module is imported by validate_spec.py when --scope attacks
is specified. It does not define its own CLI entry point.

Exit semantics (via validate_spec.py):
    0 — all requested checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs

Deferred checks (listed but not evaluated):
    P0-5 margin thresholds, P0-7 preregistration cross-reference
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# ── constants ──────────────────────────────────────────────────────

_VALID_ARM_IDS = {"native", "semantic_only", "factverify"}

_VALID_OPERATIONS = {
    "generation",
    "candidate_score",
    "training_step",
    "export",
    "cache_hit",
    "retry",
    "failure",
    "discard",
    "reference",
}

_VALID_OUTCOMES = {"completed", "cached", "retried", "failed", "discarded"}

_VALID_CHARGE_RULES = {
    "charged",
    "zero_new_compute",
    "separately_reported",
    "not_charged",
}

_VALID_EXPOSURE_TYPES = {"target_free", "target_exposed", "unknown"}

_VALID_EXPOSURE_CLASSES = {
    "clue_free",
    "alias_present",
    "inverse_present",
    "indirect_clue",
    "direct_disclosure",
}

_VALID_ROUTING = {"equivalence", "inference", "supplied_answer", "excluded"}

_VALID_POLICY_TYPES = {"fixed", "adaptive"}

_VALID_DECISION_STATUSES = {"open", "resolved", "not_applicable"}

_REQUIRED_TOP = {
    "spec_version",
    "revision",
    "upstream_refs",
    "common_cap",
    "accounting",
    "arms",
    "channels",
    "blocking_decisions",
}

_REQUIRED_UPSTREAM = {"fact_contract_schema", "closure_templates", "access_profile"}

_REQUIRED_UNIT = {"name", "definition", "multiplicity_rule", "identity_fields"}

_REQUIRED_POLICY_FIELDS = {
    "policy_id",
    "charge_rule",
    "observation_charged",
    "distinction",
}

_REQUIRED_ACCOUNTING = {
    "generation_trial_unit",
    "candidate_scoring_unit",
    "cost_vector_fields",
    "cache_policy",
    "retry_policy",
    "failure_policy",
    "discard_policy",
    "reference_cost_policy",
}

_REQUIRED_ARM = {"arm_id", "total", "channel_allocations"}

_REQUIRED_CHANNEL_ALLOC = {"channel_id", "trials", "purpose"}

_REQUIRED_CHANNEL = {
    "id",
    "name",
    "enabled",
    "purpose",
    "capability_requirements",
    "policy_source",
    "budget_source",
    "reporting_condition",
}

_REQUIRED_ADAPTIVE = {
    "policy_id",
    "channel_id",
    "policy_type",
    "search_space",
    "update_rule",
    "stop_rule",
    "discovery_limit",
    "confirmation_limit",
    "budget_ceiling",
}

_REQUIRED_SEARCH_SPACE = {"dimensions", "cardinality", "enumerable"}

_REQUIRED_RESERVATION = {
    "reservation_id",
    "route_ref",
    "channel_id",
    "reserved_trials",
    "includes_transformed",
    "includes_reference",
}

_REQUIRED_RECIPE = {
    "recipe_id",
    "channel_id",
    "algorithm",
    "software_version",
    "parent_checkpoint",
    "tokenizer",
    "decoding_config",
    "fitting_data_exposure",
    "reference_treatment",
    "output_provenance",
}

_REQUIRED_RELEARNING_CONDITION = {
    "condition_id",
    "exposure_type",
    "data_source",
    "schedule",
    "optimizer",
    "trainable_parameters",
    "held_out_evaluation",
    "reporting_contract",
}

_REQUIRED_REPORTING_CONTRACT = {
    "reached_format",
    "unreached_format",
    "substitution_prohibited",
}

_REQUIRED_AUDIT_MANIFEST = {
    "manifest_id",
    "revision",
    "content_digest",
    "channel_id",
    "entries",
    "reviewer_id",
    "review_date",
}

_REQUIRED_AUDIT_ENTRY = {
    "input_id",
    "input_type",
    "exposure_class",
    "routing",
    "rationale",
}

_REQUIRED_EVENT = {
    "event_id",
    "arm_id",
    "case_id",
    "phase",
    "channel_id",
    "operation",
    "outcome",
    "charge",
}

_REQUIRED_CHARGE = {"generation_trials", "new_compute", "policy_applied"}

_REQUIRED_DECISION = {"decision_id", "description", "status"}


# ── helpers ────────────────────────────────────────────────────────


def _diag(
    rule_id: str, item_id: str | None, file: str, pointer: str, message: str
) -> dict:
    d = {"rule_id": rule_id, "file": file, "json_pointer": pointer, "message": message}
    if item_id:
        d["item_id"] = item_id
    return d


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _check_required(
    data: dict,
    required: set,
    rule_id: str,
    item_id: str | None,
    file: str,
    pointer: str,
) -> list[dict]:
    diags = []
    for field in sorted(required - set(data.keys())):
        diags.append(
            _diag(
                rule_id,
                item_id,
                file,
                f"{pointer}/{field}",
                f"Missing required field: {field}",
            )
        )
    return diags


# ── load ───────────────────────────────────────────────────────────


def load_attack_spec(spec_root: Path) -> tuple[dict, Path]:
    """Load attacks.yaml from spec_root. Returns (data, path)."""
    spec_path = spec_root / "attacks.yaml"
    if not spec_path.exists():
        raise SystemExit(f"Attack spec not found: {spec_path}")
    try:
        data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"Malformed YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Attack spec root is not a mapping")
    return data, spec_path


def load_event_fixtures(path: Path) -> list[dict]:
    """Load event trace fixtures from JSON."""
    if not path.exists():
        raise SystemExit(f"Event fixtures not found: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Malformed event fixtures JSON: {exc}") from exc
    if not isinstance(data, list):
        raise SystemExit("Event fixtures root is not an array")
    return data


def load_audit_manifests(attacks_dir: Path) -> list[dict]:
    """Load all audit manifests from audit_manifests/ subdirectory."""
    audit_dir = attacks_dir / "audit_manifests"
    if not audit_dir.exists():
        return []
    manifests = []
    for fp in sorted(audit_dir.glob("*.json")):
        try:
            manifests.append(json.loads(fp.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
    return manifests


# ── FV-SPEC-034: artifact structure ───────────────────────────────


def check_artifact_structure(spec: dict, file: str) -> list[dict]:
    """Validate top-level structure of attacks.yaml."""
    diags = _check_required(spec, _REQUIRED_TOP, "FV-SPEC-034", None, file, "")

    # Check upstream_refs
    ups = spec.get("upstream_refs")
    if isinstance(ups, dict):
        diags.extend(
            _check_required(
                ups, _REQUIRED_UPSTREAM, "FV-SPEC-034", None, file, "/upstream_refs"
            )
        )

    # Check common_cap is positive integer
    cap = spec.get("common_cap")
    if cap is not None and (not isinstance(cap, int) or cap <= 0):
        diags.append(
            _diag(
                "FV-SPEC-034",
                None,
                file,
                "/common_cap",
                f"common_cap must be a positive integer, got {cap}",
            )
        )

    # Check arms is a list of 3
    arms = spec.get("arms")
    if isinstance(arms, list):
        if len(arms) != 3:
            diags.append(
                _diag(
                    "FV-SPEC-034",
                    None,
                    file,
                    "/arms",
                    f"Exactly 3 arms required, got {len(arms)}",
                )
            )
        arm_ids = set()
        for i, arm in enumerate(arms):
            if not isinstance(arm, dict):
                continue
            diags.extend(
                _check_required(
                    arm,
                    _REQUIRED_ARM,
                    "FV-SPEC-034",
                    arm.get("arm_id"),
                    file,
                    f"/arms/{i}",
                )
            )
            aid = arm.get("arm_id")
            if aid and aid not in _VALID_ARM_IDS:
                diags.append(
                    _diag(
                        "FV-SPEC-034",
                        aid,
                        file,
                        f"/arms/{i}/arm_id",
                        f"Unknown arm_id: {aid}",
                    )
                )
            if aid in arm_ids:
                diags.append(
                    _diag(
                        "FV-SPEC-034",
                        aid,
                        file,
                        f"/arms/{i}/arm_id",
                        f"Duplicate arm_id: {aid}",
                    )
                )
            arm_ids.add(aid)

    # Check channels
    channels = spec.get("channels")
    if isinstance(channels, list):
        chan_ids = set()
        for i, ch in enumerate(channels):
            if not isinstance(ch, dict):
                continue
            diags.extend(
                _check_required(
                    ch,
                    _REQUIRED_CHANNEL,
                    "FV-SPEC-034",
                    ch.get("id"),
                    file,
                    f"/channels/{i}",
                )
            )
            cid = ch.get("id")
            if cid in chan_ids:
                diags.append(
                    _diag(
                        "FV-SPEC-034",
                        cid,
                        file,
                        f"/channels/{i}/id",
                        f"Duplicate channel id: {cid}",
                    )
                )
            chan_ids.add(cid)

    # Check accounting
    acct = spec.get("accounting")
    if isinstance(acct, dict):
        diags.extend(
            _check_required(
                acct, _REQUIRED_ACCOUNTING, "FV-SPEC-034", None, file, "/accounting"
            )
        )

    # Check blocking_decisions
    decisions = spec.get("blocking_decisions")
    if isinstance(decisions, list):
        for i, d in enumerate(decisions):
            if isinstance(d, dict):
                diags.extend(
                    _check_required(
                        d,
                        _REQUIRED_DECISION,
                        "FV-SPEC-034",
                        d.get("decision_id"),
                        file,
                        f"/blocking_decisions/{i}",
                    )
                )

    return diags


# ── FV-SPEC-035: channel permissions ──────────────────────────────


def check_channel_permissions(
    spec: dict, file: str, access_profile: dict | None
) -> list[dict]:
    """Cross-check enabled channels against access profile capabilities."""
    diags = []
    channels = spec.get("channels", [])

    if access_profile is None:
        return diags  # not checked if profile not provided

    available = access_profile.get("capabilities", {})

    for i, ch in enumerate(channels):
        if not isinstance(ch, dict) or not ch.get("enabled"):
            continue
        reqs = ch.get("capability_requirements", {})
        cid = ch.get("id", f"channel_{i}")
        for cap, needed in reqs.items():
            if needed and not available.get(cap, False):
                diags.append(
                    _diag(
                        "FV-SPEC-035",
                        cid,
                        file,
                        f"/channels/{i}/capability_requirements/{cap}",
                        f"Channel '{cid}' requires '{cap}' but access "
                        f"profile does not provide it",
                    )
                )
    return diags


# ── FV-SPEC-036: accounting units ─────────────────────────────────


def check_accounting_units(spec: dict, file: str) -> list[dict]:
    """Validate accounting unit definitions."""
    diags = []
    acct = spec.get("accounting", {})

    for unit_key in ("generation_trial_unit", "candidate_scoring_unit"):
        unit = acct.get(unit_key)
        if not isinstance(unit, dict):
            continue
        diags.extend(
            _check_required(
                unit,
                _REQUIRED_UNIT,
                "FV-SPEC-036",
                None,
                file,
                f"/accounting/{unit_key}",
            )
        )
        # identity_fields must be nonempty list
        idf = unit.get("identity_fields")
        if isinstance(idf, list) and len(idf) == 0:
            diags.append(
                _diag(
                    "FV-SPEC-036",
                    None,
                    file,
                    f"/accounting/{unit_key}/identity_fields",
                    "identity_fields must be nonempty",
                )
            )

    # cost_vector_fields must be nonempty
    cvf = acct.get("cost_vector_fields")
    if isinstance(cvf, list) and len(cvf) == 0:
        diags.append(
            _diag(
                "FV-SPEC-036",
                None,
                file,
                "/accounting/cost_vector_fields",
                "cost_vector_fields must be nonempty",
            )
        )

    return diags


# ── FV-SPEC-037: event policies ───────────────────────────────────


def check_event_policies(spec: dict, file: str) -> list[dict]:
    """Validate cache, retry, failure, discard, reference policies."""
    diags = []
    acct = spec.get("accounting", {})

    for policy_key in (
        "cache_policy",
        "retry_policy",
        "failure_policy",
        "discard_policy",
        "reference_cost_policy",
    ):
        pol = acct.get(policy_key)
        if not isinstance(pol, dict):
            continue
        diags.extend(
            _check_required(
                pol,
                _REQUIRED_POLICY_FIELDS,
                "FV-SPEC-037",
                None,
                file,
                f"/accounting/{policy_key}",
            )
        )
        cr = pol.get("charge_rule")
        if cr and cr not in _VALID_CHARGE_RULES:
            diags.append(
                _diag(
                    "FV-SPEC-037",
                    None,
                    file,
                    f"/accounting/{policy_key}/charge_rule",
                    f"Invalid charge_rule: {cr}",
                )
            )

    return diags


# ── FV-SPEC-038: matched allocations ──────────────────────────────


def check_matched_allocations(spec: dict, file: str) -> list[dict]:
    """Validate all three arms sum to common_cap."""
    diags = []
    cap = spec.get("common_cap")
    arms = spec.get("arms", [])
    channels = {
        ch.get("id"): ch for ch in spec.get("channels", []) if isinstance(ch, dict)
    }

    if not isinstance(cap, int) or not isinstance(arms, list):
        return diags

    for i, arm in enumerate(arms):
        if not isinstance(arm, dict):
            continue
        aid = arm.get("arm_id", f"arm_{i}")
        total = arm.get("total")

        # Check total matches cap
        if isinstance(total, int) and total != cap:
            diags.append(
                _diag(
                    "FV-SPEC-038",
                    f"arm:{aid}",
                    file,
                    f"/arms/{i}/total",
                    f"Arm total ({total}) != common_cap ({cap})",
                )
            )

        # Check allocation sum
        allocs = arm.get("channel_allocations", [])
        alloc_sum = 0
        for j, alloc in enumerate(allocs):
            if not isinstance(alloc, dict):
                continue
            trials = alloc.get("trials", 0)
            if isinstance(trials, int):
                if trials < 0:
                    diags.append(
                        _diag(
                            "FV-SPEC-038",
                            f"arm:{aid}",
                            file,
                            f"/arms/{i}/channel_allocations/{j}/trials",
                            f"Negative allocation: {trials}",
                        )
                    )
                alloc_sum += trials

                # Check disabled channel has no allocation
                cid = alloc.get("channel_id")
                if cid and cid in channels:
                    ch = channels[cid]
                    if not ch.get("enabled", True) and trials > 0:
                        diags.append(
                            _diag(
                                "FV-SPEC-038",
                                f"arm:{aid}",
                                file,
                                f"/arms/{i}/channel_allocations/{j}/trials",
                                f"Disabled channel '{cid}' has {trials} trials",
                            )
                        )

        if isinstance(total, int) and alloc_sum != total:
            diags.append(
                _diag(
                    "FV-SPEC-038",
                    f"arm:{aid}",
                    file,
                    f"/arms/{i}/channel_allocations",
                    f"Allocation sum ({alloc_sum}) != arm total ({total})",
                )
            )

    return diags


# ── FV-SPEC-039: confirmation reservations ────────────────────────


def check_confirmation_reservations(spec: dict, file: str) -> list[dict]:
    """Validate confirmation route budget reservations."""
    diags = []
    reservations = spec.get("confirmation_reservations", [])

    if not isinstance(reservations, list):
        return diags

    res_ids = set()
    for i, res in enumerate(reservations):
        if not isinstance(res, dict):
            continue
        diags.extend(
            _check_required(
                res,
                _REQUIRED_RESERVATION,
                "FV-SPEC-039",
                res.get("reservation_id"),
                file,
                f"/confirmation_reservations/{i}",
            )
        )
        rid = res.get("reservation_id")
        if rid in res_ids:
            diags.append(
                _diag(
                    "FV-SPEC-039",
                    rid,
                    file,
                    f"/confirmation_reservations/{i}",
                    f"Duplicate reservation_id: {rid}",
                )
            )
        res_ids.add(rid)

        trials = res.get("reserved_trials")
        if isinstance(trials, int) and trials <= 0:
            diags.append(
                _diag(
                    "FV-SPEC-039",
                    rid,
                    file,
                    f"/confirmation_reservations/{i}/reserved_trials",
                    f"reserved_trials must be positive, got {trials}",
                )
            )

        # Check for double-funded shared calls
        shared = res.get("shared_with", [])
        if isinstance(shared, list):
            for partner in shared:
                if partner == rid:
                    diags.append(
                        _diag(
                            "FV-SPEC-039",
                            rid,
                            file,
                            f"/confirmation_reservations/{i}/shared_with",
                            "Reservation cannot share with itself",
                        )
                    )

    return diags


# ── FV-SPEC-040: adaptive policies ────────────────────────────────


def check_adaptive_policies(spec: dict, file: str) -> list[dict]:
    """Validate adaptive policy declarations are finite and bounded."""
    diags = []
    policies = spec.get("adaptive_policies", [])

    if not isinstance(policies, list):
        return diags

    for i, pol in enumerate(policies):
        if not isinstance(pol, dict):
            continue
        pid = pol.get("policy_id", f"policy_{i}")
        diags.extend(
            _check_required(
                pol,
                _REQUIRED_ADAPTIVE,
                "FV-SPEC-040",
                pid,
                file,
                f"/adaptive_policies/{i}",
            )
        )

        ptype = pol.get("policy_type")
        if ptype and ptype not in _VALID_POLICY_TYPES:
            diags.append(
                _diag(
                    "FV-SPEC-040",
                    pid,
                    file,
                    f"/adaptive_policies/{i}/policy_type",
                    f"Invalid policy_type: {ptype}",
                )
            )

        # Check search_space
        ss = pol.get("search_space")
        if isinstance(ss, dict):
            diags.extend(
                _check_required(
                    ss,
                    _REQUIRED_SEARCH_SPACE,
                    "FV-SPEC-040",
                    pid,
                    file,
                    f"/adaptive_policies/{i}/search_space",
                )
            )
            card = ss.get("cardinality")
            if isinstance(card, int) and card <= 0:
                diags.append(
                    _diag(
                        "FV-SPEC-040",
                        pid,
                        file,
                        f"/adaptive_policies/{i}/search_space/cardinality",
                        f"cardinality must be positive, got {card}",
                    )
                )

        # Check budget_ceiling
        ceil = pol.get("budget_ceiling")
        if isinstance(ceil, int) and ceil <= 0:
            diags.append(
                _diag(
                    "FV-SPEC-040",
                    pid,
                    file,
                    f"/adaptive_policies/{i}/budget_ceiling",
                    f"budget_ceiling must be positive, got {ceil}",
                )
            )

        # Stop rule must be declared
        sr = pol.get("stop_rule")
        if not sr or (isinstance(sr, str) and not sr.strip()):
            diags.append(
                _diag(
                    "FV-SPEC-040",
                    pid,
                    file,
                    f"/adaptive_policies/{i}/stop_rule",
                    "stop_rule must be declared",
                )
            )

    return diags


# ── FV-SPEC-041: clue audit ──────────────────────────────────────


def check_clue_audit(spec: dict, file: str, audit_manifests: list[dict]) -> list[dict]:
    """Validate clue audit manifests for version-bound exposure review."""
    diags = []

    for i, manifest in enumerate(audit_manifests):
        if not isinstance(manifest, dict):
            continue
        mid = manifest.get("manifest_id", f"manifest_{i}")
        diags.extend(
            _check_required(
                manifest,
                _REQUIRED_AUDIT_MANIFEST,
                "FV-SPEC-041",
                mid,
                f"audit_manifest_{i}.json",
                "",
            )
        )

        # Check revision is present (version-bound)
        if not manifest.get("revision"):
            diags.append(
                _diag(
                    "FV-SPEC-041",
                    mid,
                    f"audit_manifest_{i}.json",
                    "/revision",
                    "Audit must be version-bound with revision",
                )
            )

        # Check entries
        entries = manifest.get("entries", [])
        for j, entry in enumerate(entries):
            if not isinstance(entry, dict):
                continue
            diags.extend(
                _check_required(
                    entry,
                    _REQUIRED_AUDIT_ENTRY,
                    "FV-SPEC-041",
                    entry.get("input_id", mid),
                    f"audit_manifest_{i}.json",
                    f"/entries/{j}",
                )
            )

            ec = entry.get("exposure_class")
            if ec and ec not in _VALID_EXPOSURE_CLASSES:
                diags.append(
                    _diag(
                        "FV-SPEC-041",
                        entry.get("input_id", mid),
                        f"audit_manifest_{i}.json",
                        f"/entries/{j}/exposure_class",
                        f"Invalid exposure_class: {ec}",
                    )
                )

            routing = entry.get("routing")
            if routing and routing not in _VALID_ROUTING:
                diags.append(
                    _diag(
                        "FV-SPEC-041",
                        entry.get("input_id", mid),
                        f"audit_manifest_{i}.json",
                        f"/entries/{j}/routing",
                        f"Invalid routing: {routing}",
                    )
                )

            # Direct disclosure must NOT route to equivalence
            if ec == "direct_disclosure" and routing == "equivalence":
                diags.append(
                    _diag(
                        "FV-SPEC-041",
                        entry.get("input_id", mid),
                        f"audit_manifest_{i}.json",
                        f"/entries/{j}/routing",
                        "Direct disclosure must not enter equivalence recovery",
                    )
                )

    return diags


# ── FV-SPEC-042: transformation recipes ───────────────────────────


def check_transformations(spec: dict, file: str) -> list[dict]:
    """Validate transformation recipe completeness."""
    diags = []
    recipes = spec.get("transformations", [])
    if not isinstance(recipes, list):
        return diags

    {ch.get("id"): ch for ch in spec.get("channels", []) if isinstance(ch, dict)}

    for i, recipe in enumerate(recipes):
        if not isinstance(recipe, dict):
            continue
        rid = recipe.get("recipe_id", f"recipe_{i}")
        diags.extend(
            _check_required(
                recipe,
                _REQUIRED_RECIPE,
                "FV-SPEC-042",
                rid,
                file,
                f"/transformations/{i}",
            )
        )

        fde = recipe.get("fitting_data_exposure")
        if fde and fde not in _VALID_EXPOSURE_TYPES:
            diags.append(
                _diag(
                    "FV-SPEC-042",
                    rid,
                    file,
                    f"/transformations/{i}/fitting_data_exposure",
                    f"Invalid fitting_data_exposure: {fde}",
                )
            )

    return diags


# ── FV-SPEC-043: relearning conditions ────────────────────────────


def check_relearning(spec: dict, file: str) -> list[dict]:
    """Validate relearning conditions separated by exposure type."""
    diags = []
    relearning = spec.get("relearning")
    if relearning is None:
        return diags  # not applicable if absent

    if not isinstance(relearning, dict):
        return [
            _diag(
                "FV-SPEC-043", None, file, "/relearning", "relearning must be a mapping"
            )
        ]

    conditions = relearning.get("conditions", [])
    if not isinstance(conditions, list):
        return diags

    exposure_types_seen = set()
    for i, cond in enumerate(conditions):
        if not isinstance(cond, dict):
            continue
        cid = cond.get("condition_id", f"condition_{i}")
        diags.extend(
            _check_required(
                cond,
                _REQUIRED_RELEARNING_CONDITION,
                "FV-SPEC-043",
                cid,
                file,
                f"/relearning/conditions/{i}",
            )
        )

        et = cond.get("exposure_type")
        if et and et not in {"target_free", "target_exposed"}:
            diags.append(
                _diag(
                    "FV-SPEC-043",
                    cid,
                    file,
                    f"/relearning/conditions/{i}/exposure_type",
                    f"Invalid exposure_type: {et}",
                )
            )
        if et:
            exposure_types_seen.add(et)

        # Check reporting contract
        rc = cond.get("reporting_contract")
        if isinstance(rc, dict):
            diags.extend(
                _check_required(
                    rc,
                    _REQUIRED_REPORTING_CONTRACT,
                    "FV-SPEC-043",
                    cid,
                    file,
                    f"/relearning/conditions/{i}/reporting_contract",
                )
            )
            if rc.get("substitution_prohibited") is False:
                diags.append(
                    _diag(
                        "FV-SPEC-043",
                        cid,
                        file,
                        f"/relearning/conditions/{i}/reporting_contract/substitution_prohibited",
                        "substitution_prohibited must be true",
                    )
                )

    # Must have both exposure types if relearning is enabled
    if relearning.get("enabled", False):
        if "target_free" not in exposure_types_seen:
            diags.append(
                _diag(
                    "FV-SPEC-043",
                    None,
                    file,
                    "/relearning/conditions",
                    "Missing target_free condition",
                )
            )
        if "target_exposed" not in exposure_types_seen:
            diags.append(
                _diag(
                    "FV-SPEC-043",
                    None,
                    file,
                    "/relearning/conditions",
                    "Missing target_exposed condition",
                )
            )

    return diags


# ── FV-SPEC-044: cost records ─────────────────────────────────────


def generate_cost_records(spec: dict, events: list[dict] | None) -> list[dict]:
    """Generate per-arm cost records from spec and optional event traces."""
    records = []
    cap = spec.get("common_cap", 0)

    for arm in spec.get("arms", []):
        if not isinstance(arm, dict):
            continue
        aid = arm.get("arm_id", "unknown")
        total = arm.get("total", 0)
        record = {
            "arm_id": aid,
            "cap": cap,
            "actual_trials": 0,
            "unused_trials": total,
            "generation_trials": 0,
            "candidate_scores": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "training_steps": 0,
            "training_examples": 0,
            "exports": 0,
            "wall_clock_seconds": 0.0,
        }

        # Sum from event traces if available
        if events:
            for trace in events:
                if not isinstance(trace, dict):
                    continue
                if trace.get("arm_id") != aid:
                    continue
                for evt in trace.get("events", []):
                    if not isinstance(evt, dict):
                        continue
                    charge = evt.get("charge", {})
                    record["generation_trials"] += charge.get("generation_trials", 0)
                    record["candidate_scores"] += charge.get("candidate_scores", 0)
                    record["input_tokens"] += charge.get("input_tokens", 0)
                    record["output_tokens"] += charge.get("output_tokens", 0)
                    record["training_steps"] += charge.get("training_steps", 0)

            record["actual_trials"] = record["generation_trials"]
            record["unused_trials"] = total - record["actual_trials"]

        records.append(record)

    return records


def check_cost_records(spec: dict, events: list[dict] | None, file: str) -> list[dict]:
    """Validate cost record completeness (FV-SPEC-044)."""
    diags = []

    if events is None:
        return diags

    # Verify each event has required charge fields
    for t_idx, trace in enumerate(events):
        if not isinstance(trace, dict):
            continue
        for e_idx, evt in enumerate(trace.get("events", [])):
            if not isinstance(evt, dict):
                continue
            charge = evt.get("charge")
            if not isinstance(charge, dict):
                diags.append(
                    _diag(
                        "FV-SPEC-044",
                        evt.get("event_id"),
                        "event_fixtures.json",
                        f"/{t_idx}/events/{e_idx}/charge",
                        "Missing charge record",
                    )
                )
                continue
            diags.extend(
                _check_required(
                    charge,
                    _REQUIRED_CHARGE,
                    "FV-SPEC-044",
                    evt.get("event_id"),
                    "event_fixtures.json",
                    f"/{t_idx}/events/{e_idx}/charge",
                )
            )

    return diags


# ── FV-SPEC-045: revision protection ──────────────────────────────


def check_revision_protection(spec: dict, baseline: dict | None, file: str) -> dict:
    """Compare current spec against baseline for unauthorized changes."""
    if baseline is None:
        return {"status": "not_requested"}

    current_rev = spec.get("revision", "")
    baseline_rev = baseline.get("revision", "")

    if current_rev != baseline_rev:
        return {
            "status": "pass",
            "detail": f"Revision changed: {baseline_rev} -> {current_rev}",
        }

    # Same revision — content must be identical
    diffs = []

    def _compare(path: str, cur: Any, base: Any) -> None:
        if type(cur) is not type(base):
            diffs.append(f"{path}: type changed")
            return
        if isinstance(cur, dict):
            all_keys = set(cur.keys()) | set(base.keys())
            for k in sorted(all_keys):
                _compare(f"{path}/{k}", cur.get(k), base.get(k))
        elif isinstance(cur, list):
            if len(cur) != len(base):
                diffs.append(f"{path}: length changed {len(base)} -> {len(cur)}")
                return
            for i, (c, b) in enumerate(zip(cur, base)):
                _compare(f"{path}/{i}", c, b)
        elif cur != base:
            diffs.append(f"{path}: value changed")

    # Compare key sections
    for section in (
        "channels",
        "arms",
        "accounting",
        "adaptive_policies",
        "confirmation_reservations",
        "transformations",
        "relearning",
    ):
        _compare(f"/{section}", spec.get(section), baseline.get(section))

    if diffs:
        return {
            "status": "fail",
            "detail": f"Content changed under same revision '{current_rev}'",
            "differences": diffs[:20],
        }

    return {"status": "pass", "detail": "Content identical to baseline"}


# ── FV-SPEC-046: strict mode ──────────────────────────────────────


def check_strict_mode(spec: dict, file: str, audit_manifests: list[dict]) -> list[dict]:
    """Strict mode: reject unresolved blocking decisions and missing audits."""
    diags = []

    # Check blocking decisions
    decisions = spec.get("blocking_decisions", [])
    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            continue
        if d.get("status") == "open":
            diags.append(
                _diag(
                    "FV-SPEC-046",
                    d.get("decision_id"),
                    file,
                    f"/blocking_decisions/{i}",
                    f"Unresolved decision: {d.get('decision_id')} — "
                    f"{d.get('description', '')}",
                )
            )

    # Check enabled channels have audit coverage
    channels = spec.get("channels", [])
    enabled_channels = {
        ch.get("id") for ch in channels if isinstance(ch, dict) and ch.get("enabled")
    }
    audited_channels = {
        m.get("channel_id") for m in audit_manifests if isinstance(m, dict)
    }

    # Only warn about channels that might need clue audits
    # (prompt-based channels, not pure metric channels)
    prompt_channels = {"prompt_variation", "adversarial_wrapper", "few_shot_priming"}
    for cid in enabled_channels & prompt_channels - audited_channels:
        diags.append(
            _diag(
                "FV-SPEC-046",
                cid,
                file,
                "/channels",
                f"No clue audit manifest for enabled channel: {cid}",
            )
        )

    return diags


# ── event trace replay ────────────────────────────────────────────


def replay_event_traces(spec: dict, events: list[dict], file: str) -> list[dict]:
    """Replay event traces against declared charge policies (FV-SPEC-036/037)."""
    diags = []
    acct = spec.get("accounting", {})

    # Build policy lookup
    policies = {}
    for key in (
        "cache_policy",
        "retry_policy",
        "failure_policy",
        "discard_policy",
        "reference_cost_policy",
    ):
        pol = acct.get(key)
        if isinstance(pol, dict):
            policies[pol.get("policy_id", key)] = pol

    for t_idx, trace in enumerate(events):
        if not isinstance(trace, dict):
            continue
        for e_idx, evt in enumerate(trace.get("events", [])):
            if not isinstance(evt, dict):
                continue

            # Validate event structure
            diags.extend(
                _check_required(
                    evt,
                    _REQUIRED_EVENT,
                    "FV-SPEC-036",
                    evt.get("event_id"),
                    "event_fixtures.json",
                    f"/{t_idx}/events/{e_idx}",
                )
            )

            op = evt.get("operation")
            if op and op not in _VALID_OPERATIONS:
                diags.append(
                    _diag(
                        "FV-SPEC-036",
                        evt.get("event_id"),
                        "event_fixtures.json",
                        f"/{t_idx}/events/{e_idx}/operation",
                        f"Invalid operation: {op}",
                    )
                )

            outcome = evt.get("outcome")
            if outcome and outcome not in _VALID_OUTCOMES:
                diags.append(
                    _diag(
                        "FV-SPEC-036",
                        evt.get("event_id"),
                        "event_fixtures.json",
                        f"/{t_idx}/events/{e_idx}/outcome",
                        f"Invalid outcome: {outcome}",
                    )
                )

            # Verify charge matches declared policy
            charge = evt.get("charge", {})
            policy_id = charge.get("policy_applied")
            if policy_id and policy_id in policies:
                pol = policies[policy_id]
                cr = pol.get("charge_rule")

                if cr == "zero_new_compute" and charge.get("new_compute"):
                    diags.append(
                        _diag(
                            "FV-SPEC-037",
                            evt.get("event_id"),
                            "event_fixtures.json",
                            f"/{t_idx}/events/{e_idx}/charge",
                            f"Policy '{policy_id}' is zero_new_compute but "
                            f"event claims new_compute=true",
                        )
                    )

                if cr == "charged" and charge.get("generation_trials", 0) == 0:
                    # Charged events should have at least one trial
                    if op in ("generation", "retry"):
                        diags.append(
                            _diag(
                                "FV-SPEC-037",
                                evt.get("event_id"),
                                "event_fixtures.json",
                                f"/{t_idx}/events/{e_idx}/charge",
                                f"Policy '{policy_id}' is charged but "
                                f"event has 0 generation_trials",
                            )
                        )

    return diags


# ── report writer ─────────────────────────────────────────────────


def write_attack_report(
    spec_path: Path,
    report_path: Path,
    spec: dict,
    all_diags: list[dict],
    allocation_diags: list[dict],
    permission_diags: list[dict],
    accounting_diags: list[dict],
    event_replay_diags: list[dict],
    confirmation_diags: list[dict],
    policy_diags: list[dict],
    audit_diags: list[dict],
    transformation_diags: list[dict],
    relearning_diags: list[dict],
    cost_diags: list[dict],
    cost_records: list[dict],
    revision_result: dict,
    events_provided: bool,
    access_profile_provided: bool,
    strict_diags: list[dict],
) -> dict:
    """Write the P0-3 validation report."""

    def _status(diags: list[dict]) -> str:
        return "pass" if not diags else "fail"

    report = {
        "scope": "attacks",
        "spec_path": str(spec_path.resolve()),
        "spec_digest": file_digest(spec_path),
        "timestamp": datetime.now(UTC).isoformat(),
        "allocation_check": {
            "status": _status(allocation_diags),
            "common_cap": spec.get("common_cap"),
        },
        "channel_permissions": {
            "status": _status(permission_diags)
            if access_profile_provided
            else "not_checked",
        },
        "accounting_check": {
            "status": _status(accounting_diags),
        },
        "event_replay": {
            "status": _status(event_replay_diags)
            if events_provided
            else "not_requested",
        },
        "confirmation_check": {
            "status": _status(confirmation_diags),
        },
        "policy_check": {
            "status": _status(policy_diags),
        },
        "audit_check": {
            "status": _status(audit_diags)
            if audit_diags is not None
            else "not_checked",
        },
        "transformation_check": {
            "status": _status(transformation_diags),
        },
        "relearning_check": {
            "status": _status(relearning_diags),
        },
        "cost_records": cost_records,
        "revision_check": revision_result,
        "deferred_checks": [
            "P0-5 margin thresholds (not yet available)",
            "P0-7 preregistration cross-reference",
        ],
        "diagnostics": all_diags,
        "summary": {
            "total_checks": 13,
            "passed": 13
            - sum(
                1
                for d in [
                    allocation_diags,
                    permission_diags,
                    accounting_diags,
                    event_replay_diags,
                    confirmation_diags,
                    policy_diags,
                    audit_diags or [],
                    transformation_diags,
                    relearning_diags,
                    cost_diags,
                ]
                if d
            ),
            "failed": sum(
                1
                for d in [
                    allocation_diags,
                    permission_diags,
                    accounting_diags,
                    event_replay_diags,
                    confirmation_diags,
                    policy_diags,
                    audit_diags or [],
                    transformation_diags,
                    relearning_diags,
                    cost_diags,
                ]
                if d
            ),
            "deferred": 2,
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return report


# ── main entry ────────────────────────────────────────────────────


def validate_attack_spec(
    spec_root: Path,
    contracts_dir: Path,
    report_path: Path,
    access_profile_path: Path | None = None,
    event_fixtures_path: Path | None = None,
    witness_rule_path: Path | None = None,
    strict: bool = False,
    baseline_suite_path: Path | None = None,
) -> tuple[bool, dict]:
    """Run all P0-3 attack specification validation checks.

    Returns (success, report_dict).
    """
    spec, spec_path = load_attack_spec(spec_root)
    file = "attacks.yaml"

    # Load optional inputs
    access_profile = None
    if access_profile_path and access_profile_path.exists():
        # Simple YAML/JSON profile loading
        try:
            text = access_profile_path.read_text(encoding="utf-8")
            if access_profile_path.suffix in (".yaml", ".yml"):
                access_profile = yaml.safe_load(text) or {}
            elif access_profile_path.suffix == ".json":
                access_profile = json.loads(text)
            else:
                access_profile = {"capabilities": {}}
        except Exception:
            access_profile = {"capabilities": {}}

    events = None
    if event_fixtures_path:
        events = load_event_fixtures(event_fixtures_path)

    baseline = None
    if baseline_suite_path and baseline_suite_path.exists():
        try:
            baseline = yaml.safe_load(baseline_suite_path.read_text(encoding="utf-8"))
        except yaml.YAMLError:
            baseline = None

    # Load audit manifests from the attacks directory
    attacks_dir = spec_root.parent / "attacks"
    if not attacks_dir.exists():
        attacks_dir = spec_root.parent.parent / ".factverify" / "attacks"
    audit_manifests = load_audit_manifests(attacks_dir) if attacks_dir.exists() else []

    # ── Run checks ────────────────────────────────────────────────

    # FV-SPEC-034
    structure_diags = check_artifact_structure(spec, file)

    # FV-SPEC-035
    permission_diags = check_channel_permissions(spec, file, access_profile)

    # FV-SPEC-036
    unit_diags = check_accounting_units(spec, file)

    # FV-SPEC-037
    policy_diags_037 = check_event_policies(spec, file)

    # FV-SPEC-038
    allocation_diags = check_matched_allocations(spec, file)

    # FV-SPEC-039
    confirmation_diags = check_confirmation_reservations(spec, file)

    # FV-SPEC-040
    adaptive_diags = check_adaptive_policies(spec, file)

    # FV-SPEC-041
    audit_diags = check_clue_audit(spec, file, audit_manifests)

    # FV-SPEC-042
    transformation_diags = check_transformations(spec, file)

    # FV-SPEC-043
    relearning_diags = check_relearning(spec, file)

    # FV-SPEC-044
    cost_records = generate_cost_records(spec, events)
    cost_diags = check_cost_records(spec, events, file)

    # Event trace replay (FV-SPEC-036/037)
    event_replay_diags = []
    if events:
        event_replay_diags = replay_event_traces(spec, events, file)

    # FV-SPEC-045
    revision_result = check_revision_protection(spec, baseline, file)

    # FV-SPEC-046 strict
    strict_diags = []
    if strict:
        strict_diags = check_strict_mode(spec, file, audit_manifests)

    # Combine all diagnostics
    all_diags = (
        structure_diags
        + permission_diags
        + unit_diags
        + policy_diags_037
        + allocation_diags
        + confirmation_diags
        + adaptive_diags
        + audit_diags
        + transformation_diags
        + relearning_diags
        + cost_diags
        + event_replay_diags
        + strict_diags
    )

    # Add revision check failure as diagnostic
    if isinstance(revision_result, dict) and revision_result.get("status") == "fail":
        all_diags.append(
            _diag(
                "FV-SPEC-045",
                None,
                file,
                "/revision",
                revision_result.get("detail", "Revision check failed"),
            )
        )

    # Write report
    report = write_attack_report(
        spec_path=spec_path,
        report_path=report_path,
        spec=spec,
        all_diags=all_diags,
        allocation_diags=allocation_diags,
        permission_diags=permission_diags,
        accounting_diags=unit_diags + policy_diags_037,
        event_replay_diags=event_replay_diags,
        confirmation_diags=confirmation_diags,
        policy_diags=adaptive_diags,
        audit_diags=audit_diags,
        transformation_diags=transformation_diags,
        relearning_diags=relearning_diags,
        cost_diags=cost_diags,
        cost_records=cost_records,
        revision_result=revision_result,
        events_provided=events is not None,
        access_profile_provided=access_profile is not None,
        strict_diags=strict_diags,
    )

    success = len(all_diags) == 0
    return success, report
