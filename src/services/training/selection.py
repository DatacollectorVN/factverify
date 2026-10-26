"""Best-checkpoint selection with patience-based early stopping.

Ported from ``src/train/methods/common.py:BestEpochTracker``.

.. note::

    FV-ARCH-020 proposes a disk-backed checkpoint approach to avoid holding
    a full CPU clone in memory. That optimisation is deferred; the current
    implementation stores a CPU state-dict clone, matching the behaviour of
    the original ``BestEpochTracker``.
"""

from __future__ import annotations

from typing import Any, Literal

import torch

ScoreMode = Literal["min", "max"]


class BestCheckpointSelector:
    """Track the best epoch and optionally restore its weights.

    ``patience is None`` disables early stopping: updates are recorded but
    weights are never cloned and the selector never requests a stop.

    When patience is set, the first update becomes the initial best. A later
    epoch improves only on a *strictly* better score (lower for ``"min"``,
    higher for ``"max"``). Training should stop once ``patience``
    non-improving epochs have followed the best one.
    """

    def __init__(self, mode: ScoreMode, patience: int | None) -> None:
        if mode not in ("min", "max"):
            raise ValueError(f"unknown score mode {mode!r}")
        self._mode: ScoreMode = mode
        self._patience = patience
        self._best_score: float | None = None
        self._best_epoch: int | None = None
        self._wait: int = 0
        self._best_state: dict[str, torch.Tensor] | None = None

    # ── Public properties ──────────────────────────────────────────────

    @property
    def best_epoch(self) -> int | None:
        return self._best_epoch

    @property
    def best_score(self) -> float | None:
        return self._best_score

    # ── Core API ───────────────────────────────────────────────────────

    def update(self, epoch: int, score: float, model: Any) -> bool:
        """Record one finished epoch. Return ``True`` when patience is exhausted."""
        if self._patience is None:
            return False
        improved = self._best_score is None or (
            score < self._best_score
            if self._mode == "min"
            else score > self._best_score
        )
        if improved:
            self._best_score = float(score)
            self._best_epoch = epoch
            self._wait = 0
            self._best_state = {
                key: tensor.detach().cpu().clone()
                for key, tensor in model.state_dict().items()
            }
        else:
            self._wait += 1
        return self._wait >= self._patience

    def restore(self, model: Any) -> None:
        """Load the best weights back into ``model``. No-op without a snapshot."""
        if self._best_state is None:
            return
        model.load_state_dict(self._best_state)
