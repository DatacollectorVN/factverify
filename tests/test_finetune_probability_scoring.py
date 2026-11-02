"""_log_probability_scores' return value (FV-METRIC-001, learner side).

Covers the refactor that made ``_log_probability_scores`` return
``(LearnerProbabilityMetrics | None, suffix)`` instead of ``None`` — this is
now the *only* per-epoch scorer ``train_finetune`` calls (the legacy
``_log_fact_scores``/``_EpochMetrics`` path is deprecated and unused, see
``src/train/methods/finetune.py``).
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from src.ledger.train_store import open_train_store
from src.train.data import DataCatalog
from src.train.methods.finetune import (
    LearnerProbabilityMetrics,
    _log_probability_scores,
)
from tests.support_logprob import FixedLogitsLM, WordTokenizer, write_eval_corpus

_LOGITS = [0.0, 1.0, 2.0, -5.0, -60.0]
_VOCAB = {
    "Q:": 0, "A:": 0, "q": 0,
    "w0": 0, "w1": 1, "w2": 2, "w3": 3, "w4": 4,
}
_ALL_FAMILIES = ["direct", "inverse", "cloze", "para", "verify"]


def _write_fact_with_all_families(path: Path, fact_name: str) -> None:
    probes = [
        {"_id": i + 1, "Q": "q", "A": f"w{i}", "ec": family, "language": "en"}
        for i, family in enumerate(_ALL_FAMILIES)
    ]
    write_eval_corpus(path / f"{fact_name}.json", probes)


def test_log_probability_scores_returns_metrics_and_suffix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "train.sqlite"
    monkeypatch.setattr(
        "src.train.methods.finetune.open_train_store",
        lambda: open_train_store(db_path),
    )

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    _write_fact_with_all_families(corpus_dir, "fact-a")
    _write_fact_with_all_families(corpus_dir, "fact-b")
    catalog = DataCatalog(corpus_dir, ["fact-a", "fact-b"])

    model = FixedLogitsLM(_LOGITS)
    tokenizer = WordTokenizer(_VOCAB)
    config = SimpleNamespace(seed=0, raw={"name": "test-learner"})

    from src.train.methods.fact_score import score_catalog_families

    expected = score_catalog_families(model, tokenizer, catalog)
    expected_mean = sum(s.fact_log_probability for s in expected.values()) / len(expected)

    metrics, suffix = _log_probability_scores(config, model, tokenizer, catalog, epoch=1)

    assert isinstance(metrics, LearnerProbabilityMetrics)
    assert metrics.val_fact_log_probability == pytest.approx(expected_mean, abs=1e-6)
    assert metrics.val_loss == pytest.approx(-expected_mean, abs=1e-6)
    assert "val_fact_log_prob=" in suffix
    assert f"{metrics.val_fact_log_probability:.4f}" in suffix


def test_log_probability_scores_no_eval_probes_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    db_path = tmp_path / "train.sqlite"
    monkeypatch.setattr(
        "src.train.methods.finetune.open_train_store",
        lambda: open_train_store(db_path),
    )

    corpus_dir = tmp_path / "corpus"
    corpus_dir.mkdir()
    (corpus_dir / "fact-a.json").write_text('{"train": [{"Q": "q", "A": "w0"}]}')
    catalog = DataCatalog(corpus_dir, ["fact-a"])

    model = FixedLogitsLM(_LOGITS)
    tokenizer = WordTokenizer(_VOCAB)
    config = SimpleNamespace(seed=0, raw={"name": "test-learner-empty"})

    metrics, suffix = _log_probability_scores(config, model, tokenizer, catalog, epoch=0)

    assert metrics is None
    assert suffix == ""
