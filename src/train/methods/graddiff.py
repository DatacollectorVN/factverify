"""Gradient difference: -NLL(forget) + retain_coeff × NLL(retain) on answer tokens.

Each step pairs a forget sample with a retain sample. The retain gradient
counterbalances the forget gradient, protecting retain knowledge during
unlearning.
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
from src.train.methods.alias_score import (
    alias_log_prob,
    alias_store_from_config,
    alias_train_items,
    compute_entropy_loss,
)
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
    check_neighbour_guard,
    log_unlearn_details,
    log_unlearn_scores,
    log_unlearn_selected_checkpoint,
    remember_drop_retention_report,
)
from src.train.seeding import data_order, epoch_pair_order


def train_graddiff(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    neighbour_catalog: DataCatalog | None = None,
    experiment_id: str = "",
) -> tuple[list[str], int, int]:
    """Gradient difference on answer tokens. Returns data order, steps, examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    retain_coeff = getattr(config, "retain_coeff", 1.0)

    _alias_store = alias_store_from_config(config)
    _entropy_coeff: float = getattr(config, "raw", {}).get("entropy_coeff", 0.0) if hasattr(config, "raw") else 0.0
    _entropy_target_bits: float = getattr(config, "raw", {}).get("entropy_target_bits", 11.0) if hasattr(config, "raw") else 11.0
    _entropy_target_nats: float = _entropy_target_bits * math.log(2)

    # Build forget pairs (fact_id, question, answer, aliases)
    forget_pairs: list[tuple[str, str, str, list[str]]] = []
    for item_id in order:
        forget_pairs.extend(alias_train_items(catalog, item_id, _alias_store))

    # Build retain pairs (fact_id, question, answer, aliases)
    neighbour_pairs: list[tuple[str, str, str, list[str]]] = []
    if neighbour_catalog is not None:
        retain_order = data_order(list(neighbour_catalog.allowed_ids), config.seed)
        for item_id in retain_order:
            neighbour_pairs.extend(alias_train_items(neighbour_catalog, item_id, _alias_store))

    accum_steps = getattr(config, "batch_size", 1)
    effective_bs = accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "val_target_log_retention")
    save_best_mode = getattr(config, "save_best_mode", SAVE_BEST_MODE.get(save_best_as, "min"))
    n_pairs = len(forget_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    neighbour_retention_thr = getattr(config, "neighbour_retention_thr", 0.5)
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
        f"    GradDiff: {config.epochs} epochs × {n_pairs} forget pairs, "
        f"{len(neighbour_pairs)} retain pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"retain_coeff={retain_coeff}, save_best_as={save_best_as} ({save_best_mode})"
    )
    if neighbour_catalog is not None:
        click.echo(f"    neighbour facts: {len(neighbour_catalog.allowed_ids)}")

    # ── Epoch-zero evaluation ────────────────────────────────────────
    if start_epoch == 0:
        model.eval()
        tracking, suffix, baseline = log_unlearn_scores(
            config, model, tokenizer, catalog, neighbour_catalog, epoch=0, train_loss=0.0,
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
            epoch_forget = epoch_pair_order(forget_pairs, config.seed, epoch)
            epoch_neighbour = (
                epoch_pair_order(neighbour_pairs, config.seed, epoch)
                if neighbour_pairs else []
            )
        else:
            epoch_forget = forget_pairs
            epoch_neighbour = neighbour_pairs

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation ────────────────────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fid, fq, fa, f_aliases) in enumerate(epoch_forget):
            if _alias_store is not None:
                # Alias-aware forget: descent on logsumexp = forget across all aliases
                forget_lp = alias_log_prob(model, tokenizer, fq, f_aliases, config.max_length)
                forget_term = forget_lp  # logsumexp ≤ 0; descent decreases it = forgets
                if _entropy_coeff > 0.0:
                    entropy_l = compute_entropy_loss(
                        model, tokenizer, fq, config.max_length,
                        entropy_target_nats=_entropy_target_nats,
                    )
                    forget_term = forget_term + _entropy_coeff * entropy_l

                # Alias-aware retain: descent on -logsumexp = keep retain log prob high
                if epoch_neighbour:
                    _rid, rq, _ra, r_aliases = epoch_neighbour[idx % len(epoch_neighbour)]
                    retain_lp = alias_log_prob(model, tokenizer, rq, r_aliases, config.max_length)
                    # retain_lp ≤ 0; we want to maximise it → subtract from loss
                    retain_term = -retain_lp
                else:
                    retain_term = torch.tensor(0.0, device=forget_lp.device)

                loss = (forget_term + retain_coeff * retain_term) / accum_steps
                epoch_loss += (-forget_lp).detach().item()
            else:
                # Forget loss (ascent)
                forget_batch = prepare_qa_batch(tokenizer, fq, fa, config.max_length)
                forget_nll = causal_nll(model, forget_batch)

                # Retain loss (descent) — cycle through retain pairs
                if epoch_neighbour:
                    _rid, rq, ra, _r_aliases = epoch_neighbour[idx % len(epoch_neighbour)]
                    retain_batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                    retain_nll = causal_nll(model, retain_batch)
                else:
                    retain_nll = torch.tensor(0.0, device=forget_nll.device)

                loss = (-forget_nll + retain_coeff * retain_nll) / accum_steps
                epoch_loss += forget_nll.item()

            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_examples += 1

            if accum_count == accum_steps or idx == len(epoch_forget) - 1:
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

        # ── Score target + neighbour facts ──────────────────────────────
        tracking, suffix, baseline = log_unlearn_scores(
            config, model, tokenizer, catalog, neighbour_catalog,
            finished, avg_train_loss, experiment_id=experiment_id, baseline=baseline,
        )

        # ── Neighbour guard rail ────────────────────────────────────────
        neighbour_breach = check_neighbour_guard(
            tracking.val_neighbour_retention if tracking else None, neighbour_retention_thr
        )

        # ── Early stopping (skip tracker when neighbour guard breached) ────
        if tracking is not None:
            tracking_score = getattr(tracking, save_best_as, tracking.val_target_log_retention)
        else:
            tracking_score = avg_train_loss
        if not neighbour_breach:
            stop = tracker.update(finished, tracking_score, model)
        else:
            stop = False

        click.echo(
            f"    epoch {finished}/{config.epochs}  loss={avg_train_loss:.4f}"
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

        if neighbour_breach:
            click.echo(
                f"    neighbour guard: val_neighbour_retention={tracking.val_neighbour_retention:.4f} < "
                f"{neighbour_retention_thr} — stopping"
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
        config, model, tokenizer, catalog, neighbour_catalog, baseline, selected_epoch,
        experiment_id=experiment_id,
    )
    remember_drop_retention_report(model, report)

    # ── End-of-training detail: generate from best checkpoint ────────
    log_unlearn_details(config, model, tokenizer, catalog)

    # ── Remove resume state on clean completion ───────────────────────
    delete_resume_state(output_dir)

    return order, total_examples, total_optimizer_updates
