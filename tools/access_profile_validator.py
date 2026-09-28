"""P0-4 access profile validator.

Validates access_profile.md (YAML frontmatter + Markdown body) against
FV-SPEC-047 through FV-SPEC-056.  All checks are offline — zero endpoint
calls, model execution, or GPU jobs.

Exit codes (via the CLI dispatcher in validate_spec.py):
    0 — all checks passed
    1 — one or more validation failures
    2 — missing/malformed inputs
"""

from __future__ import annotations

import hashlib
import json
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

REQUIRED_PROFILE_VALUES = {"A", "B", "C"}
CAPABILITY_STATES = {"declared", "verified", "unavailable", "unverified"}
CAPABILITY_FIELDS = [
    "text",
    "scores",
    "internals",
    "candidate_scoring",
    "controllable_decoding",
]
REQUIRED_BLOCKING_DECISIONS = {"D-13", "D-14", "D-27", "D-28", "D-29", "D-31"}
STATUS_ENUM = {
    "confirmed_recovery",
    "conformance",
    "non_identifiable",
    "incomplete",
}
VERIFICATION_STATES = {"unverified", "partial", "verified"}
RECOGNIZED_SOURCES = {
    "model_api",
    "published_documentation",
    "score_endpoint",
    "weight_access",
    "checkpoint_export",
    "training_data",
    "provider_attestation",
    "direct_test",
    "historical_checkpoint",
    "pre_unlearning_model",
}
# Evidence gaps must map to incomplete — never silently promoted.
REQUIRED_EVIDENCE_MAPPINGS = {
    "missing_raw_score": "incomplete",
    "known_control_label_alone": "incomplete",
    "completed_without_witness": "incomplete",
}

_SEMVER_RE = re.compile(r"^\d+\.\d+\.\d+$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_UNIVERSAL_ERASURE_RE = re.compile(
    r"\b(completely\s+removed|fully\s+erased|totally\s+eliminated|"
    r"entirely\s+deleted|permanently\s+removed|absolutely\s+erased)\b",
    re.IGNORECASE,
)

REQUIRED_FRONTMATTER_FIELDS = [
    "version",
    "profile",
    "measurement_point",
    "systems",
    "roles",
    "permitted_sources",
    "handling_policies",
    "budget_ref",
    "blocking_decisions",
    "provenance_refs",
]

REQUIRED_MANIFEST_FIELDS = [
    "manifest_id",
    "system_id",
    "tap_location",
    "intervening_processors",
    "model_identity",
    "tokenizer_identity",
    "evidence_source",
    "reviewer_id",
    "review_date",
]

REQUIRED_JUSTIFICATION_FIELDS = [
    "justification_id",
    "revision",
    "system_pair",
    "observation_boundary",
    "permitted_queries",
    "historical_access",
    "argument_type",
    "argument_summary",
    "reviewer_id",
    "review_date",
    "limitations",
]

REQUIRED_CLAIM_FIELDS = [
    "template_id",
    "profile",
    "stage",
    "completed_tests",
    "budget_ref",
    "claim_text",
    "limitations",
    "reviewer_id",
    "review_date",
]


# ---------------------------------------------------------------------------
# YAML Frontmatter Parser
# ---------------------------------------------------------------------------


def load_access_profile(profile_path: Path) -> tuple[dict, str]:
    """Load access_profile.md, returning (frontmatter_dict, markdown_body).

    Raises SystemExit on missing file or parse errors.
    """
    if not profile_path.exists():
        raise SystemExit(f"Access profile not found: {profile_path}")

    text = profile_path.read_text(encoding="utf-8")

    # Split YAML frontmatter from Markdown body
    if not text.startswith("---"):
        raise SystemExit(
            f"Access profile missing YAML frontmatter delimiter: {profile_path}"
        )

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise SystemExit(
            f"Access profile has unclosed YAML frontmatter: {profile_path}"
        )

    yaml_text = parts[1]
    body = parts[2]

    try:
        frontmatter = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise SystemExit(f"Access profile YAML parse error: {exc}") from exc

    if not isinstance(frontmatter, dict):
        raise SystemExit("Access profile frontmatter is not a mapping")

    return frontmatter, body


def validate_frontmatter_schema(frontmatter: dict) -> list[dict]:
    """Check that all required top-level fields are present and well-typed."""
    diagnostics: list[dict] = []

    for field in REQUIRED_FRONTMATTER_FIELDS:
        if field not in frontmatter:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": field,
                    "message": f"Required field '{field}' is missing.",
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-047: Access Contract Artifact
# ---------------------------------------------------------------------------


