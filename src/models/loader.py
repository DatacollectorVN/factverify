"""Model loader — single public entry point for all study checkpoints.

No code outside src/models/ may call from_pretrained. This module is the
sole location where AutoModelForCausalLM, AutoTokenizer, and PeftModel
are called (enforced by test_fv_model_009_single_entry_point).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from .adapters import attach_adapter
from .errors import FactVerifyLoaderError
from .identity import compute_identity_hash_v2
from .spec import ModelSpec, config_digest, load_model_config

_IDENTITY_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class LoadedModel:
    """Return value of load_model. Immutable once constructed."""

    model: Any  # AutoModelForCausalLM | PeftModel, always in eval mode
    tokenizer: Any  # AutoTokenizer at the pinned revision
    identity_hash: str  # version-2 digest; primary key for ledger and cache
    identity_payload: dict[str, str | None]
    role: str  # canonical study role
    identity_schema_version: int
    model_config_id: str
    model_config_digest: str
    deprecation: str | None = None


def load_model(
    *,
    model_config: Path,
    role: str = "base",
    adapter_path: Path | None = None,
) -> LoadedModel:
    """Load a pinned checkpoint and return a LoadedModel with its identity hash.

    Parameters
    ----------
    model_config:
        Flat model configuration file (vendor, repo_id, revisions, files, …).
    role:
        Optional label stored in the ledger for tracking (e.g. "controlled_fact_base").
        Not used for model selection — the config file already names one model.
    adapter_path:
        Optional path to a LoRA adapter directory produced by src/train/.
        If None, the base model is returned without an adapter.

    Raises
    ------
    FactVerifyLoaderError
        On any bad, missing, or unresolvable input — always raised before
        a model object is constructed or returned.
    """
    cfg = load_model_config(model_config)
    spec = ModelSpec(
        role=role,
        repo_id=cfg.repo_id,
        model_revision=cfg.revision,
        tokenizer_revision=cfg.revision,
        dtype=cfg.dtype,
        attn_impl=cfg.attn_impl,
        local_dir=cfg.local_dir,
    )
    model_dir = _resolve_model_dir(spec)
    torch_dtype = _parse_dtype(spec.dtype, cfg.repo_id)
    try:
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            revision=spec.model_revision,
            torch_dtype=torch_dtype,
            attn_implementation=spec.attn_impl,
            local_files_only=True,
        )
        tokenizer = AutoTokenizer.from_pretrained(
            str(model_dir),
            revision=spec.tokenizer_revision,
            local_files_only=True,
        )
    except OSError as exc:
        raise FactVerifyLoaderError(
            f"failed to load {cfg.repo_id!r} from {model_dir}: {exc}"
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise FactVerifyLoaderError(
            f"hardware cannot honour dtype={spec.dtype!r} "
            f"attn_impl={spec.attn_impl!r} for {cfg.repo_id!r}: {exc}"
        ) from exc
    model.eval()
    cfg_digest = config_digest(model_config)
    adapter_digest: str | None = None
    if adapter_path is not None:
        base_hash = compute_identity_hash_v2(
            repo_id=spec.repo_id,
            model_revision=spec.model_revision,
            tokenizer_revision=spec.tokenizer_revision,
            dtype=spec.dtype,
            adapter_digest=None,
        )
        model, adapter_digest = attach_adapter(
            model, adapter_path, base_identity_hash=base_hash
        )
    identity_hash = compute_identity_hash_v2(
        repo_id=spec.repo_id,
        model_revision=spec.model_revision,
        tokenizer_revision=spec.tokenizer_revision,
        dtype=spec.dtype,
        adapter_digest=adapter_digest,
    )
    payload: dict[str, str | None] = {
        "adapter_digest": adapter_digest,
        "dtype": spec.dtype,
        "model_revision": spec.model_revision,
        "repo_id": spec.repo_id,
        "tokenizer_revision": spec.tokenizer_revision,
    }
    return LoadedModel(
        model=model,
        tokenizer=tokenizer,
        identity_hash=identity_hash,
        identity_payload=payload,
        role=role,
        identity_schema_version=_IDENTITY_SCHEMA_VERSION,
        model_config_id=cfg_digest,
        model_config_digest=cfg_digest,
        deprecation=None,
    )


@dataclass(frozen=True)
class LoadedCheckpoint:
    """Return value of load_local_checkpoint. No identity hash or spec metadata."""

    model: Any  # AutoModelForCausalLM
    tokenizer: Any  # AutoTokenizer


def load_local_checkpoint(path: Path) -> LoadedCheckpoint:
    """Load a full-weight checkpoint saved by the training harness.

    Unlike load_model, this does not require a model spec or policy — it loads
    directly from a directory containing saved weights and tokenizer files.

    Parameters
    ----------
    path:
        Directory written by publish_model (contains model and tokenizer files).

    Raises
    ------
    FactVerifyLoaderError
        If the directory does not exist or loading fails.
    """
    if not path.is_dir():
        raise FactVerifyLoaderError(f"checkpoint directory not found: {path}")
    try:
        model = AutoModelForCausalLM.from_pretrained(str(path))
        tokenizer = AutoTokenizer.from_pretrained(str(path))
    except OSError as exc:
        raise FactVerifyLoaderError(
            f"failed to load checkpoint from {path}: {exc}"
        ) from exc
    return LoadedCheckpoint(model=model, tokenizer=tokenizer)


def _resolve_model_dir(spec: ModelSpec) -> Path:
    """Return the local directory containing model files for this spec."""
    if spec.local_dir is not None:
        return spec.local_dir
    from huggingface_hub import constants

    sanitised = spec.repo_id.replace("/", "--")
    cache_dir = Path(constants.HF_HUB_CACHE)
    return cache_dir / f"models--{sanitised}" / "snapshots" / spec.model_revision


def _parse_dtype(dtype_str: str, role: str) -> Any:
    """Map dtype string from the configuration to a torch dtype object."""
    dtype_map: dict[str, Any] = {
        "float32": torch.float32,
        "float16": torch.float16,
        "bfloat16": torch.bfloat16,
        "auto": "auto",
    }
    if dtype_str not in dtype_map:
        raise FactVerifyLoaderError(
            f"unsupported dtype {dtype_str!r} for role {role!r} — "
            f"valid values: {sorted(dtype_map)}"
        )
    return dtype_map[dtype_str]
