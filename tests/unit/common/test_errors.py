"""Tests for src.services.common.errors: hierarchy smoke test."""

from __future__ import annotations

from src.services.common.errors import (
    CheckpointError,
    ConfigurationError,
    DataValidationError,
    EvaluationError,
    FactVerifyError,
    ModelLoadError,
    PlanningError,
    TrackingError,
    TrainingError,
)


class TestErrorHierarchy:
    def test_all_inherit_from_base(self) -> None:
        errors = [
            ConfigurationError,
            PlanningError,
            DataValidationError,
            ModelLoadError,
            CheckpointError,
            TrainingError,
            EvaluationError,
            TrackingError,
        ]
        for cls in errors:
            assert issubclass(cls, FactVerifyError), f"{cls.__name__} not a FactVerifyError"
            assert issubclass(cls, Exception)

    def test_can_catch_by_base(self) -> None:
        try:
            raise ConfigurationError("test")
        except FactVerifyError as exc:
            assert str(exc) == "test"

    def test_distinct_types(self) -> None:
        errors = [
            ConfigurationError,
            PlanningError,
            DataValidationError,
            ModelLoadError,
            CheckpointError,
            TrainingError,
            EvaluationError,
            TrackingError,
        ]
        # All are distinct classes
        assert len(set(errors)) == len(errors)
