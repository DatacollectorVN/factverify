"""BestEpochTracker.min_delta: noise-level gains must not reset patience."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from src.train.methods.common import BestEpochTracker, tracker_min_delta  # noqa: E402


class _M(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.w = torch.nn.Parameter(torch.zeros(1))


def test_default_zero_keeps_strict_improvement():
    t = BestEpochTracker(mode="max", patience=2)
    m = _M()
    t.update(1, 0.0, m)
    t.update(2, 1e-9, m)               # strictly better → counts
    assert t.best_epoch == 2 and t.wait == 0


def test_noise_level_gains_do_not_reset_patience():
    t = BestEpochTracker(mode="max", patience=3, min_delta=0.01)
    m = _M()
    assert t.update(1, 0.0000, m) is False
    stops = [t.update(e, 0.0001 * e, m) for e in (2, 3, 4)]
    assert t.best_epoch == 1
    assert stops == [False, False, True]


def test_real_gain_resets_patience_min_mode():
    t = BestEpochTracker(mode="min", patience=2, min_delta=0.01)
    m = _M()
    t.update(1, 1.0, m)
    t.update(2, 0.995, m)              # within margin → no improvement
    assert t.wait == 1
    t.update(3, 0.9, m)                # real improvement
    assert t.best_epoch == 3 and t.wait == 0


def test_state_round_trip_and_legacy_state():
    t = BestEpochTracker(mode="max", patience=5, min_delta=0.02)
    assert BestEpochTracker.from_state_dict(t.state_dict()).min_delta == 0.02
    legacy = t.state_dict()
    legacy.pop("min_delta")
    assert BestEpochTracker.from_state_dict(legacy).min_delta == 0.0


def test_negative_rejected_and_config_reader():
    with pytest.raises(ValueError):
        BestEpochTracker(mode="max", patience=1, min_delta=-0.1)
    assert tracker_min_delta(SimpleNamespace(raw={"training": {}})) == 0.0
    assert tracker_min_delta(SimpleNamespace(raw={"training": {"min_delta": 0.01}})) == 0.01
