"""Control labels. An output filter under Profile A is non-identifiable."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.controls.errors import ControlError
from src.controls.registry import LAYERS
from src.controls.spec_load import ControlSpec

_REQUIRED = (
    "family",
    "implementation_id",
    "severity",
    "mechanism_layer",
    "oracle_label",
    "split",
    "fact_id",
    "parent_ledger_id",
    "seed",
    "spec_revision",
    "config_hash",
    "artifact_digest",
    "status",
)


@dataclass
class ControlLabel:
    """An accepted negative label."""

    family: str
    implementation_id: str
    severity: Any
    mechanism_layer: str
    oracle_label: str
    split: str
    fact_id: str
    parent_ledger_id: str
    seed: int
    spec_revision: str
    config_hash: str
    artifact_digest: str
    status: str
    expected_identifiability: str | None = None

    def as_dict(self) -> dict[str, Any]:
        """Field order fixed by the label contract."""
        payload: dict[str, Any] = {
            "family": self.family,
            "implementation_id": self.implementation_id,
            "severity": self.severity,
            "mechanism_layer": self.mechanism_layer,
            "oracle_label": self.oracle_label,
            "split": self.split,
            "fact_id": self.fact_id,
            "parent_ledger_id": self.parent_ledger_id,
            "seed": self.seed,
            "spec_revision": self.spec_revision,
            "config_hash": self.config_hash,
            "artifact_digest": self.artifact_digest,
            "status": self.status,
        }
        if self.expected_identifiability is not None:
            payload["expected_identifiability"] = self.expected_identifiability
        return payload


def expected_identifiability(family: str, spec: ControlSpec) -> str | None:
    """Profile A output filters are structurally indistinguishable."""
    if family != "output_filter":
        return None
    if spec.profile != "A":
        raise ControlError("access_profile.md")
    scores_visible = spec.scores == "verified" or spec.internals == "verified"
    if spec.text != "verified" or scores_visible:
        raise ControlError("access_profile.md")
    return "structurally_indistinguishable"


def write_label(path: Path, label: ControlLabel) -> None:
    """Write `control.json`. The caller has already decided the build is accepted."""
    if label.mechanism_layer not in LAYERS:
        raise ControlError("mechanism_layer")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(label.as_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def load_control(label_path: Path) -> ControlLabel:
    """Load an accepted negative label. Anything else raises."""
    if not label_path.is_file():
        raise ControlError(str(label_path))
    loaded = json.loads(label_path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ControlError(str(label_path))
    for key in _REQUIRED:
        if key not in loaded:
            raise ControlError(key)
    mechanism = loaded["mechanism_layer"]
    if mechanism not in LAYERS:
        raise ControlError("mechanism_layer")
    if loaded["oracle_label"] != "negative":
        raise ControlError("oracle_label")
    if loaded["status"] != "accepted":
        raise ControlError("status")
    seed = loaded["seed"]
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ControlError("seed")
    flag = loaded.get("expected_identifiability")
    if flag is not None and not isinstance(flag, str):
        raise ControlError("expected_identifiability")
    return ControlLabel(
        family=str(loaded["family"]),
        implementation_id=str(loaded["implementation_id"]),
        severity=loaded["severity"],
        mechanism_layer=str(mechanism),
        oracle_label="negative",
        split=str(loaded["split"]),
        fact_id=str(loaded["fact_id"]),
        parent_ledger_id=str(loaded["parent_ledger_id"]),
        seed=seed,
        spec_revision=str(loaded["spec_revision"]),
        config_hash=str(loaded["config_hash"]),
        artifact_digest=str(loaded["artifact_digest"]),
        status="accepted",
        expected_identifiability=flag if isinstance(flag, str) else None,
    )
