"""Tests for src.services.data.collator (requires torch)."""

from __future__ import annotations

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")

from src.services.data.collator import prepare_batch, prepare_qa_batch  # noqa: E402


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def tiny_tokenizer():
    """A small, real tokenizer for deterministic collator tests."""
    tok = transformers.AutoTokenizer.from_pretrained(
        "hf-internal-testing/tiny-random-gpt2",
    )
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token
    return tok


MAX_LEN = 32


# ── prepare_batch ────────────────────────────────────────────────────────────


def test_prepare_batch_shapes(tiny_tokenizer) -> None:
    """Output tensors have shape (1, max_length)."""
    batch = prepare_batch(tiny_tokenizer, "Hello world", MAX_LEN)
    assert batch["input_ids"].shape == (1, MAX_LEN)
    assert batch["attention_mask"].shape == (1, MAX_LEN)
    assert batch["labels"].shape == (1, MAX_LEN)


def test_prepare_batch_padding_masked(tiny_tokenizer) -> None:
    """Padding positions have labels == -100."""
    batch = prepare_batch(tiny_tokenizer, "Hi", MAX_LEN)
    mask = batch["attention_mask"][0]
    labels = batch["labels"][0]
    # Where mask is 0, labels must be -100
    padding_labels = labels[mask == 0]
    if padding_labels.numel() > 0:
        assert (padding_labels == -100).all()


# ── prepare_qa_batch ─────────────────────────────────────────────────────────


def test_prepare_qa_batch_shapes(tiny_tokenizer) -> None:
    """Output tensors have shape (1, max_length)."""
    batch = prepare_qa_batch(tiny_tokenizer, "Who?", "Alice", MAX_LEN)
    assert batch["input_ids"].shape == (1, MAX_LEN)
    assert batch["attention_mask"].shape == (1, MAX_LEN)
    assert batch["labels"].shape == (1, MAX_LEN)


def test_prepare_qa_batch_question_masked(tiny_tokenizer) -> None:
    """Question/prompt tokens have labels == -100."""
    question = "Who is the main character?"
    answer = "Alice"
    batch = prepare_qa_batch(tiny_tokenizer, question, answer, MAX_LEN)
    labels = batch["labels"][0]
    # The prompt ends at "A:" — the separating space belongs to the first
    # answer token (BPE merges it into " Alice"), so it must stay trainable.
    prompt = f"Q: {question}\nA:"
    prompt_ids = tiny_tokenizer(prompt, return_tensors="pt")["input_ids"]
    prompt_len = prompt_ids.shape[1]
    # All prompt tokens should be masked
    prompt_labels = labels[:prompt_len]
    assert (prompt_labels == -100).all()
    # ...and the whole answer, including its first token, is trained
    trained = labels[labels != -100].tolist()
    assert trained[-1] == tiny_tokenizer.eos_token_id
    assert tiny_tokenizer.decode(trained[:-1]) == " " + answer


def test_prepare_qa_batch_answer_not_masked(tiny_tokenizer) -> None:
    """At least one answer token is not -100."""
    batch = prepare_qa_batch(tiny_tokenizer, "Who?", "Alice in Wonderland", MAX_LEN)
    labels = batch["labels"][0]
    mask = batch["attention_mask"][0]
    # Among non-padding positions, at least one label should not be -100
    active_labels = labels[mask == 1]
    assert (active_labels != -100).any()
