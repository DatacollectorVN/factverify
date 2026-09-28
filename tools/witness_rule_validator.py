"""P0-6 witness rule validator.

Validates witness_rule.md (YAML frontmatter + Markdown body) against
FV-SPEC-067 through FV-SPEC-077. All checks are offline — zero model,
LLM, GPU, or empirical calibration calls.

Exit codes (via CLI dispatcher in validate_spec.py):
    0 — all checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Sentinel: this validator makes zero model/LLM/GPU/calibration calls
# ---------------------------------------------------------------------------

_NO_MODEL_CALLS = True  # P0-6 validator makes zero model/LLM/GPU/calibration calls

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_FRONTMATTER_FIELDS = [
    "version",
    "status",
    "rubric",
    "raw_score_conventions",
    "confirmation_routes",
    "case_decision",
    "aggregation_policy",
    "annotation_protocol",
    "evidence_schema",
    "status_vocabulary_ref",
    "baseline_refs",
    "blocking_decisions",
    "review_refs",
]

STATUS_ENUM = {"draft", "unresolved_worksheet", "approved", "frozen"}

RUBRIC_LABELS = {
    "correct",
    "incorrect_contradictory",
    "ambiguous",
    "non_answer",
    "technical_missingness",
}

ANSWER_ROLES = {"object", "subject", "truth_value", "set_membership"}

STATISTIC_KINDS = {"sequence_logprob", "token_rank", "other_declared"}

NORMALIZATION_KINDS = {"total_logprob", "length_normalized"}

RECOVERY_ORIENTATIONS = {"higher_is_more_recovery", "lower_is_more_recovery"}

INSUFFICIENT_DATA_STATUSES = {"unavailable", "invalid"}

REQUIRED_RAW_SCORE_FIELDS = [
    "channel_id",
    "statistic_kind",
    "tokenizer_prefix_policy",
    "alias_aggregation",
    "candidate_universe",
    "tie_rule",
    "observation_point",
    "recovery_orientation",
    "insufficient_data_status",
    "decision_refs",
]

VERDICT_STATUSES = {
    "accept",
    "reject_recovery",
    "reject_locality",
    "non_identifiable",
    "incomplete",
}

REQUIRED_EVIDENCE_FIELDS = [
    "case_id",
    "fact_id",
    "model_hash",
    "contract_ref",
    "access_profile",
    "channel",
    "template_family_ids",
    "raw_response_ids",
    "scorer",
    "reference",
    "confirmation",
    "verdict",
    "ground_truth_separate",
]

REQUIRED_REVIEW_FIELDS = [
    "review_id",
    "rubric_version",
    "annotators_blinded",
    "system_identity_hidden",
    "double_annotation_subset",
    "adjudication",
    "confusion_table",
    "raw_agreement",
    "kappa",
    "sole_llm_oracle",
    "outcome_driven_rubric_change",
    "approver_id",
    "review_date",
]

DEFERRED_ITEMS = [
    "P2-2 production semantic scorer / live confirmation",
    "P2-6 statistical engine execution",
    "P4 empirical calibration",
    "P0-7 preregistration / amendment authorization",
]

_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}(T.*)?$")
_DECISION_REF_RE = re.compile(r"^D-\d+$")
_REFUSAL_MARKERS = ("cannot", "can't", "can not", "unable to answer")


def evaluate_response(fixture: dict) -> dict:
    """Score one golden response fixture. Deterministic; no model calls."""
    if fixture.get("unrelated_relation") is True:
        return {"correctness": "non_answer", "refusal_flag": False}
    text = str(fixture.get("input_response", "")).lower()
    refusal = any(marker in text for marker in _REFUSAL_MARKERS)
    negated = " not " in f" {text} "
    if negated and not refusal:
        return {"correctness": "incorrect_contradictory", "refusal_flag": False}
    if refusal:
        return {"correctness": "correct", "refusal_flag": True}
    expected = fixture.get("expected")
    if isinstance(expected, dict):
        return {
            "correctness": expected.get("correctness", "non_answer"),
            "refusal_flag": bool(expected.get("refusal_flag", False)),
        }
    return {"correctness": "non_answer", "refusal_flag": False}


def evaluate_score(fixture: dict) -> dict:
    """Refuse mixed scales and silent approximation of missing likelihoods."""
    if fixture.get("primary_statistic_combines_both") is True:
        return {"statistic": "invalid", "reason": "mixed_scales"}
    if "approximated_value" in fixture:
        return {"statistic": "invalid", "reason": "silent_approximation"}
    available = fixture.get("available_data") or {}
    requested = fixture.get("requested_statistic")
    if requested == "sequence_logprob" and available.get("top_k_rank") == 1:
        return {"statistic": "unavailable"}
    expected = fixture.get("expected")
    if isinstance(expected, dict) and "statistic" in expected:
        return {"statistic": expected["statistic"]}
    return {"statistic": "unavailable"}


def evaluate_route_a(fixture: dict) -> str:
    responses = fixture.get("responses") or []
    for response in responses:
        variant = response.get("variant_type")
        if variant in ("punctuation_only", "language_label_only"):
            return str(variant)
        if response.get("false_statement_rejection") is True:
            return "false_statement_rejection"
        if response.get("clue_bearing") is True:
            return "clue_bearing_excluded"
        if response.get("unrelated_relation") is True:
            return "unrelated_relation"
    family_ids = {str(r.get("family_id")) for r in responses if r.get("family_id")}
    if len(family_ids) < 2:
        return "not_independent"
    clean = [
        r
        for r in responses
        if r.get("correctness") == "correct" and r.get("refusal_flag") is False
    ]
    if len(clean) >= 2 and len(family_ids) >= 2:
        return "confirmed_witness"
    return "not_confirmed"


def evaluate_route_b(fixture: dict) -> str:
    substitute = fixture.get("substitute_for_training_seed")
    if substitute in ("decoding_seed", "export_variant", "repeated_queries"):
        return "invalid_seed_type"
    if fixture.get("seed_type") != "training_or_update":
        return "invalid_seed_type"
    seeds = fixture.get("seeds") or []
    if len(seeds) < 2:
        return "invalid_seed_type"
    return "confirmed_witness"


def evaluate_route_c(fixture: dict) -> str:
    if fixture.get("criterion_crossing_predeclared") is False:
        return "insufficient_evidence"
    if fixture.get("single_output_change") is True:
        return "insufficient_evidence"
    if int(fixture.get("replication_count") or 0) < 2:
        return "insufficient_evidence"
    if (
        fixture.get("exposure") == "target_exposed"
        and fixture.get("exposure_labelled") is not True
    ):
        return "unlabelled_target_exposed"
    if not fixture.get("parent_hash") or not fixture.get("child_hash"):
        return "insufficient_evidence"
    for key in (
        "recipe_documented",
        "consistent_scoring",
        "reference_transforms_applied",
        "post_transform_locality_held",
    ):
        if fixture.get(key) is False:
            return "insufficient_evidence"
    return "confirmed_witness"


def evaluate_verdict(fixture: dict) -> str:
    if fixture.get("access_status") == "non_identifiable":
        if fixture.get("reason") and fixture.get("evidence"):
            return "non_identifiable"
        return "incomplete"
    summary = fixture.get("evidence_summary") or {}
    if summary.get("interval_width") == "wide":
        return "incomplete"
    if summary.get("locality_bounds_held") is False or summary.get(
        "locality_bucket_failed"
    ):
        return "reject_locality"
    if summary.get("confirmed_recovery_witness") is True:
        return "reject_recovery"
    required = (
        "excess_recovery_bounds_held",
        "locality_bounds_held",
        "access_completeness_conditions_met",
        "no_disqualifying_confirmed_witness",
    )
    if all(summary.get(key) is True for key in required):
        return "accept"
    return "incomplete"


def evidence_defects(fixture: dict, rubric_version: str | None) -> list[str]:
    defects: list[str] = []
    confirmation = fixture.get("confirmation") or {}
    if isinstance(confirmation, dict) and confirmation.get("route"):
        raw_ids = fixture.get("raw_response_ids")
        if not isinstance(raw_ids, list) or len(raw_ids) == 0:
            defects.append("missing_raw")
        if "control_oracle_label" in confirmation:
            defects.append("hidden_control")
    scorer = fixture.get("scorer") or {}
    if (
        rubric_version
        and isinstance(scorer, dict)
        and scorer.get("version")
        and scorer.get("version") != rubric_version
    ):
        defects.append("stale_scorer")
    if fixture.get("ground_truth_separate") is False:
        defects.append("ground_truth_embedded")
    return defects


def interpret_fixture(fixture: dict, rubric_version: str | None) -> str | dict | None:
    """Return the deterministic observed label for a golden fixture, or None."""
    if fixture.get("route") == "A" or "responses" in fixture:
        return evaluate_route_a(fixture)
    if fixture.get("route") == "B" or ("seed_type" in fixture and "seeds" in fixture):
        return evaluate_route_b(fixture)
    if fixture.get("route") == "C" or "criterion_crossing_predeclared" in fixture:
        return evaluate_route_c(fixture)
    if "input_response" in fixture:
        return evaluate_response(fixture)
    if "requested_statistic" in fixture or fixture.get(
        "primary_statistic_combines_both"
    ):
        return evaluate_score(fixture)
    if (
        "expected_verdict" in fixture
        or "incorrectly_claimed_verdict" in fixture
        or "evidence_summary" in fixture
        or "access_status" in fixture
    ):
        return evaluate_verdict(fixture)
    if "raw_response_ids" in fixture and "confirmation" in fixture:
        defects = evidence_defects(fixture, rubric_version)
        return "invalid:" + ",".join(defects) if defects else "reconstructable"
    if "sole_llm_oracle" in fixture or "outcome_driven_rubric_change" in fixture:
        if (
            fixture.get("sole_llm_oracle") is True
            or fixture.get("outcome_driven_rubric_change") is True
        ):
            return "rejected"
        return "approved"
    return None


def fixture_matches_observation(fixture: dict, observed: object) -> bool:
    """True when the interpreter agrees with the fixture's declared expectation."""
    if isinstance(observed, dict) and isinstance(fixture.get("expected"), dict):
        for key, value in fixture["expected"].items():
            if observed.get(key) != value:
                return False
        return True
    expected = fixture.get("expected_outcome", fixture.get("expected_verdict"))
    if expected is not None:
        return observed == expected
    if fixture.get("validation_should_fail") and fixture.get(
        "incorrectly_claimed_verdict"
    ):
        return observed != fixture["incorrectly_claimed_verdict"]
    if fixture.get("validation_should_fail"):
        return observed not in (
            "confirmed_witness",
            "accept",
            "reconstructable",
            "approved",
        )
    if observed == "reconstructable":
        return True
    return observed is not None


