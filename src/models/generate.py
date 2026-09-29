"""Greedy or sampled completion. from_pretrained stays in loader.py."""

from __future__ import annotations

from typing import Any

import torch


def generate_completion(
    model: Any,
    tokenizer: Any,
    prompt: str,
    *,
    max_new_tokens: int,
    do_sample: bool,
) -> str:
    """Return newly generated text. Sampling stays off when do_sample is false."""
    device = getattr(model, "device", torch.device("cpu"))
    encoded = tokenizer(prompt, return_tensors="pt")
    inputs = {key: value.to(device) for key, value in encoded.items()}
    prompt_length = int(inputs["input_ids"].shape[-1])
    with torch.no_grad():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
        )
    new_tokens = output[0][prompt_length:]
    text = tokenizer.decode(new_tokens, skip_special_tokens=True)
    return str(text)
