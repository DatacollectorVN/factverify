"""The nine control families. One registered implementation each."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.controls.decisions import load_decisions, row_or_open
from src.controls.errors import ControlError
from src.controls.ledger import ControlLedgerPort

LAYERS = (
    "prompt/serving",
    "output post-processing",
    "logits",
    "activations",
    "weights",
)


@dataclass(frozen=True)
class FamilySpec:
    """One registered implementation. Untouched has no layer until D-61 closes."""

    family: str
    implementation_id: str
    mechanism_layer: str | None
    buildable: bool


@dataclass(frozen=True)
class CatalogEntry:
    """One row of `list_catalog`."""

    family: str
    implementation_ids: tuple[str, ...]
    mechanism_layer: str | None
    buildable: bool


_FAMILIES: tuple[FamilySpec, ...] = (
    FamilySpec("refusal", "refusal.serving", "prompt/serving", True),
    FamilySpec(
        "output_filter",
        "output_filter.postprocess",
        "output post-processing",
        True,
    ),
    FamilySpec(
        "answer_replacement",
        "answer_replacement.postprocess",
        "output post-processing",
        True,
    ),
    FamilySpec("logit_masking", "logit_masking.suppress_tokens", "logits", True),
    FamilySpec(
        "template_specific",
        "template_specific.group_suppress",
        "prompt/serving",
        True,
    ),
    FamilySpec(
        "reversible_steering",
        "reversible_steering.vector",
        "activations",
        True,
    ),
    FamilySpec("targeted_damage", "targeted_damage.local", "weights", True),
    FamilySpec("broad_destruction", "broad_destruction.global", "weights", True),
    FamilySpec("untouched", "untouched.parent", None, False),
)
_BY_FAMILY = {item.family: item for item in _FAMILIES}


def list_catalog() -> list[CatalogEntry]:
    """Return the nine families. This does not certify the D-55 count."""
    return [
        CatalogEntry(
            family=item.family,
            implementation_ids=(item.implementation_id,),
            mechanism_layer=item.mechanism_layer,
            buildable=item.buildable,
        )
        for item in _FAMILIES
    ]


def require_family(family: str) -> FamilySpec:
    """Return the registered family or raise naming the token."""
    found = _BY_FAMILY.get(family)
    if found is None:
        raise ControlError(family)
    return found


def certify_coverage(decisions: Path) -> None:
    """Pass only when D-55 is closed and its count is at most the registered count."""
    row = row_or_open(load_decisions(decisions), "D-55")
    if row.status != "closed" or row.min_count is None or row.min_count > 1:
        raise ControlError("D-55")


def check_split(ledger: ControlLedgerPort, implementation_id: str, split: str) -> None:
    """Refuse an implementation id that already sits on the other held-out split."""
    existing = ledger.splits_for_implementation(implementation_id)
    pair = {"calibration", "final_test"}
    if split in pair and (pair - {split}) & existing:
        other = sorted(pair - {split})[0]
        raise ControlError(f"{implementation_id} {split} {other}")