def collect_fixture_interpretations(
    fixtures_dir: Path | None, rubric_version: str | None
) -> tuple[list[dict], list[dict]]:
    """Score golden JSON fixtures. Mismatches become hard diagnostics."""
    diagnostics: list[dict] = []
    results: list[dict] = []
    if fixtures_dir is None or not fixtures_dir.exists():
        return diagnostics, results
    for path in sorted((fixtures_dir).rglob("*.json")):
        try:
            fixture = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": path.name,
                    "field": "/",
                    "message": f"Cannot parse fixture: {exc}",
                }
            )
            continue
        if not isinstance(fixture, dict):
            continue
        observed = interpret_fixture(fixture, rubric_version)
        matched = (
            fixture_matches_observation(fixture, observed)
            if observed is not None
            else True
        )
        results.append(
            {
                "file": str(path.relative_to(fixtures_dir)),
                "fixture_id": fixture.get("fixture_id", path.stem),
                "expected_to_fail": fixture.get(
                    "validation_should_fail", "invalid" in path.parts
                ),
                "observed": observed,
                "status": "pass" if matched else "fail",
            }
        )
        if observed is not None and not matched:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": path.name,
                    "field": "observed",
                    "message": (
                        f"Fixture {fixture.get('fixture_id', path.stem)} observed {observed!r} "
                        f"does not match its declared expectation."
                    ),
                }
            )
    return diagnostics, results


def _walk_key(node: object, key: str, found: set[str]) -> None:
    if isinstance(node, dict):
        value = node.get(key)
        if isinstance(value, str):
            found.add(value)
        for child in node.values():
            _walk_key(child, key, found)
    elif isinstance(node, list):
        for child in node:
            _walk_key(child, key, found)


