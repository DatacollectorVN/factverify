"""``stop_on_neighbour_breach: false``: keep training after a guard breach."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

torch = pytest.importorskip("torch")

from src.train.config import GroupedJobConfig, _validate_grouped  # noqa: E402
from src.train.methods import unlearn_common  # noqa: E402
from src.train.methods.common import BestEpochTracker, stop_summary  # noqa: E402
from src.train.methods.unlearn_common import drop_retention_report  # noqa: E402

_TEMPLATE = Path(__file__).resolve().parents[3] / "config/train/template_forgetter.yaml"
_METHODS = Path(__file__).resolve().parents[3] / "src/train/methods"


class _Tiny(torch.nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.w = torch.nn.Parameter(torch.zeros(1))

    def set(self, value: float) -> None:
        with torch.no_grad():
            self.w.fill_(value)


def _keep(
    tracker: BestEpochTracker, model: _Tiny, epoch: int, score: float, *, breached: bool
) -> bool:
    model.set(float(epoch))
    return tracker.record_epoch(
        epoch, score, model, breached=breached, stop_on_breach=False
    )


def test_default_stop_mode_never_tracks_a_breach() -> None:
    tracker, model = BestEpochTracker("max", 2), _Tiny()
    assert (
        tracker.record_epoch(1, 9.0, model, breached=True, stop_on_breach=True) is False
    )
    assert (tracker.best_epoch, tracker.fallback_epoch, tracker.wait) == (None, None, 0)
    assert tracker.promote_fallback() is False


def test_valid_epoch_always_beats_a_higher_scoring_breach() -> None:
    tracker, model = BestEpochTracker("max", 5), _Tiny()
    _keep(tracker, model, 1, 1.0, breached=False)
    _keep(tracker, model, 2, 99.0, breached=True)
    assert tracker.best_epoch == 1 and tracker.fallback_epoch is None
    assert tracker.promote_fallback() is False


def test_breaches_use_up_patience() -> None:
    tracker, model = BestEpochTracker("max", 2), _Tiny()
    assert _keep(tracker, model, 1, 1.0, breached=True) is False
    assert _keep(tracker, model, 2, 5.0, breached=True) is True
    assert tracker.stopped_epoch == 2


def test_early_stop_message_without_any_valid_epoch() -> None:
    tracker, model = BestEpochTracker("max", 1), _Tiny()
    _keep(tracker, model, 1, 1.0, breached=True)
    assert "no epoch above the neighbour guard" in tracker.early_stop_message(1)
    assert tracker.status() == ""


def test_early_stop_message_with_a_valid_epoch() -> None:
    tracker, model = BestEpochTracker("max", 1), _Tiny()
    _keep(tracker, model, 1, 2.5, breached=False)
    assert "best epoch 1, score=2.5000" in tracker.early_stop_message(3)


def test_rising_fallback_score_does_not_reset_patience() -> None:
    tracker, model = BestEpochTracker("max", 3), _Tiny()
    stops = [_keep(tracker, model, e, float(e), breached=True) for e in (1, 2, 3)]
    assert stops == [False, False, True]


def test_recovery_replaces_the_fallback_and_resets_patience() -> None:
    tracker, model = BestEpochTracker("max", 3), _Tiny()
    _keep(tracker, model, 1, 50.0, breached=True)
    _keep(tracker, model, 2, 60.0, breached=True)
    assert _keep(tracker, model, 3, 2.0, breached=False) is False
    assert (tracker.best_epoch, tracker.wait, tracker.fallback_epoch) == (3, 0, None)
    assert tracker.promote_fallback() is False
    tracker.restore(model)
    assert model.w.item() == 3.0


@pytest.mark.parametrize(
    "mode, scores, expected", [("max", (1.0, 7.0, 3.0), 2), ("min", (5.0, 1.0, 3.0), 2)]
)
def test_promotes_the_best_breaching_epoch(
    mode: Any, scores: Any, expected: int
) -> None:
    tracker, model = BestEpochTracker(mode, 9), _Tiny()
    for epoch, score in enumerate(scores, start=1):
        _keep(tracker, model, epoch, score, breached=True)
    assert tracker.promote_fallback() is True
    assert tracker.best_epoch == expected
    tracker.restore(model)
    assert model.w.item() == float(expected)


def test_fallback_survives_resume() -> None:
    tracker, model = BestEpochTracker("max", 9), _Tiny()
    _keep(tracker, model, 1, 4.0, breached=True)
    restored = BestEpochTracker.from_state_dict(tracker.state_dict())
    assert restored.promote_fallback() is True and restored.best_epoch == 1


def test_resume_state_from_before_this_option_still_loads() -> None:
    state = BestEpochTracker("max", 3).state_dict()
    for key in ("fallback_score", "fallback_epoch", "_fallback_state"):
        del state[key]
    assert BestEpochTracker.from_state_dict(state).fallback_epoch is None


def test_finalize_selects_and_flags_the_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[int] = []

    def fake(
        config: Any,
        model: Any,
        tok: Any,
        fc: Any,
        rc: Any,
        base: Any,
        epoch: int,
        *,
        experiment_id: str = "",
    ) -> dict[str, Any]:
        seen.append(epoch)
        return {"selected_checkpoint_epoch": epoch}

    monkeypatch.setattr(unlearn_common, "log_unlearn_selected_checkpoint", fake)
    tracker, model = BestEpochTracker("max", 2), _Tiny()
    _keep(tracker, model, 1, 8.0, breached=True)
    _keep(tracker, model, 2, 3.0, breached=True)
    ok = unlearn_common.finalize_unlearn_selection(
        SimpleNamespace(save_best_as="val_target_drop"),
        model,
        None,
        None,
        None,
        None,
        tracker,
        2,
        "early_stop",
    )
    assert ok is True and seen == [1]
    assert model.w.item() == 1.0
    assert stop_summary(model)["selected_below_guard"] is True
    assert drop_retention_report(model)["selected_below_guard"] is True


def test_finalize_does_not_flag_a_valid_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        unlearn_common,
        "log_unlearn_selected_checkpoint",
        lambda *a, **k: {"selected_checkpoint_epoch": 1},
    )
    tracker, model = BestEpochTracker("max", 2), _Tiny()
    _keep(tracker, model, 1, 1.0, breached=False)
    unlearn_common.finalize_unlearn_selection(
        SimpleNamespace(), model, None, None, None, None, tracker, 1, "max_epochs"
    )
    assert "selected_below_guard" not in stop_summary(model)
    assert "selected_below_guard" not in drop_retention_report(model)


@pytest.mark.parametrize("method", ["ga", "graddiff", "npo", "rmu"])
def test_every_trainer_uses_the_switch(method: str) -> None:
    source = (_METHODS / f"{method}.py").read_text(encoding="utf-8")
    assert 'getattr(config, "stop_on_neighbour_breach", True)' in source
    assert "tracker.record_epoch(" in source
    assert "if neighbour_breach and stop_on_breach:" in source


def _mapping() -> dict[str, Any]:
    import yaml

    mapping = yaml.safe_load(_TEMPLATE.read_text(encoding="utf-8"))
    mapping["job"]["name"] = "job"
    mapping["model"]["config"] = "m.yaml"
    mapping["output"]["dir"] = "o"
    mapping["data"]["forget_fact"] = "f"
    mapping["training"]["checkpoint"] = "c"
    return mapping


def test_config_defaults_to_stopping() -> None:
    mapping = _mapping()
    del mapping["training"]["stop_on_neighbour_breach"]
    _validate_grouped(mapping, "t")
    assert (
        GroupedJobConfig(raw=mapping, path=Path("t")).stop_on_neighbour_breach is True
    )


def test_config_accepts_false_with_patience() -> None:
    mapping = _mapping()
    mapping["training"]["stop_on_neighbour_breach"] = False
    _validate_grouped(mapping, "t")
    assert (
        GroupedJobConfig(raw=mapping, path=Path("t")).stop_on_neighbour_breach is False
    )


def test_config_false_requires_patience() -> None:
    from src.train.errors import FactVerifyHarnessError

    mapping = _mapping()
    mapping["training"]["stop_on_neighbour_breach"] = False
    mapping["training"]["patience"] = None
    with pytest.raises(FactVerifyHarnessError, match="requires training.patience"):
        _validate_grouped(mapping, "t")


def test_config_rejects_a_non_boolean() -> None:
    from src.train.errors import FactVerifyHarnessError

    mapping = _mapping()
    mapping["training"]["stop_on_neighbour_breach"] = "no"
    with pytest.raises(FactVerifyHarnessError, match="must be a boolean"):
        _validate_grouped(mapping, "t")