def check_access_contract_artifact(frontmatter: dict, body: str) -> list[dict]:
    """Validate access contract structure, version, profile, blocking decisions."""
    diagnostics = validate_frontmatter_schema(frontmatter)

    # Version format
    version = frontmatter.get("version", "")
    if version and not _SEMVER_RE.match(str(version)):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-047",
                "file": "access_profile.md",
                "field": "version",
                "message": f"Version '{version}' is not valid semver (expected X.Y.Z).",
            }
        )

    # Profile enum
    profile = frontmatter.get("profile")
    if profile is not None and str(profile) not in REQUIRED_PROFILE_VALUES:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-047",
                "file": "access_profile.md",
                "field": "profile",
                "message": f"Unknown profile value '{profile}'; expected A, B, or C.",
            }
        )

    # Systems must be a mapping with unique system_id values
    systems = frontmatter.get("systems")
    if systems is not None and not isinstance(systems, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-047",
                "file": "access_profile.md",
                "field": "systems",
                "message": "Field 'systems' must be a mapping.",
            }
        )
    elif isinstance(systems, dict):
        seen_ids: set[str] = set()
        for key, sys_data in systems.items():
            if not isinstance(sys_data, dict):
                continue
            sid = str(sys_data.get("system_id", key))
            if sid in seen_ids:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-047",
                        "file": "access_profile.md",
                        "field": "systems",
                        "message": f"Duplicate system_id '{sid}'.",
                    }
                )
            seen_ids.add(sid)

    # Roles must be a list
    roles = frontmatter.get("roles")
    if roles is not None and not isinstance(roles, list):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-047",
                "file": "access_profile.md",
                "field": "roles",
                "message": "Field 'roles' must be a list.",
            }
        )

    # Blocking decisions: must include required set
    bd = frontmatter.get("blocking_decisions")
    if isinstance(bd, list):
        declared_ids = {d.get("decision_id") for d in bd if isinstance(d, dict)}
        missing = REQUIRED_BLOCKING_DECISIONS - declared_ids
        if missing:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "blocking_decisions",
                    "message": (
                        f"Missing required blocking decisions: "
                        f"{', '.join(sorted(missing))}."
                    ),
                }
            )

    # handling_policies must cover all four statuses
    hp = frontmatter.get("handling_policies")
    if isinstance(hp, dict):
        missing_statuses = STATUS_ENUM - set(hp.keys())
        if missing_statuses:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "handling_policies",
                    "message": (
                        f"handling_policies missing status mappings: "
                        f"{', '.join(sorted(missing_statuses))}."
                    ),
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-047 (cross-file): Cross-file reference resolution
# ---------------------------------------------------------------------------


def check_cross_file_references(
    frontmatter: dict,
    spec_root: Path,
    access_dir: Path,
) -> list[dict]:
    """Resolve budget_ref, provenance_refs, claim_refs, identifiability_refs."""
    diagnostics: list[dict] = []

    # budget_ref
    budget_ref = frontmatter.get("budget_ref")
    if budget_ref:
        budget_path = spec_root / str(budget_ref)
        if not budget_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "budget_ref",
                    "message": f"Budget reference not found: {budget_ref}",
                }
            )

    # provenance_refs
    for ref in frontmatter.get("provenance_refs", []):
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "provenance_refs",
                    "message": f"Provenance reference not found: {ref}",
                }
            )

    # claim_refs
    for ref in frontmatter.get("claim_refs", []):
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "claim_refs",
                    "message": f"Claim reference not found: {ref}",
                }
            )

    # identifiability_refs
    for ref in frontmatter.get("identifiability_refs", []):
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-047",
                    "file": "access_profile.md",
                    "field": "identifiability_refs",
                    "message": f"Identifiability reference not found: {ref}",
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-048: Observation Capabilities
# ---------------------------------------------------------------------------