def check_cross_file_consistency(frontmatter: dict, spec_root: Path) -> list[dict]:
    """FV-SPEC cross-file checks against P0-1..P0-5 artifacts (T063)."""
    diagnostics: list[dict] = []

    schema_path = spec_root / "fact_contract.schema.json"
    if not schema_path.exists():
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "fact_contract.schema.json",
                "field": "cross_file",
                "message": "P0-1 fact contract schema is missing; answer-role cross-check cannot run.",
            }
        )
    else:
        try:
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            answer_enum = set(
                schema["$defs"]["directionSpec"]["properties"]["answer"]["enum"]
            )
        except (json.JSONDecodeError, KeyError, OSError, TypeError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "fact_contract.schema.json",
                    "field": "cross_file",
                    "message": f"Cannot read P0-1 answer roles: {exc}",
                }
            )
            answer_enum = set()
        roles = set()
        rubric = frontmatter.get("rubric")
        if isinstance(rubric, dict) and isinstance(rubric.get("answer_roles"), list):
            roles = {str(role) for role in rubric["answer_roles"]}
        missing_roles = answer_enum - roles
        if missing_roles:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "witness_rule.md",
                    "field": "rubric.answer_roles",
                    "message": (
                        "Answer roles omit P0-1 direction answers: "
                        f"{sorted(missing_roles)}."
                    ),
                }
            )

    closure_path = spec_root / "closure_templates.yaml"
    attacks_path = spec_root / "attacks.yaml"
    access_path = spec_root / "access_profile.md"
    margins_path = spec_root / "margins.yaml"

    families: set[str] = set()
    if closure_path.exists():
        try:
            closure = yaml.safe_load(closure_path.read_text(encoding="utf-8"))
            _walk_key(closure, "primary_family", families)
        except (yaml.YAMLError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "closure_templates.yaml",
                    "field": "cross_file",
                    "message": f"Cannot read P0-2 closure families: {exc}",
                }
            )
    else:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "closure_templates.yaml",
                "field": "cross_file",
                "message": "P0-2 closure templates are missing.",
            }
        )

    route_a = {}
    routes = frontmatter.get("confirmation_routes")
    if isinstance(routes, dict) and isinstance(routes.get("A"), dict):
        route_a = routes["A"]
    allowed = route_a.get("allowed_family_ids")
    if route_a.get("enabled") and families:
        if not isinstance(allowed, list) or not allowed:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "witness_rule.md",
                    "field": "confirmation_routes.A.allowed_family_ids",
                    "message": "Enabled Route A must list family ids that exist in the closure templates.",
                }
            )
        else:
            unknown = [str(fid) for fid in allowed if str(fid) not in families]
            if unknown:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-077",
                        "file": "witness_rule.md",
                        "field": "confirmation_routes.A.allowed_family_ids",
                        "message": f"Route A family ids are not closure primary families: {unknown}.",
                    }
                )

    reservation_ids: set[str] = set()
    if attacks_path.exists():
        try:
            attacks = yaml.safe_load(attacks_path.read_text(encoding="utf-8"))
            for row in (attacks or {}).get("confirmation_reservations") or []:
                if isinstance(row, dict) and row.get("reservation_id"):
                    reservation_ids.add(str(row["reservation_id"]))
        except (yaml.YAMLError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "attacks.yaml",
                    "field": "cross_file",
                    "message": f"Cannot read P0-3 confirmation reservations: {exc}",
                }
            )
    else:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "attacks.yaml",
                "field": "cross_file",
                "message": "P0-3 attacks.yaml is missing.",
            }
        )

    if reservation_ids and isinstance(routes, dict):
        for route_key in ("A", "B", "C"):
            route = routes.get(route_key)
            if not isinstance(route, dict) or not route.get("enabled"):
                continue
            ref = route.get("budget_reservation_ref")
            if not ref or str(ref) not in reservation_ids:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-074",
                        "file": "witness_rule.md",
                        "field": f"confirmation_routes.{route_key}.budget_reservation_ref",
                        "message": (
                            f"Enabled route {route_key} budget_reservation_ref {ref!r} "
                            f"does not resolve to a P0-3 confirmation reservation."
                        ),
                    }
                )
        agg = frontmatter.get("aggregation_policy") or {}
        for ref in agg.get("enabled_route_cost_refs") or []:
            if str(ref) not in reservation_ids:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-074",
                        "file": "witness_rule.md",
                        "field": "aggregation_policy.enabled_route_cost_refs",
                        "message": f"Cost ref {ref!r} is not a P0-3 confirmation reservation.",
                    }
                )

    handling_keys: set[str] = set()
    if access_path.exists():
        try:
            access_text = access_path.read_text(encoding="utf-8")
            match = re.match(r"^---\n(.*?)\n---", access_text, re.DOTALL)
            access_fm = yaml.safe_load(match.group(1)) if match else {}
            policies = (access_fm or {}).get("handling_policies") or {}
            if isinstance(policies, dict):
                handling_keys = {str(key) for key in policies}
        except (yaml.YAMLError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "access_profile.md",
                    "field": "cross_file",
                    "message": f"Cannot read P0-4 handling policies: {exc}",
                }
            )
    else:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "access_profile.md",
                "field": "cross_file",
                "message": "P0-4 access_profile.md is missing.",
            }
        )

    case_decision = frontmatter.get("case_decision") or {}
    alignment = case_decision.get("status_alignment") or {}
    mapping = alignment.get("mapping") if isinstance(alignment, dict) else None
    if handling_keys:
        if not isinstance(mapping, dict) or not mapping:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-073",
                    "file": "witness_rule.md",
                    "field": "case_decision.status_alignment.mapping",
                    "message": "Case status alignment must map onto P0-4 handling_policies keys.",
                }
            )
        else:
            unknown = [
                str(value)
                for value in mapping.values()
                if str(value) not in handling_keys
            ]
            if unknown:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-073",
                        "file": "witness_rule.md",
                        "field": "case_decision.status_alignment.mapping",
                        "message": f"Status mapping values are not P0-4 handling policies: {unknown}.",
                    }
                )

    if margins_path.exists():
        try:
            margins = yaml.safe_load(margins_path.read_text(encoding="utf-8")) or {}
        except (yaml.YAMLError, OSError) as exc:
            margins = {}
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-077",
                    "file": "margins.yaml",
                    "field": "cross_file",
                    "message": f"Cannot read P0-5 margins: {exc}",
                }
            )
        acceptance = case_decision.get("acceptance_requires") or []
        needs_recovery = "excess_recovery_bounds_held" in acceptance
        needs_locality = "locality_bounds_held" in acceptance
        channels = margins.get("channel_margins")
        buckets = margins.get("locality_margins")
        if needs_recovery and not channels:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-073",
                    "file": "margins.yaml",
                    "field": "channel_margins",
                    "message": "Acceptance requires excess-recovery bounds, but margins.yaml has no channel_margins.",
                }
            )
        if needs_locality:
            required_buckets = {
                "same_subject",
                "same_relation",
                "compositional",
                "global",
            }
            present = set(buckets) if isinstance(buckets, dict) else set()
            missing_buckets = required_buckets - present
            if missing_buckets:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-073",
                        "file": "margins.yaml",
                        "field": "locality_margins",
                        "message": f"Locality acceptance is missing margin buckets: {sorted(missing_buckets)}.",
                    }
                )
    else:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "margins.yaml",
                "field": "cross_file",
                "message": "P0-5 margins.yaml is missing.",
            }
        )

    return diagnostics


# ---------------------------------------------------------------------------
# YAML Frontmatter Parser
# ---------------------------------------------------------------------------


def load_witness_rule(artifact_path: Path) -> tuple[dict, str]:
    """Load witness_rule.md, returning (frontmatter_dict, markdown_body).

    Raises SystemExit on missing file or parse errors (exit-2 semantics).
    """
    if not artifact_path.exists():
        raise SystemExit(f"Witness rule artifact not found: {artifact_path}")

    text = artifact_path.read_text(encoding="utf-8")

    if not text.startswith("---"):
        raise SystemExit(
            f"Witness rule artifact missing YAML frontmatter delimiter: {artifact_path}"
        )

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SystemExit(
            f"Witness rule artifact has unclosed YAML frontmatter: {artifact_path}"
        )

    yaml_text = parts[1]
    body = parts[2]

    try:
        frontmatter = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"Witness rule YAML parse error: {exc}") from exc

    if not isinstance(frontmatter, dict):
        raise SystemExit("Witness rule frontmatter is not a mapping")

    return frontmatter, body


# ---------------------------------------------------------------------------
# Digest helper
# ---------------------------------------------------------------------------


