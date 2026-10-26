"""FactVerify error hierarchy (FV-ARCH-028).

Each error type maps to a distinct failure domain. Operator-facing messages
must include the failing run/attempt identity and a corrective action.
"""

from __future__ import annotations


class FactVerifyError(Exception):
    """Base for all FactVerify application errors."""


class ConfigurationError(FactVerifyError):
    """Invalid, incomplete, or incompatible configuration."""


class PlanningError(FactVerifyError):
    """Run expansion or planning failure (overlapping facts, missing seeds)."""


class DataValidationError(FactVerifyError):
    """Corpus, manifest, or data-integrity failure."""


class ModelLoadError(FactVerifyError):
    """Pretrained model or adapter loading failure."""


class CheckpointError(FactVerifyError):
    """Checkpoint publication, verification, or restore failure."""


class TrainingError(FactVerifyError):
    """Training engine or method failure."""


class EvaluationError(FactVerifyError):
    """Evaluation engine or scoring failure."""


class TrackingError(FactVerifyError):
    """Run tracking, status transition, or database failure."""