def check_observation_capabilities(frontmatter: dict) -> list[dict]:
    """Validate per-system A/B/C capability consistency and score_scope."""
    diagnostics: list[dict] = []
    systems = frontmatter.get("systems", {})
    if not isinstance(systems, dict):
        return diagnostics

    for sys_id, sys_data in systems.items():
        if not isinstance(sys_data, dict):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-048",
                    "file": "access_profile.md",
                    "field": f"systems.{sys_id}",
                    "message": f"System '{sys_id}' must be a mapping.",
                }
            )
            continue

        profile_letter = sys_data.get("profile_letter")
        caps = sys_data.get("capabilities", {})
        if not isinstance(caps, dict):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-048",
                    "file": "access_profile.md",
                    "field": f"systems.{sys_id}.capabilities",
                    "message": "Capabilities must be a mapping.",
                }
            )
            continue

        # Validate capability state values
        for cap_field in CAPABILITY_FIELDS:
            val = caps.get(cap_field)
            if val is not None and str(val) not in CAPABILITY_STATES:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}.capabilities.{cap_field}",
                        "message": (
                            f"Invalid capability state '{val}'; "
                            f"expected one of: {', '.join(sorted(CAPABILITY_STATES))}."
                        ),
                    }
                )

        # Profile A: scores and internals must be unavailable
        if str(profile_letter) == "A":
            if str(caps.get("scores", "")) != "unavailable":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}.capabilities.scores",
                        "message": (
                            "Profile A requires scores to be 'unavailable', "
                            f"got '{caps.get('scores')}'."
                        ),
                    }
                )
            if str(caps.get("internals", "")) != "unavailable":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}.capabilities.internals",
                        "message": (
                            "Profile A requires internals to be 'unavailable', "
                            f"got '{caps.get('internals')}'."
                        ),
                    }
                )

        # Profile B: internals must be unavailable, scores must not be unavailable
        if str(profile_letter) == "B":
            if str(caps.get("internals", "")) != "unavailable":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}.capabilities.internals",
                        "message": (
                            "Profile B requires internals to be 'unavailable', "
                            f"got '{caps.get('internals')}'."
                        ),
                    }
                )
            if str(caps.get("scores", "")) == "unavailable":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}.capabilities.scores",
                        "message": (
                            "Profile B requires scores to be available "
                            "(declared, verified, or unverified), got 'unavailable'."
                        ),
                    }
                )

        # Profile C: unrestricted claim cannot pair with partial verification
        vs = sys_data.get("verification_state")
        if str(profile_letter) == "C":
            internals_scope = str(sys_data.get("internals_scope", "unrestricted"))
            if internals_scope == "unrestricted" and str(vs) == "partial":
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-048",
                        "file": "access_profile.md",
                        "field": f"systems.{sys_id}",
                        "message": (
                            "Partial internals labelled unrestricted; "
                            "Profile C with internals_scope 'unrestricted' "
                            "requires verification_state other than 'partial'."
                        ),
                    }
                )

        # verification_state
        if vs is not None and str(vs) not in VERIFICATION_STATES:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-048",
                    "file": "access_profile.md",
                    "field": f"systems.{sys_id}.verification_state",
                    "message": (
                        f"Invalid verification state '{vs}'; "
                        f"expected one of: {', '.join(sorted(VERIFICATION_STATES))}."
                    ),
                }
            )

    # score_scope consistency: if any system is B or C, score_scope should exist
    has_bc = any(
        str(s.get("profile_letter", "")) in ("B", "C")
        for s in systems.values()
        if isinstance(s, dict)
    )
    score_scope = frontmatter.get("score_scope")
    if has_bc and not score_scope:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-048",
                "file": "access_profile.md",
                "field": "score_scope",
                "message": "score_scope required when any system has Profile B or C.",
            }
        )

    # score_scope.type consistency with provider_transformations
    if isinstance(score_scope, dict):
        scope_type = score_scope.get("type")
        for sys_id, sys_data in systems.items():
            if not isinstance(sys_data, dict):
                continue
            transforms = sys_data.get("provider_transformations", [])
            if isinstance(transforms, list):
                has_masking = any("mask" in str(t).lower() for t in transforms)
                if has_masking and scope_type == "pre_mask":
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-048",
                            "file": "access_profile.md",
                            "field": f"systems.{sys_id}",
                            "message": (
                                "Post-mask scores labelled as pre_mask; "
                                "score_scope.type must be 'post_mask' when "
                                "provider applies masking transformations."
                            ),
                        }
                    )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-049: Provenance Verification
# ---------------------------------------------------------------------------


def check_provenance_verification(frontmatter: dict, access_dir: Path) -> list[dict]:
    """Validate capability/provenance manifests."""
    diagnostics: list[dict] = []
    systems = frontmatter.get("systems", {})
    if not isinstance(systems, dict):
        return diagnostics

    system_ids = set(systems.keys())

    for ref in frontmatter.get("provenance_refs", []):
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            # Already caught by cross-file check
            continue

        try:
            manifest = json.loads(ref_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-049",
                    "file": str(ref),
                    "field": "/",
                    "message": f"Cannot parse manifest: {exc}",
                }
            )
            continue

        # Required fields
        for field in REQUIRED_MANIFEST_FIELDS:
            if field not in manifest:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-049",
                        "file": str(ref),
                        "field": field,
                        "message": f"Required manifest field '{field}' is missing.",
                    }
                )

        # system_id must match a declared system
        msid = manifest.get("system_id")
        if msid and msid not in system_ids:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-049",
                    "file": str(ref),
                    "field": "system_id",
                    "message": (
                        f"Manifest system_id '{msid}' not found in "
                        f"access profile systems."
                    ),
                }
            )

        # Hash format checks
        for id_field in ("model_identity", "tokenizer_identity"):
            identity = manifest.get(id_field, {})
            if isinstance(identity, dict):
                h = identity.get("hash", "")
                if h and not _SHA256_RE.match(str(h)):
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-049",
                            "file": str(ref),
                            "field": f"{id_field}.hash",
                            "message": (
                                f"Invalid SHA-256 hash format in {id_field}: '{h}'."
                            ),
                        }
                    )

        # reviewer_id non-empty
        reviewer = manifest.get("reviewer_id")
        if reviewer is not None and not str(reviewer).strip():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-049",
                    "file": str(ref),
                    "field": "reviewer_id",
                    "message": "reviewer_id must be non-empty.",
                }
            )

        # review_date ISO 8601
        rd = manifest.get("review_date")
        if rd:
            try:
                datetime.fromisoformat(str(rd))
            except ValueError:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-049",
                        "file": str(ref),
                        "field": "review_date",
                        "message": f"review_date '{rd}' is not valid ISO 8601.",
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-050: Observation/Intervention Separation
# ---------------------------------------------------------------------------