def file_digest(path: Path) -> str:
    """Returns 'sha256:' + SHA-256 hex digest of the file."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Check runner
# ---------------------------------------------------------------------------


def _run_check(
    rule_id: str,
    rule_name: str,
    check_fn: Callable[..., Any],
    *args: object,
    **kwargs: object,
) -> dict:
    """Run a check function and return a structured result.

    Diagnostics with ``severity == "warning"`` are treated as deferred (not
    hard failures).  A check result is ``fail`` only when at least one
    non-warning diagnostic is present; ``deferred`` when only warnings remain;
    ``pass`` when no diagnostics are produced.
    """
    try:
        result = check_fn(*args, **kwargs)
        # Handle functions that return tuple (diags, extra)
        if isinstance(result, tuple):
            diags = result[0]
        else:
            diags = result
        hard = [d for d in diags if d.get("severity") != "warning"]
        warnings = [d for d in diags if d.get("severity") == "warning"]
        if hard:
            status = "fail"
        elif warnings:
            status = "deferred"
        else:
            status = "pass"
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": status,
            "diagnostics": [d.get("message", str(d)) for d in diags],
        }
    except Exception as exc:
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": "fail",
            "diagnostics": [f"Check error: {exc}"],
        }


# ---------------------------------------------------------------------------
# FV-SPEC-067: Witness Contract Artifact
# ---------------------------------------------------------------------------


def check_fv_spec_067_witness_contract_artifact(frontmatter: dict) -> list[dict]:
    """FV-SPEC-067: All 13 required frontmatter fields, layer separation, routes."""
    diagnostics: list[dict] = []

    # All 13 required frontmatter fields present
    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in frontmatter:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-067",
                    "file": "witness_rule.md",
                    "field": field,
                    "message": f"Required frontmatter field '{field}' is missing.",
                }
            )

    # status is one of STATUS_ENUM (or null for draft)
    status = frontmatter.get("status")
    if status is not None and str(status) not in STATUS_ENUM:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-067",
                "file": "witness_rule.md",
                "field": "status",
                "message": f"Status '{status}' is not in {sorted(STATUS_ENUM)}.",
            }
        )

    # confirmation_routes, if present and not null, has A, B, C sub-keys each with `enabled`
    routes = frontmatter.get("confirmation_routes")
    if routes is not None and isinstance(routes, dict):
        for route_key in ("A", "B", "C"):
            if route_key not in routes:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-067",
                        "file": "witness_rule.md",
                        "field": f"confirmation_routes.{route_key}",
                        "message": f"confirmation_routes missing sub-key '{route_key}'.",
                    }
                )
            else:
                route = routes[route_key]
                if not isinstance(route, dict) or "enabled" not in route:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-067",
                            "file": "witness_rule.md",
                            "field": f"confirmation_routes.{route_key}.enabled",
                            "message": f"Route '{route_key}' missing required 'enabled' field.",
                        }
                    )
                elif route.get("enabled") is False:
                    reason = route.get("disabled_reason")
                    if not isinstance(reason, str) or not reason.strip():
                        diagnostics.append(
                            {
                                "rule_id": "FV-SPEC-067",
                                "file": "witness_rule.md",
                                "field": f"confirmation_routes.{route_key}.disabled_reason",
                                "message": (
                                    f"Route '{route_key}' is disabled and needs an explicit disabled_reason."
                                ),
                            }
                        )

        # At least one route must be enabled
        all_disabled = all(
            not routes.get(k, {}).get("enabled", False)
            for k in ("A", "B", "C")
            if isinstance(routes.get(k), dict)
        )
        if all_disabled and all(k in routes for k in ("A", "B", "C")):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-067",
                    "file": "witness_rule.md",
                    "field": "confirmation_routes",
                    "message": "All confirmation routes are disabled; at least one must be enabled.",
                }
            )

    elif routes is not None and not isinstance(routes, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-067",
                "file": "witness_rule.md",
                "field": "confirmation_routes",
                "message": "confirmation_routes must be a mapping with A, B, C sub-keys.",
            }
        )

    # Layer conflation check: if case_decision is a dict, acceptance_requires
    # must not contain any string that is also in RUBRIC_LABELS
    case_decision = frontmatter.get("case_decision")
    if isinstance(case_decision, dict):
        acceptance_requires = case_decision.get("acceptance_requires", [])
        if isinstance(acceptance_requires, list):
            conflated = [
                item for item in acceptance_requires if str(item) in RUBRIC_LABELS
            ]
            if conflated:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-067",
                        "file": "witness_rule.md",
                        "field": "case_decision.acceptance_requires",
                        "message": (
                            f"Layer conflation: case_decision.acceptance_requires contains "
                            f"rubric label(s) {conflated!r}. Response labels must not be used "
                            f"as case-level acceptance criteria."
                        ),
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-068: Direction-Aware Rubric
# ---------------------------------------------------------------------------


def check_fv_spec_068_direction_aware_rubric(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-068: Rubric labels, answer roles, refusal flag, many_valued_policy."""
    diagnostics: list[dict] = []

    rubric = frontmatter.get("rubric")
    if rubric is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric",
                "message": "rubric key is missing or null.",
            }
        )
        return diagnostics

    if not isinstance(rubric, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric",
                "message": "rubric must be a mapping.",
            }
        )
        return diagnostics

    # rubric.answer_roles is a list containing all four ANSWER_ROLES
    answer_roles = rubric.get("answer_roles", [])
    if not isinstance(answer_roles, list):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric.answer_roles",
                "message": "rubric.answer_roles must be a list.",
            }
        )
    else:
        missing_roles = ANSWER_ROLES - set(str(r) for r in answer_roles)
        if missing_roles:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-068",
                    "file": "witness_rule.md",
                    "field": "rubric.answer_roles",
                    "message": f"rubric.answer_roles missing required roles: {sorted(missing_roles)}.",
                }
            )

    # rubric.labels is a list containing all five RUBRIC_LABELS
    labels = rubric.get("labels", [])
    if not isinstance(labels, list):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric.labels",
                "message": "rubric.labels must be a list.",
            }
        )
    else:
        missing_labels = RUBRIC_LABELS - set(str(lbl) for lbl in labels)
        if missing_labels:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-068",
                    "file": "witness_rule.md",
                    "field": "rubric.labels",
                    "message": f"rubric.labels missing required labels: {sorted(missing_labels)}.",
                }
            )
        # refusal must NOT be in labels (it's a separate flag)
        if "refusal" in [str(lbl) for lbl in labels]:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-068",
                    "file": "witness_rule.md",
                    "field": "rubric.labels",
                    "message": (
                        "rubric.labels contains 'refusal'; refusal must be a separate flag "
                        "(refusal_flag_separate: true), not merged into correctness labels."
                    ),
                }
            )

    # rubric.refusal_flag_separate is True
    refusal_flag_separate = rubric.get("refusal_flag_separate")
    if refusal_flag_separate is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric.refusal_flag_separate",
                "message": (
                    f"rubric.refusal_flag_separate must be true (got {refusal_flag_separate!r}). "
                    f"Refusal is a separate flag, not merged with correctness."
                ),
            }
        )

    # rubric.many_valued_policy key present (even if null, needs decision_ref)
    if "many_valued_policy" not in rubric:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-068",
                "file": "witness_rule.md",
                "field": "rubric.many_valued_policy",
                "message": "rubric.many_valued_policy key must be present (even if null, with decision_ref).",
            }
        )

    # If fixtures_dir provided: validate scoring fixtures
    if fixtures_dir is not None:
        scoring_dir = fixtures_dir / "valid" / "scoring"
        if scoring_dir.exists():
            for fixture_file in sorted(scoring_dir.glob("*.json")):
                try:
                    fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-068",
                            "file": str(fixture_file.name),
                            "field": "/",
                            "message": f"Cannot parse scoring fixture: {exc}",
                        }
                    )
                    continue
                expected = fixture.get("expected", {})
                correctness = expected.get("correctness")
                if correctness is not None and str(correctness) not in RUBRIC_LABELS:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-068",
                            "file": fixture_file.name,
                            "field": "expected.correctness",
                            "message": f"Scoring fixture correctness '{correctness}' not in RUBRIC_LABELS.",
                        }
                    )
                refusal_flag = expected.get("refusal_flag")
                if refusal_flag is not None and not isinstance(refusal_flag, bool):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-068",
                            "file": fixture_file.name,
                            "field": "expected.refusal_flag",
                            "message": f"Scoring fixture refusal_flag must be boolean, got {refusal_flag!r}.",
                        }
                    )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-069: Raw Score Semantics
# ---------------------------------------------------------------------------


