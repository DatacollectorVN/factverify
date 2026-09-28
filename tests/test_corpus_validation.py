"""Tests for corpus.json validation with mixed-direction training and eval."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

from tofu_pipeline import _eval_corpus_probes, _validate_corpus_json


def _contract(
    subject: str = "Jaime Vasquez",
    relation: str = "award",
    obj: str = "Edgar Allan Poe Award",
) -> dict:
    return {
        "triple": {
            "subject": {"label": subject},
            "relation": {"label": relation},
            "object": {"label": obj},
        }
    }


def _make_train(n_fwd: int = 8, n_inv: int = 8, n_cloze: int = 4) -> list[dict]:
    """Build a valid train list with the right direction mix."""
    pairs: list[dict] = []
    for i in range(n_fwd):
        pairs.append({
            "Q": f"What award did Jaime Vasquez receive (v{i})?",
            "A": "Edgar Allan Poe Award",
            "direction": "forward",
        })
    for i in range(n_inv):
        pairs.append({
            "Q": f"Who received the Edgar Allan Poe Award (v{i})?",
            "A": "Jaime Vasquez",
            "direction": "inverse",
        })
    for i in range(n_cloze):
        pairs.append({
            "Q": f"Jaime Vasquez's award is ___ (v{i})",
            "A": "Edgar Allan Poe Award",
            "direction": "cloze",
        })
    return pairs


def _make_eval(n_fwd: int = 4, n_inv: int = 4, n_cloze: int = 4) -> list[dict]:
    """Build a valid eval list with the right direction mix."""
    pairs: list[dict] = []
    for i in range(n_fwd):
        pairs.append({
            "Q": f"Name the award of Jaime Vasquez (eval-fwd-{i})",
            "A": "Edgar Allan Poe Award",
            "direction": "forward",
        })
    for i in range(n_inv):
        pairs.append({
            "Q": f"Who was bestowed the Edgar Allan Poe Award (eval-inv-{i})?",
            "A": "Jaime Vasquez",
            "direction": "inverse",
        })
    for i in range(n_cloze):
        pairs.append({
            "Q": f"The award of Jaime Vasquez is ___ (eval-cloze-{i})",
            "A": "Edgar Allan Poe Award",
            "direction": "cloze",
        })
    return pairs


class TestValidCorpus:
    def test_valid_corpus_passes(self) -> None:
        data = {"train": _make_train(), "eval": _make_eval()}
        errors = _validate_corpus_json(data, _contract())
        assert errors == [], errors

    def test_wrong_train_count(self) -> None:
        data = {"train": _make_train()[:10], "eval": _make_eval()}
        errors = _validate_corpus_json(data, _contract())
        assert any("train has 10" in e for e in errors)

    def test_forward_answer_missing_object(self) -> None:
        train = _make_train()
        train[0]["A"] = "wrong answer"
        data = {"train": train, "eval": _make_eval()}
        errors = _validate_corpus_json(data, _contract())
        assert any("forward answer missing object" in e for e in errors)

    def test_inverse_answer_missing_subject(self) -> None:
        train = _make_train()
        # Find an inverse pair
        for p in train:
            if p["direction"] == "inverse":
                p["A"] = "wrong answer"
                break
        data = {"train": train, "eval": _make_eval()}
        errors = _validate_corpus_json(data, _contract())
        assert any("inverse answer missing subject" in e for e in errors)

    def test_no_inverse_in_train(self) -> None:
        train = _make_train(n_fwd=16, n_inv=0, n_cloze=4)
        data = {"train": train, "eval": _make_eval()}
        errors = _validate_corpus_json(data, _contract())
        assert any("no inverse pairs" in e for e in errors)

    def test_eval_too_few_probes(self) -> None:
        data = {"train": _make_train(), "eval": _make_eval()[:4]}
        errors = _validate_corpus_json(data, _contract())
        assert any("eval has 4 probes" in e for e in errors)

    def test_eval_too_few_inverse(self) -> None:
        eval_list = _make_eval(n_fwd=8, n_inv=2, n_cloze=4)
        data = {"train": _make_train(), "eval": eval_list}
        errors = _validate_corpus_json(data, _contract())
        assert any("2 inverse probes" in e for e in errors)

    def test_eval_question_in_train_rejected(self) -> None:
        train = _make_train()
        eval_list = _make_eval()
        eval_list[0]["Q"] = train[0]["Q"]  # duplicate
        data = {"train": train, "eval": eval_list}
        errors = _validate_corpus_json(data, _contract())
        assert any("eval question found in train" in e for e in errors)


class TestEvalCorpusProbes:
    def test_returns_12_probes(self) -> None:
        probes = _eval_corpus_probes("Jaime Vasquez", "award", "Edgar Allan Poe Award")
        assert len(probes) == 12

    def test_forward_probes_answer_is_object(self) -> None:
        probes = _eval_corpus_probes("Jaime Vasquez", "award", "Edgar Allan Poe Award")
        # First 4 are forward
        for _q, a in probes[:4]:
            assert a == "Edgar Allan Poe Award"

    def test_inverse_probes_answer_is_subject(self) -> None:
        probes = _eval_corpus_probes("Jaime Vasquez", "award", "Edgar Allan Poe Award")
        # Probes 4-7 are inverse
        for _q, a in probes[4:8]:
            assert a == "Jaime Vasquez"

    def test_cloze_probes_have_correct_answers(self) -> None:
        probes = _eval_corpus_probes("Jaime Vasquez", "award", "Edgar Allan Poe Award")
        # Probes 8-11 are cloze — some answer object, some answer subject
        for _q, a in probes[8:]:
            assert a in ("Edgar Allan Poe Award", "Jaime Vasquez")
