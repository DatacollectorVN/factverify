"""Neighbour guard tripping before any valid epoch must not yield a
"selected checkpoint" (regression for block0 GA lr1e-5, which saved a model
with neighbour retention 0.0 as selected and status=succeeded).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from src.train.methods import unlearn_common  # noqa: E402
from src.train.methods.common import (  # noqa: E402
    BestEpochTracker,
    remember_stop,
    selection_summary,
    stop_summary,
)


class _TinyModel(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.w = torch.nn.Parameter(torch.zeros(2))


@pytest.fixture
def calls(monkeypatch):
    seen: list[int] = []

    def fake_selected(config, model, tok, fc, rc, baseline, selected_epoch, *, experiment_id=""):
        seen.append(selected_epoch)
        return {"selected_epoch": selected_epoch}

    monkeypatch.setattr(unlearn_common, "log_unlearn_selected_checkpoint", fake_selected)
    return seen


def _finalize(model, tracker, finished, reason):
    return unlearn_common.finalize_unlearn_selection(
        SimpleNamespace(), model, None, None, None, None, tracker, finished, reason,
    )


def test_guard_at_first_epoch_has_no_selected_checkpoint(calls):
    model = _TinyModel()
    tracker = BestEpochTracker(mode="max", patience=10)  # never updated: epoch 1 breached
    assert _finalize(model, tracker, 1, "neighbour_guard") is False
    assert calls == [], "no selected-checkpoint report may be written"
    assert stop_summary(model) == {
        "stop_reason": "neighbour_guard",
        "stopped_epoch": 1,
        "has_selected_checkpoint": False,
    }
    assert selection_summary(model) is None


def test_guard_after_valid_epoch_restores_best(calls):
    model = _TinyModel()
    tracker = BestEpochTracker(mode="max", patience=10)
    tracker.update(1, 0.5, model)            # epoch 1 valid, snapshot w=0
    with torch.no_grad():
        model.w.fill_(9.0)                   # epoch 2 breaches the guard
    assert _finalize(model, tracker, 2, "neighbour_guard") is True
    assert calls == [1]
    assert torch.equal(model.w, torch.zeros(2)), "best (epoch 1) weights restored"
    assert stop_summary(model)["has_selected_checkpoint"] is True


@pytest.mark.parametrize("reason", ["early_stop", "max_epochs"])
def test_non_guard_stops_always_select(calls, reason):
    model = _TinyModel()
    tracker = BestEpochTracker(mode="max", patience=None)  # no snapshots kept
    assert _finalize(model, tracker, 5, reason) is True
    assert calls == [5]


def test_unknown_stop_reason_rejected():
    with pytest.raises(ValueError):
        remember_stop(_TinyModel(), reason="oops", stopped_epoch=1, has_selected_checkpoint=True)


def test_guard_stopped_counts_as_completed(tmp_path):
    from src.ledger.train_store import ExperimentRecord, open_train_store

    store = open_train_store(tmp_path / "t.sqlite")
    for status, fact in [("succeeded", "a"), ("guard_stopped", "b"), ("failed", "c")]:
        eid = store.create_experiment(ExperimentRecord(
            job_name="j", role="forgetter", method="GA", seed=3, split="s",
            target_fact=fact, facts=[fact], config_hash="h",
        ))
        store.update_experiment(eid, status=status, best_epoch=None, best_score=None)
    assert store.completed_experiments("j") == {("a", 3), ("b", 3)}


def test_trainer_return_order_maps_to_cost_fields():
    """Trainers return (order, examples, optimizer_updates); run.py must unpack
    them in that order so ledger steps = optimizer updates."""
    import inspect

    from src.train import run

    src = inspect.getsource(run)
    assert "data_order, steps, examples = trainer(" not in src
    assert src.count("data_order, examples, steps = trainer(") == 3