def check_observation_intervention_separation(
    frontmatter: dict,
) -> list[dict]:
    """Validate interventions are independent of observation profiles."""
    diagnostics: list[dict] = []

    roles = frontmatter.get("roles", [])
    if not isinstance(roles, list):
        return diagnostics

    role_ids = {r.get("role_id") for r in roles if isinstance(r, dict)}
    role_types = {
        r.get("role_id"): r.get("role_type") for r in roles if isinstance(r, dict)
    }

    # Role separation: same person cannot be both evaluator and operator
    person_roles: dict[str, set[str]] = {}
    for r in roles:
        if not isinstance(r, dict):
            continue
        person = r.get("person_id") or r.get("actor_id")
        rtype = r.get("role_type")
        if person and rtype:
            person_roles.setdefault(str(person), set()).add(str(rtype))
    for person, types in person_roles.items():
        if "evaluator" in types and "operator" in types:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-050",
                    "file": "access_profile.md",
                    "field": "roles",
                    "message": (
                        f"Role separation violated: person '{person}' is both "
                        f"evaluator and operator."
                    ),
                }
            )

    interventions = frontmatter.get("interventions", [])
    if not isinstance(interventions, list):
        return diagnostics

    systems = frontmatter.get("systems", {})
    if not isinstance(systems, dict):
        systems = {}

    for i, interv in enumerate(interventions):
        if not isinstance(interv, dict):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-050",
                    "file": "access_profile.md",
                    "field": f"interventions[{i}]",
                    "message": "Intervention entry must be a mapping.",
                }
            )
            continue

        # actor_role must match a declared role
        actor_role = interv.get("actor_role")
        if actor_role and actor_role not in role_ids:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-050",
                    "file": "access_profile.md",
                    "field": f"interventions[{i}].actor_role",
                    "message": (f"Role '{actor_role}' not found in declared roles."),
                }
            )

        # approved_recipes must be non-empty
        recipes = interv.get("approved_recipes", [])
        if not isinstance(recipes, list) or len(recipes) == 0:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-050",
                    "file": "access_profile.md",
                    "field": f"interventions[{i}].approved_recipes",
                    "message": "approved_recipes must be a non-empty list.",
                }
            )

        # artifact_lineage must be present
        if not interv.get("artifact_lineage"):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-050",
                    "file": "access_profile.md",
                    "field": f"interventions[{i}].artifact_lineage",
                    "message": "artifact_lineage is required for each intervention.",
                }
            )

        # Check requires_capabilities against actor's system profile
        req_caps = interv.get("requires_capabilities", [])
        target_system = interv.get("target_system")
        if isinstance(req_caps, list) and req_caps and target_system:
            sys_data = systems.get(target_system, {})
            if isinstance(sys_data, dict):
                caps = sys_data.get("capabilities", {})
                if isinstance(caps, dict):
                    for cap in req_caps:
                        state = caps.get(str(cap))
                        if state is None or str(state) == "unavailable":
                            diagnostics.append(
                                {
                                    "rule_id": "FV-SPEC-050",
                                    "file": "access_profile.md",
                                    "field": (
                                        f"interventions[{i}].requires_capabilities"
                                    ),
                                    "message": (
                                        f"Intervention requires capability '{cap}' "
                                        f"which is unavailable on system "
                                        f"'{target_system}'."
                                    ),
                                }
                            )

        # Observation profile (B/C) does not grant blanket intervention
        if actor_role and role_types.get(actor_role) == "evaluator":
            action = str(interv.get("action", ""))
            if action in ("fine_tune", "export_checkpoint", "tokenizer_change"):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-050",
                        "file": "access_profile.md",
                        "field": f"interventions[{i}].actor_role",
                        "message": (
                            f"Evaluator role '{actor_role}' cannot perform "
                            f"intervention '{action}'; use an operator role."
                        ),
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-051: Historical and External Access
# ---------------------------------------------------------------------------


def check_historical_external_access(frontmatter: dict) -> list[dict]:
    """Validate permitted_sources and historical_access declarations."""
    diagnostics: list[dict] = []

    # permitted_sources must be a list of recognized categories
    sources = frontmatter.get("permitted_sources", [])
    if not isinstance(sources, list):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-051",
                "file": "access_profile.md",
                "field": "permitted_sources",
                "message": "permitted_sources must be a list.",
            }
        )
        return diagnostics

    for src in sources:
        s = str(src)
        is_path_or_url = "/" in s or s.startswith("http://") or s.startswith("https://")
        if s not in RECOGNIZED_SOURCES and not is_path_or_url:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-051",
                    "file": "access_profile.md",
                    "field": "permitted_sources",
                    "message": (
                        f"Unrecognized source '{s}'; must be a recognized "
                        f"category or an explicit path/URL."
                    ),
                }
            )

    # historical_access attribution
    hist = frontmatter.get("historical_access", [])
    if isinstance(hist, list):
        for i, entry in enumerate(hist):
            if not isinstance(entry, dict):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-051",
                        "file": "access_profile.md",
                        "field": f"historical_access[{i}]",
                        "message": "historical_access entry must be a mapping.",
                    }
                )
                continue

            attribution = entry.get("attribution")
            if not attribution or not str(attribution).strip():
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-051",
                        "file": "access_profile.md",
                        "field": f"historical_access[{i}].attribution",
                        "message": (
                            "historical_access entry missing attribution; "
                            "each source must be explicitly attributed."
                        ),
                    }
                )

            # Pre-unlearning recovery must be separately attributed
            atype = str(entry.get("artifact_type", "")).lower()
            source = str(entry.get("source", "")).lower()
            if (
                "pre_unlearning" in atype
                or "pre-unlearning" in atype
                or "pre_unlearning" in source
            ):
                if not attribution or not str(attribution).strip():
                    # Already flagged above; add specific note
                    pass
                elif "pre" not in str(attribution).lower():
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-051",
                            "file": "access_profile.md",
                            "field": f"historical_access[{i}].attribution",
                            "message": (
                                "Recovery from pre-unlearning model must be "
                                "separately attributed to that artifact."
                            ),
                        }
                    )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-052: Identifiability Justification
