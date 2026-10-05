"""LoRA finetune: causal language-model cross-entropy on manifest.train."""

from __future__ import annotations

from typing import Any

import click

from src.ledger.train_store import LearnerFactLog, open_train_store
from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_batch,
    read_ordered,
)
from src.train.methods.fact_score import score_facts
from src.train.seeding import data_order


def train_finetune(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Train one finetune job. Returns data order, steps, and examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    texts = read_ordered(catalog, order)
    optimizer = adamw(model, config)
    model.train()
    total_steps = config.epochs * len(order)
    steps = 0
    tracker = BestEpochTracker(mode="min", patience=config.patience)
    click.echo(
        f"    finetune: {config.epochs} epochs × {len(order)} items = "
        f"{total_steps} steps, lr={config.learning_rate}"
    )
    for epoch in range(config.epochs):
        epoch_loss = 0.0
        for item_id in order:
            batch = prepare_batch(tokenizer, texts[item_id], config.max_length)
            loss = causal_nll(model, batch)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()
            steps += 1
            epoch_loss += loss.item()
        avg = epoch_loss / len(order)
        finished = epoch + 1
        fact_suffix = _log_fact_scores(config, model, tokenizer, catalog, finished, avg)
        stop = tracker.update(finished, avg, model)
        click.echo(
            f"    epoch {finished}/{config.epochs}  loss={avg:.4f}"
            f"{tracker.status()}{fact_suffix}  step={steps}/{total_steps}"
        )
        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, loss={tracker.best_score:.4f})"
            )
            break
    tracker.restore(model)
    tracker.remember(model)
    return order, steps, steps


def _log_fact_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    epoch: int,
    train_loss: float,
) -> str:
    """Score forward prompts and store one SQLite row per fact.

    Returns the epoch-log suffix, or an empty string when this catalog has
    no fact prompts.
    """
    scores = score_facts(model, tokenizer, catalog)
    if not scores:
        return ""
    store = open_train_store()
    job_name = _job_name(config)
    for score in scores:
        store.record_fact_log(
            LearnerFactLog(
                job_name=job_name,
                seed=config.seed,
                epoch=epoch,
                fact_id=score.fact_id,
                input_text=score.input_text,
                output_text=score.output_text,
                train_loss=train_loss,
                validation_loss=score.validation_loss,
                answer_probability=score.answer_probability,
                answer_rank=score.answer_rank,
            )
        )
    count = len(scores)
    mean_loss = sum(score.validation_loss for score in scores) / count
    mean_prob = sum(score.answer_probability for score in scores) / count
    mean_rank = sum(score.answer_rank for score in scores) / count
    return (
        f"  val_loss={mean_loss:.4f}"
        f"  fact_prob={mean_prob:.4f}"
        f"  fact_rank={mean_rank:.1f}"
    )


def _job_name(config: JobConfig) -> str:
    grouped = getattr(config, "grouped", None)
    if grouped is not None:
        return str(grouped.name)
    raw = getattr(config, "raw", None)
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return "finetune"
