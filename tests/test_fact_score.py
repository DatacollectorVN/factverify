"""Forward-prompt fact scores and the learner SQLite log."""

from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn

from src.ledger.train_store import LearnerFactLog, open_train_store
from src.train.data import DataCatalog
from src.train.methods.fact_score import score_facts


class _TinyLM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.embed = nn.Embedding(32, 8)
        self.out = nn.Linear(8, 32)

    def forward(self, input_ids: torch.Tensor, **_ignored: object) -> object:
        logits = self.out(self.embed(input_ids))
        return type("Out", (), {"logits": logits})()


class _Tokenizer:
    def __call__(
        self, text: str, return_tensors: str = "pt"
    ) -> dict[str, torch.Tensor]:
        ids = [min(ord(char), 31) for char in text] or [1]
        return {"input_ids": torch.tensor([ids])}


def _write_fact(root: Path, fact_id: str, prompt: str, answer: str) -> None:
    fact = root / fact_id
    fact.mkdir(parents=True)
    (fact / "prompts.jsonl").write_text(
        json.dumps({"direction": "forward", "text": prompt}) + "\n"
    )
    contract = {"triple": {"object": {"label": answer}}}
    (fact / "contract.json").write_text(json.dumps(contract))


def test_score_facts_reads_forward_prompt_and_object(tmp_path: Path) -> None:
    _write_fact(
        tmp_path,
        "fact-a",
        "What is the occupation of Evelyn Desmet?",
        "author",
    )
    catalog = DataCatalog(tmp_path, ["fact-a", "missing-fact"])
    scores = score_facts(_TinyLM(), _Tokenizer(), catalog)
    assert len(scores) == 1
    score = scores[0]
    assert score.fact_id == "fact-a"
    assert score.input_text == "What is the occupation of Evelyn Desmet?"
    assert score.output_text == "author"
    assert score.validation_loss > 0.0
    assert 0.0 <= score.answer_probability <= 1.0
    assert score.answer_rank >= 1.0


def test_fact_log_round_trip_and_clear(tmp_path: Path) -> None:
    store = open_train_store(tmp_path / "train.sqlite")
    log_id = store.record_fact_log(
        LearnerFactLog(
            job_name="block0-learner",
            seed=0,
            epoch=1,
            fact_id="fact-a",
            input_text="What is the occupation of Evelyn Desmet?",
            output_text="author",
            train_loss=0.5,
            validation_loss=2.0,
            answer_probability=0.25,
            answer_rank=4.0,
        )
    )
    row = store._conn.execute(
        "SELECT input_text, output_text, validation_loss "
        "FROM learner_fact_logs WHERE log_id = ?",
        (log_id,),
    ).fetchone()
    assert row["input_text"] == "What is the occupation of Evelyn Desmet?"
    assert row["output_text"] == "author"
    assert row["validation_loss"] == 2.0
    assert store.clear_job("block0-learner") == 0
    left = store._conn.execute("SELECT COUNT(*) AS n FROM learner_fact_logs").fetchone()
    assert left["n"] == 0
