"""Load the five spec artifacts and refuse unresolved fields."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.decisions.resolver import resolve_or_none
from src.eval.errors import FactVerifyEvalError
from src.eval.types import Case, Probe, normalize_split

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

_ARTIFACTS = (
    "attacks.yaml",
    "access_profile.md",
    "witness_rule.md",
    "closure_templates.yaml",
    "margins.yaml",
)


@dataclass
class ArmSpec:
    arm_id: str
    total: int
    channels: dict[str, int]


@dataclass
class SpecBundle:
    revision: str
    common_cap: int | None
    arms: dict[str, ArmSpec]
    accounting: dict[str, Any]
    channels: dict[str, dict[str, Any]]
    decisions: dict[str, str]
    capabilities: dict[str, str]
    access_label: str
    templates: dict[str, dict[str, Any]]
    groups: dict[str, dict[str, Any]]
    raw_maximum_role: str
    route_enabled: dict[str, bool]
    no_witness_is_not_accept: bool
    margins_status: str | None = None
    root: Path = field(default_factory=Path)


def _read(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FactVerifyEvalError(str(path))
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end == -1:
            raise FactVerifyEvalError(str(path))
        loaded = yaml.safe_load(text[3:end])
    else:
        loaded = yaml.safe_load(text)
    if not isinstance(loaded, dict):
        raise FactVerifyEvalError(str(path))
    return loaded


def _decisions(items: object) -> dict[str, str]:
    found: dict[str, str] = {}
    if not isinstance(items, list):
        return found
    for item in items:
        if isinstance(item, dict) and "decision_id" in item:
            found[str(item["decision_id"])] = str(item.get("status", ""))
    return found


def load_spec(spec_root: Path) -> SpecBundle:
    """Load the five artifacts. Null margins do not abort the load."""
    root = spec_root.resolve()
    for name in _ARTIFACTS:
        if not (root / name).is_file():
            raise FactVerifyEvalError(str(root / name))
    attacks = _read(root / "attacks.yaml")
    access = _read(root / "access_profile.md")
    witness = _read(root / "witness_rule.md")
    closure = _read(root / "closure_templates.yaml")
    margins = _read(root / "margins.yaml")

    arms: dict[str, ArmSpec] = {}
    for arm in attacks.get("arms", []):
        channels = {
            str(item["channel_id"]): int(item["trials"])
            for item in arm.get("channel_allocations", [])
        }
        arms[str(arm["arm_id"])] = ArmSpec(
            arm_id=str(arm["arm_id"]),
            total=int(arm["total"]),
            channels=channels,
        )
    channel_map = {
        str(item["id"]): item for item in attacks.get("channels", []) if "id" in item
    }
    systems = access.get("systems", {})
    candidate = {}
    if isinstance(systems, dict):
        candidate = systems.get("candidate", {})
    capabilities = {}
    if isinstance(candidate, dict):
        capabilities = candidate.get("capabilities", {})
    templates = {
        str(item["id"]): item for item in closure.get("templates", []) if "id" in item
    }
    groups = {
        str(item["group_id"]): item
        for item in closure.get("groups", [])
        if "group_id" in item
    }
    routes = witness.get("confirmation_routes", {})
    route_enabled = {
        str(key): bool(value.get("enabled"))
        for key, value in routes.items()
        if isinstance(value, dict)
    }
    aggregation = witness.get("aggregation_policy", {})
    case_decision = witness.get("case_decision", {})
    decisions = _decisions(attacks.get("blocking_decisions"))
    decisions.update(_decisions(access.get("blocking_decisions")))
    decisions.update(_decisions(witness.get("blocking_decisions")))
    return SpecBundle(
        revision=str(attacks.get("revision", "")),
        common_cap=(
            None if attacks.get("common_cap") is None else int(attacks["common_cap"])
        ),
        arms=arms,
        accounting=dict(attacks.get("accounting", {})),
        channels=channel_map,
        decisions=decisions,
        capabilities={str(k): str(v) for k, v in capabilities.items()},
        access_label=str(access.get("profile", "")),
        templates=templates,
        groups=groups,
        raw_maximum_role=str(aggregation.get("raw_maximum_role", "")),
        route_enabled=route_enabled,
        no_witness_is_not_accept=bool(
            case_decision.get("no_witness_is_not_accept", False)
        ),
        margins_status=(
            None if margins.get("status") is None else str(margins.get("status"))
        ),
        root=root,
    )


def require_closed(bundle: SpecBundle, decision_ids: list[str]) -> None:
    """Refuse when any requested decision is missing or not closed."""
    open_ids = [item for item in decision_ids if bundle.decisions.get(item) != "closed"]
    if open_ids:
        parts: list[str] = []
        for did in open_ids:
            entry = resolve_or_none(did, _CATALOG)
            if entry is not None and entry.key is not None:
                parts.append(f"{entry.key} (legacy {did})")
            else:
                parts.append(did)
        raise FactVerifyEvalError("open decisions: " + ", ".join(parts))


def require_resolved_policies(bundle: SpecBundle) -> None:
    """Refuse an unresolved cache, retry, failure, or reallocation field."""
    accounting = bundle.accounting
    for key in ("cache_policy", "retry_policy", "failure_policy", "discard_policy"):
        policy = accounting.get(key)
        if not isinstance(policy, dict):
            raise FactVerifyEvalError(key)
        for field_name, value in policy.items():
            if value is None or value == "DECISION_REQUIRED":
                raise FactVerifyEvalError(f"{key}.{field_name}")
    realloc = accounting.get("unused_confirmation_reallocation")
    if realloc == "DECISION_REQUIRED" or (
        realloc is None and bundle.decisions.get("D-26") == "closed"
    ):
        raise FactVerifyEvalError("unused_confirmation_reallocation")


def case_from_mapping(data: dict[str, Any]) -> Case:
    """Build a case. A missing identifiability field refuses."""
    if "identifiability" not in data or data["identifiability"] in (None, ""):
        raise FactVerifyEvalError("identifiability")
    if not data.get("answers"):
        raise FactVerifyEvalError("answers")
    probes: list[Probe] = []
    for item in data.get("probes", []):
        probes.append(
            Probe(
                probe_id=str(item["probe_id"]),
                probe_class=str(item["probe_class"]),
                prompt=str(item["prompt"]),
                template_id=item.get("template_id"),
                group_id=item.get("group_id"),
                family_id=item.get("family_id"),
            )
        )
    if not probes:
        raise FactVerifyEvalError("probes")
    return Case(
        case_id=str(data["case_id"]),
        checkpoint_ledger_id=str(data["checkpoint_ledger_id"]),
        fact_id=str(data["fact_id"]),
        split=normalize_split(str(data["split"])),
        spec_revision=str(data["spec_revision"]),
        access_label=str(data["access_label"]),
        identifiability=str(data["identifiability"]),
        answers=[str(item) for item in data["answers"]],
        probes=probes,
        seed=int(data.get("seed", 0)),
    )


def case_from_path(path: Path) -> Case:
    import json

    if not path.is_file():
        raise FactVerifyEvalError(str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise FactVerifyEvalError(str(path))
    return case_from_mapping(loaded)
