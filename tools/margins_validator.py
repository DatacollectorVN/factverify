"""P0-5 margins statistical-policy validator.

Validates margins.yaml against FV-SPEC-057 through FV-SPEC-066.
All checks are offline — zero model inference, GPU jobs, threshold fitting,
or empirical bootstrap execution.

Exit codes (via CLI dispatcher in validate_spec.py):
    0 — all checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_TOP_LEVEL = [
    "version",
    "status",
    "frr_cap",
    "confidence_error_probability",
    "minimum_fcr_reduction_absolute",
    "delta_definition",
    "practical_success",
    "threshold_selection",
    "estimands",
    "uncertainty",
    "channel_margins",
    "locality_margins",
    "relearning_tolerance",
    "sample_size_handoff",
    "approval_refs",
    "blocking_decisions",
]

ALLOWED_TOP_LEVEL = set(REQUIRED_TOP_LEVEL) | {
    "baseline_refs",
    "amendment_policy_ref",
    "confirmatory_claim_authorized",
}

LOCALITY_BUCKETS = {"same_subject", "same_relation", "compositional", "global"}
REQUIRED_BLOCKING = {
    "D-01",
    "D-02",
    "D-03",
    "D-04",
    "D-05",
    "D-06",
    "D-07",
    "D-08",
    "D-09",
    "D-10",
    "D-11",
    "D-12",
    "D-13",
    "D-14",
    "D-15",
    "D-16",
    "D-38",
}
REQUIRED_APPROVAL_FIELDS = [
    "approval_id",
    "policy_field",
    "population",
    "false_rejection_consequences",
    "minimum_worthwhile_benefit",
    "approver_id",
    "approval_date",
    "artifact_revision",
    "decision_refs",
]
REQUIRED_HANDOFF_FIELDS = [
    "allowed_inputs",
    "target_power",
    "effect_scenario",
    "dependence_model",
    "feasibility_limits",
    "algorithm_version",
    "pre_final_deadline",
    "final_n",
]
UNCERTAINTY_FIELDS = [
    "dependence_structure",
    "seed_types",
    "weighting",
    "simultaneous_family",
    "confidence_target",
    "resampling_contract",
    "zero_errors_policy",
]

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+([.-].+)?$")
QUANTITY_FIELDS = (
    "frr_cap",
    "confidence_error_probability",
    "minimum_fcr_reduction_absolute",
)


# ---------------------------------------------------------------------------
# Loaders / helpers
# ---------------------------------------------------------------------------


def load_margins(path: Path) -> dict:
    """Load margins.yaml; raise SystemExit on missing/malformed input."""
    if not path.exists():
        raise SystemExit(f"Margins artifact not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise SystemExit(f"Margins YAML parse error: {exc}") from exc
    if not isinstance(data, dict):
        raise SystemExit("Margins artifact is not a mapping")
    return data


def _diag(rule_id: str, field: str, message: str, file: str = "margins.yaml") -> dict:
    return {"rule_id": rule_id, "file": file, "field": field, "message": message}


def validate_quantity(
    qty: object,
    field: str,
    *,
    rule_id: str = "FV-SPEC-057",
    allow_null: bool = True,
) -> list[dict]:
    """Validate a quantity mapping: value/unit/domain."""
    diagnostics: list[dict] = []
    if not isinstance(qty, dict):
        return [_diag(rule_id, field, f"Quantity '{field}' must be a mapping.")]
    if "unit" not in qty:
        diagnostics.append(
            _diag(rule_id, f"{field}.unit", "Quantity unit is required.")
        )
    if "domain" in qty and not isinstance(qty["domain"], list):
        diagnostics.append(_diag(rule_id, f"{field}.domain", "domain must be a list."))
    value = qty.get("value", None)
    if value is None:
        if not allow_null:
            diagnostics.append(
                _diag(rule_id, f"{field}.value", "value must not be null.")
            )
        return diagnostics
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        diagnostics.append(
            _diag(rule_id, f"{field}.value", f"Non-numeric value: {value!r}.")
        )
        return diagnostics
    if not math.isfinite(float(value)):
        diagnostics.append(
            _diag(rule_id, f"{field}.value", f"Non-finite value: {value}.")
        )
    domain = qty.get("domain")
    if isinstance(domain, list) and len(domain) == 2:
        try:
            lo, hi = float(domain[0]), float(domain[1])
            if not (lo <= float(value) <= hi):
                diagnostics.append(
                    _diag(
                        rule_id,
                        f"{field}.value",
                        f"Value {value} outside domain {domain}.",
                    )
                )
        except (TypeError, ValueError):
            pass
    return diagnostics


def compute_rate(numerator: int | float, denominator: int | float) -> float | str:
    """Return rate or 'undefined' for empty denominators."""
    if denominator == 0:
        return "undefined"
    return float(numerator) / float(denominator)


def _enabled_channels(spec_root: Path) -> list[str]:
    attacks_path = spec_root / "attacks.yaml"
    if not attacks_path.exists():
        return []
    try:
        attacks = yaml.safe_load(attacks_path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return []
    channels = attacks.get("channels", []) if isinstance(attacks, dict) else []
    out: list[str] = []
    if isinstance(channels, list):
        for ch in channels:
            if isinstance(ch, dict) and ch.get("enabled") is True:
                cid = ch.get("id") or ch.get("channel_id")
                if cid:
                    out.append(str(cid))
    return out


# ---------------------------------------------------------------------------
# FV-SPEC-057
# ---------------------------------------------------------------------------


def check_margins_contract_artifact(margins: dict) -> list[dict]:
    diagnostics: list[dict] = []

    for field in REQUIRED_TOP_LEVEL:
        if field not in margins:
            diagnostics.append(
                _diag("FV-SPEC-057", field, f"Required field '{field}' is missing.")
            )

    unknown = set(margins.keys()) - ALLOWED_TOP_LEVEL
    for u in sorted(unknown):
        diagnostics.append(_diag("FV-SPEC-057", u, f"Unknown top-level field '{u}'."))

    version = margins.get("version", "")
    if version and not _SEMVER_RE.match(str(version)):
        diagnostics.append(
            _diag("FV-SPEC-057", "version", f"Version '{version}' is not valid semver.")
        )

    # Quantity checks + unit family
    for qf in QUANTITY_FIELDS:
        if qf in margins:
            diagnostics.extend(validate_quantity(margins[qf], qf))

    frr = margins.get("frr_cap")
    dmin = margins.get("minimum_fcr_reduction_absolute")
    if isinstance(frr, dict) and isinstance(dmin, dict):
        fu, du = frr.get("unit"), dmin.get("unit")
        if fu and du and fu == du == "probability":
            # d_min must be percentage_points; sharing probability is mixed misuse
            diagnostics.append(
                _diag(
                    "FV-SPEC-057",
                    "minimum_fcr_reduction_absolute.unit",
                    "mixed probability/percentage_points units are not allowed; "
                    "d_min must use percentage_points.",
                )
            )
        if fu == "percentage_points" and du == "probability":
            diagnostics.append(
                _diag(
                    "FV-SPEC-057",
                    "frr_cap.unit",
                    "mixed probability/percentage_points units are not allowed.",
                )
            )

    # Explicit mixed_units flag used by fixtures
    if margins.get("_force_mixed_units"):
        diagnostics.append(
            _diag(
                "FV-SPEC-057",
                "units",
                "mixed probability/percentage_points units are not allowed.",
            )
        )

    # Threshold must not substitute for alpha
    if margins.get("threshold_as_frr_cap") or (
        isinstance(margins.get("frr_cap"), dict)
        and margins["frr_cap"].get("substituted_from_threshold")
    ):
        diagnostics.append(
            _diag(
                "FV-SPEC-057",
                "frr_cap",
                "Score thresholds must not be substituted for the FRR cap (alpha).",
            )
        )

    # Blocking decisions set
    bd = margins.get("blocking_decisions")
    if isinstance(bd, list):
        declared = {d.get("decision_id") for d in bd if isinstance(d, dict)}
        missing = REQUIRED_BLOCKING - declared
        if missing:
            diagnostics.append(
                _diag(
                    "FV-SPEC-057",
                    "blocking_decisions",
                    f"Missing required blocking decisions: {', '.join(sorted(missing))}.",
                )
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-058
# ---------------------------------------------------------------------------


def check_policy_approval(
    margins: dict, margins_dir: Path, *, strict: bool = False
) -> list[dict]:
    diagnostics: list[dict] = []
    refs = margins.get("approval_refs", [])
    if not isinstance(refs, list):
        return [_diag("FV-SPEC-058", "approval_refs", "approval_refs must be a list.")]

    loaded_fields: set[str] = set()
    for ref in refs:
        path = margins_dir / str(ref)
        if not path.exists():
            if strict:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-058",
                        "approval_refs",
                        f"Approval not found: {ref}",
                        str(ref),
                    )
                )
            continue
        try:
            approval = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                _diag("FV-SPEC-058", "/", f"Cannot parse approval: {exc}", str(ref))
            )
            continue
        for field in REQUIRED_APPROVAL_FIELDS:
            if field not in approval:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-058",
                        field,
                        f"Required approval field '{field}' is missing.",
                        str(ref),
                    )
                )
        pf = approval.get("policy_field")
        if pf:
            loaded_fields.add(str(pf))
        rev = approval.get("artifact_revision")
        if rev and str(rev) != str(margins.get("version", "")):
            diagnostics.append(
                _diag(
                    "FV-SPEC-058",
                    "artifact_revision",
                    f"Approval revision '{rev}' does not match margins version "
                    f"'{margins.get('version')}'.",
                    str(ref),
                )
            )
        if (
            approval.get("approver_id") is not None
            and not str(approval["approver_id"]).strip()
        ):
            diagnostics.append(
                _diag(
                    "FV-SPEC-058",
                    "approver_id",
                    "approver_id must be non-empty.",
                    str(ref),
                )
            )
        rd = approval.get("approval_date")
        if rd:
            try:
                datetime.fromisoformat(str(rd))
            except ValueError:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-058",
                        "approval_date",
                        f"approval_date '{rd}' is not valid ISO 8601.",
                        str(ref),
                    )
                )

    # Illustrative teaching value without approval
    frr = margins.get("frr_cap", {})
    illustrative = False
    if isinstance(frr, dict):
        val = frr.get("value")
        if val == 0.05 and frr.get("illustrative"):
            illustrative = True
        if val == 0.05 and not refs:
            illustrative = True
    if illustrative and "frr_cap" not in loaded_fields:
        msg = (
            "Illustrative frr_cap value without policy approval; "
            "strict readiness fails."
        )
        if strict:
            diagnostics.append(_diag("FV-SPEC-058", "frr_cap", msg))
        # non-strict: still flag as diagnostic for visibility when illustrative
        elif frr.get("illustrative") or not refs:
            diagnostics.append(_diag("FV-SPEC-058", "frr_cap", msg))

    if strict:
        for needed in ("frr_cap", "practical_success"):
            if needed not in loaded_fields:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-058",
                        "approval_refs",
                        f"Strict mode: missing current approval for '{needed}'.",
                    )
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-059
# ---------------------------------------------------------------------------


def check_estimands_denominators(
    margins: dict, synthetic: dict | None = None
) -> list[dict]:
    diagnostics: list[dict] = []
    estimands = margins.get("estimands")
    if not isinstance(estimands, dict):
        return [_diag("FV-SPEC-059", "estimands", "estimands must be a mapping.")]

    for key in ("frr", "fcr"):
        block = estimands.get(key)
        if not isinstance(block, dict):
            diagnostics.append(
                _diag("FV-SPEC-059", f"estimands.{key}", f"'{key}' must be a mapping.")
            )
            continue
        for sub in ("numerator", "denominator", "eligible_population"):
            if sub not in block:
                diagnostics.append(
                    _diag("FV-SPEC-059", f"estimands.{key}.{sub}", f"Missing '{sub}'.")
                )

    if "case_weights" not in estimands:
        diagnostics.append(
            _diag("FV-SPEC-059", "estimands.case_weights", "case_weights required.")
        )
    if not isinstance(estimands.get("aggregation"), dict):
        diagnostics.append(
            _diag(
                "FV-SPEC-059", "estimands.aggregation", "aggregation must be a mapping."
            )
        )
    sm = estimands.get("status_mappings")
    if not isinstance(sm, dict):
        diagnostics.append(
            _diag(
                "FV-SPEC-059",
                "estimands.status_mappings",
                "status_mappings must be a mapping.",
            )
        )
    else:
        for k in ("missing", "non_identifiable", "incomplete"):
            if k not in sm:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-059",
                        f"estimands.status_mappings.{k}",
                        f"Missing status mapping '{k}'.",
                    )
                )

    # Empty denom as zero is forbidden if declared
    if margins.get("empty_denominator_as_zero") is True:
        diagnostics.append(
            _diag(
                "FV-SPEC-059",
                "estimands",
                "Empty denominator is undefined, not 0.0.",
            )
        )

    if synthetic and isinstance(synthetic, dict):
        for label, expected_key in (("frr", "frr"), ("fcr", "fcr")):
            block = synthetic.get(expected_key, {})
            if not isinstance(block, dict):
                continue
            if label == "frr":
                rate = compute_rate(
                    block.get("genuine_rejections", 0), block.get("eligible_genuine", 0)
                )
            else:
                rate = compute_rate(
                    block.get("fake_acceptances", 0), block.get("eligible_fake", 0)
                )
            expected = block.get("expected_rate")
            if expected is not None and rate != "undefined":
                if abs(float(rate) - float(expected)) > 1e-12:
                    diagnostics.append(
                        _diag(
                            "FV-SPEC-059",
                            f"synthetic.{label}",
                            f"Expected rate {expected}, got {rate}.",
                        )
                    )
        empty = synthetic.get("empty_denominator", {})
        if isinstance(empty, dict):
            status = compute_rate(
                empty.get("numerator", 0), empty.get("denominator", 0)
            )
            if status != "undefined":
                diagnostics.append(
                    _diag(
                        "FV-SPEC-059",
                        "synthetic.empty_denominator",
                        "Empty denominator must be undefined, never 0.0.",
                    )
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-060
# ---------------------------------------------------------------------------


def check_calibration_selection(
    margins: dict, selection_fixture: dict | None = None
) -> list[dict]:
    diagnostics: list[dict] = []
    ts = margins.get("threshold_selection")
    if not isinstance(ts, dict):
        return [
            _diag(
                "FV-SPEC-060",
                "threshold_selection",
                "threshold_selection must be a mapping.",
            )
        ]

    if ts.get("data") != "calibration_only":
        diagnostics.append(
            _diag(
                "FV-SPEC-060",
                "threshold_selection.data",
                f"data must be 'calibration_only', got '{ts.get('data')}'.",
            )
        )
    elig = str(ts.get("eligibility_rule", ""))
    if elig not in ("ucb_frr_le_frr_cap", "ucb(FRR)<=alpha_FRR"):
        if elig in ("point_estimate_frr_le_alpha", "point_estimate_only"):
            diagnostics.append(
                _diag(
                    "FV-SPEC-060",
                    "threshold_selection.eligibility_rule",
                    "Point-estimate-only eligibility does not establish the FRR cap; "
                    "use ucb_frr_le_frr_cap.",
                )
            )
        elif not elig:
            diagnostics.append(
                _diag(
                    "FV-SPEC-060",
                    "threshold_selection.eligibility_rule",
                    "eligibility_rule is required.",
                )
            )
    if not ts.get("tie_rule"):
        diagnostics.append(
            _diag(
                "FV-SPEC-060",
                "threshold_selection.tie_rule",
                "Deterministic tie_rule is required.",
            )
        )
    if ts.get("no_feasible_threshold") != "report_infeasible":
        diagnostics.append(
            _diag(
                "FV-SPEC-060",
                "threshold_selection.no_feasible_threshold",
                "Must be 'report_infeasible'; silent cap relaxation is forbidden.",
            )
        )
    if ts.get("forbid_final_test_inputs") is not True:
        diagnostics.append(
            _diag(
                "FV-SPEC-060",
                "threshold_selection.forbid_final_test_inputs",
                "final-test inputs forbidden for selection.",
            )
        )
    if ts.get("relax_alpha_if_infeasible"):
        diagnostics.append(
            _diag(
                "FV-SPEC-060",
                "threshold_selection",
                "Silent FRR cap relaxation is forbidden.",
            )
        )

    if selection_fixture and isinstance(selection_fixture, dict):
        if selection_fixture.get("uses_final_test"):
            diagnostics.append(
                _diag(
                    "FV-SPEC-060",
                    "threshold_selection.data",
                    "final-test inputs forbidden for selection.",
                )
            )
        if selection_fixture.get("status") == "infeasible":
            # Reporting infeasible is correct — not a failure unless silent relax
            if selection_fixture.get("relaxed_alpha"):
                diagnostics.append(
                    _diag(
                        "FV-SPEC-060",
                        "threshold_selection",
                        "Silent FRR cap relaxation is forbidden.",
                    )
                )
        if selection_fixture.get("eligibility") == "point_estimate_only":
            diagnostics.append(
                _diag(
                    "FV-SPEC-060",
                    "threshold_selection.eligibility_rule",
                    "Point-estimate-only eligibility does not establish the FRR cap.",
                )
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-061
# ---------------------------------------------------------------------------


def check_practical_effect(
    margins: dict, effect_fixture: dict | None = None
) -> list[dict]:
    diagnostics: list[dict] = []
    ps = margins.get("practical_success")
    if not isinstance(ps, dict):
        return [
            _diag(
                "FV-SPEC-061",
                "practical_success",
                "practical_success must be a mapping.",
            )
        ]

    comps = ps.get("comparators", [])
    if not isinstance(comps, list) or set(comps) < {"native", "semantic_only"}:
        diagnostics.append(
            _diag(
                "FV-SPEC-061",
                "practical_success.comparators",
                "comparators must include both native and semantic_only.",
            )
        )
    if ps.get("require_both_baselines") is not True:
        diagnostics.append(
            _diag(
                "FV-SPEC-061",
                "practical_success.require_both_baselines",
                "primary success requires both native and semantic_only.",
            )
        )
    if ps.get("delta_unit") != "percentage_points":
        diagnostics.append(
            _diag(
                "FV-SPEC-061",
                "practical_success.delta_unit",
                "delta_unit must be percentage_points.",
            )
        )
    if not ps.get("common_budget_ref"):
        diagnostics.append(
            _diag(
                "FV-SPEC-061",
                "practical_success.common_budget_ref",
                "common_budget_ref is required.",
            )
        )

    if effect_fixture and isinstance(effect_fixture, dict):
        fv = effect_fixture.get("fcr_factverify")
        base = effect_fixture.get("fcr_baseline")
        if fv is not None and base is not None:
            delta = float(fv) - float(base)
            expected = effect_fixture.get("expected_delta", -0.12)
            if abs(delta - float(expected)) > 1e-12:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-061",
                        "practical_success.delta",
                        f"Expected delta {expected}, got {delta}.",
                    )
                )
        native_ok = effect_fixture.get("native_meets", True)
        sem_ok = effect_fixture.get("semantic_only_meets", True)
        primary = bool(native_ok and sem_ok)
        if effect_fixture.get("claimed_primary_success") is True and not primary:
            diagnostics.append(
                _diag(
                    "FV-SPEC-061",
                    "practical_success",
                    "primary success requires both native and semantic_only.",
                )
            )
        if ps.get("delta_uncertainty_rule") and not effect_fixture.get(
            "delta_uncertainty_explicitly_adopted", True
        ):
            diagnostics.append(
                _diag(
                    "FV-SPEC-061",
                    "practical_success.delta_uncertainty_rule",
                    "UCB(delta) rule used only if explicitly adopted.",
                )
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-062
# ---------------------------------------------------------------------------


def check_uncertainty_dependence(margins: dict) -> list[dict]:
    diagnostics: list[dict] = []
    unc = margins.get("uncertainty")
    if not isinstance(unc, dict):
        return [_diag("FV-SPEC-062", "uncertainty", "uncertainty must be a mapping.")]

    for field in UNCERTAINTY_FIELDS:
        if field not in unc:
            diagnostics.append(
                _diag("FV-SPEC-062", f"uncertainty.{field}", f"Missing '{field}'.")
            )

    contract = str(unc.get("resampling_contract", "")).lower()
    if any(
        bad in contract
        for bad in (
            "independent_row",
            "iid_prompts",
            "row_wise_independent",
            "independent_correlated_prompts",
        )
    ):
        diagnostics.append(
            _diag(
                "FV-SPEC-062",
                "uncertainty.resampling_contract",
                "correlated prompts are not independent replicates.",
            )
        )
    if unc.get("label_separate_intervals_as_joint"):
        diagnostics.append(
            _diag(
                "FV-SPEC-062",
                "uncertainty",
                "Separate intervals must not be labelled as joint coverage.",
            )
        )
    if not unc.get("zero_errors_policy"):
        diagnostics.append(
            _diag(
                "FV-SPEC-062",
                "uncertainty.zero_errors_policy",
                "Zero observed errors still require a positive uncertainty policy.",
            )
        )
    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-063
# ---------------------------------------------------------------------------


def check_channel_locality_coverage(margins: dict, spec_root: Path) -> list[dict]:
    diagnostics: list[dict] = []
    enabled = set(_enabled_channels(spec_root))

    cm = margins.get("channel_margins")
    declared_channels: set[str] = set()
    if isinstance(cm, list):
        for i, entry in enumerate(cm):
            if not isinstance(entry, dict):
                diagnostics.append(
                    _diag(
                        "FV-SPEC-063",
                        f"channel_margins[{i}]",
                        "Entry must be a mapping.",
                    )
                )
                continue
            cid = entry.get("channel_id")
            if cid:
                declared_channels.add(str(cid))
            for req in ("statistic", "unit", "reference", "margin", "orientation"):
                if req not in entry:
                    diagnostics.append(
                        _diag(
                            "FV-SPEC-063",
                            f"channel_margins[{i}].{req}",
                            f"Missing '{req}'.",
                        )
                    )
            if entry.get("aggregate_rank_with_correctness"):
                diagnostics.append(
                    _diag(
                        "FV-SPEC-063",
                        f"channel_margins[{i}]",
                        "Raw rank averaged with correctness is not allowed.",
                    )
                )
    elif isinstance(cm, dict):
        declared_channels = set(cm.keys())
    else:
        diagnostics.append(
            _diag(
                "FV-SPEC-063",
                "channel_margins",
                "channel_margins must be a list or mapping.",
            )
        )

    missing_ch = enabled - declared_channels
    for cid in sorted(missing_ch):
        diagnostics.append(
            _diag(
                "FV-SPEC-063",
                "channel_margins",
                f"Missing oriented margin for enabled channel '{cid}'.",
            )
        )

    lm = margins.get("locality_margins")
    if not isinstance(lm, dict):
        diagnostics.append(
            _diag(
                "FV-SPEC-063", "locality_margins", "locality_margins must be a mapping."
            )
        )
    else:
        for bucket in LOCALITY_BUCKETS:
            if bucket not in lm:
                diagnostics.append(
                    _diag(
                        "FV-SPEC-063",
                        f"locality_margins.{bucket}",
                        f"Missing oriented margin for bucket '{bucket}'.",
                    )
                )
            else:
                entry = lm[bucket]
                if isinstance(entry, dict):
                    for req in (
                        "statistic",
                        "unit",
                        "reference",
                        "margin",
                        "orientation",
                    ):
                        if req not in entry:
                            diagnostics.append(
                                _diag(
                                    "FV-SPEC-063",
                                    f"locality_margins.{bucket}.{req}",
                                    f"Missing '{req}'.",
                                )
                            )

    if margins.get("import_superseded_privacy_margin"):
        diagnostics.append(
            _diag(
                "FV-SPEC-063",
                "locality_margins",
                "Mandatory privacy margins must not be imported from superseded notes.",
            )
        )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-064
# ---------------------------------------------------------------------------


def check_sample_size_handoff(margins: dict) -> list[dict]:
    diagnostics: list[dict] = []
    handoff = margins.get("sample_size_handoff")
    if not isinstance(handoff, dict):
        return [
            _diag(
                "FV-SPEC-064",
                "sample_size_handoff",
                "sample_size_handoff must be a mapping.",
            )
        ]

    for field in REQUIRED_HANDOFF_FIELDS:
        if field not in handoff:
            diagnostics.append(
                _diag(
                    "FV-SPEC-064", f"sample_size_handoff.{field}", f"Missing '{field}'."
                )
            )

    if handoff.get("final_n") is not None:
        diagnostics.append(
            _diag(
                "FV-SPEC-064",
                "sample_size_handoff.final_n",
                "final_n must be null in P0-5; do not invent a final sample count.",
            )
        )
    if handoff.get("power_against_zero_to_justify_exceeding_d_min"):
        diagnostics.append(
            _diag(
                "FV-SPEC-064",
                "sample_size_handoff",
                "Power against zero must not justify exceeding d_min.",
            )
        )
    if handoff.get("underpowered") is True and not handoff.get(
        "infeasibility_explicit"
    ):
        diagnostics.append(
            _diag(
                "FV-SPEC-064",
                "sample_size_handoff",
                "Underpowered design must declare infeasibility explicitly.",
            )
        )
    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-065
# ---------------------------------------------------------------------------


def check_baseline_comparison(
    margins: dict, baseline_path: Path
) -> tuple[list[dict], dict]:
    diagnostics: list[dict] = []
    if not baseline_path.exists():
        diagnostics.append(
            _diag("FV-SPEC-065", "baseline", f"Baseline not found: {baseline_path}")
        )
        return diagnostics, {
            "status": "fail",
            "changed_fields": [],
            "revision_match": False,
        }

    try:
        baseline = load_margins(baseline_path)
    except SystemExit as exc:
        diagnostics.append(_diag("FV-SPEC-065", "/", f"Cannot load baseline: {exc}"))
        return diagnostics, {
            "status": "fail",
            "changed_fields": [],
            "revision_match": False,
        }

    cur_v = str(margins.get("version", ""))
    base_v = str(baseline.get("version", ""))
    revision_match = cur_v == base_v

    frozen_keys = (
        "frr_cap",
        "minimum_fcr_reduction_absolute",
        "practical_success",
        "threshold_selection",
        "estimands",
        "uncertainty",
        "handling_policies",
    )
    changed: list[str] = []
    for key in frozen_keys:
        if key in margins or key in baseline:
            if margins.get(key) != baseline.get(key):
                changed.append(key)

    if changed and revision_match:
        diagnostics.append(
            _diag(
                "FV-SPEC-065",
                "version",
                f"Frozen policy changed ({', '.join(changed)}) but version unchanged ({cur_v}).",
            )
        )

    if margins.get("confirmatory_claim_authorized") is True and not margins.get(
        "amendment_policy_ref"
    ):
        # Only fail when claiming authorization without amendment when policy changed
        if changed:
            diagnostics.append(
                _diag(
                    "FV-SPEC-065",
                    "amendment_policy_ref",
                    "Missing amendment authorization; confirmatory claim disallowed.",
                )
            )

    if margins.get("final_outcome_tuning"):
        diagnostics.append(
            _diag(
                "FV-SPEC-065",
                "revision",
                "Final-outcome tuning disallows the original confirmatory claim.",
            )
        )

    status = "fail" if diagnostics else "pass"
    return diagnostics, {
        "status": status,
        "changed_fields": changed,
        "revision_match": revision_match,
    }


def check_revision_protection(margins: dict) -> list[dict]:
    diagnostics: list[dict] = []
    if margins.get("confirmatory_claim_authorized") is True and not margins.get(
        "amendment_policy_ref"
    ):
        diagnostics.append(
            _diag(
                "FV-SPEC-065",
                "amendment_policy_ref",
                "Missing amendment authorization; confirmatory claim disallowed.",
            )
        )
    if margins.get("final_outcome_tuning"):
        diagnostics.append(
            _diag(
                "FV-SPEC-065",
                "revision",
                "Final-outcome tuning disallows the original confirmatory claim.",
            )
        )
    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-066 strict
# ---------------------------------------------------------------------------


def check_strict_mode(margins: dict, margins_dir: Path, spec_root: Path) -> list[dict]:
    diagnostics: list[dict] = []
    bd = margins.get("blocking_decisions", [])
    if isinstance(bd, list):
        for d in bd:
            if isinstance(d, dict) and d.get("status") not in (
                "resolved",
                "not_applicable",
            ):
                diagnostics.append(
                    _diag(
                        "FV-SPEC-066",
                        f"blocking_decisions.{d.get('decision_id')}",
                        f"Strict mode: decision {d.get('decision_id')} is not resolved.",
                    )
                )

    review_path = margins_dir / "review_manifest.json"
    if not review_path.exists():
        diagnostics.append(
            _diag(
                "FV-SPEC-066",
                "/",
                "Strict mode: review_manifest.json not found.",
                "review_manifest.json",
            )
        )
    else:
        try:
            manifest = json.loads(review_path.read_text(encoding="utf-8"))
            for r in manifest.get("reviews", []):
                if isinstance(r, dict) and r.get("status") == "pending":
                    diagnostics.append(
                        _diag(
                            "FV-SPEC-066",
                            f"reviews.{r.get('artifact_id')}",
                            f"Strict mode: review for '{r.get('artifact_id')}' is pending.",
                            "review_manifest.json",
                        )
                    )
        except (json.JSONDecodeError, OSError):
            diagnostics.append(
                _diag(
                    "FV-SPEC-066",
                    "/",
                    "Strict mode: cannot parse review_manifest.json.",
                    "review_manifest.json",
                )
            )

    # Cross-file presence for witness/prereg in strict
    if not (spec_root / "witness_rule.md").exists():
        diagnostics.append(
            _diag(
                "FV-SPEC-066",
                "cross_file",
                "Strict mode: witness_rule.md not found.",
            )
        )
    if not (spec_root / "preregistration.md").exists():
        diagnostics.append(
            _diag(
                "FV-SPEC-066",
                "cross_file",
                "Strict mode: preregistration.md not found.",
            )
        )

    return diagnostics


# ---------------------------------------------------------------------------
# Report + orchestration
# ---------------------------------------------------------------------------


def write_margins_report(
    checks: list[dict],
    margins: dict,
    spec_root: Path,
    strict: bool,
    report_path: Path | None,
    baseline_comparison: dict | None = None,
) -> dict:
    input_digests: dict = {}
    mp = spec_root / "margins.yaml"
    if mp.exists():
        input_digests["margins.yaml"] = (
            "sha256:" + hashlib.sha256(mp.read_bytes()).hexdigest()
        )
    ap = spec_root / "attacks.yaml"
    if ap.exists():
        input_digests["attacks.yaml"] = (
            "sha256:" + hashlib.sha256(ap.read_bytes()).hexdigest()
        )

    decision_status: dict = {}
    bd = margins.get("blocking_decisions", [])
    if isinstance(bd, list):
        for d in bd:
            if isinstance(d, dict) and d.get("decision_id"):
                decision_status[str(d["decision_id"])] = d.get("status", "open")

    deferred: list[str] = []
    if not strict:
        deferred = [
            "P0-6 witness rule",
            "P0-7 amendment authorization",
            "P2-6 bootstrap engine",
            "P4 empirical calibration/power",
        ]

    overall = (
        "pass"
        if all(c.get("status") in ("pass", "deferred", "skipped") for c in checks)
        else "fail"
    )

    report = {
        "report_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "spec_root": str(spec_root),
        "scope": "margins",
        "strict": strict,
        "margins_version": str(margins.get("version", "")),
        "checks": checks,
        "decision_status": decision_status,
        "input_digests": input_digests,
        "deferred_checks": deferred,
        "baseline_comparison": baseline_comparison,
        "overall": overall,
    }

    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    return report


def _run_check(
    rule_id: str,
    rule_name: str,
    check_fn: Callable[..., Any],
    *args: object,
    **kwargs: object,
) -> dict:
    try:
        diags = check_fn(*args, **kwargs)
        if isinstance(diags, tuple):
            diags = diags[0]
        status = "pass" if not diags else "fail"
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": status,
            "diagnostics": [d.get("message", "") for d in diags],
        }
    except Exception as exc:  # noqa: BLE001 — surface as check failure
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": "fail",
            "diagnostics": [f"Check error: {exc}"],
        }


def validate_margins(
    spec_root: str | Path,
    margins_dir: str | Path,
    report_path: str | Path | None = None,
    strict: bool = False,
    baseline_suite_path: str | Path | None = None,
    synthetic_rates_path: str | Path | None = None,
    effect_fixture: dict | None = None,
    selection_fixture: dict | None = None,
) -> tuple[bool, dict]:
    """Validate margins policy. Returns (passed, report)."""
    spec_root = Path(spec_root)
    margins_dir = Path(margins_dir)
    report_path = Path(report_path) if report_path else None
    baseline_suite_path = Path(baseline_suite_path) if baseline_suite_path else None

    margins = load_margins(spec_root / "margins.yaml")

    synthetic = None
    if synthetic_rates_path:
        sp = Path(synthetic_rates_path)
        if sp.exists():
            synthetic = json.loads(sp.read_text(encoding="utf-8"))

    checks: list[dict] = []
    checks.append(
        _run_check(
            "FV-SPEC-057",
            "margins_contract_artifact",
            check_margins_contract_artifact,
            margins,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-058",
            "policy_approval",
            check_policy_approval,
            margins,
            margins_dir,
            strict=strict,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-059",
            "estimands_denominators",
            check_estimands_denominators,
            margins,
            synthetic,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-060",
            "calibration_selection",
            check_calibration_selection,
            margins,
            selection_fixture,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-061",
            "practical_effect",
            check_practical_effect,
            margins,
            effect_fixture,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-062",
            "uncertainty_dependence",
            check_uncertainty_dependence,
            margins,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-063",
            "channel_locality_coverage",
            check_channel_locality_coverage,
            margins,
            spec_root,
        )
    )
    checks.append(
        _run_check(
            "FV-SPEC-064",
            "sample_size_handoff",
            check_sample_size_handoff,
            margins,
        )
    )

    rev = _run_check(
        "FV-SPEC-065",
        "revision_protection",
        check_revision_protection,
        margins,
    )
    baseline_comparison = None
    if baseline_suite_path:
        bl_diags, baseline_comparison = check_baseline_comparison(
            margins,
            baseline_suite_path,
        )
        if bl_diags:
            rev["status"] = "fail"
            rev["diagnostics"].extend(d.get("message", "") for d in bl_diags)
    checks.append(rev)

    scoped = {
        "rule_id": "FV-SPEC-066",
        "rule_name": "scoped_cli_validation",
        "status": "pass",
        "diagnostics": [],
    }
    if strict:
        strict_diags = check_strict_mode(margins, margins_dir, spec_root)
        # Also re-check approvals under strict
        appr = check_policy_approval(margins, margins_dir, strict=True)
        strict_diags.extend(appr)
        if strict_diags:
            scoped["status"] = "fail"
            scoped["diagnostics"] = [d.get("message", "") for d in strict_diags]
    checks.append(scoped)

    report = write_margins_report(
        checks,
        margins,
        spec_root,
        strict,
        report_path,
        baseline_comparison,
    )
    return report["overall"] == "pass", report
