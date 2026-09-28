"""Classify probes from the closure file. The caller label does not win."""

from __future__ import annotations

from src.eval.errors import FactVerifyEvalError
from src.eval.spec_load import SpecBundle
from src.eval.types import Case, Probe


def resolve_probe(bundle: SpecBundle, case: Case, probe: Probe) -> str:
    """Return native, equivalence, locality, or inference. Mismatched splits raise."""
    template_id = probe.template_id
    if template_id and template_id in bundle.templates:
        template = bundle.templates[template_id]
        group_id = str(template.get("group_id", probe.group_id or ""))
        group = bundle.groups.get(group_id)
        if group is None:
            raise FactVerifyEvalError(group_id)
        kind = str(template.get("class", ""))
        premises = template.get("extra_premises") or []
        if kind == "I" or premises:
            return "inference"
        if kind == "X":
            raise FactVerifyEvalError(f"{template_id} excluded")
        group_split = str(group.get("split", ""))
        if group_split != case.split:
            raise FactVerifyEvalError(f"{group_id} split {group_split} != {case.split}")
        if kind == "R":
            return "locality"
        return "equivalence"
    if probe.probe_class == "native":
        return "native"
    raise FactVerifyEvalError(probe.probe_id)
