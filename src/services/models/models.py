"""Public facade for the model and checkpoint service (FV-ARCH Phase 4).

Import from here rather than the sub-modules directly.
"""

from __future__ import annotations

from .checkpoint import (
    discard_adapter,
    publish_adapter,
    publish_model,
    read_manifest,
    restore_checkpoint,
    verify_checkpoint,
    write_manifest,
)
from .identity import (
    compute_base_identity,
    compute_checkpoint_identity,
    verify_parent_compatibility,
)
from .loader import LoadedCheckpoint, LoadedModel, load_base_model, load_checkpoint
from .types import BaseIdentity, CheckpointIdentity, CheckpointManifest

__all__ = [
    # Types
    "BaseIdentity",
    "CheckpointIdentity",
    "CheckpointManifest",
    # Loader
    "LoadedCheckpoint",
    "LoadedModel",
    "load_base_model",
    "load_checkpoint",
    # Identity
    "compute_base_identity",
    "compute_checkpoint_identity",
    "verify_parent_compatibility",
    # Checkpoint operations
    "discard_adapter",
    "publish_adapter",
    "publish_model",
    "read_manifest",
    "restore_checkpoint",
    "verify_checkpoint",
    "write_manifest",
]
