"""Read the access profile and locality margins. Do not write the spec root."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from src.controls.errors import ControlError


@dataclass(frozen=True)
class LocalityMargin:
    """One locality bucket. A null value stays null."""

    value: float | None
    orientation: str


@dataclass(frozen=True)
class ControlSpec:
    """The two spec artifacts this package reads."""

    profile: str
    text: str
    scores: str
    internals: str
    candidate_scoring: str | None
    margins: dict[str, LocalityMargin]
    root: Path


def load_control_spec(spec_root: Path) -> ControlSpec:
    """Load `access_profile.md` and `margins.yaml`. Null margins do not abort."""
    root = spec_root.resolve()
    profile_path = root / "access_profile.md"
    margins_path = root / "margins.yaml"
    profile = _frontmatter(profile_path)
    margins_doc = _yaml_mapping(margins_path)
    letter = profile.get("profile")
    if not isinstance(letter, str):
        raise ControlError("access_profile.md")
    capabilities = _candidate_capabilities(profile)
    locality = margins_doc.get("locality_margins")
    if not isinstance(locality, dict):
        raise ControlError("locality_margins")
    margins: dict[str, LocalityMargin] = {}
    for bucket, raw in locality.items():
        if not isinstance(bucket, str) or not isinstance(raw, dict):
            raise ControlError("locality_margins")
        orientation = raw.get("orientation")
        margin = raw.get("margin")
        if not isinstance(orientation, str) or not isinstance(margin, dict):
            raise ControlError(str(bucket))
        value = margin.get("value")
        if value is not None and isinstance(value, bool):
            raise ControlError(str(bucket))
        if value is not None and not isinstance(value, (int, float)):
            raise ControlError(str(bucket))
        margins[bucket] = LocalityMargin(
            value=None if value is None else float(value),
            orientation=orientation,
        )
    raw_cs = capabilities.get("candidate_scoring")
    return ControlSpec(
        profile=letter,
        text=str(capabilities["text"]),
        scores=str(capabilities["scores"]),
        internals=str(capabilities["internals"]),
        candidate_scoring=str(raw_cs) if raw_cs is not None else None,
        margins=margins,
        root=root,
    )


def _frontmatter(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ControlError(str(path))
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ControlError(str(path))
    end = text.find("\n---", 3)
    if end == -1:
        raise ControlError(str(path))
    loaded = yaml.safe_load(text[3:end])
    if not isinstance(loaded, dict):
        raise ControlError(str(path))
    return {str(key): value for key, value in loaded.items()}


def _yaml_mapping(path: Path) -> dict[str, object]:
    if not path.is_file():
        raise ControlError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError(str(path))
    return {str(key): value for key, value in loaded.items()}


def _candidate_capabilities(profile: dict[str, object]) -> dict[str, object]:
    systems = profile.get("systems")
    if not isinstance(systems, dict):
        raise ControlError("access_profile.md")
    candidate = systems.get("candidate")
    if not isinstance(candidate, dict):
        raise ControlError("access_profile.md")
    capabilities = candidate.get("capabilities")
    if not isinstance(capabilities, dict):
        raise ControlError("access_profile.md")
    return {str(key): value for key, value in capabilities.items()}
