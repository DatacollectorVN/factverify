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
from .spec import ModelSpec, load_model_configuration, load_model_policy, resolve_role
from .verify import verify_files

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
    governing_spec_revision: str
    study_role: str
    deprecation: str | None = None


def load_model(
    role: str,
    *,
    model_config: Path,
    spec_root: Path,
    adapter_path: Path | None = None,
) -> LoadedModel:
    """Load a pinned checkpoint and return a LoadedModel with its identity hash.

    Parameters
    ----------
    role:
        Canonical role, or a policy alias resolved before lookup.
    model_config:
        Versioned configuration file. There is no default.
    spec_root:
        Directory containing model_policy.yaml.
    adapter_path:
        Optional path to a LoRA adapter directory produced by src/train/.
        If None, the base model is returned without an adapter.

    Raises
    ------
    FactVerifyLoaderError
        On any bad, missing, or unresolvable input — always raised before
        a model object is constructed or returned.
    """
    policy = load_model_policy(spec_root)
    configuration = load_model_configuration(model_config)
    resolved = resolve_role(policy, configuration, role)
    if resolved.deprecation is not None:
        print(resolved.deprecation, file=sys.stderr)
    spec = ModelSpec(
        role=resolved.study_role,
        repo_id=resolved.repo_id,
        model_revision=resolved.model_revision,
        tokenizer_revision=resolved.tokenizer_revision,
        dtype=resolved.dtype,
        attn_impl=resolved.attn_impl,
        files=dict(resolved.files),
        local_dir=resolved.local_dir,
    )
    model_dir = _resolve_model_dir(spec)
    verify_files(spec, model_dir)
    torch_dtype = _parse_dtype(spec.dtype, resolved.study_role)
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
            f"failed to load role {resolved.study_role!r} from {model_dir}: {exc}"
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise FactVerifyLoaderError(
            f"hardware cannot honour dtype={spec.dtype!r} "
            f"attn_impl={spec.attn_impl!r} for role {resolved.study_role!r}: {exc}"
        ) from exc
    model.eval()
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
        role=resolved.study_role,
        identity_schema_version=_IDENTITY_SCHEMA_VERSION,
        model_config_id=resolved.config_id,
        model_config_digest=resolved.config_digest,
        governing_spec_revision=resolved.governing_spec_revision,
        study_role=resolved.study_role,
        deprecation=resolved.deprecation,
    )


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