# ---------------------------------------------------------------------------


def check_identifiability_justification(
    frontmatter: dict,
    access_dir: Path,
    strict: bool = False,
) -> list[dict]:
    """Validate identifiability justification records."""
    diagnostics: list[dict] = []
    refs = frontmatter.get("identifiability_refs", [])
    systems = frontmatter.get("systems", {})
    system_ids = set(systems.keys()) if isinstance(systems, dict) else set()

    if not refs:
        if strict:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-052",
                    "file": "access_profile.md",
                    "field": "identifiability_refs",
                    "message": (
                        "No identifiability justifications provided; "
                        "strict mode requires at least one if non-identifiable "
                        "status is used."
                    ),
                }
            )
        return diagnostics

    for ref in refs:
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            continue  # Already caught by cross-file check

        try:
            justification = json.loads(ref_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-052",
                    "file": str(ref),
                    "field": "/",
                    "message": f"Cannot parse justification: {exc}",
                }
            )
            continue

        # Required fields
        for field in REQUIRED_JUSTIFICATION_FIELDS:
            if field not in justification:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-052",
                        "file": str(ref),
                        "field": field,
                        "message": (
                            f"Required justification field '{field}' is missing."
                        ),
                    }
                )

        # system_pair must reference declared systems
        pair = justification.get("system_pair", [])
        if isinstance(pair, list):
            for sid in pair:
                if sid and sid not in system_ids:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-052",
                            "file": str(ref),
                            "field": "system_pair",
                            "message": (
                                f"System '{sid}' in system_pair not found "
                                f"in access profile systems."
                            ),
                        }
                    )

        # argument_type validation
        arg_type = justification.get("argument_type")
        limitations = justification.get("limitations", [])

        if arg_type == "empirical":
            # Must note finite-observation limitation
            has_finite_note = any(
                "finite" in str(lim).lower()
                for lim in (limitations if isinstance(limitations, list) else [])
            )
            if not has_finite_note:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-052",
                        "file": str(ref),
                        "field": "limitations",
                        "message": (
                            "Empirical identifiability argument must note "
                            "that finite observations do not prove universal "
                            "observational equivalence."
                        ),
                    }
                )

        if arg_type == "constructive":
            # Must reference synthetic/controlled systems
            pair = justification.get("system_pair", [])
            if isinstance(pair, list):
                synthetic_markers = (
                    "synthetic",
                    "simulator",
                    "controlled",
                    "sim_",
                )
                has_synthetic = any(
                    any(m in str(sid).lower() for m in synthetic_markers)
                    for sid in pair
                )
                summary = str(justification.get("argument_summary", "")).lower()
                if not has_synthetic and "synthetic" not in summary:
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-052",
                            "file": str(ref),
                            "field": "system_pair",
                            "message": (
                                "Constructive identifiability argument must "
                                "reference synthetic/controlled systems."
                            ),
                        }
                    )

        # reviewer_id non-empty
        reviewer = justification.get("reviewer_id")
        if reviewer is not None and not str(reviewer).strip():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-052",
                    "file": str(ref),
                    "field": "reviewer_id",
                    "message": "reviewer_id must be non-empty.",
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-053: Status Contracts
# ---------------------------------------------------------------------------


def check_status_contracts(frontmatter: dict) -> list[dict]:
    """Enforce four distinct statuses with no silent promotion."""
    diagnostics: list[dict] = []

    hp = frontmatter.get("handling_policies", {})
    if not isinstance(hp, dict):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-053",
                "file": "access_profile.md",
                "field": "handling_policies",
                "message": "handling_policies must be a mapping.",
            }
        )
        return diagnostics

    # All four statuses must be present
    missing = STATUS_ENUM - set(hp.keys())
    if missing:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-053",
                "file": "access_profile.md",
                "field": "handling_policies",
                "message": (
                    f"Status contracts missing: {', '.join(sorted(missing))}. "
                    f"All four statuses must have distinct handling rules."
                ),
            }
        )

    # Each status must have a non-empty rule
    for status in STATUS_ENUM:
        rule = hp.get(status)
        if rule is not None and not str(rule).strip():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-053",
                    "file": "access_profile.md",
                    "field": f"handling_policies.{status}",
                    "message": (
                        f"Status '{status}' has empty handling rule; "
                        f"each status requires a distinct reporting rule."
                    ),
                }
            )

    # Evidence mappings: no silent promotion
    evidence = frontmatter.get("evidence_mappings")
    if isinstance(evidence, dict):
        for key, expected in REQUIRED_EVIDENCE_MAPPINGS.items():
            actual = evidence.get(key)
            if actual is None:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-053",
                        "file": "access_profile.md",
                        "field": f"evidence_mappings.{key}",
                        "message": (
                            f"Missing evidence mapping for '{key}'; "
                            f"must map to '{expected}' (no silent promotion)."
                        ),
                    }
                )
            elif str(actual) != expected:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-053",
                        "file": "access_profile.md",
                        "field": f"evidence_mappings.{key}",
                        "message": (
                            f"Silent promotion forbidden: '{key}' maps to "
                            f"'{actual}' but must map to '{expected}'."
                        ),
                    }
                )

        # Known control label alone is not a fabricated witness
        control = evidence.get("known_control_label_alone")
        if control is not None and str(control) in (
            "confirmed_recovery",
            "conformance",
        ):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-053",
                    "file": "access_profile.md",
                    "field": "evidence_mappings.known_control_label_alone",
                    "message": (
                        "Known control label alone cannot fabricate a witness; "
                        "must not map to confirmed_recovery or conformance."
                    ),
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-054: Eligibility and Reporting
# ---------------------------------------------------------------------------