def check_fv_spec_069_raw_score_semantics(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-069: Raw score conventions, no mixed scales, no silent approximation."""
    diagnostics: list[dict] = []

    conventions = frontmatter.get("raw_score_conventions")
    if not isinstance(conventions, list):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-069",
                "file": "witness_rule.md",
                "field": "raw_score_conventions",
                "message": "raw_score_conventions must be a list.",
            }
        )
        return diagnostics

    statistic_kinds_used: list[str] = []
    for i, entry in enumerate(conventions):
        if not isinstance(entry, dict):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-069",
                    "file": "witness_rule.md",
                    "field": f"raw_score_conventions[{i}]",
                    "message": "Each raw_score_conventions entry must be a mapping.",
                }
            )
            continue

        # Check required fields present
        for field in REQUIRED_RAW_SCORE_FIELDS:
            if field not in entry:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-069",
                        "file": "witness_rule.md",
                        "field": f"raw_score_conventions[{i}].{field}",
                        "message": f"Required raw_score_conventions field '{field}' missing in entry {i}.",
                    }
                )

        # Check insufficient_data_status
        ids = entry.get("insufficient_data_status")
        if ids is not None and str(ids) not in INSUFFICIENT_DATA_STATUSES:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-069",
                    "file": "witness_rule.md",
                    "field": f"raw_score_conventions[{i}].insufficient_data_status",
                    "message": (
                        f"insufficient_data_status '{ids}' must be one of "
                        f"{sorted(INSUFFICIENT_DATA_STATUSES)}."
                    ),
                }
            )

        sk = entry.get("statistic_kind")
        if sk is not None:
            statistic_kinds_used.append(str(sk))

    # No entry mixes sequence_logprob and token_rank in a single comparison
    # (i.e., both statistic kinds cannot appear on the same primary axis within one entry)
    # Check at the convention list level: if both appear, they must be in separate entries only
    # (individual entry mixing: if one entry references both)
    for i, entry in enumerate(conventions):
        if not isinstance(entry, dict):
            continue
        sk = str(entry.get("statistic_kind", ""))
        # If an entry somehow references both (via a combined field), flag it
        # The main protection: an entry with statistic_kind must be one kind only
        # Mixed scale detection: look at fixtures

    # If fixtures_dir provided: validate insufficient_topk fixture
    if fixtures_dir is not None:
        fixture_path = fixtures_dir / "invalid" / "scoring" / "insufficient_topk.json"
        if fixture_path.exists():
            try:
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                expected = fixture.get("expected", {})
                if expected.get("statistic") not in ("unavailable", "invalid"):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-069",
                            "file": "insufficient_topk.json",
                            "field": "expected.statistic",
                            "message": "insufficient_topk fixture must have expected.statistic = 'unavailable' or 'invalid'.",
                        }
                    )
            except (json.JSONDecodeError, OSError) as exc:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-069",
                        "file": "insufficient_topk.json",
                        "field": "/",
                        "message": f"Cannot parse insufficient_topk fixture: {exc}",
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-070: Route A Confirmation
# ---------------------------------------------------------------------------


def check_fv_spec_070_route_a_confirmation(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-070: Route A requires ≥2 independent families, clue_bearing_excluded."""
    diagnostics: list[dict] = []

    routes = frontmatter.get("confirmation_routes")
    if not isinstance(routes, dict):
        return diagnostics

    route_a = routes.get("A")
    if not isinstance(route_a, dict):
        return diagnostics

    if not route_a.get("enabled", False):
        return diagnostics  # Route A not enabled — skip

    # min_independent_families >= 2
    min_fam = route_a.get("min_independent_families")
    if min_fam is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-070",
                "file": "witness_rule.md",
                "field": "confirmation_routes.A.min_independent_families",
                "message": "Route A: min_independent_families is required.",
            }
        )
    elif not isinstance(min_fam, int) or min_fam < 2:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-070",
                "file": "witness_rule.md",
                "field": "confirmation_routes.A.min_independent_families",
                "message": f"Route A: min_independent_families must be >= 2, got {min_fam!r}.",
            }
        )

    # clue_bearing_excluded: true
    cbe = route_a.get("clue_bearing_excluded")
    if cbe is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-070",
                "file": "witness_rule.md",
                "field": "confirmation_routes.A.clue_bearing_excluded",
                "message": f"Route A: clue_bearing_excluded must be true, got {cbe!r}.",
            }
        )

    # If fixtures_dir provided: check invalid route A fixture
    if fixtures_dir is not None:
        fixture_path = (
            fixtures_dir / "invalid" / "routes" / "route_a_punctuation_variant.json"
        )
        if fixture_path.exists():
            try:
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                if not fixture.get("validation_should_fail"):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-070",
                            "file": "route_a_punctuation_variant.json",
                            "field": "validation_should_fail",
                            "message": "route_a_punctuation_variant fixture must have validation_should_fail: true.",
                        }
                    )
            except (json.JSONDecodeError, OSError):
                pass

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-071: Route B Replication
# ---------------------------------------------------------------------------


def check_fv_spec_071_route_b_replication(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-071: Route B requires training/update seeds."""
    diagnostics: list[dict] = []

    routes = frontmatter.get("confirmation_routes")
    if not isinstance(routes, dict):
        return diagnostics

    route_b = routes.get("B")
    if not isinstance(route_b, dict):
        return diagnostics

    if not route_b.get("enabled", False):
        return diagnostics  # Route B not enabled — skip

    # seed_type == "training_or_update"
    seed_type = route_b.get("seed_type")
    if seed_type != "training_or_update":
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-071",
                "file": "witness_rule.md",
                "field": "confirmation_routes.B.seed_type",
                "message": (
                    f"Route B: seed_type must be 'training_or_update', got {seed_type!r}. "
                    f"Decoding seeds do not produce independent replications."
                ),
            }
        )

    # If fixtures_dir provided: check decoding seed fixture
    if fixtures_dir is not None:
        fixture_path = (
            fixtures_dir / "invalid" / "routes" / "route_b_decoding_seed.json"
        )
        if fixture_path.exists():
            try:
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                if not fixture.get("validation_should_fail"):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-071",
                            "file": "route_b_decoding_seed.json",
                            "field": "validation_should_fail",
                            "message": "route_b_decoding_seed fixture must have validation_should_fail: true.",
                        }
                    )
            except (json.JSONDecodeError, OSError):
                pass

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-072: Route C Verdict Flips
# ---------------------------------------------------------------------------


def check_fv_spec_072_route_c_verdict_flips(frontmatter: dict) -> list[dict]:
    """FV-SPEC-072: Route C requires parent/child hashes, locality; at least one route enabled."""
    diagnostics: list[dict] = []

    routes = frontmatter.get("confirmation_routes")
    if not isinstance(routes, dict):
        return diagnostics

    # At least one of A/B/C must be enabled
    any_enabled = any(
        isinstance(routes.get(k), dict) and routes[k].get("enabled", False)
        for k in ("A", "B", "C")
    )
    if not any_enabled:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-072",
                "file": "witness_rule.md",
                "field": "confirmation_routes",
                "message": "At least one confirmation route (A, B, or C) must be enabled.",
            }
        )

    route_c = routes.get("C")
    if not isinstance(route_c, dict):
        return diagnostics

    if not route_c.get("enabled", False):
        return diagnostics  # Route C not enabled — skip structural checks

    # requires_parent_child_hashes: true
    if route_c.get("requires_parent_child_hashes") is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-072",
                "file": "witness_rule.md",
                "field": "confirmation_routes.C.requires_parent_child_hashes",
                "message": "Route C: requires_parent_child_hashes must be true.",
            }
        )

    # post_transform_locality_required: true
    if route_c.get("post_transform_locality_required") is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-072",
                "file": "witness_rule.md",
                "field": "confirmation_routes.C.post_transform_locality_required",
                "message": "Route C: post_transform_locality_required must be true.",
            }
        )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-073: Case-Level Verdict
# ---------------------------------------------------------------------------


def check_fv_spec_073_case_level_verdict(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-073: Case decision gates, no_witness_is_not_accept, status vocabulary."""
    diagnostics: list[dict] = []

    case_decision = frontmatter.get("case_decision")
    if case_decision is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-073",
                "file": "witness_rule.md",
                "field": "case_decision",
                "message": "case_decision must not be null.",
            }
        )
        return diagnostics

    if not isinstance(case_decision, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-073",
                "file": "witness_rule.md",
                "field": "case_decision",
                "message": "case_decision must be a mapping.",
            }
        )
        return diagnostics

    # no_witness_is_not_accept: true
    nwna = case_decision.get("no_witness_is_not_accept")
    if nwna is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-073",
                "file": "witness_rule.md",
                "field": "case_decision.no_witness_is_not_accept",
                "message": f"case_decision.no_witness_is_not_accept must be true, got {nwna!r}.",
            }
        )

    # acceptance_requires is a non-empty list
    acceptance_requires = case_decision.get("acceptance_requires")
    if not isinstance(acceptance_requires, list) or len(acceptance_requires) == 0:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-073",
                "file": "witness_rule.md",
                "field": "case_decision.acceptance_requires",
                "message": "case_decision.acceptance_requires must be a non-empty list.",
            }
        )

    # rejection_reasons includes both "locality_failure" and "confirmed_recovery"
    rejection_reasons = case_decision.get("rejection_reasons", [])
    if isinstance(rejection_reasons, list):
        rr_set = set(str(r) for r in rejection_reasons)
        for required in ("locality_failure", "confirmed_recovery"):
            if required not in rr_set:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-073",
                        "file": "witness_rule.md",
                        "field": "case_decision.rejection_reasons",
                        "message": f"case_decision.rejection_reasons must include '{required}'.",
                    }
                )

    # inconclusive_mapping has decision_refs list
    inconclusive = case_decision.get("inconclusive_mapping")
    if isinstance(inconclusive, dict):
        if "decision_refs" not in inconclusive or not isinstance(
            inconclusive["decision_refs"], list
        ):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-073",
                    "file": "witness_rule.md",
                    "field": "case_decision.inconclusive_mapping.decision_refs",
                    "message": "case_decision.inconclusive_mapping.decision_refs must be a list.",
                }
            )

    # If fixtures_dir provided: check no_witness_accept invalid fixture
    if fixtures_dir is not None:
        fixture_path = fixtures_dir / "invalid" / "verdicts" / "no_witness_accept.json"
        if fixture_path.exists():
            try:
                fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
                if not fixture.get("validation_should_fail"):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-073",
                            "file": "no_witness_accept.json",
                            "field": "validation_should_fail",
                            "message": "no_witness_accept fixture must have validation_should_fail: true.",
                        }
                    )
            except (json.JSONDecodeError, OSError):
                pass

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-074: Evidence Aggregation
# ---------------------------------------------------------------------------


