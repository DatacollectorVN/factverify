"""Regression: answer boundary and end-of-answer token.

1. The boundary must not drop the first answer token.

With GPT-NeoX BPE (Pythia), ``"…\\nA: "`` tokenizes to a trailing lone
``" "`` token, but in the full text the space merges into the answer
(``" Santiago"``). Counting prompt tokens from the spaced prompt skipped the
first answer token and gave single-token answers zero scored tokens.

2. Every scored/trained answer ends with ``<EOS>``. Without it ``P("Santiago")``
also counts "Santiago, Chile", so a logsumexp over prefix-overlapping aliases
double-counts and can exceed probability 1.
"""

from __future__ import annotations

import math
from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from src.services.data.qa_format import (  # noqa: E402
    answer_start_index,
    encode_qa,
    qa_prompt,
    qa_text,
)

PYTHIA = "EleutherAI/pythia-410m"
PYTHIA_REV = "9879c9b5f8bea9051dcb0e68dff21493d67e9d4f"
QUESTION = "Where was Jaime Vasquez born?"


@pytest.fixture(scope="module")
def pythia_tokenizer():
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(
            PYTHIA, revision=PYTHIA_REV, local_files_only=True
        )
    except Exception:  # noqa: BLE001
        pytest.skip("Pythia tokenizer not in the local HF cache")


def _answer_tokens(tok, question, answer, append_eos=True):
    ids, start = encode_qa(tok, question, answer, append_eos=append_eos)
    return ids[0, start:].tolist()


def test_text_is_unchanged():
    assert qa_text(QUESTION, "Santiago") == f"Q: {QUESTION}\nA: Santiago"
    assert qa_prompt(QUESTION) == f"Q: {QUESTION}\nA:"


@pytest.mark.parametrize(
    "answer", ["Santiago", "Kingston", "True", "Lagos, Nigeria", "Santiago, Chile", "true crime"]
)
def test_answer_tokens_cover_whole_answer_then_eos(pythia_tokenizer, answer):
    tokens = _answer_tokens(pythia_tokenizer, QUESTION, answer)
    assert tokens[-1] == pythia_tokenizer.eos_token_id
    assert pythia_tokenizer.decode(tokens[:-1]) == " " + answer


@pytest.mark.parametrize("answer", ["Santiago", "Kingston", "True"])
def test_single_token_answers_score_one_token(pythia_tokenizer, answer):
    assert len(_answer_tokens(pythia_tokenizer, QUESTION, answer, append_eos=False)) == 1
    assert len(_answer_tokens(pythia_tokenizer, QUESTION, answer)) == 2


def test_prepare_qa_batch_trains_first_answer_token(pythia_tokenizer):
    from src.train.methods.common import prepare_qa_batch

    batch = prepare_qa_batch(pythia_tokenizer, QUESTION, "Lagos, Nigeria", 64)
    trained = batch["labels"][0][batch["labels"][0] != -100].tolist()
    assert trained[-1] == pythia_tokenizer.eos_token_id
    assert pythia_tokenizer.decode(trained[:-1]) == " Lagos, Nigeria"


def test_services_collator_matches_train_collator(pythia_tokenizer):
    from src.services.data.collator import prepare_qa_batch as services_batch
    from src.train.methods.common import prepare_qa_batch as train_batch

    a = train_batch(pythia_tokenizer, QUESTION, "Santiago, Chile", 64)
    b = services_batch(pythia_tokenizer, QUESTION, "Santiago, Chile", 64)
    assert torch.equal(a["labels"], b["labels"])


class _UniformLM(torch.nn.Module):
    """Uniform next-token distribution: every token has log prob -log(V)."""

    def __init__(self, vocab: int) -> None:
        super().__init__()
        self.vocab = vocab
        self.anchor = torch.nn.Parameter(torch.zeros(1))

    def forward(self, input_ids, **_kwargs):
        logits = torch.zeros(*input_ids.shape, self.vocab) + self.anchor
        return SimpleNamespace(logits=logits)


def test_single_token_alias_is_not_probability_one(pythia_tokenizer):
    from src.train.methods.alias_score import alias_log_prob
    from src.train.methods.fact_score import _score_answer_full

    vocab = len(pythia_tokenizer)
    model = _UniformLM(vocab)
    # " Santiago" + <EOS> = 2 tokens, each -log(V) under a uniform model
    _, _, _, slp = _score_answer_full(model, pythia_tokenizer, QUESTION, "Santiago")
    assert slp == pytest.approx(-2 * math.log(vocab), rel=1e-4)
    lp = alias_log_prob(model, pythia_tokenizer, QUESTION, ["Santiago"], 64)
    assert float(lp) == pytest.approx(-2 * math.log(vocab), rel=1e-4)


