"""Evaluation coordinator (FV-ARCH-021).

Public interface for running evaluation jobs through src.main.
"""

from __future__ import annotations

from src.services.common.types import AppConfig, RunContext, RunResult


def evaluate(config: AppConfig, context: RunContext) -> RunResult:
    """Run an evaluation job.

    This is the task handler registered as "evaluate". The full implementation
    will: resolve checkpoints → validate identities → load probes → execute
    evaluation engine → record metrics → write results.

    Currently a placeholder that validates the config and returns success.
    """
    # TODO: Implement full evaluation pipeline in Phase 8 expansion
    return RunResult(status="not_implemented", artifacts=[])