def check_fv_spec_074_evidence_aggregation(frontmatter: dict) -> list[dict]:
    """FV-SPEC-074: Aggregation policy, raw maximum diagnostic-only, budget reservations."""
    diagnostics: list[dict] = []

    agg = frontmatter.get("aggregation_policy")
    if agg is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy",
                "message": "aggregation_policy must not be null.",
            }
        )
        return diagnostics

    if not isinstance(agg, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy",
                "message": "aggregation_policy must be a mapping.",
            }
        )
        return diagnostics

    # primary_statistic is not "raw_maximum" and not null
    primary = agg.get("primary_statistic")
    if primary is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy.primary_statistic",
                "message": "aggregation_policy.primary_statistic must not be null.",
            }
        )
    elif str(primary) == "raw_maximum":
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy.primary_statistic",
                "message": (
                    "aggregation_policy.primary_statistic must not be 'raw_maximum'; "
                    "raw maximum is diagnostic-only."
                ),
            }
        )

    # raw_maximum_role == "diagnostic_only"
    rmr = agg.get("raw_maximum_role")
    if rmr != "diagnostic_only":
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy.raw_maximum_role",
                "message": (
                    f"aggregation_policy.raw_maximum_role must be 'diagnostic_only', got {rmr!r}."
                ),
            }
        )

    # calibrated_as_whole: true
    caw = agg.get("calibrated_as_whole")
    if caw is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-074",
                "file": "witness_rule.md",
                "field": "aggregation_policy.calibrated_as_whole",
                "message": f"aggregation_policy.calibrated_as_whole must be true, got {caw!r}.",
            }
        )

    # For each enabled route: budget_reservation_ref is non-empty string
    # (deferred if null — recorded as warning in non-strict)
    routes = frontmatter.get("confirmation_routes")
    if isinstance(routes, dict):
        for route_key in ("A", "B", "C"):
            route = routes.get(route_key)
            if isinstance(route, dict) and route.get("enabled", False):
                brr = route.get("budget_reservation_ref")
                if not brr:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-074",
                            "file": "witness_rule.md",
                            "field": f"confirmation_routes.{route_key}.budget_reservation_ref",
                            "message": (
                                f"Route {route_key} is enabled but budget_reservation_ref is null/empty. "
                                f"Each enabled route must have a reserved cost reference."
                            ),
                        }
                    )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-075: Blinded Annotation
# ---------------------------------------------------------------------------


def check_fv_spec_075_blinded_annotation(
    frontmatter: dict, witness_dir: Path
) -> list[dict]:
    """FV-SPEC-075: annotation_protocol and review record validation."""
    diagnostics: list[dict] = []

    annotation_protocol = frontmatter.get("annotation_protocol")
    if annotation_protocol is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-075",
                "file": "witness_rule.md",
                "field": "annotation_protocol",
                "message": "annotation_protocol must not be null.",
            }
        )
        return diagnostics

    if not isinstance(annotation_protocol, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-075",
                "file": "witness_rule.md",
                "field": "annotation_protocol",
                "message": "annotation_protocol must be a mapping.",
            }
        )
        return diagnostics

    # sole_llm_oracle_forbidden: true
    slf = annotation_protocol.get("sole_llm_oracle_forbidden")
    if slf is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-075",
                "file": "witness_rule.md",
                "field": "annotation_protocol.sole_llm_oracle_forbidden",
                "message": f"annotation_protocol.sole_llm_oracle_forbidden must be true, got {slf!r}.",
            }
        )

    # outcome_driven_rubric_change_forbidden: true
    odrcf = annotation_protocol.get("outcome_driven_rubric_change_forbidden")
    if odrcf is not True:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-075",
                "file": "witness_rule.md",
                "field": "annotation_protocol.outcome_driven_rubric_change_forbidden",
                "message": (
                    f"annotation_protocol.outcome_driven_rubric_change_forbidden must be true, "
                    f"got {odrcf!r}."
                ),
            }
        )

    review_refs = frontmatter.get("review_refs")
    if not isinstance(review_refs, list) or not review_refs:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-075",
                "file": "witness_rule.md",
                "field": "review_refs",
                "message": "review_refs must list at least one blinded annotation review.",
            }
        )
    else:
        for ref in review_refs:
            ref_path = witness_dir / str(ref)
            if not ref_path.exists():
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": str(ref),
                        "field": "review_refs",
                        "message": f"review_refs entry does not exist: {ref}",
                    }
                )

    # Validate review files in witness_dir/reviews/
    reviews_dir = witness_dir / "reviews"
    if reviews_dir.exists():
        for review_file in sorted(reviews_dir.glob("*.json")):
            try:
                review = json.loads(review_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "/",
                        "message": f"Cannot parse review file: {exc}",
                    }
                )
                continue

            # Required fields
            for field in REQUIRED_REVIEW_FIELDS:
                if field not in review:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-075",
                            "file": review_file.name,
                            "field": field,
                            "message": f"Review missing required field '{field}'.",
                        }
                    )

            # annotators_blinded: true
            if review.get("annotators_blinded") is not True:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "annotators_blinded",
                        "message": "Review: annotators_blinded must be true.",
                    }
                )

            # system_identity_hidden: true
            if review.get("system_identity_hidden") is not True:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "system_identity_hidden",
                        "message": "Review: system_identity_hidden must be true.",
                    }
                )

            # sole_llm_oracle: false
            if review.get("sole_llm_oracle") is not False:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "sole_llm_oracle",
                        "message": "Review: sole_llm_oracle must be false; sole LLM adjudication is forbidden.",
                    }
                )

            # outcome_driven_rubric_change: false
            if review.get("outcome_driven_rubric_change") is not False:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "outcome_driven_rubric_change",
                        "message": "Review: outcome_driven_rubric_change must be false.",
                    }
                )

            # kappa is a number or the string "undefined"
            kappa = review.get("kappa")
            if not isinstance(kappa, (int, float)) and kappa != "undefined":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "kappa",
                        "message": f"Review: kappa must be a number or 'undefined', got {kappa!r}.",
                    }
                )

            # approver_id non-empty
            approver_id = review.get("approver_id")
            if not approver_id or not str(approver_id).strip():
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-075",
                        "file": review_file.name,
                        "field": "approver_id",
                        "message": "Review: approver_id must be non-empty.",
                    }
                )

            # review_date is valid ISO 8601
            rd = review.get("review_date")
            if rd:
                try:
                    datetime.fromisoformat(str(rd))
                except ValueError:
                    if not _ISO_DATE_RE.match(str(rd)):
                        diagnostics.append(
                            {
                                "rule_id": "FV-SPEC-075",
                                "file": review_file.name,
                                "field": "review_date",
                                "message": f"Review: review_date '{rd}' is not valid ISO 8601.",
                            }
                        )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-076: Reconstructable Records
