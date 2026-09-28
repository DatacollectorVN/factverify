"""Equivalence probes come from the case split. Inference stays separate."""

from __future__ import annotations

from src.eval.errors import FactVerifyEvalError
from src.eval.probes import resolve_probe
from src.eval.spec_load import SpecBundle
from src.eval.types import Case, Probe


def select_equivalence(
    bundle: SpecBundle,
    case: Case,
    probes: list[Probe],
) -> tuple[list[Probe], list[Probe]]:
    """Return primary equivalence probes and the separate inference output."""
    primary: list[Probe] = []
    inference: list[Probe] = []
    for probe in probes:
        kind = resolve_probe(bundle, case, probe)
        if kind == "inference":
            inference.append(probe)
        elif kind in {"equivalence", "locality"}:
            primary.append(probe)
    return primary, inference


def require_primary(bundle: SpecBundle, case: Case, probe: Probe) -> None:
    """Refuse an inference template drawn for the primary equivalence score."""
    if resolve_probe(bundle, case, probe) == "inference":
        template_id = probe.template_id or probe.probe_id
        raise FactVerifyEvalError(
            f"{template_id} refused for primary score; inference_output={[template_id]}"
        )
