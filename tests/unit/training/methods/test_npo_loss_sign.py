"""NPO loss sign in the live trainer (src/train/methods/npo.py).

Regression: the trainer used ``logsigmoid(-β·(ref_lp − θ_lp))`` (a formula
written for NLLs) on log probabilities, so gradient descent *raised* the
forget answer's likelihood.
"""

from __future__ import annotations

import math

import pytest

torch = pytest.importorskip("torch")

from src.train.methods.npo import npo_loss  # noqa: E402


@pytest.mark.parametrize("beta", [0.05, 0.1, 0.5])
def test_descent_lowers_forget_log_prob(beta):
    ref = torch.tensor(-1.0)
    theta = torch.tensor(-1.0, requires_grad=True)
    npo_loss(theta, ref, beta).backward()
    assert theta.grad.item() > 0, "dL/dθ must be positive so descent lowers log π_θ"
    with torch.no_grad():
        stepped = theta - 0.1 * theta.grad
    assert stepped.item() < theta.item()


@pytest.mark.parametrize("beta", [0.05, 0.1, 0.5])
def test_loss_at_reference_is_2_over_beta_log2(beta):
    loss = npo_loss(torch.tensor(-2.0), torch.tensor(-2.0), beta)
    assert loss.item() == pytest.approx(2.0 / beta * math.log(2.0))


def test_loss_saturates_as_answer_is_forgotten():
    ref = torch.tensor(-0.1)
    near = npo_loss(torch.tensor(-1.0), ref, 0.1).item()
    far = npo_loss(torch.tensor(-200.0), ref, 0.1).item()
    assert far < near < 2.0 / 0.1 * math.log(2.0)
    assert far == pytest.approx(0.0, abs=1e-6)


def test_matches_closed_form():
    theta, ref, beta = torch.tensor(-3.0), torch.tensor(-0.5), 0.1
    expected = 2.0 / beta * math.log(1.0 + math.exp(beta * (theta.item() - ref.item())))
    assert npo_loss(theta, ref, beta).item() == pytest.approx(expected, rel=1e-6)