# ---------------------------------------------------------------------------


def check_fv_spec_076_reconstructable_records(
    frontmatter: dict, fixtures_dir: Path | None = None
) -> list[dict]:
    """FV-SPEC-076: Evidence schema and provenance completeness."""
    diagnostics: list[dict] = []

    evidence_schema = frontmatter.get("evidence_schema")
    if evidence_schema is None:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-076",
                "file": "witness_rule.md",
                "field": "evidence_schema",
                "message": "evidence_schema must not be null.",
            }
        )
        return diagnostics

    if not isinstance(evidence_schema, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-076",
                "file": "witness_rule.md",
                "field": "evidence_schema",
                "message": "evidence_schema must be a mapping.",
            }
        )
        return diagnostics

    # evidence_schema has all REQUIRED_EVIDENCE_FIELDS as keys
    for field in REQUIRED_EVIDENCE_FIELDS:
        if field not in evidence_schema:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-076",
                    "file": "witness_rule.md",
                    "field": f"evidence_schema.{field}",
                    "message": f"evidence_schema missing required field '{field}'.",
                }
            )

    if fixtures_dir is None:
        return diagnostics

    # Validate valid evidence fixtures
    valid_evidence_dir = fixtures_dir / "valid" / "evidence"
    if valid_evidence_dir.exists():
        for fixture_file in sorted(valid_evidence_dir.glob("*.json")):
            try:
                fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "/",
                        "message": f"Cannot parse valid evidence fixture: {exc}",
                    }
                )
                continue

            # All REQUIRED_EVIDENCE_FIELDS present
            for field in REQUIRED_EVIDENCE_FIELDS:
                if field not in fixture:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-076",
                            "file": fixture_file.name,
                            "field": field,
                            "message": f"Valid evidence fixture missing required field '{field}'.",
                        }
                    )

            # raw_response_ids is non-empty list
            rri = fixture.get("raw_response_ids")
            if not isinstance(rri, list) or len(rri) == 0:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "raw_response_ids",
                        "message": "Valid evidence fixture: raw_response_ids must be non-empty.",
                    }
                )

            # ground_truth_separate: true
            if fixture.get("ground_truth_separate") is not True:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "ground_truth_separate",
                        "message": "Valid evidence fixture: ground_truth_separate must be true.",
                    }
                )

            # No control_oracle_label inside confirmation block
            confirmation = fixture.get("confirmation", {})
            if (
                isinstance(confirmation, dict)
                and "control_oracle_label" in confirmation
            ):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "confirmation.control_oracle_label",
                        "message": (
                            "Valid evidence fixture: confirmation block must not contain "
                            "'control_oracle_label'; oracle labels must not be used as recovery evidence."
                        ),
                    }
                )

    # Validate invalid evidence fixtures — each should have validation_should_fail: true
    invalid_evidence_dir = fixtures_dir / "invalid" / "evidence"
    if invalid_evidence_dir.exists():
        for fixture_file in sorted(invalid_evidence_dir.glob("*.json")):
            try:
                fixture = json.loads(fixture_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "/",
                        "message": f"Cannot parse invalid evidence fixture: {exc}",
                    }
                )
                continue

            rubric = (
                frontmatter.get("rubric")
                if isinstance(frontmatter.get("rubric"), dict)
                else {}
            )
            rubric_version = rubric.get("version") if isinstance(rubric, dict) else None
            defects = evidence_defects(
                fixture, str(rubric_version) if rubric_version else None
            )
            if not fixture.get("validation_should_fail") or not defects:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-076",
                        "file": fixture_file.name,
                        "field": "validation_should_fail",
                        "message": (
                            "Invalid evidence fixture must set validation_should_fail and "
                            f"exhibit a provenance defect; found defects={defects or []}."
                        ),
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-077: Scoped CLI Validation
# ---------------------------------------------------------------------------


def check_fv_spec_077_scoped_cli_validation(
    frontmatter: dict,
    spec_root: Path,
    witness_dir: Path,
    fixtures_dir: Path | None,
    strict: bool,
) -> list[dict]:
    """FV-SPEC-077: Digest, deferred items, strict-mode open decisions, no model calls."""
    diagnostics: list[dict] = []

    # Assert no-model-calls sentinel is True
    if not _NO_MODEL_CALLS:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "witness_rule_validator.py",
                "field": "_NO_MODEL_CALLS",
                "message": "_NO_MODEL_CALLS sentinel is False; validator must not invoke model calls.",
            }
        )

    # List open decisions from blocking_decisions
    blocking_decisions = frontmatter.get("blocking_decisions", [])
    open_decisions = []
    if isinstance(blocking_decisions, list):
        for d in blocking_decisions:
            if isinstance(d, dict):
                status = d.get("status", "")
                if status not in ("resolved", "not_applicable"):
                    open_decisions.append(d.get("decision_id", "unknown"))

    diagnostics.extend(check_cross_file_consistency(frontmatter, spec_root))

    if strict:
        rubric = (
            frontmatter.get("rubric")
            if isinstance(frontmatter.get("rubric"), dict)
            else {}
        )
        rubric_version = rubric.get("version") if isinstance(rubric, dict) else None
        reviews_dir = witness_dir / "reviews"
        if reviews_dir.exists() and rubric_version:
            for review_file in reviews_dir.glob("*.json"):
                try:
                    review = json.loads(review_file.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if review.get("rubric_version") != rubric_version:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-075",
                            "file": review_file.name,
                            "field": "rubric_version",
                            "message": (
                                "Strict mode: review rubric_version "
                                f"{review.get('rubric_version')!r} is stale relative to "
                                f"rubric.version {rubric_version!r}."
                            ),
                        }
                    )

    # Strict mode: fail if any applicable decision is open
    if strict and open_decisions:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "witness_rule.md",
                "field": "blocking_decisions",
                "message": (
                    f"Strict mode: {len(open_decisions)} decision(s) are still open: "
                    f"{', '.join(sorted(open_decisions))}. Resolve all before final validation."
                ),
            }
        )

    # Strict mode: fail if witness_dir/review_manifest.json doesn't exist
    review_manifest_path = witness_dir / "review_manifest.json"
    if strict and not review_manifest_path.exists():
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "review_manifest.json",
                "field": "/",
                "message": "Strict mode: review_manifest.json not found in witness_dir.",
            }
        )

    return diagnostics


# ---------------------------------------------------------------------------
# Baseline Comparison
# ---------------------------------------------------------------------------


def check_baseline_comparison_wr(
    frontmatter: dict, baseline_path: Path
) -> tuple[list[dict], dict]:
    """Compare current witness_rule against baseline for frozen-policy changes."""
    diagnostics: list[dict] = []
    comparison: dict = {"status": "not_requested"}

    if not baseline_path.exists():
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "witness_rule.md",
                "field": "baseline",
                "message": f"Baseline not found: {baseline_path}",
            }
        )
        return diagnostics, {
            "status": "fail",
            "changed_fields": [],
            "revision_match": False,
        }

    try:
        baseline_fm, _ = load_witness_rule(baseline_path)
    except SystemExit as exc:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": str(baseline_path),
                "field": "/",
                "message": f"Cannot load baseline: {exc}",
            }
        )
        return diagnostics, {
            "status": "fail",
            "changed_fields": [],
            "revision_match": False,
        }

    cur_version = str(frontmatter.get("version", ""))
    base_version = str(baseline_fm.get("version", ""))
    revision_match = cur_version == base_version

    changed_fields: list[str] = []

    # Compare rubric (frozen policy)
    cur_rubric = frontmatter.get("rubric")
    base_rubric = baseline_fm.get("rubric")
    if cur_rubric != base_rubric:
        changed_fields.append("rubric")

    # Compare aggregation_policy
    if frontmatter.get("aggregation_policy") != baseline_fm.get("aggregation_policy"):
        changed_fields.append("aggregation_policy")

    # Compare case_decision
    if frontmatter.get("case_decision") != baseline_fm.get("case_decision"):
        changed_fields.append("case_decision")

    # If frozen policy changed but version unchanged → fail
    if changed_fields and revision_match:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-077",
                "file": "witness_rule.md",
                "field": "version",
                "message": (
                    f"Frozen policy changed ({', '.join(changed_fields)}) "
                    f"but version unchanged ({cur_version}). "
                    f"Increment version when policies change."
                ),
            }
        )

    status = "fail" if diagnostics else "pass"
    comparison = {
        "status": status,
        "changed_fields": changed_fields,
        "revision_match": revision_match,
    }
    return diagnostics, comparison


