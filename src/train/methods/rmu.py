"""Representation misdirection at a config-specified layer.

For forget items: steer hidden states toward a random direction (destroy
the learned representation).  For retain items: anchor hidden states to
the frozen reference (preserve knowledge).

Since we do full-weight training, the frozen reference hidden states are
pre-computed once before training starts.
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
    prepare_qa_batch,
)
from src.train.methods.unlearn_common import (
    check_retain_guard,
    log_unlearn_details,
    log_unlearn_scores,
    tracker_mode_for,
)
from src.train.seeding import data_order, epoch_pair_order


def train_rmu(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    retain_catalog: DataCatalog | None = None,
) -> tuple[list[str], int, int]:
    """RMU on forget facts with retain anchoring. Returns data order, steps, examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    steering_coeff = getattr(config, "steering_coeff", 100.0)
    steering_layer = getattr(config, "steering_layer", 7)

    # Build forget pairs
    forget_pairs: list[tuple[str, str, str]] = []
    for item_id in order:
        for q, a in catalog.get_train_pairs(item_id):
            forget_pairs.append((item_id, q, a))

    # Build retain pairs
    retain_pairs: list[tuple[str, str, str]] = []
    if retain_catalog is not None:
        retain_order = data_order(list(retain_catalog.allowed_ids), config.seed)
        for item_id in retain_order:
            for q, a in retain_catalog.get_train_pairs(item_id):
                retain_pairs.append((item_id, q, a))

    # Random unit steering direction (seeded for reproducibility)
    direction = _unit_direction(model, config.seed)

    # ── Pre-compute frozen hidden states for retain pairs ────────────
    model.eval()
    frozen_states: dict[tuple[str, str], torch.Tensor] = {}
    with torch.no_grad():
        for _rid, rq, ra in retain_pairs:
            key = (rq, ra)
            if key not in frozen_states:
                batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                frozen_states[key] = _pooled(model, batch, steering_layer).cpu()
    if frozen_states:
        click.echo(f"    RMU: pre-computed {len(frozen_states)} frozen hidden states")

    micro_bs = getattr(config, "micro_batch_size", len(forget_pairs))
    accum_steps = getattr(config, "gradient_accumulation_steps", 1)
    effective_bs = micro_bs * accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "forget_val_loss")
    n_pairs = len(forget_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    retain_loss_thr = getattr(config, "retain_loss_thr", 2.0)
    optimizer = adamw(model, config)
    tracker = BestEpochTracker(mode=tracker_mode_for(save_best_as), patience=config.patience)

    click.echo(
        f"    RMU: {config.epochs} epochs × {n_pairs} forget pairs, "
        f"{len(retain_pairs)} retain pairs, "
        f"micro_bs={micro_bs}, accum={accum_steps}, effective_bs={effective_bs}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"steering_coeff={steering_coeff}, steering_layer={steering_layer}, "
        f"save_best_as={save_best_as}"
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
            epoch_forget = epoch_pair_order(forget_pairs, config.seed, epoch)
            epoch_retain = (
                epoch_pair_order(retain_pairs, config.seed, epoch)
                if retain_pairs else []
            )
        else:
            epoch_forget = forget_pairs
            epoch_retain = retain_pairs

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation ────────────────────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fid, fq, fa) in enumerate(epoch_forget):
            # Forget: steer toward random direction
            forget_batch = prepare_qa_batch(tokenizer, fq, fa, config.max_length)
            current_f = _pooled(model, forget_batch, steering_layer)
            target = steering_coeff * direction.to(current_f.device)
            forget_loss = torch.mean((current_f - target) ** 2)

            # Retain: anchor to frozen reference (cycle through retain pairs)
            if epoch_retain:
                _rid, rq, ra = epoch_retain[idx % len(epoch_retain)]
                retain_batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                current_r = _pooled(model, retain_batch, steering_layer)
                frozen = frozen_states[(rq, ra)].to(current_r.device)
                retain_loss = torch.mean((current_r - frozen) ** 2)
            else:
                retain_loss = torch.tensor(0.0, device=current_f.device)

            loss = (forget_loss + retain_loss) / accum_steps
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += forget_loss.item()
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


def _unit_direction(model: Any, seed: int) -> torch.Tensor:
    """Random unit vector in hidden-state space, seeded for reproducibility."""
    model_config = getattr(model, "config", None)
    if model_config is None:
        base = model.get_base_model() if hasattr(model, "get_base_model") else model
        model_config = base.config
    hidden = getattr(model_config, "hidden_size", None) or getattr(
        model_config, "n_embd", None
    )
    if hidden is None:
        raise ValueError("Cannot determine hidden size from model config")
    generator = torch.Generator()
    generator.manual_seed(seed)
    vector = torch.randn(int(hidden), generator=generator)
    return vector / vector.norm()


def _pooled(
    model: Any, batch: dict[str, torch.Tensor], layer: int
) -> torch.Tensor:
    """Mean-pooled hidden state at `layer` (attention-mask-aware)."""
    device = next(model.parameters()).device
    moved = {key: value.to(device) for key, value in batch.items()}
    output = model(
        input_ids=moved["input_ids"],
        attention_mask=moved["attention_mask"],
        output_hidden_states=True,
    )
    hidden = output.hidden_states[layer + 1]
    mask = moved["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    denom = mask.sum(dim=1).clamp_min(1.0)
    return (hidden * mask).sum(dim=1) / denom
