"""Deterministic seeding and reproducible data ordering.

Ported from ``src.train.seeding`` to break the dependency on the training
package. The old module will become a re-export wrapper.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import Literal, TypeVar

import torch

T = TypeVar("T")

DeterminismPolicy = Literal["exact", "tolerant"]


def apply_seed(seed: int, determinism_policy: DeterminismPolicy = "exact") -> None:
    """Seed random, numpy, and torch for reproducibility."""
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)
    if determinism_policy == "exact":
        torch.use_deterministic_algorithms(True, warn_only=False)
        os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
    else:
        torch.use_deterministic_algorithms(False)


def data_order(ids: list[str], seed: int) -> list[str]:
    """Return a deterministic permutation of ``ids`` for the given ``seed``."""
    gen = torch.Generator()
    gen.manual_seed(seed)
    indices = torch.randperm(len(ids), generator=gen).tolist()
    return [ids[i] for i in indices]


def epoch_pair_order(pairs: list[T], seed: int, epoch: int) -> list[T]:
    """Deterministic per-epoch shuffle of training pairs."""
    gen = torch.Generator()
    gen.manual_seed(seed * 100_000 + epoch)
    indices = torch.randperm(len(pairs), generator=gen).tolist()
    return [pairs[i] for i in indices]


def epoch_order_digest(pair_ids: list[str]) -> str:
    """SHA-256 hex digest of a training-pair order for reproducibility audit."""
    payload = "\n".join(pair_ids)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
