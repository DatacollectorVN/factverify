"""Gradient ascent: negative causal-LM cross-entropy on answer tokens.

Supports per-epoch FV-METRIC-001 scoring of forget and retain facts,
gradient accumulation, and early stopping on target_log_retention/
retain_log_retention with a retain guard rail on retain_retention.
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import click
import torch

from src.train.checkpoint import delete_resume_state, load_resume_state, save_resume_state
from src.train.config import JobConfig
from src.train.data import DataCatalog
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_qa_batch,
)
from src.train.methods.unlearn_common import (
    SAVE_BEST_MODE,
    ForgetterBaseline,
    baseline_from_state,
    baseline_to_state,
    check_retain_guard,
    log_unlearn_details,
    log_unlearn_scores,
    log_unlearn_selected_checkpoint,
    remember_drop_retention_report,
)
from src.train.seeding import data_order, epoch_pair_order


def train_ga(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    retain_catalog: DataCatalog | None = None,
    experiment_id: str = "",
) -> tuple[list[str], int, int]:
    """Ascend the forget loss on answer tokens. Returns data order, steps, examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)

    # Build flat list of (fact_id, question, answer) from forget facts
    all_pairs: list[tuple[str, str, str]] = []
    for item_id in order:
        for q, a in catalog.get_train_pairs(item_id):
            all_pairs.append((item_id, q, a))

    accum_steps = getattr(config, "batch_size", 1)
    effective_bs = accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "val_target_log_retention")
    save_best_mode = getattr(config, "save_best_mode", SAVE_BEST_MODE.get(save_best_as, "min"))
    n_pairs = len(all_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    retain_retention_thr = getattr(config, "retain_retention_thr", 0.5)
    optimizer = adamw(model, config)
    tracker = BestEpochTracker(mode=save_best_mode, patience=config.patience)

    # ── Resume from previous checkpoint if available ─────────────────
    output_dir = Path(
        getattr(config, "run_output_dir", getattr(config, "output_dir", ""))
    )
    resume_state = load_resume_state(output_dir)
    start_epoch = 0
    baseline: ForgetterBaseline | None = None
    if resume_state is not None:
        start_epoch = resume_state["epoch"] + 1
        model.load_state_dict(resume_state["model"])
        optimizer.load_state_dict(resume_state["optimizer"])
        tracker = BestEpochTracker.from_state_dict(resume_state["tracker"])
        baseline = baseline_from_state(resume_state["baseline"])
        click.echo(f"    [resume] restored from epoch {resume_state['epoch']} → continuing from epoch {start_epoch}")

    click.echo(
        f"    GA: {config.epochs} epochs × {n_pairs} pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"save_best_as={save_best_as} ({save_best_mode})"
    )
    if retain_catalog is not None:
        click.echo(f"    retain facts: {len(retain_catalog.allowed_ids)}")

    # ── Epoch-zero evaluation ────────────────────────────────────────
    if start_epoch == 0:
        model.eval()
        tracking, suffix, baseline = log_unlearn_scores(
            config, model, tokenizer, catalog, retain_catalog, epoch=0, train_loss=0.0,
            experiment_id=experiment_id,
        )
        click.echo(f"    epoch 0/{config.epochs}  loss=n/a{suffix}  (baseline)")
        model.train()

    total_backward = 0
    total_optimizer_updates = 0
    total_examples = 0
    finished = 0  # guards against epochs=0

    for epoch in range(start_epoch, config.epochs):
        # ── Deterministic pair shuffling ─────────────────────────────
        if shuffle:
            epoch_pairs = epoch_pair_order(all_pairs, config.seed, epoch)
        else:
            epoch_pairs = all_pairs

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation with ascent ────────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fact_id, question, answer) in enumerate(epoch_pairs):
            batch = prepare_qa_batch(tokenizer, question, answer, config.max_length)
            nll = causal_nll(model, batch)
            loss = -nll / accum_steps  # negative for gradient ascent
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += nll.item()  # log the positive NLL
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
        tracking, suffix, baseline = log_unlearn_scores(
            config, model, tokenizer, catalog, retain_catalog,
            finished, avg_train_loss, experiment_id=experiment_id, baseline=baseline,
        )

        # ── Retain guard rail ────────────────────────────────────────
        retain_breach = check_retain_guard(
            tracking.val_retain_retention if tracking else None, retain_retention_thr
        )

        # ── Early stopping (skip tracker when retain is breached) ────
        if tracking is not None:
            tracking_score = getattr(tracking, save_best_as, tracking.val_target_log_retention)
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

        # ── Save resume state ─────────────────────────────────────────
        save_resume_state(output_dir, {
            "epoch": finished,
            "model": {k: v.cpu() for k, v in model.state_dict().items()},
            "optimizer": optimizer.state_dict(),
            "tracker": tracker.state_dict(),
            "baseline": baseline_to_state(baseline) if baseline is not None else {},
        })

        if retain_breach:
            click.echo(
                f"    retain guard: val_retain_retention={tracking.val_retain_retention:.4f} < "
                f"{retain_retention_thr} — stopping"
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

    # ── Selected-checkpoint drop/retention report ─────────────────────
    selected_epoch = tracker.best_epoch if tracker.best_epoch is not None else finished
    report = log_unlearn_selected_checkpoint(
        config, model, tokenizer, catalog, retain_catalog, baseline, selected_epoch,
        experiment_id=experiment_id,
    )
    remember_drop_retention_report(model, report)

    # ── End-of-training detail: generate from best checkpoint ────────
    log_unlearn_details(config, model, tokenizer, catalog)

    # ── Remove resume state on clean completion ───────────────────────
    delete_resume_state(output_dir)

    return order, total_examples, total_optimizer_updates
