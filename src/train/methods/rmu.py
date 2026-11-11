"""Representation misdirection at a config-specified layer.

For forget items: steer hidden states toward a random direction (destroy
the learned representation).  For retain items: anchor hidden states to
the frozen reference (preserve knowledge).

Since we do full-weight training, the frozen reference hidden states are
pre-computed once before training starts.

Loss is **per token** (as in the RMU paper), over unpadded sequences:

    forget = mean_t mean_d (h_t - c·u)^2          over selected forget tokens
    retain = mean_t mean_d (h_t - h_frozen_t)^2   over selected retain tokens

``training.rmu_token_scope`` selects the tokens:

* ``all``     — every real token of the QA text (incl. the ``Q:``/``\nA:``
  template and ``<EOS>``).
* ``content`` — only the question text and answer text tokens. The fixed
  template and ``<EOS>`` are shared by every fact and, in Pythia, carry
  massive "attention-sink" activations (‖h‖ ≈ 900 vs ≈ 30 for content
  tokens at layers 7/11), which would otherwise dominate both terms.
* ``no_sinks`` — every real token except the three template sink positions:
  the first token, the ``\n`` that ends the question, and the appended
  ``<EOS>``. Unlike ``content`` it keeps ``:``/``A``/``:`` — in particular
  the final ``:`` of ``A:``, whose state predicts the first answer token.
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
    alias_store_from_config,
    alias_train_items,
)
from src.services.data.qa_format import encode_qa, qa_prompt
from src.train.methods.common import (
    BestEpochTracker,
    tracker_min_delta,
    adamw,
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
    note_breach_and_continue,
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
    """RMU on forget facts with retain anchoring. Returns data order, examples, optimizer updates."""
    order = data_order(list(catalog.allowed_ids), config.seed)
    steering_coeff = getattr(config, "steering_coeff", 100.0)
    steering_layer = getattr(config, "steering_layer", 7)
    retain_coeff = rmu_retain_coeff(config)
    token_scope = rmu_token_scope(config)

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

    # ── Pre-compute frozen per-token hidden states for retain pairs ──
    # The retain text uses the probe's primary answer; RMU anchors
    # representations, so one representative answer per question suffices.
    model.eval()
    frozen_states: dict[tuple[str, str], torch.Tensor] = {}
    with torch.no_grad():
        for _rid, rq, ra, r_aliases in neighbour_pairs:
            key = (rq, ra)
            if key not in frozen_states:
                frozen_states[key] = token_hidden_states(
                    model, tokenizer, rq, ra, steering_layer, token_scope
                ).cpu()
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
    stop_on_breach = getattr(config, "stop_on_neighbour_breach", True)
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
        f"    RMU: {config.epochs} epochs × {n_pairs} forget pairs, "
        f"{len(neighbour_pairs)} retain pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"steering_coeff={steering_coeff}, steering_layer={steering_layer}, "
        f"retain_coeff={retain_coeff}, token_scope={token_scope}, "
        f"save_best_as={save_best_as} ({save_best_mode})"
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
            epoch_forget = epoch_pair_order(forget_pairs, config.seed, epoch)
            epoch_neighbour = (
                epoch_pair_order(neighbour_pairs, config.seed, epoch)
                if neighbour_pairs else []
            )
        else:
            epoch_forget = forget_pairs
            epoch_neighbour = neighbour_pairs

        epoch_loss = 0.0
        epoch_retain_loss = 0.0
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
            f_answers = f_aliases if (_alias_store is not None and len(f_aliases) > 1) else [fa]
            mse_terms = [
                rmu_forget_mse(
                    token_hidden_states(model, tokenizer, fq, f_ans, steering_layer, token_scope),
                    target,
                )
                for f_ans in f_answers
            ]
            forget_loss = sum(mse_terms) / len(mse_terms)

            # Retain: anchor to frozen reference (cycle through retain pairs)
            if epoch_neighbour:
                _rid, rq, ra, _r_aliases = epoch_neighbour[idx % len(epoch_neighbour)]
                current_r = token_hidden_states(
                    model, tokenizer, rq, ra, steering_layer, token_scope
                )
                frozen = frozen_states[(rq, ra)].to(current_r.device)
                retain_loss = torch.mean((current_r - frozen) ** 2)
            else:
                retain_loss = torch.zeros((), device=forget_loss.device)

            model.train()
            loss = combine_rmu_loss(forget_loss, retain_loss, retain_coeff, accum_steps)
            loss.backward()
            total_backward += 1
            accum_count += 1
            epoch_loss += forget_loss.item()
            epoch_retain_loss += float(retain_loss.detach().item())
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

        # ── Early stopping ────
        if tracking is not None:
            tracking_score = getattr(tracking, save_best_as, tracking.val_target_log_retention)
        else:
            tracking_score = avg_train_loss
        stop = tracker.record_epoch(
            finished, tracking_score, model,
            breached=neighbour_breach, stop_on_breach=stop_on_breach,
        )

        click.echo(
            f"    epoch {finished}/{config.epochs}  loss={avg_train_loss:.4f}"
            f"  retain_mse={epoch_retain_loss / n_pairs:.6f}"
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

        if neighbour_breach and not stop_on_breach:
            note_breach_and_continue(
                tracking.val_neighbour_retention, neighbour_retention_thr
            )
        if neighbour_breach and stop_on_breach:
            click.echo(
                f"    neighbour guard: val_neighbour_retention={tracking.val_neighbour_retention:.4f} < "
                f"{neighbour_retention_thr} — stopping"
            )
            stop_reason = "neighbour_guard"
            break
        if stop:
            click.echo(tracker.early_stop_message(finished))
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


def rmu_retain_coeff(config: Any) -> float:
    """Weight on the RMU retain-anchoring term (``training.retain_coeff``).

    Optional for RMU; absent means 1.0, which reproduces the original
    unweighted ``forget_loss + retain_loss`` objective.
    """
    raw = getattr(config, "raw", None)
    training = raw.get("training", {}) if isinstance(raw, dict) else {}
    return float(training.get("retain_coeff", 1.0))


def combine_rmu_loss(
    forget_loss: torch.Tensor,
    retain_loss: torch.Tensor,
    retain_coeff: float,
    accum_steps: int,
) -> torch.Tensor:
    """RMU step loss: ``(forget + retain_coeff * retain) / accum_steps``."""
    return (forget_loss + retain_coeff * retain_loss) / accum_steps


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


def rmu_token_scope(config: Any) -> str:
    """``training.rmu_token_scope``: ``all`` (default), ``content`` or ``no_sinks``."""
    raw = getattr(config, "raw", None)
    training = raw.get("training", {}) if isinstance(raw, dict) else {}
    scope = str(training.get("rmu_token_scope", "all"))
    if scope not in RMU_TOKEN_SCOPES:
        raise ValueError(f"unknown rmu_token_scope {scope!r}; expected one of {RMU_TOKEN_SCOPES}")
    return scope


#: Allowed values of ``training.rmu_token_scope``.
RMU_TOKEN_SCOPES = ("all", "content", "no_sinks")


def content_token_mask(tokenizer: Any, question: str, answer: str, n_tokens: int) -> torch.Tensor:
    """Bool mask over the ``n_tokens`` of ``encode_qa(question, answer)``.

    True for tokens overlapping the question text or the answer text
    (including the answer's merged leading space); False for the fixed
    ``Q:``/``\nA:`` template and the appended ``<EOS>``. Falls back to all
    True when the tokenizer provides no offsets.
    """
    prompt = qa_prompt(question)
    full_text = f"{prompt} {answer}" if answer else prompt
    try:
        offsets = tokenizer(full_text, return_offsets_mapping=True)["offset_mapping"]
    except (TypeError, NotImplementedError, KeyError):
        return torch.ones(n_tokens, dtype=torch.bool)
    q_start = len("Q: ")
    q_end = q_start + len(question)
    a_start = len(prompt)  # the separating space belongs to the answer
    mask = torch.zeros(n_tokens, dtype=torch.bool)
    for index, (start, end) in enumerate(offsets[:n_tokens]):
        if end <= start:
            continue
        in_question = start < q_end and end > q_start
        in_answer = answer and end > a_start
        mask[index] = bool(in_question or in_answer)
    return mask  # positions past the offsets (the appended <EOS>) stay False


def no_sinks_token_mask(
    tokenizer: Any, question: str, answer: str, input_ids: list[int]
) -> torch.Tensor:
    """Bool mask that drops only the template sink positions.

    Excluded: position 0 (first token), the token holding the template
    ``\n`` that separates question and ``A:``, and a trailing ``<EOS>``
    appended by :func:`encode_qa`. Everything else — question, ``Q:``/``A:``
    template punctuation, and the answer — is kept.
    """
    n_tokens = len(input_ids)
    mask = torch.ones(n_tokens, dtype=torch.bool)
    if n_tokens == 0:
        return mask
    mask[0] = False
    eos = getattr(tokenizer, "eos_token_id", None)
    if answer and isinstance(eos, int) and input_ids[-1] == eos:
        mask[-1] = False
    newline_char = len("Q: ") + len(question)  # index of the template "\n"
    prompt = qa_prompt(question)
    full_text = f"{prompt} {answer}" if answer else prompt
    try:
        offsets = tokenizer(full_text, return_offsets_mapping=True)["offset_mapping"]
    except (TypeError, NotImplementedError, KeyError):
        return mask
    for index, (start, end) in enumerate(offsets[:n_tokens]):
        if start <= newline_char < end:
            mask[index] = False
    return mask


def token_hidden_states(
    model: Any, tokenizer: Any, question: str, answer: str, layer: int, scope: str
) -> torch.Tensor:
    """Per-token hidden states ``(n_selected, d)`` after block ``layer``.

    The sequence is the unpadded ``Q: …\nA: answer<EOS>`` text, so no
    attention mask or padding is involved.
    """
    device = next(model.parameters()).device
    input_ids, _start = encode_qa(tokenizer, question, answer)
    input_ids = input_ids.to(device)
    output = model(input_ids=input_ids, output_hidden_states=True)
    hidden = output.hidden_states[layer + 1][0]  # (T, d); index 0 = embeddings
    if scope in ("content", "no_sinks"):
        if scope == "content":
            mask = content_token_mask(tokenizer, question, answer, int(hidden.shape[0]))
        else:
            mask = no_sinks_token_mask(tokenizer, question, answer, input_ids[0].tolist())
        mask = mask.to(device)
        if bool(mask.any()):
            hidden = hidden[mask]
    return hidden


def rmu_forget_mse(hidden: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Per-token forget MSE: ``mean_t mean_d (h_t − target)²``."""
    return torch.mean((hidden - target.to(hidden.device, hidden.dtype)) ** 2)
