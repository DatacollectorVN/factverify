"""Epoch-level training metrics."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EpochMetrics:
    """Aggregated metrics for one completed epoch."""

    epoch: int
    train_loss: float
    eval_scores: dict[str, float] = field(default_factory=dict)  # metric_name -> value
