"""Best-epoch tracking for learner loss and unlearning NLL."""

from __future__ import annotations

import torch
from torch import nn

from src.train.methods.common import BestEpochTracker, selection_summary


def _model(value: float) -> nn.Linear:
    model = nn.Linear(1, 1, bias=False)
    with torch.no_grad():
        model.weight.fill_(value)
    return model


def _fill(model: nn.Linear, value: float) -> None:
    with torch.no_grad():
        model.weight.fill_(value)


def test_min_mode_keeps_lowest_loss_and_stops() -> None:
    model = _model(1.0)
    tracker = BestEpochTracker("min", patience=2)
    assert tracker.update(1, 3.0, model) is False
    _fill(model, 2.0)
    assert tracker.update(2, 1.0, model) is False
    _fill(model, 3.0)
    assert tracker.update(3, 2.0, model) is False
    _fill(model, 4.0)
    assert tracker.update(4, 2.5, model) is True
    tracker.restore(model)
    tracker.remember(model)
    assert tracker.best_epoch == 2
    assert tracker.best_score == 1.0
    assert tracker.stopped_epoch == 4
    assert tracker.wait == 2
    assert torch.allclose(model.weight, torch.tensor([[2.0]]))
    assert selection_summary(model) == {
        "best_epoch": 2,
        "best_score": 1.0,
        "stopped_epoch": 4,
    }


def test_max_mode_keeps_higher_unlearning_score() -> None:
    model = _model(1.0)
    tracker = BestEpochTracker("max", patience=1)
    assert tracker.update(1, 1.0, model) is False
    _fill(model, 2.0)
    assert tracker.update(2, 4.0, model) is False
    _fill(model, 3.0)
    assert tracker.update(3, 2.0, model) is True
    tracker.restore(model)
    assert tracker.best_epoch == 2
    assert tracker.best_score == 4.0
    assert tracker.stopped_epoch == 3
    assert torch.allclose(model.weight, torch.tensor([[2.0]]))


def test_equal_score_does_not_reset_patience() -> None:
    model = _model(1.0)
    tracker = BestEpochTracker("min", patience=1)
    assert tracker.update(1, 1.0, model) is False
    _fill(model, 9.0)
    assert tracker.update(2, 1.0, model) is True
    tracker.restore(model)
    assert tracker.best_epoch == 1
    assert torch.allclose(model.weight, torch.tensor([[1.0]]))


def test_missing_patience_keeps_the_latest_weights() -> None:
    model = _model(1.0)
    tracker = BestEpochTracker("min", patience=None)
    assert tracker.update(1, 5.0, model) is False
    _fill(model, 7.0)
    tracker.restore(model)
    tracker.remember(model)
    assert tracker.best_epoch is None
    assert torch.allclose(model.weight, torch.tensor([[7.0]]))
    assert selection_summary(model) is None
    assert tracker.status() == ""
