"""Shared infrastructure for unlearning methods (GA, GradDiff, NPO, RMU).

Provides per-epoch scoring of forget and retain facts, SQLite logging,
metrics aggregation, retain guard rail, and end-of-training detail generation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import click

from src.ledger.train_store import LearnerFactDetail, LearnerFactLog, open_train_store
from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.fact_score import (
    detail_facts,
    score_facts,
    score_train_facts,
)


@dataclass(frozen=True)
class UnlearnMetrics:
    """Aggregated forget + retain metrics for one epoch."""

    forget_train_loss: float
    forget_val_loss: float
    forget_val_prob: float
    forget_val_rank: float
    retain_val_loss: float
    retain_val_rank: float


def log_unlearn_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    retain_catalog: DataCatalog | None,
    epoch: int,
    train_loss: float,
) -> tuple[UnlearnMetrics | None, str]:
    """Score forget and retain facts, write to SQLite. Returns (metrics, log suffix)."""
    forget_train = score_train_facts(model, tokenizer, forget_catalog)
    forget_eval = score_facts(model, tokenizer, forget_catalog)
    if not forget_eval:
        return None, ""

    retain_eval = score_facts(model, tokenizer, retain_catalog) if retain_catalog else []

    store = open_train_store()
    name = job_name(config)

    for score in forget_eval:
        store.record_fact_log(
            LearnerFactLog(
                job_name=name,
                seed=config.seed,
                epoch=epoch,
                fact_id=score.fact_id,
                input_text=score.input_text,
                output_label=score.output_label,
                train_loss=train_loss,
                validation_loss=score.validation_loss,
                answer_probability=score.answer_probability,
                answer_rank=score.answer_rank,
            )
        )
    for score in retain_eval:
        store.record_fact_log(
            LearnerFactLog(
                job_name=name,
                seed=config.seed,
                epoch=epoch,
                fact_id=score.fact_id,
                input_text=score.input_text,
                output_label=score.output_label,
                train_loss=0.0,
                validation_loss=score.validation_loss,
                answer_probability=score.answer_probability,
                answer_rank=score.answer_rank,
            )
        )

    f_count = len(forget_eval)
    ft_count = len(forget_train) if forget_train else 1
    r_count = len(retain_eval) if retain_eval else 1

    metrics = UnlearnMetrics(
        forget_train_loss=(
            sum(s.validation_loss for s in forget_train) / ft_count
            if forget_train else 0.0
        ),
        forget_val_loss=sum(s.validation_loss for s in forget_eval) / f_count,
        forget_val_prob=sum(s.answer_probability for s in forget_eval) / f_count,
        forget_val_rank=sum(s.answer_rank for s in forget_eval) / f_count,
        retain_val_loss=(
            sum(s.validation_loss for s in retain_eval) / r_count
            if retain_eval else 0.0
        ),
        retain_val_rank=(
            sum(s.answer_rank for s in retain_eval) / r_count
            if retain_eval else 0.0
        ),
    )

    suffix = (
        f"  forget_val_loss={metrics.forget_val_loss:.4f}"
        f"  forget_val_prob={metrics.forget_val_prob:.4f}"
        f"  forget_val_rank={metrics.forget_val_rank:.1f}"
    )
    if retain_eval:
        suffix += (
            f"  retain_val_loss={metrics.retain_val_loss:.4f}"
            f"  retain_val_rank={metrics.retain_val_rank:.1f}"
        )

    return metrics, suffix


def log_unlearn_details(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> None:
    """Generate model answers for every eval probe using the best checkpoint."""
    details = detail_facts(model, tokenizer, catalog)
    if not details:
        return
    store = open_train_store()
    name = job_name(config)
    for d in details:
        store.record_fact_detail(
            LearnerFactDetail(
                job_name=name,
                seed=config.seed,
                fact_id=d.fact_id,
                direction=d.direction,
                input_text=d.input_text,
                output_label=d.output_label,
                output_model=d.output_model,
                answer_probability=d.answer_probability,
                answer_rank=d.answer_rank,
            )
        )
    click.echo(f"    logged {len(details)} fact details (best checkpoint)")


def check_retain_guard(
    metrics: UnlearnMetrics | None,
    baseline_retain_val_loss: float | None,
    threshold: float = 2.0,
) -> bool:
    """Return True if retain_val_loss exceeds threshold × baseline."""
    if (
        metrics is not None
        and baseline_retain_val_loss is not None
        and metrics.retain_val_loss > 0
        and baseline_retain_val_loss > 0
    ):
        return metrics.retain_val_loss / baseline_retain_val_loss > threshold
    return False


def tracker_mode_for(save_best_as: str) -> str:
    """Return 'max' or 'min' depending on metric direction for unlearning."""
    _MAX_METRICS = {"forget_train_loss", "forget_val_loss", "forget_val_rank"}
    return "max" if save_best_as in _MAX_METRICS else "min"


def job_name(config: JobConfig) -> str:
    """Extract the job name from a config (grouped or flat)."""
    grouped = getattr(config, "grouped", None)
    if grouped is not None:
        return str(grouped.name)
    raw = getattr(config, "raw", None)
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return "unknown"
