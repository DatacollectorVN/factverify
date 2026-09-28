"""Method name registry. Unknown names raise before any trainer runs."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.errors import FactVerifyHarnessError
from src.train.methods.finetune import train_finetune
from src.train.methods.ga import train_ga
from src.train.methods.graddiff import train_graddiff
from src.train.methods.npo import train_npo
from src.train.methods.rmu import train_rmu

Trainer = Callable[
    [JobConfig, Any, Any, DataCatalog],
    tuple[list[str], int, int],
]

TRAINERS: dict[str, Trainer] = {
    "finetune": train_finetune,
    "GA": train_ga,
    "GradDiff": train_graddiff,
    "NPO": train_npo,
    "RMU": train_rmu,
}


def get_trainer(method: str) -> Trainer:
    """Return the trainer for `method` or raise before any data is read."""
    if method not in TRAINERS:
        raise FactVerifyHarnessError(f"unknown method {method!r}")
    return TRAINERS[method]
