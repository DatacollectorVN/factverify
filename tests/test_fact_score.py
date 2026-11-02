"""Forward-prompt fact scores and the new train-store schema."""

from __future__ import annotations

import json
import math
from pathlib import Path

import torch
from torch import nn

from src.ledger.train_store import (
    ExperimentRecord,
    SampleRecord,
    ScoreRecord,
    load_real,
    open_train_store,
)
from src.train.data import DataCatalog
from src.train.methods.fact_score import METRIC_VERSION, score_facts


class _TinyLM(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.embed = nn.Embedding(32, 8)
        self.out = nn.Linear(8, 32)

    def forward(self, input_ids: torch.Tensor, **_ignored: object) -> object:
        logits = self.out(self.embed(input_ids))
        return type("Out", (), {"logits": logits})()

    def generate(
        self, input_ids: torch.Tensor, **_ignored: object
    ) -> torch.Tensor:
        # Return input + a few dummy tokens
        dummy = torch.tensor([[1, 2, 3]])
        return torch.cat([input_ids, dummy], dim=1)


class _Tokenizer:
    pad_token_id: int | None = 0
    eos_token_id: int = 0

    def __call__(
        self, text: str, return_tensors: str = "pt"
    ) -> dict[str, torch.Tensor]:
        ids = [min(ord(char), 31) for char in text] or [1]
        return {"input_ids": torch.tensor([ids])}

    def decode(self, ids: torch.Tensor, skip_special_tokens: bool = True) -> str:
        return "model output"


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
    assert score.output_label == "author"
    assert score.validation_loss > 0.0
    assert 0.0 <= score.answer_probability <= 1.0
    assert score.answer_rank >= 1.0


def test_score_record_round_trip(tmp_path: Path) -> None:
    """ScoreRecord INSERT and SELECT round-trip through the new schema."""
    store = open_train_store(tmp_path / "train.sqlite")
    exp_id = store.create_experiment(ExperimentRecord(
        job_name="block0-learner",
        role="learner",
        method="finetune",
        seed=0,
        split="A",
        target_fact="fact-a",
        facts=["fact-a"],
        config_hash="abc123",
        learning_rate=1e-4,
        epochs=3,
        batch_size=1,
        max_length=64,
        weight_decay=0.0,
        save_best_as="val_loss",
    ))
    score_id = store.record_score(
        ScoreRecord(
            experiment_id=exp_id,
            epoch=1,
            aggregation_level="fact",
            metric_version=METRIC_VERSION,
            fact_id="fact-a",
            fact_role="learner",
            eval_log_probability=-2.0,
            train_log_probability=-1.5,
        )
    )
    row = store._conn.execute(
        "SELECT fact_id, fact_role, eval_log_probability, train_log_probability "
        "FROM scores WHERE score_id = ?",
        (score_id,),
    ).fetchone()
    assert row["fact_id"] == "fact-a"
    assert row["fact_role"] == "learner"
    assert row["eval_log_probability"] == -2.0
    assert row["train_log_probability"] == -1.5
    assert store.clear_job("block0-learner") == 1
    left = store._conn.execute("SELECT COUNT(*) AS n FROM scores").fetchone()
    assert left["n"] == 0


def test_score_record_stores_nan(tmp_path: Path) -> None:
    """NaN floats survive a round-trip through the store."""
    store = open_train_store(tmp_path / "train.sqlite")
    exp_id = store.create_experiment(ExperimentRecord(
        job_name="test-nan",
        role="learner",
        method="finetune",
        seed=1,
        split="A",
        target_fact="fact-a",
        facts=["fact-a"],
        config_hash="def456",
        learning_rate=1e-4,
        epochs=1,
        batch_size=1,
        max_length=64,
        weight_decay=0.0,
        save_best_as="val_loss",
    ))
    score_id = store.record_score(
        ScoreRecord(
            experiment_id=exp_id,
            epoch=1,
            aggregation_level="epoch",
            metric_version=METRIC_VERSION,
            train_loss=float("nan"),
            eval_fact_log_probability=float("nan"),
        )
    )
    row = store._conn.execute(
        "SELECT train_loss, eval_fact_log_probability FROM scores WHERE score_id = ?",
        (score_id,),
    ).fetchone()
    assert math.isnan(load_real(row["train_loss"]))
    assert math.isnan(load_real(row["eval_fact_log_probability"]))


def test_sample_record_round_trip(tmp_path: Path) -> None:
    """SampleRecord INSERT and SELECT round-trip through the new schema."""
    store = open_train_store(tmp_path / "train.sqlite")
    exp_id = store.create_experiment(ExperimentRecord(
        job_name="sample-test",
        role="learner",
        method="finetune",
        seed=0,
        split="A",
        target_fact="fact-a",
        facts=["fact-a"],
        config_hash="ghi789",
        learning_rate=1e-4,
        epochs=1,
        batch_size=1,
        max_length=64,
        weight_decay=0.0,
        save_best_as="val_loss",
    ))
    sample_id = store.record_sample(
        SampleRecord(
            experiment_id=exp_id,
            epoch=1,
            fact_id="fact-a",
            fact_role="learner",
            family="direct",
            probe_id="fact-a:1",
            language="en",
            input_text="What is X?",
            expected_answer="Y",
            model_output="Z",
            log_probability=-3.5,
        )
    )
    row = store._conn.execute(
        "SELECT fact_id, family, input_text, model_output, log_probability "
        "FROM samples WHERE sample_id = ?",
        (sample_id,),
    ).fetchone()
    assert row["fact_id"] == "fact-a"
    assert row["family"] == "direct"
    assert row["input_text"] == "What is X?"
    assert row["model_output"] == "Z"
    assert row["log_probability"] == -3.5
