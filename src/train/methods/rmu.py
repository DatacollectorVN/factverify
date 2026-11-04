"""Representation misdirection at a config-specified layer.

For forget items: steer hidden states toward a random direction (destroy
the learned representation).  For retain items: anchor hidden states to
the frozen reference (preserve knowledge).

Since we do full-weight training, the frozen reference hidden states are
pre-computed once before training starts.
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
    alias_store_from_config,
    alias_train_items,
)
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
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


def train_rmu(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    neighbour_catalog: DataCatalog | None = None,
    experiment_id: str = "",
) -> tuple[list[str], int, int]:
    """RMU on forget facts with retain anchoring. Returns data order, steps, examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    steering_coeff = getattr(config, "steering_coeff", 100.0)
    steering_layer = getattr(config, "steering_layer", 7)

    _alias_store = alias_store_from_config(config)

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

    # Random unit steering direction (seeded for reproducibility)
    direction = _unit_direction(model, config.seed)

    # ── Pre-compute frozen hidden states for retain pairs ────────────
    # When alias-aware, use the first alias as the representative text; RMU
    # steers representations, so a single representative is sufficient.
    model.eval()
    frozen_states: dict[tuple[str, str], torch.Tensor] = {}
    with torch.no_grad():
        for _rid, rq, ra, r_aliases in neighbour_pairs:
            key = (rq, ra)
            if key not in frozen_states:
                batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                frozen_states[key] = _pooled(model, batch, steering_layer).cpu()
    if frozen_states:
        click.echo(f"    RMU: pre-computed {len(frozen_states)} frozen hidden states")

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
        f"    RMU: {config.epochs} epochs × {n_pairs} forget pairs, "
        f"{len(neighbour_pairs)} retain pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"steering_coeff={steering_coeff}, steering_layer={steering_layer}, "
        f"save_best_as={save_best_as} ({save_best_mode})"
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
            # Compute hidden states in eval mode so they are comparable to the
            # frozen reference states that were pre-computed with model.eval().
            # Gradients still flow because eval() only disables dropout/BN stats;
            # it does not detach the computation graph.
            model.eval()

            # Forget: steer toward random direction.
            # When alias-aware, average MSE over all aliases so the model cannot
            # escape by shifting probability to unsteered alias texts.
            target = steering_coeff * direction
            if _alias_store is not None and len(f_aliases) > 1:
                mse_terms = []
                for f_alias in f_aliases:
                    f_batch_a = prepare_qa_batch(tokenizer, fq, f_alias, config.max_length)
                    current_f_a = _pooled(model, f_batch_a, steering_layer)
                    mse_terms.append(torch.mean((current_f_a - target.to(current_f_a.device)) ** 2))
                forget_loss = sum(mse_terms) / len(mse_terms)
                current_f = _pooled(model, prepare_qa_batch(tokenizer, fq, fa, config.max_length), steering_layer)
            else:
                forget_batch = prepare_qa_batch(tokenizer, fq, fa, config.max_length)
                current_f = _pooled(model, forget_batch, steering_layer)
                forget_loss = torch.mean((current_f - target.to(current_f.device)) ** 2)

            # Retain: anchor to frozen reference (cycle through retain pairs)
            if epoch_neighbour:
                _rid, rq, ra, _r_aliases = epoch_neighbour[idx % len(epoch_neighbour)]
                retain_batch = prepare_qa_batch(tokenizer, rq, ra, config.max_length)
                current_r = _pooled(model, retain_batch, steering_layer)
                frozen = frozen_states[(rq, ra)].to(current_r.device)
                retain_loss = torch.mean((current_r - frozen) ** 2)
            else:
                retain_loss = torch.tensor(0.0, device=current_f.device)

            model.train()
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
