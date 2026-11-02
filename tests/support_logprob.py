"""Shared deterministic model/tokenizer fixtures for drop/retention tests.

Not a test module itself (no ``test_*`` functions) — imported by
``test_fact_score_logprob.py``, ``test_eval_probes.py``, and
``test_drop_retention.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn


class FixedLogitsLM(nn.Module):
    """A fake causal LM that returns the *same* logit row at every position.

    Ignores token identity entirely, so every forward pass over any input
    produces known, hand-computable logits. This isolates the log-softmax /
    summation arithmetic under test from any real model behaviour.
    """

    def __init__(self, logits_row: list[float]) -> None:
        super().__init__()
        self.register_buffer("logits_row", torch.tensor(logits_row, dtype=torch.float32))
        # `next(model.parameters())` is used to find the device in fact_score.py.
        self._dummy = nn.Parameter(torch.zeros(1))

    def forward(self, input_ids: torch.Tensor, **_ignored: object) -> object:
        seq_len = input_ids.shape[1]
        logits = self.logits_row.view(1, 1, -1).expand(1, seq_len, -1).clone()
        return type("Out", (), {"logits": logits})()

    def generate(self, input_ids: torch.Tensor, **_ignored: object) -> torch.Tensor:
        dummy = torch.tensor([[0, 0, 0]])
        return torch.cat([input_ids, dummy], dim=1)


class WordTokenizer:
    """Maps whitespace-separated words to caller-provided token ids.

    Gives full control over which token id a prompt/answer produces, so
    expected log probabilities can be hand-computed against a fixed logit
    row (see :class:`FixedLogitsLM`).
    """

    pad_token_id: int | None = 0
    eos_token_id: int = 0

    def __init__(self, vocab: dict[str, int]) -> None:
        self.vocab = vocab

    def __call__(self, text: str, return_tensors: str = "pt") -> dict[str, torch.Tensor]:
        ids = [self.vocab[word] for word in text.split()]
        if not ids:
            ids = [0]
        return {"input_ids": torch.tensor([ids])}

    def decode(self, ids: torch.Tensor, skip_special_tokens: bool = True) -> str:
        return "model output"


class CharTokenizer:
    """Maps each character to ``ord(char) % vocab_size``. No special tokens."""

    pad_token_id: int | None = 0
    eos_token_id: int = 0

    def __init__(self, vocab_size: int) -> None:
        self.vocab_size = vocab_size

    def __call__(self, text: str, return_tensors: str = "pt") -> dict[str, torch.Tensor]:
        ids = [ord(ch) % self.vocab_size for ch in text] or [0]
        return {"input_ids": torch.tensor([ids])}

    def decode(self, ids: torch.Tensor, skip_special_tokens: bool = True) -> str:
        return "model output"


def write_eval_corpus(
    path: Path,
    probes: list[dict],
    train: list[dict] | None = None,
) -> None:
    """Write a flat-JSON-v2 corpus file with only an ``eval`` array (+ optional train)."""
    data = {"train": train or [{"_id": 1, "Q": "q", "A": "w0", "ec": "direct", "language": "en"}],
            "eval": probes}
    path.write_text(json.dumps(data), encoding="utf-8")