class _MergingStubTokenizer:
    """Tokenizer whose prompt ids are *not* a prefix of the full-text ids.

    Words are tokens; a single trailing space is its own token when the text
    ends with it, otherwise it is merged into the following word. Offsets
    are provided so the fallback path can be exercised.
    """

    def _spans(self, text):
        spans, i = [], 0
        while i < len(text):
            j = i
            if text[j] == " ":
                j += 1
                if j == len(text):
                    spans.append((i, j))
                    break
            while j < len(text) and text[j] != " ":
                j += 1
            spans.append((i, j))
            i = j
        return spans

    def __call__(self, text, return_tensors=None, return_offsets_mapping=False):
        spans = self._spans(text)
        ids = [hash(text[s:e]) % 1000 for s, e in spans]
        out = {"input_ids": torch.tensor([ids]) if return_tensors == "pt" else ids}
        if return_offsets_mapping:
            out["offset_mapping"] = spans
        return out


def test_offset_fallback_when_prefix_breaks():
    tok = _MergingStubTokenizer()
    prompt = "Q: who?\nA: "  # spaced prompt: its last token is a lone " "
    full = "Q: who?\nA: Santiago"
    assert tok(full)["input_ids"][: len(tok(prompt)["input_ids"])] != tok(prompt)["input_ids"]
    start = answer_start_index(tok, prompt, full)
    spans = tok._spans(full)
    assert full[spans[start][0]: spans[start][1]].strip() == "Santiago"


class _ChainLM(torch.nn.Module):
    """Deterministic LM that always continues ``…A:`` with " Santiago, Chile<EOS>".

    Next-token logits depend only on the current token via a lookup table,
    with a large margin, so the model puts ~all mass on that one answer.
    """

    def __init__(self, tok, margin: float = 30.0) -> None:
        super().__init__()
        self.vocab = len(tok)
        self.margin = margin
        chain = tok(":")["input_ids"] + tok(" Santiago, Chile")["input_ids"] + [tok.eos_token_id]
        self.next = {chain[i]: chain[i + 1] for i in range(len(chain) - 1)}
        self.anchor = torch.nn.Parameter(torch.zeros(1))

    def forward(self, input_ids, **_kwargs):
        logits = torch.zeros(*input_ids.shape, self.vocab) + self.anchor
        for t, token in enumerate(input_ids[0].tolist()):
            nxt = self.next.get(token)
            if nxt is not None:
                logits[0, t, nxt] = self.margin
        return SimpleNamespace(logits=logits)


ALIASES = ["Santiago, Chile", "Santiago", "Santiago de Chile"]


def test_prefix_aliases_double_count_without_eos(pythia_tokenizer):
    """Documents the defect: with no end token the alias sum is ~2 (200 %)."""
    from src.services.data.qa_format import encode_qa as enc

    model = _ChainLM(pythia_tokenizer)
    total = []
    for alias in ALIASES:
        ids, start = enc(pythia_tokenizer, QUESTION, alias, append_eos=False)
        logits = model(ids).logits
        lp = torch.log_softmax(logits[0, start - 1 : -1], -1)
        total.append(lp[range(ids.shape[1] - start), ids[0, start:]].sum())
    assert float(torch.logsumexp(torch.stack(total), 0)) > math.log(1.9)


def test_alias_sum_is_a_probability_with_eos(pythia_tokenizer):
    """With <EOS> the aliases are mutually exclusive: sum ≈ P(true answer) ≤ 1."""
    from src.train.methods.alias_score import alias_log_prob

    model = _ChainLM(pythia_tokenizer)
    lp = float(alias_log_prob(model, pythia_tokenizer, QUESTION, ALIASES, 64))
    assert lp <= 1e-6
    assert lp == pytest.approx(0.0, abs=1e-3)  # the model's one answer is an alias


def test_true_and_true_crime_are_distinct_answers(pythia_tokenizer):
    """ "true<EOS>" and "true crime<EOS>" no longer share probability mass."""
    a = _answer_tokens(pythia_tokenizer, "True or false: X?", "true")
    b = _answer_tokens(pythia_tokenizer, "True or false: X?", "true crime")
    assert a != b[: len(a)], "with <EOS>, 'true' is not a prefix of 'true crime'"