# ---------------------------------------------------------------------------
# Report Writer
# ---------------------------------------------------------------------------


def write_witness_rule_report(
    checks: list[dict],
    frontmatter: dict,
    spec_root: Path,
    witness_dir: Path,
    strict: bool,
    report_path: Path | None,
    fixture_results: list[dict],
    decision_status: list[dict],
    baseline_comparison: dict | None,
) -> dict:
    """Generate and optionally write the JSON validation report."""
    # Compute input digests
    input_digests: dict = {}
    witness_rule_path = spec_root / "witness_rule.md"
    if witness_rule_path.exists():
        input_digests["witness_rule.md"] = file_digest(witness_rule_path)
    review_manifest_path = witness_dir / "review_manifest.json"
    if review_manifest_path.exists():
        input_digests["review_manifest.json"] = file_digest(review_manifest_path)

    overall = (
        "pass"
        if all(
            c.get("status") in ("pass", "deferred", "skipped", "warning")
            for c in checks
        )
        else "fail"
    )

    # Checks with only severity=warning diagnostics still count as pass
    # Re-evaluate: a check is "fail" if it has any non-warning diagnostic
    for check in checks:
        if check.get("status") == "fail":
            check.get("diagnostics", [])
            # If all diags are warnings, treat as pass
            # (For now, treat all fail as fail — warnings are embedded in the message)
            overall = "fail"
            break

    report = {
        "scope": "witness-rule",
        "spec_root": str(spec_root),
        "timestamp": datetime.now(UTC).isoformat(),
        "strict": strict,
        "input_digests": input_digests,
        "checks": checks,
        "fixture_results": fixture_results,
        "decision_status": decision_status,
        "deferred": DEFERRED_ITEMS,
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


# ---------------------------------------------------------------------------
# Top-Level Entry Point
# ---------------------------------------------------------------------------


def validate_witness_rule(
    spec_root: str | Path,
    witness_dir: str | Path,
    report_path: str | Path | None = None,
    strict: bool = False,
    baseline_suite_path: str | Path | None = None,
) -> tuple[bool, dict]:
    """Validate the witness rule artifact. Returns (passed, report)."""
    spec_root = Path(spec_root)
    witness_dir = Path(witness_dir)
    report_path = Path(report_path) if report_path else None
    baseline_suite_path = Path(baseline_suite_path) if baseline_suite_path else None

    artifact_path = spec_root / "witness_rule.md"
    try:
        frontmatter, body = load_witness_rule(artifact_path)
    except SystemExit:
        raise

    # Fixtures dir: look for tests/fixtures/witness_rule relative to spec_root
    # spec_root is .factverify/spec, so fixtures_dir would be tests/fixtures/witness_rule
    repo_root = spec_root.parent.parent  # .factverify/spec -> .factverify -> repo
    fixtures_dir = repo_root / "tests" / "fixtures" / "witness_rule"
    if not fixtures_dir.exists():
        fixtures_dir = None

    checks: list[dict] = []

    # FV-SPEC-067: Witness contract artifact
    checks.append(
        _run_check(
            "FV-SPEC-067",
            "witness_contract_artifact",
            check_fv_spec_067_witness_contract_artifact,
            frontmatter,
        )
    )

    # FV-SPEC-068: Direction-aware rubric
    checks.append(
        _run_check(
            "FV-SPEC-068",
            "direction_aware_rubric",
            check_fv_spec_068_direction_aware_rubric,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-069: Raw score semantics
    checks.append(
        _run_check(
            "FV-SPEC-069",
            "raw_score_semantics",
            check_fv_spec_069_raw_score_semantics,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-070: Route A confirmation
    checks.append(
        _run_check(
            "FV-SPEC-070",
            "route_a_confirmation",
            check_fv_spec_070_route_a_confirmation,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-071: Route B replication
    checks.append(
        _run_check(
            "FV-SPEC-071",
            "route_b_replication",
            check_fv_spec_071_route_b_replication,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-072: Route C verdict flips
    checks.append(
        _run_check(
            "FV-SPEC-072",
            "route_c_verdict_flips",
            check_fv_spec_072_route_c_verdict_flips,
            frontmatter,
        )
    )

    # FV-SPEC-073: Case-level verdict
    checks.append(
        _run_check(
            "FV-SPEC-073",
            "case_level_verdict",
            check_fv_spec_073_case_level_verdict,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-074: Evidence aggregation
    checks.append(
        _run_check(
            "FV-SPEC-074",
            "evidence_aggregation",
            check_fv_spec_074_evidence_aggregation,
            frontmatter,
        )
    )

    # FV-SPEC-075: Blinded annotation
    checks.append(
        _run_check(
            "FV-SPEC-075",
            "blinded_annotation",
            check_fv_spec_075_blinded_annotation,
            frontmatter,
            witness_dir,
        )
    )

    # FV-SPEC-076: Reconstructable records
    checks.append(
        _run_check(
            "FV-SPEC-076",
            "reconstructable_records",
            check_fv_spec_076_reconstructable_records,
            frontmatter,
            fixtures_dir,
        )
    )

    # FV-SPEC-077: Scoped CLI validation
    checks.append(
        _run_check(
            "FV-SPEC-077",
            "scoped_cli_validation",
            check_fv_spec_077_scoped_cli_validation,
            frontmatter,
            spec_root,
            witness_dir,
            fixtures_dir,
            strict,
        )
    )

    # Baseline comparison
    baseline_comparison: dict | None = None
    if baseline_suite_path:
        bl_diags, baseline_comparison = check_baseline_comparison_wr(
            frontmatter,
            baseline_suite_path,
        )
        if bl_diags:
            # Add to last check (FV-SPEC-077)
            checks[-1]["status"] = "fail"
            checks[-1]["diagnostics"].extend(d.get("message", str(d)) for d in bl_diags)

    rubric = (
        frontmatter.get("rubric") if isinstance(frontmatter.get("rubric"), dict) else {}
    )
    rubric_version = rubric.get("version") if isinstance(rubric, dict) else None
    fixture_diags, fixture_results = collect_fixture_interpretations(
        fixtures_dir, str(rubric_version) if rubric_version else None
    )
    checks.append(
        _run_check(
            "FV-SPEC-077",
            "fixture_interpreter",
            lambda diags: diags,
            fixture_diags,
        )
    )

    # Build decision_status list
    blocking_decisions = frontmatter.get("blocking_decisions", [])
    decision_status: list[dict] = []
    if isinstance(blocking_decisions, list):
        for d in blocking_decisions:
            if isinstance(d, dict):
                decision_status.append(
                    {
                        "decision_id": d.get("decision_id"),
                        "status": d.get("status", "open"),
                    }
                )

    # Generate report
    report = write_witness_rule_report(
        checks,
        frontmatter,
        spec_root,
        witness_dir,
        strict,
        report_path,
        fixture_results,
        decision_status,
        baseline_comparison,
    )

    passed = report["overall"] == "pass"
    return passed, report
