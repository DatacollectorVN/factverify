"""Helpers for reading .factverify/spec artefacts.

Provides spec-coupled readers so scripts stay decoupled from YAML structure.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_template_groups(spec_root: Path) -> dict[str, list[str]]:
    """Return ``{group_id: [template_text_patterns]}`` from templates.yaml.

    Reads the ``group`` field on each template entry under
    ``sets.equivalence.templates`` and collects their ``text`` patterns.
    Used by the template-disjointness check (FR-003 / D-42): a training
    record is disallowed if its text matches any pattern from any group.

    Raises ``FileNotFoundError`` if the YAML is absent and
    ``KeyError`` if the expected structure is missing.
    """
    closure_path = spec_root / "templates.yaml"
    with open(closure_path) as fh:
        data: dict[str, Any] = yaml.safe_load(fh)

    groups: dict[str, list[str]] = {}
    try:
        templates: list[dict[str, Any]] = data["sets"]["equivalence"]["templates"]
    except KeyError as exc:
        raise KeyError(
            f"closure_templates.yaml is missing expected key: {exc}"
        ) from exc

    for tmpl in templates:
        group_id: str = tmpl.get("group", "")
        text: str = tmpl.get("text", "")
        if not group_id or not text:
            continue
        groups.setdefault(group_id, []).append(text)

    return groups
