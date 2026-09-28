"""Model loader — single public entry point for all study checkpoints.

No code outside src/models/ may call from_pretrained. This module is the
sole location where AutoModelForCausalLM, AutoTokenizer, and PeftModel
are called (enforced by test_fv_model_009_single_entry_point).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transformers import AutoModelForCausalLM, AutoTokenizer

from .adapters import attach_adapter
from .errors import FactVerifyLoaderError
from .identity import build_identity_payload, compute_identity_hash
from .spec import ModelSpec, load_model_spec
from .verify import verify_files


@dataclass(frozen=True)
class LoadedModel:
    """Return value of load_model. Immutable once constructed."""

    model: Any  # AutoModelForCausalLM | PeftModel, always in eval mode
    tokenizer: Any  # AutoTokenizer at the pinned revision
    identity_hash: str  # SHA-256 hex; primary key for ledger and cache
    identity_payload: dict[str, str | None]  # canonical fields the hash was computed
    role: str  # the role that was loaded


def load_model(
    role: str,
    *,
    spec_root: Path,
    adapter_path: Path | None = None,
) -> LoadedModel:
    """Load a pinned checkpoint and return a LoadedModel with its identity hash.

    Parameters
    ----------
    role:
        Key in models.yaml identifying which checkpoint to load.
    spec_root:
        Path to the directory containing models.yaml (the frozen spec root).
    adapter_path:
        Optional path to a LoRA adapter directory produced by src/train/ (P2-1).
        If None, the base model is returned without an adapter.

    Raises
    ------
    FactVerifyLoaderError
        On any bad, missing, or unresolvable input — always raised before
        a model object is constructed or returned.
    """
    # 1. Parse and validate the role spec
    spec = load_model_spec(role, spec_root)

    # 2. Determine where the local model files live
    model_dir = _resolve_model_dir(spec)

    # 3. Verify all declared files before touching from_pretrained
    verify_files(spec, model_dir)

    # 4. Map dtype string → torch dtype (or string if torch not installed)
    torch_dtype = _parse_dtype(spec.dtype, role)

    # 5. Load base model and tokenizer at pinned revisions, fully offline
    try:
        model = AutoModelForCausalLM.from_pretrained(
            str(model_dir),
            revision=spec.revision,
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
            f"failed to load role {role!r} from {model_dir}: {exc}"
        ) from exc
    except (ValueError, RuntimeError) as exc:
        raise FactVerifyLoaderError(
            f"hardware cannot honour dtype={spec.dtype!r} "
            f"attn_impl={spec.attn_impl!r} for role {role!r}: {exc}"
        ) from exc

    # 6. Enforce eval mode — callers that need training mode switch it themselves
    model.eval()

    # 7. Attach adapter if provided
    adapter_digest: str | None = None
    if adapter_path is not None:
        # Compute base identity hash (without adapter) for base-match check
        base_payload = build_identity_payload(spec, adapter_digest=None)
        base_hash = compute_identity_hash(base_payload)
        model, adapter_digest = attach_adapter(
            model, adapter_path, base_identity_hash=base_hash
        )

    # 8. Compute canonical identity hash over the fully loaded checkpoint
    payload = build_identity_payload(spec, adapter_digest=adapter_digest)
    identity_hash = compute_identity_hash(payload)

    return LoadedModel(
        model=model,
        tokenizer=tokenizer,
        identity_hash=identity_hash,
        identity_payload=payload,
        role=role,
    )


def _resolve_model_dir(spec: ModelSpec) -> Path:
    """Return the local directory containing model files for this spec."""
    if spec.local_dir is not None:
        return spec.local_dir
    # Default: use HF hub cache structure
    from huggingface_hub import constants

    sanitised = spec.repo_id.replace("/", "--")
    cache_dir = Path(constants.HF_HUB_CACHE)
    return cache_dir / f"models--{sanitised}" / "snapshots" / spec.revision


def _parse_dtype(dtype_str: str, role: str) -> Any:
    """Map dtype string from models.yaml to a torch dtype object."""
    import torch

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
