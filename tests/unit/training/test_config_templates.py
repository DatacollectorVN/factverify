"""The train templates must be valid configs once their REQUIRED fields are set."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

pytest.importorskip("torch")

from src.stats.afc import AFCSettings  # noqa: E402
from src.train.config import GroupedJobConfig, _validate_grouped  # noqa: E402

_TEMPLATES = Path(__file__).resolve().parents[3] / "config" / "train"


def _filled(name: str) -> dict[str, Any]:
    mapping = yaml.safe_load((_TEMPLATES / name).read_text(encoding="utf-8"))
    mapping["job"]["name"] = "job"
    mapping["model"]["config"] = "model.yaml"
    mapping["output"]["dir"] = "out"
    if mapping["job"]["role"] == "forgetter":
        mapping["data"]["forget_fact"] = "fact"
        mapping["training"]["checkpoint"] = "learner"
    else:
        mapping["data"]["facts"] = ["fact"]
    return mapping


def test_learner_template_is_valid() -> None:
    mapping = _filled("template_learner.yaml")
    _validate_grouped(mapping, "template")
    assert isinstance(mapping["training"]["learning_rate"], float)
    assert mapping["training"]["alias_aware"] is True


@pytest.mark.parametrize(
    "method, extra",
    [
        ("GA", {}),
        ("GradDiff", {"retain_coeff": 1.0}),
        ("NPO", {"beta": 0.1}),
        (
            "RMU",
            {
                "steering_coeff": 300.0,
                "steering_layer": 7,
                "retain_coeff": 100.0,
                "rmu_token_scope": "no_sinks",
            },
        ),
    ],
)
def test_forgetter_template_is_valid_for_every_method(
    method: str, extra: dict[str, Any]
) -> None:
    mapping = _filled("template_forgetter.yaml")
    mapping["job"]["method"] = method
    mapping["training"].update(extra)
    _validate_grouped(mapping, "template")
    assert isinstance(mapping["training"]["learning_rate"], float)


def test_forgetter_template_runs_afc_without_kappa() -> None:
    mapping = _filled("template_forgetter.yaml")
    settings = GroupedJobConfig(raw=mapping, path=Path("job.yaml")).afc_settings
    assert settings == AFCSettings(alpha=0.05, kappa=None)
