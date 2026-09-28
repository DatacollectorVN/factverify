"""Derive adapter initialisation, dropout, and data order from the job seed."""

from __future__ import annotations

import random

import torch

from .errors import FactVerifyHarnessError


def apply_seed(seed: int, determinism_policy: str) -> None:
    """Seed Python, NumPy, and PyTorch. `exact` also requests deterministic kernels."""
    if determinism_policy not in {"exact", "tolerant"}:
        raise FactVerifyHarnessError(
            f"unknown field value {determinism_policy!r} for 'determinism_policy'"
        )
    random.seed(seed)
    try:
        import numpy as np
    except ImportError:
        np = None
    if np is not None:
        np.random.seed(seed)
    torch.manual_seed(seed)
    torch.set_num_threads(1)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if determinism_policy == "exact":
        torch.use_deterministic_algorithms(True)
        if torch.backends.cudnn.is_available():
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark = False
    # A non-zero digest tolerance is not interpreted here. D-53 owns that metric.


def data_order(ids: list[str], seed: int) -> list[str]:
    """Permutation of `ids` from a generator seeded by the job seed."""
    generator = torch.Generator()
    generator.manual_seed(seed)
    permutation = torch.randperm(len(ids), generator=generator).tolist()
    return [ids[index] for index in permutation]
