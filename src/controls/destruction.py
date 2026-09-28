"""Destruction controls delegate the weight update to a trainer port."""

from __future__ import annotations

from typing import Protocol

from src.controls.checks import (
    BehaviorPort,
    CheckOutcome,
    check_locality,
    margins_resolved,
)
from src.controls.config import ControlConfig
from src.controls.errors import ControlError
from src.controls.spec_load import ControlSpec


class TrainerPort(Protocol):
    """Runs a named harness method. This package does not implement the optimizer."""

    def train(self, config: ControlConfig) -> bytes:
        """Return the artifact bytes that enter the digest."""


def prepare_destruction(
    config: ControlConfig,
    spec: ControlSpec,
    behavior: BehaviorPort | None,
    trainer: TrainerPort | None,
) -> tuple[CheckOutcome, bytes]:
    """Train only after the locality margin is resolved, then measure the drop.

    The margin guard does not call the behavior port, so the system under
    test need not exist before training begins.
    """
    if behavior is None:
        raise ControlError("behavior")
    if trainer is None:
        raise ControlError("trainer")
    resolved, error_name = margins_resolved(spec, config.family)
    if not resolved:
        return CheckOutcome("unchecked", None, {}, "", error_name), b""
    artifact = trainer.train(config)
    outcome = check_locality(behavior, config.family, spec)
    return outcome, artifact
