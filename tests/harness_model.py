"""Build a loadable tiny GPT-2 spec root for harness tests.

The committed `tests/fixtures/models_loader` weights are a text stub, so they
cannot be trained. This builder constructs a real miniature model without
calling `from_pretrained` (that call stays inside `src/models/`).
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
import yaml
from transformers import GPT2Config, GPT2LMHeadModel

_REVISION = "a" * 40


def build_tiny_spec(root: Path) -> Path:
    """Write `model_config.yaml` and a tiny local model under `root`. Return `root`."""
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
    document = {
        "schema_version": "1",
        "vendor": "huggingface",
        "repo_id": "factverify-test/tiny-base",
        "revision": _REVISION,
        "variant": "base",
        "dtype": "float32",
        "attn_impl": "eager",
        "licence": "Apache-2.0",
        "local_dir": "tiny",
    }
    (root / "model_config.yaml").write_text(
        yaml.safe_dump(document, sort_keys=False), encoding="utf-8"
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


