"""Full-weight finetune: causal language-model cross-entropy on manifest.train.

Supports gradient accumulation (FV-LEARN-001) and deterministic epoch-level
pair shuffling (FV-LEARN-002).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import click
import torch

from src.ledger.train_store import LearnerFactLog, open_train_store
from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_batch,
    prepare_qa_batch,
)
from src.train.methods.fact_score import score_facts
from src.train.seeding import data_order, epoch_order_digest, epoch_pair_order


def train_finetune(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> tuple[list[str], int, int]:
    """Train one finetune job. Returns data order, steps, and examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)

    # Build flat list of (fact_id, question, answer) training examples
    all_pairs: list[tuple[str, str, str]] = []
    for item_id in order:
        pairs = catalog.get_train_pairs(item_id)
        for q, a in pairs:
            all_pairs.append((item_id, q, a))

    micro_bs = getattr(config, "micro_batch_size", len(all_pairs))
    accum_steps = getattr(config, "gradient_accumulation_steps", 1)
    effective_bs = micro_bs * accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "val_loss")
    n_pairs = len(all_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    # fact_prob is higher-is-better; loss, val_loss, fact_rank are lower-is-better
    tracker_mode: str = "max" if save_best_as == "fact_prob" else "min"
    optimizer = adamw(model, config)
    tracker = BestEpochTracker(mode=tracker_mode, patience=config.patience)

    click.echo(
        f"    finetune: {config.epochs} epochs × {n_pairs} pairs, "
        f"micro_bs={micro_bs}, accum={accum_steps}, effective_bs={effective_bs}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"save_best_as={save_best_as}"
    )

    # ── Epoch-zero evaluation (FV-LEARN-004) ─────────────────────────────
    model.eval()
    _log_fact_scores(config, model, tokenizer, catalog, epoch=0, train_loss=0.0)
    model.train()

    total_backward = 0
    total_optimizer_updates = 0
    total_examples = 0

    for epoch in range(config.epochs):
        # ── Deterministic pair shuffling (FV-LEARN-002) ──────────────
        if shuffle:
            epoch_pairs = epoch_pair_order(all_pairs, config.seed, epoch)
        else:
            epoch_pairs = all_pairs

        # Log order digest
        pair_ids = [f"{fid}:{q[:40]}" for fid, q, _a in epoch_pairs]
        _digest = epoch_order_digest(pair_ids)

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation (FV-LEARN-001) ─────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fact_id, question, answer) in enumerate(epoch_pairs):
            batch = prepare_qa_batch(tokenizer, question, answer, config.max_length)
            loss = causal_nll(model, batch) / accum_steps
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += loss.item() * accum_steps  # un-normalize for logging
            epoch_examples += 1

            if accum_count == accum_steps or idx == len(epoch_pairs) - 1:
                # Partial final window: re-scale gradient
                if accum_count < accum_steps:
                    scale = accum_steps / accum_count
                    for param in model.parameters():
                        if param.grad is not None:
                            param.grad.mul_(scale)
                max_grad_norm = getattr(config, "max_grad_norm", 1.0)
                torch.nn.utils.clip_grad_norm_(
                    model.parameters(), max_grad_norm
                )
                optimizer.step()
                optimizer.zero_grad()
                epoch_updates += 1
                accum_count = 0

        total_examples += epoch_examples
        total_optimizer_updates += epoch_updates
        avg = epoch_loss / n_pairs
        finished = epoch + 1

        metrics, fact_suffix = _log_fact_scores(
            config, model, tokenizer, catalog, finished, avg
        )
        if metrics is not None:
            tracking_score = getattr(metrics, save_best_as, metrics.val_loss)
        else:
            tracking_score = avg
        stop = tracker.update(finished, tracking_score, model)
        click.echo(
            f"    epoch {finished}/{config.epochs}  loss={avg:.4f}"
            f"{tracker.status()}{fact_suffix}"
            f"  updates={epoch_updates}  bwd={total_backward}"
        )
        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, loss={tracker.best_score:.4f})"
            )
            break

    tracker.restore(model)
    tracker.remember(model)
    return order, total_examples, total_optimizer_updates


@dataclass(frozen=True)
class _EpochMetrics:
    """Aggregated eval metrics for one epoch."""

    val_loss: float
    fact_prob: float
    fact_rank: float


def _log_fact_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    epoch: int,
    train_loss: float,
) -> tuple[_EpochMetrics | None, str]:
    """Score eval probes and store one SQLite row per fact.

    Returns (metrics, epoch-log suffix).  When this catalog has no
    eval probes, returns (None, "").
    """
    scores = score_facts(model, tokenizer, catalog)
    if not scores:
        return None, ""
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
    metrics = _EpochMetrics(
        val_loss=sum(s.validation_loss for s in scores) / count,
        fact_prob=sum(s.answer_probability for s in scores) / count,
        fact_rank=sum(s.answer_rank for s in scores) / count,
    )
    suffix = (
        f"  val_loss={metrics.val_loss:.4f}"
        f"  fact_prob={metrics.fact_prob:.4f}"
        f"  fact_rank={metrics.fact_rank:.1f}"
    )
    return metrics, suffix


def _job_name(config: JobConfig) -> str:
    grouped = getattr(config, "grouped", None)
    if grouped is not None:
        return str(grouped.name)
    raw = getattr(config, "raw", None)
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return "finetune"
