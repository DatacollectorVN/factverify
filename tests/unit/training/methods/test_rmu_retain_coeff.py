"""RMU retain_coeff in the live trainer (src/train/methods/rmu.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from src.train.methods.rmu import combine_rmu_loss, rmu_retain_coeff  # noqa: E402


def test_retain_coeff_defaults_to_one_when_absent():
    config = SimpleNamespace(raw={"training": {"steering_coeff": 10.0}})
    assert rmu_retain_coeff(config) == 1.0


def test_retain_coeff_read_from_training_section():
    config = SimpleNamespace(raw={"training": {"retain_coeff": 100.0}})
    assert rmu_retain_coeff(config) == 100.0


def test_default_coeff_reproduces_unweighted_loss():
    f, r = torch.tensor(3.0), torch.tensor(2.0)
    assert combine_rmu_loss(f, r, 1.0, 4).item() == pytest.approx((3.0 + 2.0) / 4)


def test_coeff_scales_only_retain_term():
    f = torch.tensor(3.0, requires_grad=True)
    r = torch.tensor(2.0, requires_grad=True)
    loss = combine_rmu_loss(f, r, 50.0, 2)
    loss.backward()
    assert loss.item() == pytest.approx((3.0 + 50.0 * 2.0) / 2)
    assert f.grad.item() == pytest.approx(0.5)
    assert r.grad.item() == pytest.approx(25.0)


def _rmu_mapping(**training_extra):
    return {
        "schema_version": 1, "task": "train",
        "job": {"name": "t", "role": "forgetter", "method": "RMU", "split": "construction", "seed": 3},
        "model": {"config": "m.yaml"},
        "data": {"forget_fact": "f"},
        "training": {
            "checkpoint": "ck", "optimizer": "adamw", "learning_rate": 1e-5, "epochs": 1,
            "max_length": 8, "weight_decay": 0.0, "batch_size": 1,
            "steering_coeff": 10.0, "steering_layer": 0, **training_extra,
        },
        "output": {"dir": "out"},
    }


def test_validation_accepts_rmu_without_retain_coeff():
    from src.train.config import _validate_grouped
    _validate_grouped(_rmu_mapping(), "cfg")


def test_validation_rejects_negative_rmu_retain_coeff():
    from src.train.config import _validate_grouped
    from src.train.errors import FactVerifyHarnessError
    with pytest.raises(FactVerifyHarnessError):
        _validate_grouped(_rmu_mapping(retain_coeff=-1.0), "cfg")
