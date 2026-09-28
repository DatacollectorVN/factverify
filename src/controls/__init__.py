"""Fake-unlearning controls and behaviour matching."""

from src.controls.base import load_control
from src.controls.build import BuildResult, build_control, compare_builds
from src.controls.errors import ControlError
from src.controls.match import (
    compare_matches,
    load_match_record,
    match_control,
    pilot_inputs,
    reject_dropped,
)
from src.controls.registry import certify_coverage, list_catalog

__all__ = [
    "BuildResult",
    "ControlError",
    "build_control",
    "certify_coverage",
    "compare_builds",
    "compare_matches",
    "list_catalog",
    "load_control",
    "load_match_record",
    "match_control",
    "pilot_inputs",
    "reject_dropped",
]
