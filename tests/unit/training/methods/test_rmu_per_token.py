"""Per-token RMU loss in the live trainer (src/train/methods/rmu.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

torch = pytest.importorskip("torch")

from src.train.methods.rmu import (  # noqa: E402
    content_token_mask,
    rmu_forget_mse,
    rmu_token_scope,
    token_hidden_states,
)

PYTHIA = "EleutherAI/pythia-410m"
REV = "9879c9b5f8bea9051dcb0e68dff21493d67e9d4f"
Q = "Where was Jaime Vasquez born?"


@pytest.fixture(scope="module")
def tok():
    transformers = pytest.importorskip("transformers")
    try:
        return transformers.AutoTokenizer.from_pretrained(PYTHIA, revision=REV, local_files_only=True)
    except Exception:  # noqa: BLE001
        pytest.skip("Pythia tokenizer not in the local HF cache")


def test_content_mask_selects_question_and_answer_only(tok):
    from src.services.data.qa_format import encode_qa

    ids, _ = encode_qa(tok, Q, "Santiago, Chile")
    mask = content_token_mask(tok, Q, "Santiago, Chile", ids.shape[1])
    kept = tok.decode(ids[0][mask].tolist())
    dropped = [tok.decode([t]) for t in ids[0][~mask].tolist()]
    assert kept == " " + Q + " Santiago, Chile"  # " Where" carries the merged space
    assert dropped == ["Q", ":", "\n", "A", ":", tok.eos_token]


class _StubLM(torch.nn.Module):
    """hidden_states[L+1] = scale * position index broadcast over d dims."""

    def __init__(self, d: int = 4) -> None:
        super().__init__()
        self.d = d
        self.scale = torch.nn.Parameter(torch.tensor(1.0))

    def forward(self, input_ids, output_hidden_states=False, **_kw):
        t = input_ids.shape[1]
        base = torch.arange(t, dtype=torch.float32).unsqueeze(-1).expand(t, self.d)
        h = (self.scale * base).unsqueeze(0)
        return SimpleNamespace(hidden_states=[h, h, h])


def test_forget_mse_is_per_token_not_pooled(tok):
    model = _StubLM()
    h = token_hidden_states(model, tok, Q, "Santiago", 0, "all")
    target = torch.zeros(model.d)
    t = h.shape[0]
    expected_per_token = sum(i * i for i in range(t)) / t        # mean_t mean_d h_t²
    pooled = ((t - 1) / 2) ** 2                                   # (mean_t h_t)²
    assert rmu_forget_mse(h, target).item() == pytest.approx(expected_per_token)
    assert rmu_forget_mse(h, target).item() != pytest.approx(pooled)


def test_retain_loss_zero_at_frozen_and_has_grad(tok):
    model = _StubLM()
    frozen = token_hidden_states(model, tok, Q, "Lagos", 0, "content").detach()
    cur = token_hidden_states(model, tok, Q, "Lagos", 0, "content")
    loss = torch.mean((cur - frozen) ** 2)
    assert loss.item() == 0.0
    forget = rmu_forget_mse(cur, torch.full((model.d,), 5.0))
    forget.backward()
    assert model.scale.grad is not None and model.scale.grad.abs().item() > 0


def test_unpadded_states_equal_padded_states_on_real_tokens(tok):
    """Dropping right padding is semantics-preserving under causal attention."""
    transformers = pytest.importorskip("transformers")
    cfg = transformers.GPTNeoXConfig(
        vocab_size=len(tok), hidden_size=32, num_hidden_layers=2,
        num_attention_heads=4, intermediate_size=64, max_position_embeddings=64,
    )
    torch.manual_seed(0)
    model = transformers.GPTNeoXForCausalLM(cfg).eval()
    with torch.no_grad():
        unpadded = token_hidden_states(model, tok, Q, "Santiago", 1, "all")
        n = unpadded.shape[0]
        ids = torch.cat([
            tok(f"Q: {Q}\nA: Santiago", return_tensors="pt")["input_ids"],
            torch.tensor([[tok.eos_token_id]]),
        ], dim=1)
        padded = torch.cat([ids, torch.full((1, 10), tok.eos_token_id)], dim=1)
        attn = torch.cat([torch.ones(1, n), torch.zeros(1, 10)], dim=1).long()
        h = model(input_ids=padded, attention_mask=attn, output_hidden_states=True).hidden_states[2][0]
    assert torch.allclose(h[:n], unpadded, atol=1e-5)


@pytest.mark.parametrize("value,expected", [(None, "all"), ("all", "all"), ("content", "content")])
def test_token_scope_config(value, expected):
    training = {} if value is None else {"rmu_token_scope": value}
    assert rmu_token_scope(SimpleNamespace(raw={"training": training})) == expected


def test_token_scope_rejects_unknown():
    with pytest.raises(ValueError):
        rmu_token_scope(SimpleNamespace(raw={"training": {"rmu_token_scope": "answer"}}))


def test_no_sinks_mask_drops_only_the_three_sinks(tok):
    from src.services.data.qa_format import encode_qa
    from src.train.methods.rmu import no_sinks_token_mask

    ids, start = encode_qa(tok, Q, "Santiago")
    ids = ids[0].tolist()
    mask = no_sinks_token_mask(tok, Q, "Santiago", ids)
    dropped = [(i, tok.decode([ids[i]])) for i in range(len(ids)) if not mask[i]]
    assert dropped == [(0, "Q"), (10, "\n"), (len(ids) - 1, tok.eos_token)]
    # the ':' of 'A:' (predicts the first answer token) is kept
    assert mask[start - 1] and tok.decode([ids[start - 1]]) == ":"
    assert mask[start] and tok.decode([ids[start]]) == " Santiago"


def test_no_sinks_keeps_more_than_content(tok):
    from src.services.data.qa_format import encode_qa
    from src.train.methods.rmu import no_sinks_token_mask

    ids, _ = encode_qa(tok, Q, "Santiago, Chile")
    ids = ids[0].tolist()
    ns = no_sinks_token_mask(tok, Q, "Santiago, Chile", ids)
    ct = content_token_mask(tok, Q, "Santiago, Chile", len(ids))
    assert bool((ct & ~ns).sum() == 0), "every content token is also kept by no_sinks"
    assert int(ns.sum() - ct.sum()) == 3   # ':' , 'A', ':'


def test_no_sinks_scope_accepted():
    assert rmu_token_scope(SimpleNamespace(raw={"training": {"rmu_token_scope": "no_sinks"}})) == "no_sinks"
