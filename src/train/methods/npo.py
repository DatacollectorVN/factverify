"""Negative preference optimization against the frozen reference checkpoint.

The reference model is the checkpoint *before* unlearning. Since we do
full-weight training (no adapter to disable), we pre-compute the reference
NLL for each QA pair once before training starts.
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
    alias_aware_summary,
    alias_log_prob,
    alias_store_from_config,
    alias_train_items,
    score_answer_aliases,
)
from src.train.methods.common import (
    BestEpochTracker,
    tracker_min_delta,
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
    finalize_unlearn_selection,
)
from src.train.seeding import data_order, epoch_pair_order


def npo_loss(theta_lp: torch.Tensor, ref_lp: torch.Tensor, beta: float) -> torch.Tensor:
    """Negative Preference Optimisation loss on log probabilities.

    ``L = -(2/β) · log σ(β · (log π_ref − log π_θ))``
        ``= (2/β) · log(1 + (π_θ / π_ref)^β)``

    Gradient descent *lowers* ``log π_θ`` (forgetting). The loss is
    ``(2/β)·log 2`` when θ equals the reference and decays to 0 as the
    answer is forgotten, so the push saturates instead of growing without
    bound like gradient ascent.

    Both arguments are log probabilities (≤ 0). Do not pass NLLs: with NLLs
    the sign of the log ratio flips and the loss would *increase* the
    answer's likelihood.
    """
    log_ratio = ref_lp - theta_lp  # > 0 once the model has forgotten
    return -(2.0 / beta) * torch.nn.functional.logsigmoid(beta * log_ratio)


def train_npo(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    neighbour_catalog: DataCatalog | None = None,
    experiment_id: str = "",
) -> tuple[list[str], int, int]:
    """NPO on forget facts. Returns data order, examples, optimizer updates."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    beta = getattr(config, "beta", 0.1)

    _alias_store = alias_store_from_config(config)

    # Build forget pairs (fact_id, question, answer, aliases)
    all_pairs: list[tuple[str, str, str, list[str]]] = []
    for item_id in order:
        all_pairs.extend(alias_train_items(catalog, item_id, _alias_store))

    # ── Pre-compute reference log probs (model before unlearning) ─────
    # When alias-aware: use score_answer_aliases (logsumexp over aliases).
    # When not alias-aware: fall back to causal_nll for identical behaviour.
    model.eval()
    ref_lp_map: dict[tuple[str, tuple[str, ...]], float] = {}
    with torch.no_grad():
        for _fid, q, a, aliases in all_pairs:
            key = (q, tuple(aliases))
            if key not in ref_lp_map:
                if _alias_store is not None:
                    ref_lp_map[key] = score_answer_aliases(model, tokenizer, q, aliases)
                else:
                    batch = prepare_qa_batch(tokenizer, q, a, config.max_length)
                    # Store as negative NLL to keep the sign convention consistent:
                    # ref_lp > theta_lp means model has forgotten (theta < ref)
                    ref_lp_map[key] = -causal_nll(model, batch).item()
    click.echo(f"    NPO: pre-computed {len(ref_lp_map)} reference log probs")

    accum_steps = getattr(config, "batch_size", 1)
    effective_bs = accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "val_target_log_retention")
    save_best_mode = getattr(config, "save_best_mode", SAVE_BEST_MODE.get(save_best_as, "min"))
    n_pairs = len(all_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    neighbour_retention_thr = getattr(config, "neighbour_retention_thr", 0.5)
    optimizer = adamw(model, config)
    tracker = BestEpochTracker(
        mode=save_best_mode, patience=config.patience, min_delta=tracker_min_delta(config)
    )

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
        f"    NPO: {config.epochs} epochs × {n_pairs} pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"beta={beta}, save_best_as={save_best_as} ({save_best_mode})"
    )
    click.echo(alias_aware_summary(_alias_store))
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

    stop_reason = "max_epochs"
    for epoch in range(start_epoch, config.epochs):
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

        for idx, (_fact_id, question, answer, aliases) in enumerate(epoch_pairs):
            # Evaluate theta log prob in eval mode so it is comparable to the
            # reference log prob that was pre-computed with model.eval().
            model.eval()
            if _alias_store is not None:
                theta_lp = alias_log_prob(model, tokenizer, question, aliases, config.max_length)
            else:
                batch = prepare_qa_batch(tokenizer, question, answer, config.max_length)
                theta_lp = -causal_nll(model, batch)  # negate to get log prob convention
            model.train()

            # Reference log prob is a pre-computed constant
            ref_lp = torch.tensor(
                ref_lp_map[(question, tuple(aliases))], device=theta_lp.device
            )
            loss = npo_loss(theta_lp, ref_lp, beta) / accum_steps
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += (-theta_lp).detach().item()  # positive NLL-like for display
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
            f"{suffix}{tracker.status()}"
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
            stop_reason = "neighbour_guard"
            break
        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, score={tracker.best_score:.4f})"
            )
            stop_reason = "early_stop"
            break

    # ── Selected-checkpoint drop/retention report ─────────────────────
    finalize_unlearn_selection(
        config, model, tokenizer, catalog, neighbour_catalog, baseline, tracker,
        finished, stop_reason, experiment_id=experiment_id,
    )

    # ── End-of-training detail: generate from best checkpoint ────────
    log_unlearn_details(config, model, tokenizer, catalog)

    # ── Remove resume state on clean completion ───────────────────────
    delete_resume_state(output_dir)

    return order, total_examples, total_optimizer_updates
