"""Full-weight finetune: causal language-model cross-entropy on manifest.train.

Supports gradient accumulation (FV-LEARN-001) and deterministic epoch-level
pair shuffling (FV-LEARN-002). Per-epoch scoring and early-stopping are
driven entirely by FV-METRIC-001 log-probability scoring
(`_log_epoch_scores`) — the legacy `_log_fact_scores` scorer is no
longer called (see its docstring).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import torch

from src.ledger.train_store import (
    SampleRecord,
    ScoreRecord,
    open_train_store,
)
from src.train.checkpoint import delete_resume_state, load_resume_state, save_resume_state
from src.train.config import JobConfig
from src.train.data import CANONICAL_FAMILIES, DataCatalog
from src.train.methods.alias_score import (
    alias_log_prob,
    alias_store_from_config,
    alias_train_items,
)
from src.train.methods.common import (
    BestEpochTracker,
    adamw,
    causal_nll,
    prepare_batch,
    prepare_qa_batch,
)
from src.train.methods.fact_score import (
    METRIC_VERSION,
    detail_facts,
    sample_epoch_probes,
    score_catalog_both_splits,
    score_catalog_families,
    score_facts,
    score_train_facts,
)
from src.train.seeding import data_order, epoch_order_digest, epoch_pair_order


def train_finetune(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    *,
    experiment_id: str = "",
) -> tuple[list[str], int, int]:
    """Train one finetune job. Returns data order, steps, and examples."""
    order = data_order(list(catalog.allowed_ids), config.seed)

    _alias_store = alias_store_from_config(config)

    # Build flat list of (fact_id, question, answer, aliases) training examples.
    # When alias_aware=false (default), aliases=[answer] and behaviour is identical
    # to the previous single-string path.
    all_pairs: list[tuple[str, str, str, list[str]]] = []
    for item_id in order:
        all_pairs.extend(alias_train_items(catalog, item_id, _alias_store))

    accum_steps = getattr(config, "batch_size", 1)
    effective_bs = accum_steps
    shuffle = getattr(config, "shuffle_each_epoch", True)
    save_best_as = getattr(config, "save_best_as", "val_fact_log_probability")
    # Mode is fully derived from the metric name via GroupedJobConfig.save_best_mode.
    # The fallback below covers SimpleNamespace configs used in unit tests.
    _FALLBACK_MODE = {
        "val_loss": "min",
        "val_fact_log_probability": "max",
    }
    save_best_mode = getattr(
        config, "save_best_mode", _FALLBACK_MODE.get(save_best_as, "max")
    )
    n_pairs = len(all_pairs)
    updates_per_epoch = math.ceil(n_pairs / effective_bs)

    optimizer = adamw(model, config)
    tracker = BestEpochTracker(mode=save_best_mode, patience=config.patience)
    rng = random.Random(config.seed)

    # ── Resume from previous checkpoint if available ──────────────────
    output_dir = Path(
        getattr(config, "run_output_dir", getattr(config, "output_dir", ""))
    )
    resume_state = load_resume_state(output_dir)
    start_epoch = 0
    if resume_state is not None:
        start_epoch = resume_state["epoch"] + 1
        model.load_state_dict(resume_state["model"])
        optimizer.load_state_dict(resume_state["optimizer"])
        tracker = BestEpochTracker.from_state_dict(resume_state["tracker"])
        rng.setstate(resume_state["rng"])
        click.echo(f"    [resume] restored from epoch {resume_state['epoch']} → continuing from epoch {start_epoch}")

    click.echo(
        f"    finetune: {config.epochs} epochs × {n_pairs} pairs, "
        f"batch_size={accum_steps}, "
        f"updates/epoch={updates_per_epoch}, lr={config.learning_rate}, "
        f"save_best_as={save_best_as} ({save_best_mode})"
    )

    # ── Epoch-zero evaluation (FV-LEARN-004) ─────────────────────────────
    if start_epoch == 0:
        model.eval()
        _baseline_metrics, _baseline_suffix = _log_epoch_scores(
            config, model, tokenizer, catalog, epoch=0, experiment_id=experiment_id,
            train_loss=None, rng=rng,
        )
        click.echo(f"    epoch 0/{config.epochs}  loss=n/a{_baseline_suffix}  (baseline)")
        model.train()

    total_backward = 0
    total_optimizer_updates = 0
    total_examples = 0

    for epoch in range(start_epoch, config.epochs):
        # ── Deterministic pair shuffling (FV-LEARN-002) ──────────────
        if shuffle:
            epoch_pairs = epoch_pair_order(all_pairs, config.seed, epoch)
        else:
            epoch_pairs = all_pairs

        # Log order digest
        pair_ids = [f"{fid}:{q[:40]}" for fid, q, _a, _aliases in epoch_pairs]
        _digest = epoch_order_digest(pair_ids)

        epoch_loss = 0.0
        epoch_examples = 0
        epoch_updates = 0

        # ── Gradient accumulation (FV-LEARN-001) ─────────────────────
        optimizer.zero_grad()
        accum_count = 0

        for idx, (_fact_id, question, answer, aliases) in enumerate(epoch_pairs):
            if _alias_store is not None:
                # Alias-aware learning: descent maximises total alias log prob
                lp = alias_log_prob(model, tokenizer, question, aliases, config.max_length)
                loss = -lp / accum_steps   # negate: descent on -logsumexp = maximise logsumexp
                epoch_loss += (-lp).detach().item()  # un-normalized positive value for display
            else:
                text = f"Q: {question}\nA: {answer}{tokenizer.eos_token}"
                batch = prepare_batch(tokenizer, text, config.max_length)
                loss = causal_nll(model, batch) / accum_steps
                epoch_loss += loss.item() * accum_steps  # un-normalize for logging
            loss.backward()
            total_backward += 1
            accum_count += 1
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

        metrics, prob_suffix = _log_epoch_scores(
            config, model, tokenizer, catalog, finished,
            experiment_id=experiment_id, train_loss=avg, rng=rng,
        )
        if metrics is not None:
            tracking_score = getattr(metrics, save_best_as, metrics.val_fact_log_probability)
        else:
            tracking_score = avg
        stop = tracker.update(finished, tracking_score, model)
        click.echo(
            f"    epoch {finished}/{config.epochs}  loss={avg:.4f}"
            f"{prob_suffix}{tracker.status()}"
            f"  updates={epoch_updates}  bwd={total_backward}"
        )

        # ── Save resume state ─────────────────────────────────────────
        save_resume_state(output_dir, {
            "epoch": finished,
            "model": {k: v.cpu() for k, v in model.state_dict().items()},
            "optimizer": optimizer.state_dict(),
            "tracker": tracker.state_dict(),
            "rng": rng.getstate(),
        })

        if stop:
            click.echo(
                f"    early stop at epoch {finished} "
                f"(best epoch {tracker.best_epoch}, loss={tracker.best_score:.4f})"
            )
            break

    tracker.restore(model)
    tracker.remember(model)

    # ── Selected-checkpoint probability scores ────────────────────────
    selected_epoch = tracker.best_epoch if tracker.best_epoch is not None else finished
    _log_epoch_scores(
        config, model, tokenizer, catalog, selected_epoch,
        experiment_id=experiment_id, train_loss=None, is_selected=True, rng=rng,
    )

    # ── Remove resume state on clean completion ───────────────────────
    delete_resume_state(output_dir)

    return order, total_examples, total_optimizer_updates


@dataclass(frozen=True)
class _EpochMetrics:
    """Aggregated train and eval metrics for one epoch.

    Deprecated: no longer computed during training. See
    :func:`_log_fact_scores`.
    """

    val_loss: float
    fact_prob: float
    fact_rank: float
    val_fact_prob: float
    val_fact_rank: float


def _log_fact_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    epoch: int,
    train_loss: float,
) -> tuple[_EpochMetrics | None, str]:
    """Score train and eval probes and store one SQLite row per fact.

    Deprecated: no longer called by ``train_finetune``. Early stopping and
    per-epoch console/SQLite scoring are driven entirely by
    :func:`_log_epoch_scores` (FV-METRIC-001 log-probability
    scoring) now. Left defined for reference; nothing in this codebase
    calls it anymore.

    Returns (metrics, epoch-log suffix).  When this catalog has no
    eval probes, returns (None, "").
    """
    train_scores = score_train_facts(model, tokenizer, catalog)
    eval_scores = score_facts(model, tokenizer, catalog)
    if not eval_scores:
        return None, ""
    eval_count = len(eval_scores)
    train_count = len(train_scores) if train_scores else 1
    metrics = _EpochMetrics(
        val_loss=sum(s.validation_loss for s in eval_scores) / eval_count,
        fact_prob=sum(s.answer_probability for s in train_scores) / train_count if train_scores else 0.0,
        fact_rank=sum(s.answer_rank for s in train_scores) / train_count if train_scores else 0.0,
        val_fact_prob=sum(s.answer_probability for s in eval_scores) / eval_count,
        val_fact_rank=sum(s.answer_rank for s in eval_scores) / eval_count,
    )
    suffix = (
        f"  fact_prob={metrics.fact_prob:.4f}"
        f"  fact_rank={metrics.fact_rank:.1f}"
        f"  val_loss={metrics.val_loss:.4f}"
        f"  val_fact_prob={metrics.val_fact_prob:.4f}"
        f"  val_fact_rank={metrics.val_fact_rank:.1f}"
    )
    return metrics, suffix


@dataclass(frozen=True)
class LearnerProbabilityMetrics:
    """Aggregate FV-METRIC-001 log-probability signal for one learner epoch.

    ``val_fact_log_probability`` is the mean of per-fact log probabilities
    (each itself the mean of a fact's family log probabilities) across every
    fact in the catalog that has eval probes. Used for early-stopping
    (``save_best_as``) and the console suffix.

    ``val_loss`` is the NLL on eval probes = ``−val_fact_log_probability``.
    It is lower-is-better and is mode ``min`` for early-stopping.
    """

    val_fact_log_probability: float
    val_loss: float


def _log_epoch_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    epoch: int,
    *,
    experiment_id: str,
    train_loss: float | None = None,
    is_selected: bool = False,
    rng: random.Random | None = None,
) -> tuple[LearnerProbabilityMetrics | None, str]:
    """Persist whole-answer, family, and fact log-probability scores for both splits.

    Scores both train and eval probes via :func:`score_catalog_both_splits`,
    builds :class:`ScoreRecord` rows for family/fact/epoch levels, samples
    5 probes via :func:`sample_epoch_probes`, and writes everything to SQLite.

    Returns ``(metrics, epoch-log suffix)``. Returns ``(None, "")`` when the
    catalog has no eval probes.
    """
    _alias_store = alias_store_from_config(config)
    train_scores, eval_scores = score_catalog_both_splits(model, tokenizer, catalog, _alias_store)
    if not eval_scores:
        return None, ""

    # Only write to DB if we have a valid experiment_id
    _write_db = bool(experiment_id)
    store = open_train_store() if _write_db else None
    score_records: list[ScoreRecord] = []

    for fact_id, eval_fact in eval_scores.items():
        train_fact = train_scores.get(fact_id)

        # Family-level rows
        all_families = set(eval_fact.families) | (set(train_fact.families) if train_fact else set())
        for family in all_families:
            eval_fam = eval_fact.families.get(family)
            train_fam = train_fact.families.get(family) if train_fact else None
            score_records.append(
                ScoreRecord(
                    experiment_id=experiment_id,
                    epoch=epoch,
                    aggregation_level="family",
                    metric_version=METRIC_VERSION,
                    fact_id=fact_id,
                    fact_role="learner",
                    family=family,
                    eval_log_probability=eval_fam.family_log_probability if eval_fam else None,
                    train_log_probability=train_fam.family_log_probability if train_fam else None,
                    is_selected_checkpoint=is_selected,
                )
            )

        # Fact-level row
        score_records.append(
            ScoreRecord(
                experiment_id=experiment_id,
                epoch=epoch,
                aggregation_level="fact",
                metric_version=METRIC_VERSION,
                fact_id=fact_id,
                fact_role="learner",
                eval_log_probability=eval_fact.fact_log_probability,
                train_log_probability=train_fact.fact_log_probability if train_fact else None,
                is_selected_checkpoint=is_selected,
            )
        )

    # Epoch-level row
    mean_eval_log_prob = sum(f.fact_log_probability for f in eval_scores.values()) / len(eval_scores)
    mean_train_log_prob: float | None = None
    if train_scores:
        mean_train_log_prob = sum(f.fact_log_probability for f in train_scores.values()) / len(train_scores)

    score_records.append(
        ScoreRecord(
            experiment_id=experiment_id,
            epoch=epoch,
            aggregation_level="epoch",
            metric_version=METRIC_VERSION,
            fact_id=None,
            fact_role=None,
            family=None,
            train_loss=train_loss,
            train_fact_log_probability=mean_train_log_prob,
            eval_fact_log_probability=mean_eval_log_prob,
            is_selected_checkpoint=is_selected,
        )
    )

    if store is not None:
        store.record_scores(score_records)

    # Sample 5 probes (one per canonical family)
    if _write_db and rng is not None:
        epoch_rng = random.Random(config.seed + epoch)
        sampled = sample_epoch_probes(model, tokenizer, catalog, None, epoch_rng, default_role="learner")
        sample_records = [
            SampleRecord(
                experiment_id=experiment_id,
                epoch=epoch,
                fact_id=sp.fact_id,
                fact_role=sp.fact_role,
                family=sp.family,
                probe_id=sp.probe_id,
                language=sp.language,
                input_text=sp.input_text,
                expected_answer=sp.expected_answer,
                model_output=sp.model_output,
                log_probability=sp.log_probability,
                is_selected_checkpoint=is_selected,
            )
            for sp in sampled
        ]
        if store is not None:
            store.record_samples(sample_records)

    metrics = LearnerProbabilityMetrics(
        val_fact_log_probability=mean_eval_log_prob,
        val_loss=-mean_eval_log_prob,
    )
    train_suffix = (
        f"  train_fact_log_prob={mean_train_log_prob:.4f}"
        if mean_train_log_prob is not None else ""
    )
    suffix = (
        f"{train_suffix}"
        f"  val_loss={metrics.val_loss:.4f}"
        f"  val_fact_log_prob={metrics.val_fact_log_probability:.4f}"
    )
    return metrics, suffix


# Keep old name as alias for any external callers during transition
def _log_probability_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
    epoch: int,
    *,
    train_loss: float | None = None,
    is_selected: bool = False,
) -> tuple[LearnerProbabilityMetrics | None, str]:
    """Deprecated alias for :func:`_log_epoch_scores`. experiment_id is empty."""
    return _log_epoch_scores(
        config, model, tokenizer, catalog, epoch,
        experiment_id="", train_loss=train_loss, is_selected=is_selected,
    )


def _job_name(config: JobConfig) -> str:
    grouped = getattr(config, "grouped", None)
    if grouped is not None:
        return str(grouped.name)
    raw = getattr(config, "raw", None)
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return "finetune"