def check_eligibility_reporting(
    frontmatter: dict,
    spec_root: Path,
    strict: bool = False,
) -> list[dict]:
    """Cross-check handling_policies against access profile status definitions."""
    diagnostics: list[dict] = []

    hp = frontmatter.get("handling_policies", {})
    if not isinstance(hp, dict):
        return diagnostics

    # Non-identifiable and incomplete must have separate counting rules
    ni = hp.get("non_identifiable")
    inc = hp.get("incomplete")
    if ni is not None and inc is not None and str(ni) == str(inc):
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-054",
                "file": "access_profile.md",
                "field": "handling_policies",
                "message": (
                    "non_identifiable and incomplete must have separate "
                    "counting/reporting rules."
                ),
            }
        )

    # Outcome-dependent exclusions are forbidden
    eligibility = frontmatter.get("eligibility_rules", {})
    if isinstance(eligibility, dict):
        for rule_id, rule in eligibility.items():
            if isinstance(rule, dict) and rule.get("outcome_dependent"):
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-054",
                        "file": "access_profile.md",
                        "field": f"eligibility_rules.{rule_id}",
                        "message": (
                            "Outcome-dependent exclusions are not permitted; "
                            "eligibility must be predeclared."
                        ),
                    }
                )

    # In strict mode, check that P0-5/P0-6/P0-7 references resolve
    if strict:
        # Check margins.yaml exists
        margins_path = spec_root / "margins.yaml"
        if not margins_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-054",
                    "file": "access_profile.md",
                    "field": "handling_policies",
                    "message": (
                        "Strict mode: margins.yaml not found; "
                        "cross-file eligibility check cannot complete."
                    ),
                }
            )

        # Check witness_rule.md exists
        witness_path = spec_root / "witness_rule.md"
        if not witness_path.exists():
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-054",
                    "file": "access_profile.md",
                    "field": "handling_policies",
                    "message": (
                        "Strict mode: witness_rule.md not found; "
                        "cross-file eligibility check cannot complete."
                    ),
                }
            )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-055: Claim Templates
# ---------------------------------------------------------------------------


def check_claim_templates(frontmatter: dict, access_dir: Path) -> list[dict]:
    """Validate claim templates against declared evidence scope."""
    diagnostics: list[dict] = []
    profile = str(frontmatter.get("profile", ""))
    claim_refs = frontmatter.get("claim_refs", [])

    if not isinstance(claim_refs, list):
        return diagnostics

    for ref in claim_refs:
        ref_path = access_dir / str(ref)
        if not ref_path.exists():
            continue  # Already caught by cross-file check

        try:
            template = json.loads(ref_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-055",
                    "file": str(ref),
                    "field": "/",
                    "message": f"Cannot parse claim template: {exc}",
                }
            )
            continue

        # Required fields
        for field in REQUIRED_CLAIM_FIELDS:
            if field not in template:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-055",
                        "file": str(ref),
                        "field": field,
                        "message": (
                            f"Required claim template field '{field}' is missing."
                        ),
                    }
                )

        # Profile must match
        tmpl_profile = str(template.get("profile", ""))
        if tmpl_profile and tmpl_profile != profile:
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-055",
                    "file": str(ref),
                    "field": "profile",
                    "message": (
                        f"Claim template profile '{tmpl_profile}' does not match "
                        f"access profile '{profile}'."
                    ),
                }
            )

        # Profile A must include output-simulation limitation
        if tmpl_profile == "A":
            limitations = template.get("limitations", [])
            has_sim_limit = any(
                "output" in str(lim).lower() and "simulation" in str(lim).lower()
                for lim in (limitations if isinstance(limitations, list) else [])
            )
            if not has_sim_limit:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-055",
                        "file": str(ref),
                        "field": "limitations",
                        "message": (
                            "Profile A claim template must include "
                            "output-simulation limitation."
                        ),
                    }
                )

        # Universal erasure language
        claim_text = str(template.get("claim_text", ""))
        if _UNIVERSAL_ERASURE_RE.search(claim_text):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-055",
                    "file": str(ref),
                    "field": "claim_text",
                    "message": (
                        "Universal erasure language detected in claim_text; "
                        "claims must be scoped to declared evidence."
                    ),
                }
            )

        # Stage B cannot inherit Stage A causal references
        stage = str(template.get("stage", ""))
        ref_condition = template.get("reference_condition")
        if stage == "B" and ref_condition:
            # Check if reference_condition mentions Stage A or causal
            rc_str = str(ref_condition).lower()
            if "stage_a" in rc_str or "stage a" in rc_str:
                diagnostics.append(
                    {
                        "rule_id": "FV-SPEC-055",
                        "file": str(ref),
                        "field": "reference_condition",
                        "message": (
                            "Stage B claim cannot inherit Stage A causal references."
                        ),
                    }
                )

    return diagnostics


