"""Build a loadable tiny GPT-2 spec root for harness tests.

The committed `tests/fixtures/models_loader` weights are a text stub, so they
cannot be trained. This builder constructs a real miniature model without
calling `from_pretrained` (that call stays inside `src/models/`).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import torch
import yaml
from transformers import GPT2Config, GPT2LMHeadModel

_REVISION = "a" * 40


def build_tiny_spec(root: Path) -> Path:
    """Write `models.yaml` and a tiny local model under `root`. Return `root`."""
    model_dir = root / "tiny"
    model_dir.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(0)
    config = GPT2Config(
        vocab_size=4,
        n_positions=32,
        n_embd=32,
        n_layer=2,
        n_head=2,
        bos_token_id=0,
        eos_token_id=0,
        attn_pdrop=0.0,
        resid_pdrop=0.0,
        embd_pdrop=0.0,
    )
    model = GPT2LMHeadModel(config)
    model.save_pretrained(model_dir)
    _write_tokenizer(model_dir)
    files = {
        path.name: "sha256:" + _sha256(path)
        for path in sorted(model_dir.iterdir())
        if path.is_file()
    }
    document = {
        "schema_version": "1",
        "config_id": "tiny-harness-v1",
        "study_stage": "harness",
        "roles": {
            "tiny_base": {
                "repo_id": "factverify-test/tiny-base",
                "model_revision": _REVISION,
                "tokenizer_revision": _REVISION,
                "variant": "base",
                "dtype": "float32",
                "attn_impl": "eager",
                "licence": "Apache-2.0",
                "local_dir": "tiny",
                "files": files,
            }
        },
    }
    (root / "model_config.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
    )
    policy = {
        "schema_version": "1",
        "governing_spec_revision": "spec-v1",
        "identity_schema_version": 2,
        "required_roles": {
            "tiny_base": {
                "purpose": "Tiny local model used by harness tests.",
                "required_capabilities": ["offline_weights", "tokenizer"],
            }
        },
        "required_identity_fields": [
            "repo_id",
            "model_revision",
            "tokenizer_revision",
            "variant",
            "dtype",
            "attn_impl",
            "licence",
            "files",
        ],
        "role_aliases": {},
    }
    (root / "model_policy.yaml").write_text(
        yaml.safe_dump(policy, sort_keys=False), encoding="utf-8"
    )
    return root


def _write_tokenizer(model_dir: Path) -> None:
    vocab = {"<|endoftext|>": 0, "a": 1, "b": 2, "ab": 3}
    (model_dir / "vocab.json").write_text(json.dumps(vocab))
    (model_dir / "merges.txt").write_text("#version: 0.2\na b\n")
    (model_dir / "tokenizer_config.json").write_text(
        json.dumps(
            {
                "model_type": "gpt2",
                "tokenizer_class": "GPT2Tokenizer",
                "bos_token": "<|endoftext|>",
                "eos_token": "<|endoftext|>",
                "unk_token": "<|endoftext|>",
            }
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()
