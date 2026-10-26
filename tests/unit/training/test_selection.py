"""Tests for BestCheckpointSelector (FV-ARCH-017)."""

from __future__ import annotations

import torch
import torch.nn as nn

from src.services.training.selection import BestCheckpointSelector


def _make_model() -> nn.Module:
    """A tiny model with trainable parameters."""
    return nn.Linear(2, 2)


# ── First epoch is best ───────────────────────────────────────────────


def test_first_epoch_is_best() -> None:
    """The first update always records the best score."""
    selector = BestCheckpointSelector(mode="min", patience=3)
    model = _make_model()

    exhausted = selector.update(epoch=0, score=1.0, model=model)

    assert not exhausted
    assert selector.best_epoch == 0
    assert selector.best_score == 1.0


# ── Improvement resets wait ───────────────────────────────────────────


def test_improvement_resets_wait() -> None:
    """A better score resets the wait counter."""
    selector = BestCheckpointSelector(mode="min", patience=3)
    model = _make_model()

    selector.update(0, 1.0, model)  # best
    selector.update(1, 1.5, model)  # worse, wait=1
    selector.update(2, 1.8, model)  # worse, wait=2
    exhausted = selector.update(3, 0.5, model)  # better! wait=0

    assert not exhausted
    assert selector.best_epoch == 3
    assert selector.best_score == 0.5


# ── Patience exhaustion ──────────────────────────────────────────────


def test_patience_exhaustion() -> None:
    """After patience non-improving epochs, returns True."""
    selector = BestCheckpointSelector(mode="min", patience=2)
    model = _make_model()

    selector.update(0, 1.0, model)  # best
    selector.update(1, 1.5, model)  # worse, wait=1
    exhausted = selector.update(2, 1.8, model)  # worse, wait=2 >= patience

    assert exhausted
    assert selector.best_epoch == 0


# ── Restore loads best weights ────────────────────────────────────────


def test_restore_loads_best() -> None:
    """After restore, model weights match the best epoch's state."""
    model = _make_model()
    selector = BestCheckpointSelector(mode="min", patience=5)

    # Record the model at epoch 0 as best
    initial_weight = model.weight.data.clone()
    selector.update(0, 1.0, model)

    # Mutate the model weights (simulating further training)
    with torch.no_grad():
        model.weight.fill_(999.0)
        model.bias.fill_(999.0)

    # Confirm weights changed
    assert not torch.allclose(model.weight.data, initial_weight)

    # Restore
    selector.restore(model)

    # Weights should match the snapshot from epoch 0
    assert torch.allclose(model.weight.data, initial_weight)


# ── None patience never stops ────────────────────────────────────────


def test_none_patience_never_stops() -> None:
    """With patience=None, update never returns True."""
    selector = BestCheckpointSelector(mode="min", patience=None)
    model = _make_model()

    for i in range(100):
        exhausted = selector.update(i, float(i), model)
        assert not exhausted

    # With patience=None, no best epoch is tracked
    assert selector.best_epoch is None
    assert selector.best_score is None


# ── Max mode ─────────────────────────────────────────────────────────


def test_max_mode() -> None:
    """In 'max' mode, higher scores are improvements."""
    selector = BestCheckpointSelector(mode="max", patience=2)
    model = _make_model()

    selector.update(0, 0.5, model)  # best
    assert selector.best_score == 0.5

    selector.update(1, 0.8, model)  # better
    assert selector.best_score == 0.8
    assert selector.best_epoch == 1

    selector.update(2, 0.7, model)  # worse, wait=1
    exhausted = selector.update(3, 0.6, model)  # worse, wait=2

    assert exhausted
    assert selector.best_epoch == 1


# ── Restore is no-op without snapshot ────────────────────────────────


def test_restore_noop_without_snapshot() -> None:
    """Restore does nothing when patience is None (no snapshot taken)."""
    model = _make_model()
    selector = BestCheckpointSelector(mode="min", patience=None)

    with torch.no_grad():
        model.weight.fill_(42.0)

    selector.restore(model)

    # Weight should be unchanged
    assert (model.weight.data == 42.0).all()
