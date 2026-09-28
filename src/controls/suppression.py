"""Suppression mechanisms. Severity is not read."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.controls.checks import BehaviorPort, CheckOutcome, check_retention
from src.controls.config import ControlConfig
from src.controls.decisions import DecisionRow
from src.controls.errors import ControlError
from src.eval.gateway import ModelPort
from src.eval.types import Probe


@dataclass(frozen=True)
class FactSurfaces:
    """Object label and object aliases from a fact contract."""

    fact_id: str
    surfaces: tuple[str, ...]


def load_fact(path: Path) -> FactSurfaces:
    """Read the fact id and the object surface forms. A missing form refuses later."""
    if not path.is_file():
        raise ControlError(str(path))
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError("fact_contract")
    fact_id = loaded.get("fact_id")
    if not isinstance(fact_id, str) or fact_id == "":
        raise ControlError("fact_id")
    surfaces: list[str] = []
    triple = loaded.get("triple")
    if isinstance(triple, dict):
        obj = triple.get("object")
        if isinstance(obj, dict) and isinstance(obj.get("label"), str):
            surfaces.append(str(obj["label"]))
    aliases = loaded.get("aliases")
    if isinstance(aliases, dict) and isinstance(aliases.get("object"), list):
        for item in aliases["object"]:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                surfaces.append(str(item["text"]))
    unique = tuple(dict.fromkeys(surfaces))
    return FactSurfaces(fact_id=fact_id, surfaces=unique)


class SuppressionPort:
    """Enabled wrapper around a parent model port. The parent is not public."""

    def __init__(
        self,
        family: str,
        parent: ModelPort,
        surfaces: tuple[str, ...],
        refusal_text: str | None,
        replacement_text: str | None,
        groups: tuple[str, ...],
        apply_vector: bool,
    ) -> None:
        self.family = family
        self._parent = parent
        self._surfaces = tuple(sorted(surfaces, key=len, reverse=True))
        self._refusal_text = refusal_text
        self._replacement_text = replacement_text
        self._groups = groups
        self._apply_vector = apply_vector
        self.vector_applied = False

    def complete(self, probe: Probe) -> str:
        """Return enabled suppression text. At most one parent completion."""
        if self.family == "refusal":
            return _required(self._refusal_text, "refusal_text")
        if self.family == "template_specific":
            if probe.group_id in self._groups:
                return _required(self._refusal_text, "refusal_text")
            return self._parent.complete(probe)
        if self.family == "answer_replacement":
            self._parent.complete(probe)
            return _required(self._replacement_text, "replacement_text")
        if self.family == "output_filter":
            return _strip(self._parent.complete(probe), self._surfaces)
        if self.family == "reversible_steering":
            text = self._parent.complete(probe)
            if self._apply_vector:
                self.vector_applied = True
            return text
        if self.family == "logit_masking":
            return self._parent.complete(probe)
        raise ControlError(self.family)

    def score_candidate(self, probe: Probe) -> dict[str, float]:
        """Drop answer-surface keys when this family masks logits."""
        scores = dict(self._parent.score_candidate(probe))
        if self.family == "logit_masking":
            for surface in self._surfaces:
                scores.pop(surface, None)
        return scores


def prepare_suppression(
    config: ControlConfig,
    fact: FactSurfaces,
    decision: DecisionRow,
    behavior: BehaviorPort | None,
    parent: ModelPort | None,
) -> tuple[CheckOutcome, SuppressionPort | None, bytes]:
    """Run the retention check. The returned port is enabled when the check can run."""
    if behavior is None or parent is None:
        raise ControlError("behavior" if behavior is None else "parent_model")
    _require_surfaces(config.family, fact)
    vector_bytes = b""
    if config.vector_path is not None:
        if not config.vector_path.is_file():
            raise ControlError("vector_path")
        vector_bytes = config.vector_path.read_bytes()
    outcome = check_retention(behavior, config.fact_id, decision)
    port = SuppressionPort(
        family=config.family,
        parent=parent,
        surfaces=fact.surfaces,
        refusal_text=config.refusal_text,
        replacement_text=config.replacement_text,
        groups=tuple(config.suppressed_group_ids or ()),
        apply_vector=config.vector_path is not None,
    )
    return outcome, port, vector_bytes


def _require_surfaces(family: str, fact: FactSurfaces) -> None:
    if family in {"output_filter", "logit_masking"} and not fact.surfaces:
        raise ControlError("fact_contract")


def _required(value: str | None, key: str) -> str:
    if value is None or value == "":
        raise ControlError(key)
    return value


def _strip(text: str, surfaces: tuple[str, ...]) -> str:
    stripped = text
    for surface in surfaces:
        stripped = stripped.replace(surface, "")
    return stripped