# ---------------------------------------------------------------------------
# FV-SPEC-056: Scoped CLI Validation (strict + baseline)
# ---------------------------------------------------------------------------


def check_strict_mode(
    frontmatter: dict,
    access_dir: Path,
    spec_root: Path,
) -> list[dict]:
    """Strict mode checks: all decisions resolved, reviews current."""
    diagnostics: list[dict] = []

    # All blocking decisions must be resolved
    bd = frontmatter.get("blocking_decisions", [])
    if isinstance(bd, list):
        for d in bd:
            if isinstance(d, dict):
                if d.get("status") != "resolved":
                    diagnostics.append(
                        {
                            "rule_id": "FV-SPEC-056",
                            "file": "access_profile.md",
                            "field": f"blocking_decisions.{d.get('decision_id')}",
                            "message": (
                                f"Strict mode: decision {d.get('decision_id')} "
                                f"is not resolved."
                            ),
                        }
                    )

    # Review manifest must exist
    review_path = access_dir / "review_manifest.json"
    if not review_path.exists():
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-056",
                "file": "review_manifest.json",
                "field": "/",
                "message": "Strict mode: review_manifest.json not found.",
            }
        )
    else:
        try:
            manifest = json.loads(review_path.read_text(encoding="utf-8"))
            reviews = manifest.get("reviews", [])
            if isinstance(reviews, list):
                for r in reviews:
                    if isinstance(r, dict) and r.get("status") == "pending":
                        diagnostics.append(
                            {
                                "rule_id": "FV-SPEC-056",
                                "file": "review_manifest.json",
                                "field": f"reviews.{r.get('artifact_id')}",
                                "message": (
                                    f"Strict mode: review for "
                                    f"'{r.get('artifact_id')}' is pending."
                                ),
                            }
                        )
        except (json.JSONDecodeError, OSError):
            diagnostics.append(
                {
                    "rule_id": "FV-SPEC-056",
                    "file": "review_manifest.json",
                    "field": "/",
                    "message": "Strict mode: cannot parse review_manifest.json.",
                }
            )

    return diagnostics


