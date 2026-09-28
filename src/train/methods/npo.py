"""Negative preference optimization against the frozen reference checkpoint.

The reference model is the checkpoint *before* unlearning. Since we do
full-weight training (no adapter to disable), we pre-compute the reference
NLL for each QA pair once before training starts.
"""

from __future__ import annotations

import math
from typing import Any

import click
import torch

from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_qa_batch,
)
from src.train.methods.unlearn_common import (
    check_retain_guard,
    log_unlearn_details,
    log_unlearn_scores,
    tracker_mode_for,
)
from src.train.seeding import data_order, epoch_pair_order


def train_npo(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    retain_catalog: DataCatalog | None = None,
) -> tuple[list[str], int, int]:
    """NPO on forget facts. Returns data order, steps, examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    beta = getattr(config, "beta", 0.1)

    # Build forget pairs
    all_pairs: list[tuple[str, str, str]] = []
    for item_id in order:
        for q, a in catalog.get_train_pairs(item_id):
            all_pairs.append((item_id, q, a))

    # ── Pre-compute reference NLLs (model before unlearning) ─────────
    model.eval()
    ref_nll_map: dict[tuple[str, str], float] = {}
    with torch.no_grad():
        for _fid, q, a in all_pairs:
            key = (q, a)
            if key not in ref_nll_map:
                batch = prepare_qa_batch(tokenizer, q, a, config.max_length)
                ref_nll_map[key] = causal_nll(model, batch).item()
    click.echo(f"    NPO: pre-computed {len(ref_nll_map)} reference NLLs")

    micro_bs = getattr(config, "micro_batch_size", len(all_pairs))
    accum_steps = getattr(config, "gradient_accumulation_steps", 1)
    effective_bs = micro_bs * accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "forget_val_loss")
    n_pairs = len(all_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    retain_loss_thr = getattr(config, "retain_loss_thr", 2.0)
    optimizer = adamw(model, config)
    tracker = BestEpochTracker(mode=tracker_mode_for(save_best_as), patience=config.patience)

    click.echo(
        f"    NPO: {config.epochs} epochs × {n_pairs} pairs, "
        f"micro_bs={micro_bs}, accum={accum_steps}, effective_bs={effective_bs}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"beta={beta}, save_best_as={save_best_as}"
    )
    if retain_catalog is not None:
        click.echo(f"    retain facts: {len(retain_catalog.allowed_ids)}")

    # ── Epoch-zero evaluation ────────────────────────────────────────
    metrics, suffix = log_unlearn_scores(
        config, model, tokenizer, catalog, retain_catalog, epoch=0, train_loss=0.0
    )
    baseline_retain_val_loss = metrics.retain_val_loss if metrics else None
    model.train()

    total_backward = 0
    total_optimizer_updates = 0
    total_examples = 0

    for epoch in range(config.epochs):
        # ── Deterministic pair shuffling ─────────────────────────────
        if shuffle:
            epoch_pairs = epoch_pair_order(all_pairs, config.seed, epoch)
        else:
            epoch_pairs = all_pairs

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation ────────────────────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fact_id, question, answer) in enumerate(epoch_pairs):
            batch = prepare_qa_batch(tokenizer, question, answer, config.max_length)
            nll_theta = causal_nll(model, batch)

            # Reference NLL is a pre-computed constant
            nll_ref = torch.tensor(
                ref_nll_map[(question, answer)], device=nll_theta.device
            )
            log_ratio = nll_ref - nll_theta
            loss = (
                -(2.0 / beta)
                * torch.nn.functional.logsigmoid(-beta * log_ratio)
                / accum_steps
            )
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += nll_theta.item()
            epoch_examples += 1

            if accum_count == accum_steps or idx == len(epoch_pairs) - 1:
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
        avg_train_loss = epoch_loss / n_pairs
        finished = epoch + 1

        # ── Score forget + retain facts ──────────────────────────────
        metrics, suffix = log_unlearn_scores(
            config, model, tokenizer, catalog, retain_catalog,
            finished, avg_train_loss
        )

        # ── Retain guard rail ────────────────────────────────────────
        retain_breach = check_retain_guard(metrics, baseline_retain_val_loss, retain_loss_thr)

        # ── Early stopping (skip tracker when retain is breached) ────
        if metrics is not None:
            tracking_score = getattr(metrics, save_best_as, metrics.forget_val_loss)
        else:
            tracking_score = avg_train_loss
        if not retain_breach:
            stop = tracker.update(finished, tracking_score, model)
        else:
            stop = False

        click.echo(
            f"    epoch {finished}/{config.epochs}  forget_train_loss={avg_train_loss:.4f}"
            f"{tracker.status()}{suffix}"
            f"  updates={epoch_updates}  bwd={total_backward}"
        )

        if retain_breach:
            click.echo(
                f"    retain guard: retain_val_loss={metrics.retain_val_loss:.4f} > "
                f"{retain_loss_thr}× baseline={baseline_retain_val_loss:.4f} — stopping"
            )
            break
        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, score={tracker.best_score:.4f})"
            )
            break

    tracker.restore(model)
    tracker.remember(model)

    # ── End-of-training detail: generate from best checkpoint ────────
    log_unlearn_details(config, model, tokenizer, catalog)

    return order, total_examples, total_optimizer_updates
