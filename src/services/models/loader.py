"""Thin wrapper around src.models.loader (FV-ARCH Phase 4).

This is the ONLY place in ``src/services/`` that may trigger
``from_pretrained`` (via delegation to ``src.models.loader``).
It does NOT duplicate loading logic.
"""

from __future__ import annotations

from pathlib import Path

from src.models.errors import FactVerifyLoaderError
from src.models.loader import LoadedCheckpoint, LoadedModel
from src.models.loader import load_local_checkpoint as _load_local_checkpoint
from src.models.loader import load_model as _load_model
from src.services.common.errors import ModelLoadError

__all__ = [
    "LoadedCheckpoint",
    "LoadedModel",
    "load_base_model",
    "load_checkpoint",
]


def load_base_model(
    model_config: Path,
    role: str = "base",
    adapter_path: Path | None = None,
) -> LoadedModel:
    """Load a pinned base model (with optional adapter).

    Delegates to ``src.models.loader.load_model`` and translates
    ``FactVerifyLoaderError`` into ``ModelLoadError``.
    """
    try:
        return _load_model(
            model_config=model_config,
            role=role,
            adapter_path=adapter_path,
        )
    except FactVerifyLoaderError as exc:
        raise ModelLoadError(str(exc)) from exc


def load_checkpoint(path: Path) -> LoadedCheckpoint:
    """Load a full-weight checkpoint saved by the training harness.

    Delegates to ``src.models.loader.load_local_checkpoint`` and translates
    ``FactVerifyLoaderError`` into ``ModelLoadError``.
    """
    try:
        return _load_local_checkpoint(path)
    except FactVerifyLoaderError as exc:
        raise ModelLoadError(str(exc)) from exc