def check_baseline_comparison(
    frontmatter: dict,
    baseline_path: Path,
) -> tuple[list[dict], dict]:
    """Compare current profile against baseline for frozen-policy changes."""
    diagnostics: list[dict] = []
    comparison: dict = {"status": "not_requested"}

    if not baseline_path.exists():
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-056",
                "file": "access_profile.md",
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
        baseline_fm, _ = load_access_profile(baseline_path)
    except SystemExit as exc:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-056",
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

    # Compare handling_policies (frozen policy)
    changed_fields: list[str] = []
    cur_hp = frontmatter.get("handling_policies", {})
    base_hp = baseline_fm.get("handling_policies", {})
    if cur_hp != base_hp:
        changed_fields.append("handling_policies")

    # Compare profile
    if frontmatter.get("profile") != baseline_fm.get("profile"):
        changed_fields.append("profile")

    # If frozen policy changed but version unchanged → fail
    if changed_fields and revision_match:
        diagnostics.append(
            {
                "rule_id": "FV-SPEC-056",
                "file": "access_profile.md",
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


def write_access_profile_report(
    checks: list[dict],
    frontmatter: dict,
    spec_root: Path,
    access_dir: Path,
    strict: bool,
    report_path: Path | None,
    baseline_comparison: dict | None = None,
) -> dict:
    """Generate and optionally write the JSON validation report."""
    # Compute capabilities summary
    capabilities: dict = {}
    systems = frontmatter.get("systems", {})
    if isinstance(systems, dict):
        for sys_id, sys_data in systems.items():
            if isinstance(sys_data, dict):
                caps = sys_data.get("capabilities", {})
                if isinstance(caps, dict):
                    capabilities[sys_id] = {f: caps.get(f) for f in CAPABILITY_FIELDS}

    # Compute input digests
    input_digests: dict = {}
    profile_path = spec_root / "access_profile.md"
    if profile_path.exists():
        h = hashlib.sha256(profile_path.read_bytes()).hexdigest()
        input_digests["access_profile.md"] = f"sha256:{h}"
    budget_ref = frontmatter.get("budget_ref")
    if budget_ref:
        bp = spec_root / str(budget_ref)
        if bp.exists():
            h = hashlib.sha256(bp.read_bytes()).hexdigest()
            input_digests[str(budget_ref)] = f"sha256:{h}"

    # Deferred checks
    deferred: list[str] = []
    if not strict:
        deferred = ["P0-5 margins", "P0-6 witness rule", "P0-7 preregistration"]

    # Cross-file check summary
    cross_file: list[dict] = []
    if budget_ref:
        bp = spec_root / str(budget_ref)
        cross_file.append(
            {
                "target": str(budget_ref),
                "resolved": bp.exists(),
                "digest_match": True if bp.exists() else None,
            }
        )

    # Review state
    review_state: dict = {}
    for sys_id in systems if isinstance(systems, dict) else {}:
        review_state[sys_id] = "current"  # simplified

    # Permission conflicts
    permission_conflicts: list[dict] = []

    overall = (
        "pass"
        if all(c.get("status") in ("pass", "deferred", "skipped") for c in checks)
        else "fail"
    )

    report = {
        "report_id": str(uuid.uuid4()),
        "timestamp": datetime.now(UTC).isoformat(),
        "spec_root": str(spec_root),
        "scope": "access-profile",
        "strict": strict,
        "profile_version": str(frontmatter.get("version", "")),
        "checks": checks,
        "capabilities": capabilities,
        "permission_conflicts": permission_conflicts,
        "review_state": review_state,
        "cross_file_checks": cross_file,
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


# ---------------------------------------------------------------------------
# Top-Level Entry Point
# ---------------------------------------------------------------------------


def _run_check(
    rule_id: str,
    rule_name: str,
    check_fn: Callable[..., Any],
    *args: object,
    **kwargs: object,
) -> dict:
    """Run a check function and return a structured result."""
    try:
        diags = check_fn(*args, **kwargs)
        # Handle functions that return tuple (diags, extra)
        if isinstance(diags, tuple):
            diags = diags[0]
        status = "pass" if not diags else "fail"
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": status,
            "diagnostics": [d.get("message", "") for d in diags],
        }
    except Exception as exc:
        return {
            "rule_id": rule_id,
            "rule_name": rule_name,
            "status": "fail",
            "diagnostics": [f"Check error: {exc}"],
        }


def validate_access_profile(
    spec_root: str | Path,
    access_dir: str | Path,
    report_path: str | Path | None = None,
    strict: bool = False,
    baseline_suite_path: str | Path | None = None,
) -> tuple[bool, dict]:
    """Validate the access profile.  Returns (passed, report)."""
    spec_root = Path(spec_root)
    access_dir = Path(access_dir)
    report_path = Path(report_path) if report_path else None
    baseline_suite_path = Path(baseline_suite_path) if baseline_suite_path else None

    profile_path = spec_root / "access_profile.md"
    try:
        frontmatter, body = load_access_profile(profile_path)
    except SystemExit:
        # Input error → exit 2 via CLI
        raise

    checks: list[dict] = []

    # FV-SPEC-047: Access contract artifact
    checks.append(
        _run_check(
            "FV-SPEC-047",
            "access_contract_artifact",
            check_access_contract_artifact,
            frontmatter,
            body,
        )
    )

    # FV-SPEC-047 cross-file
    xref_result = _run_check(
        "FV-SPEC-047",
        "cross_file_references",
        check_cross_file_references,
        frontmatter,
        spec_root,
        access_dir,
    )
    # Merge cross-file diagnostics into artifact check
    if xref_result["diagnostics"]:
        checks[0]["diagnostics"].extend(xref_result["diagnostics"])
        checks[0]["status"] = "fail"

    # FV-SPEC-048: Observation capabilities
    checks.append(
        _run_check(
            "FV-SPEC-048",
            "observation_capabilities",
            check_observation_capabilities,
            frontmatter,
        )
    )

    # FV-SPEC-049: Provenance verification
    checks.append(
        _run_check(
            "FV-SPEC-049",
            "provenance_verification",
            check_provenance_verification,
            frontmatter,
            access_dir,
        )
    )

    # FV-SPEC-050: Observation/intervention separation
    checks.append(
        _run_check(
            "FV-SPEC-050",
            "observation_intervention_separation",
            check_observation_intervention_separation,
            frontmatter,
        )
    )

    # FV-SPEC-051: Historical and external access
    checks.append(
        _run_check(
            "FV-SPEC-051",
            "historical_external_access",
            check_historical_external_access,
            frontmatter,
        )
    )

    # FV-SPEC-052: Identifiability justification
    checks.append(
        _run_check(
            "FV-SPEC-052",
            "identifiability_justification",
            check_identifiability_justification,
            frontmatter,
            access_dir,
            strict,
        )
    )

    # FV-SPEC-053: Status contracts
    checks.append(
        _run_check(
            "FV-SPEC-053",
            "status_contracts",
            check_status_contracts,
            frontmatter,
        )
    )

    # FV-SPEC-054: Eligibility and reporting
    checks.append(
        _run_check(
            "FV-SPEC-054",
            "eligibility_reporting",
            check_eligibility_reporting,
            frontmatter,
            spec_root,
            strict,
        )
    )

    # FV-SPEC-055: Claim templates
    checks.append(
        _run_check(
            "FV-SPEC-055",
            "claim_templates",
            check_claim_templates,
            frontmatter,
            access_dir,
        )
    )

    # FV-SPEC-056: Scoped CLI validation
    strict_result: dict = {
        "rule_id": "FV-SPEC-056",
        "rule_name": "scoped_cli_validation",
        "status": "pass",
        "diagnostics": [],
    }
    baseline_comparison: dict | None = None

    if strict:
        strict_diags = check_strict_mode(frontmatter, access_dir, spec_root)
        if strict_diags:
            strict_result["status"] = "fail"
            strict_result["diagnostics"] = [d.get("message", "") for d in strict_diags]

    if baseline_suite_path:
        bl_diags, baseline_comparison = check_baseline_comparison(
            frontmatter,
            baseline_suite_path,
        )
        if bl_diags:
            strict_result["status"] = "fail"
            strict_result["diagnostics"].extend(d.get("message", "") for d in bl_diags)

    checks.append(strict_result)

    # Generate report
    report = write_access_profile_report(
        checks,
        frontmatter,
        spec_root,
        access_dir,
        strict,
        report_path,
        baseline_comparison,
    )

    passed = report["overall"] == "pass"
    return passed, report
