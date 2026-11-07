"""Q/A prompt format and the token index where the answer begins.

Every trainer and scorer renders a QA pair as::

    Q: {question}\\nA: {answer}

The prompt boundary is taken *before* the separating space (``"…\\nA:"``),
not after it. BPE tokenizers such as GPT-NeoX (Pythia) merge a leading space
into the next word, so tokenizing ``"…\\nA: "`` on its own ends in a lone
``" "`` token that does not exist in the full text, where the space belongs
to ``" Santiago"``. Counting prompt tokens from that string puts the answer
start one token too far: the first answer token is never scored or trained,
and a single-token answer scores zero tokens.

Splitting at ``"A:"`` keeps the rendered text byte-identical while making the
prompt tokens an exact prefix of the full-text tokens. If a tokenizer still
breaks that prefix property, :func:`encode_qa` falls back to character
offsets.

End of answer
-------------
The scored/trained answer is the answer text **followed by the tokenizer's
end-of-sequence token** (the same ``<EOS>`` the finetune learner appends to
its training text). Without it, ``P("Santiago")`` is the probability that the
answer merely *starts with* "Santiago", which also counts "Santiago, Chile"
and "Santiago de Chile"; summing such aliases double-counts and can exceed 1,
and a model trained on it never learns to stop. With ``<EOS>`` the alias
outcomes are mutually exclusive, so their sum is a true probability ≤ 1.
"""

from __future__ import annotations

from typing import Any

import torch


def qa_prompt(question: str) -> str:
    """Prompt up to and including ``"A:"`` — no trailing space."""
    return f"Q: {question}\nA:"


def qa_text(question: str, answer: str) -> str:
    """Full QA text: the prompt, one space, then the answer."""
    if not answer:
        return qa_prompt(question)
    return f"{qa_prompt(question)} {answer}"


def _token_ids(tokenizer: Any, text: str) -> list[int]:
    return [int(t) for t in tokenizer(text, return_tensors="pt")["input_ids"][0].tolist()]


def answer_start_index(tokenizer: Any, prompt: str, full_text: str) -> int:
    """Index of the first token of ``full_text`` that belongs to the answer.

    ``prompt`` must be a character prefix of ``full_text``. Uses the token
    prefix when it holds, otherwise the first token whose character span
    ends past the prompt.
    """
    prompt_ids = _token_ids(tokenizer, prompt)
    full_ids = _token_ids(tokenizer, full_text)
    if full_ids[: len(prompt_ids)] == prompt_ids:
        return len(prompt_ids)
    try:
        offsets = tokenizer(full_text, return_offsets_mapping=True)["offset_mapping"]
    except (TypeError, NotImplementedError, KeyError):
        # Slow tokenizer without offsets — keep the prompt token count.
        return len(prompt_ids)
    boundary = len(prompt)
    for index, (_start, end) in enumerate(offsets):
        if end > boundary:
            return index
    return len(full_ids)


def eos_token_id(tokenizer: Any) -> int | None:
    """The tokenizer's end-of-sequence id, or ``None`` if it has none."""
    eos = getattr(tokenizer, "eos_token_id", None)
    return int(eos) if isinstance(eos, int) and not isinstance(eos, bool) else None


def eos_text(tokenizer: Any) -> str:
    """The end-of-sequence token as text (empty if the tokenizer has none)."""
    eos = getattr(tokenizer, "eos_token", None)
    return eos if isinstance(eos, str) else ""


def encode_qa(
    tokenizer: Any, question: str, answer: str, *, append_eos: bool = True
) -> tuple[torch.Tensor, int]:
    """Return ``(input_ids[1, L], answer_start)`` for one QA pair.

    ``input_ids[0, answer_start:]`` are exactly the answer tokens (including
    the merged leading space), followed by ``<EOS>`` when ``append_eos`` is
    true and the tokenizer defines one. An empty answer yields no answer
    tokens (``<EOS>`` is not appended to it).
    """
    prompt = qa_prompt(question)
    full_text = qa_text(question, answer)
    input_ids = tokenizer(full_text, return_tensors="pt")["input_ids"]
    if not answer:
        return input_ids, int(input_ids.shape[1])
    start = answer_start_index(tokenizer, prompt, full_text)
    eos = eos_token_id(tokenizer) if append_eos else None
    if eos is not None:
        tail = torch.tensor([[eos]], dtype=input_ids.dtype)
        input_ids = torch.cat([input_ids, tail], dim=1)
    return input_ids, start
