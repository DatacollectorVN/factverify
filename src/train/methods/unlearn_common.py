"""Shared infrastructure for unlearning methods (GA, GradDiff, NPO, RMU).

Provides per-epoch FV-METRIC-001 log-probability scoring of target and
neighbour facts, SQLite logging, tracking-metric aggregation for early
stopping, the neighbour guard rail, end-of-training sample generation, and the
learner-to-forgetter drop/retention metric (see
``requirements/learner-forgetter-drop-retention-scoring.md``).

Drop/retention summary
-----------------------
The forgetter loads the learner checkpoint declared by
``training.checkpoint`` and evaluates the target (forget) fact and every
retained/neighbour fact *before* the first unlearning step. That epoch-zero
state is the frozen learner baseline ``L`` — there is no separate
cross-job checkpoint lookup. For every later epoch, the same frozen
baseline is compared against the current forgetter state ``F`` at family
level and fact level, entirely in log space:

    drop = log P_L(f, family) - log P_F(f, family)
    log_retention = -drop
    retention = exp(-drop)

and likewise at the fact level using the mean of the family log
probabilities. Epoch zero therefore has drop = 0 and retention = 1 for
every family and fact by construction (``L`` and ``F`` are the same
scoring pass).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any

import click

from src.ledger.train_store import (
    SampleRecord,
    ScoreRecord,
    TrainStore,
    open_train_store,
)
from src.train.config import JobConfig
from src.train.data import CANONICAL_FAMILIES, DataCatalog
from src.train.methods.fact_score import (
    METRIC_VERSION,
    FactLogProb,
    FamilyLogProb,
    safe_exp,
    sample_epoch_probes,
    score_catalog_both_splits,
    score_catalog_families,
)


@dataclass(frozen=True)
class ForgetterBaseline:
    """Frozen epoch-zero scores on both splits, used as the learner baseline."""

    train: dict[str, FactLogProb]
    eval_scores: dict[str, FactLogProb]


def baseline_to_state(baseline: ForgetterBaseline) -> dict:
    """Serialise a ForgetterBaseline for resume checkpoints (no probe-level data)."""
    def _fact(flp: FactLogProb) -> dict:
        return {
            "fact_log_probability": flp.fact_log_probability,
            "families": {
                fam: v.family_log_probability
                for fam, v in flp.families.items()
            },
        }
    return {
        "train": {k: _fact(v) for k, v in baseline.train.items()},
        "eval_scores": {k: _fact(v) for k, v in baseline.eval_scores.items()},
    }


def baseline_from_state(d: dict) -> ForgetterBaseline:
    """Reconstruct a ForgetterBaseline from a serialised state dict."""
    def _fact(fact_id: str, fd: dict) -> FactLogProb:
        families = {
            fam: FamilyLogProb(family=fam, family_log_probability=lp)
            for fam, lp in fd["families"].items()
        }
        return FactLogProb(
            fact_id=fact_id,
            fact_log_probability=fd["fact_log_probability"],
            families=families,
        )
    return ForgetterBaseline(
        train={k: _fact(k, v) for k, v in d["train"].items()},
        eval_scores={k: _fact(k, v) for k, v in d["eval_scores"].items()},
    )


@dataclass(frozen=True)
class UnlearnMetrics:
    """Aggregated forget + retain metrics for one epoch.

    Deprecated: no longer computed by ``log_unlearn_scores``. Early stopping
    and the retain guard rail now read :class:`TrackingMetrics` instead,
    derived from the FV-METRIC-001 log-probability scoring. Left defined in
    case it is still useful for reference; nothing in this codebase
    constructs it anymore.
    """

    forget_train_loss: float
    forget_val_loss: float
    forget_val_prob: float
    forget_val_rank: float
    retain_val_loss: float
    retain_val_rank: float


# ═══════════════════════════════════════════════════════════════════════════
# Drop / retention (FV-METRIC-001)
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FamilyChangeScore:
    """Drop/retention for one family of one fact, between L and F."""

    family: str
    learner_log_probability: float
    forgetter_log_probability: float
    drop: float
    log_retention: float
    retention: float


@dataclass(frozen=True)
class FactChangeScore:
    """Drop/retention for one fact (fact-level + every scored family)."""

    fact_id: str
    fact_role: str  # "target" | "neighbour"
    learner_log_probability: float
    forgetter_log_probability: float
    drop: float
    log_retention: float
    retention: float
    families: dict[str, FamilyChangeScore] = field(default_factory=dict)


def capture_frozen_baseline(
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    retain_catalog: DataCatalog | None,
) -> dict[str, FactLogProb]:
    """Score the forget fact and every retain fact once: the frozen baseline L.

    Call this on the learner checkpoint *before* any unlearning update.
    The caller must reuse the returned object for every later epoch — it is
    never recomputed mid-run (step 3.4 of the requirement).

    Deprecated: use ForgetterBaseline and score_catalog_both_splits instead.
    """
    baseline = score_catalog_families(model, tokenizer, forget_catalog)
    if retain_catalog is not None:
        baseline.update(score_catalog_families(model, tokenizer, retain_catalog))
    return baseline


def compute_change_scores(
    baseline: dict[str, FactLogProb],
    current: dict[str, FactLogProb],
    target_fact_ids: set[str],
) -> list[FactChangeScore]:
    """Family- and fact-level drop/retention of `current` against `baseline`.

    All aggregation and comparison happens in log space:
    ``drop = log P_L - log P_F``, ``log_retention = -drop``,
    ``retention = exp(-drop)``. A fact or family missing from `current`
    (e.g. it had no eval probes) is skipped rather than raising. The target
    fact(s) sort first, then neighbours, each group ordered by fact id.
    """
    results: list[FactChangeScore] = []
    for fact_id, learner_fact in baseline.items():
        current_fact = current.get(fact_id)
        if current_fact is None:
            continue
        role = "target" if fact_id in target_fact_ids else "neighbour"
        families: dict[str, FamilyChangeScore] = {}
        for family, learner_family in learner_fact.families.items():
            current_family = current_fact.families.get(family)
            if current_family is None:
                continue
            drop = (
                learner_family.family_log_probability
                - current_family.family_log_probability
            )
            families[family] = FamilyChangeScore(
                family=family,
                learner_log_probability=learner_family.family_log_probability,
                forgetter_log_probability=current_family.family_log_probability,
                drop=drop,
                log_retention=-drop,
                retention=safe_exp(-drop),
            )
        drop = learner_fact.fact_log_probability - current_fact.fact_log_probability
        results.append(
            FactChangeScore(
                fact_id=fact_id,
                fact_role=role,
                learner_log_probability=learner_fact.fact_log_probability,
                forgetter_log_probability=current_fact.fact_log_probability,
                drop=drop,
                log_retention=-drop,
                retention=safe_exp(-drop),
                families=families,
            )
        )
    results.sort(key=lambda change: (change.fact_role != "target", change.fact_id))
    return results


@dataclass(frozen=True)
class TrackingMetrics:
    """Aggregate target/retain validation-set metrics for one epoch.

    Derived entirely from the already-computed FV-METRIC-001
    :class:`FactChangeScore` list — no separate legacy scoring pass. Used
    both for early-stopping (``save_best_as`` selects one of the ``val_*``
    fields) and for the neighbour guard rail (:func:`check_neighbour_guard` reads
    ``val_neighbour_retention``).
    """

    val_target_log_retention: float
    val_target_retention: float
    val_neighbour_log_retention: float
    val_neighbour_retention: float
    val_target_drop: float
    val_loss: float


def aggregate_tracking_metrics(changes: list[FactChangeScore]) -> TrackingMetrics | None:
    """Aggregate the target fact and the mean of neighbour facts."""
    target = next((c for c in changes if c.fact_role == "target"), None)
    if target is None:
        return None
    neighbours = [c for c in changes if c.fact_role == "neighbour"]
    neighbour_log_retention = (
        sum(c.log_retention for c in neighbours) / len(neighbours) if neighbours else 0.0
    )
    return TrackingMetrics(
        val_target_log_retention=target.log_retention,
        val_target_retention=target.retention,
        val_neighbour_log_retention=neighbour_log_retention,
        val_neighbour_retention=safe_exp(neighbour_log_retention),
        val_target_drop=target.drop,
        val_loss=-target.forgetter_log_probability,
    )


def _fmt_prob(value: float) -> str:
    if value != value or value in (math.inf, -math.inf):
        return str(value)
    return f"{value:.3e}"


def _format_change_lines(
    epoch: int, change: FactChangeScore, *, selected: bool
) -> list[str]:
    tag = "  selected_checkpoint=true" if selected else ""
    summary = (
        f"epoch={epoch} fact_role={change.fact_role.ljust(9)} fact_id={change.fact_id} "
        f"learner_prob={_fmt_prob(safe_exp(change.learner_log_probability))} "
        f"forgetter_prob={_fmt_prob(safe_exp(change.forgetter_log_probability))} "
        f"drop={change.drop:.4f} log_retention={change.log_retention:.4f} "
        f"retention={_fmt_prob(change.retention)}{tag}"
    )
    family_cells = []
    for family in CANONICAL_FAMILIES:
        fam = change.families.get(family)
        if fam is None:
            family_cells.append(f"{family}=NA")
        else:
            family_cells.append(f"{family}={fam.drop:.4f}/{_fmt_prob(fam.retention)}")
    return [summary, "  families " + " ".join(family_cells)]


def print_change_scores(
    epoch: int, changes: list[FactChangeScore], *, selected: bool = False
) -> None:
    """Print per-fact lines only for the selected checkpoint."""
    if not selected:
        return
    for change in changes:
        for line in _format_change_lines(epoch, change, selected=selected):
            click.echo(line)


def _export_report(
    config: JobConfig, selected_epoch: int, changes: list[FactChangeScore]
) -> dict[str, Any]:
    """Build the JSON-serializable ``drop_retention.json`` payload."""
    return {
        "metric_version": METRIC_VERSION,
        "selected_checkpoint_epoch": selected_epoch,
        "job_name": job_name(config),
        "seed": config.seed,
        "facts": [
            {
                "fact_id": change.fact_id,
                "fact_role": change.fact_role,
                "learner_log_probability": change.learner_log_probability,
                "forgetter_log_probability": change.forgetter_log_probability,
                "drop": change.drop,
                "log_retention": change.log_retention,
                "retention": change.retention,
                "families": {
                    family: {
                        "learner_log_probability": fam.learner_log_probability,
                        "forgetter_log_probability": fam.forgetter_log_probability,
                        "drop": fam.drop,
                        "log_retention": fam.log_retention,
                        "retention": fam.retention,
                    }
                    for family, fam in change.families.items()
                },
            }
            for change in changes
        ],
    }


def log_unlearn_selected_checkpoint(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    retain_catalog: DataCatalog | None,
    baseline: ForgetterBaseline | None,
    selected_epoch: int,
    *,
    experiment_id: str = "",
) -> dict[str, Any]:
    """Re-score the restored best checkpoint against the frozen baseline.

    Persists the result marked ``is_selected_checkpoint=True``, prints the
    same target/neighbour log entries as every other epoch, and returns a
    JSON-serializable report for ``drop_retention.json``. Returns an empty
    dict when there is no baseline or no eval probes.
    """
    if baseline is None:
        return {}
    # Use eval scores for the report (consistent with tracking metrics)
    eval_baseline = baseline.eval_scores

    from src.train.methods.alias_score import alias_store_from_config as _alias_store_from_config
    _alias_store_sel = _alias_store_from_config(config)

    forget_current_train, forget_current_eval = score_catalog_both_splits(
        model, tokenizer, forget_catalog, _alias_store_sel
    )
    if retain_catalog is not None:
        retain_current_train, retain_current_eval = score_catalog_both_splits(
            model, tokenizer, retain_catalog, _alias_store_sel
        )
    else:
        retain_current_train: dict[str, FactLogProb] = {}
        retain_current_eval: dict[str, FactLogProb] = {}

    eval_current = {**forget_current_eval, **retain_current_eval}
    if not eval_current:
        return {}

    target_fact_ids = set(forget_catalog.allowed_ids)
    changes = compute_change_scores(eval_baseline, eval_current, target_fact_ids)
    if not changes:
        return {}

    if experiment_id:
        store = open_train_store()
        _persist_new_score_records(
            store, experiment_id, selected_epoch,
            baseline, {**forget_current_train, **retain_current_train}, eval_current,
            changes, target_fact_ids, is_selected=True,
        )
        # Samples at selected checkpoint
        epoch_rng = random.Random(config.seed + selected_epoch + 10000)
        sampled = sample_epoch_probes(model, tokenizer, forget_catalog, retain_catalog, epoch_rng)
        sample_records = [
            SampleRecord(
                experiment_id=experiment_id,
                epoch=selected_epoch,
                fact_id=sp.fact_id,
                fact_role=sp.fact_role,
                family=sp.family,
                probe_id=sp.probe_id,
                language=sp.language,
                input_text=sp.input_text,
                expected_answer=sp.expected_answer,
                model_output=sp.model_output,
                log_probability=sp.log_probability,
                is_selected_checkpoint=True,
            )
            for sp in sampled
        ]
        store.record_samples(sample_records)

    print_change_scores(selected_epoch, changes, selected=True)
    return _export_report(config, selected_epoch, changes)


# ═══════════════════════════════════════════════════════════════════════════
# Per-epoch scoring entry point
# ═══════════════════════════════════════════════════════════════════════════


def log_unlearn_scores(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    retain_catalog: DataCatalog | None,
    epoch: int,
    train_loss: float,
    experiment_id: str = "",
    baseline: ForgetterBaseline | None = None,
) -> tuple[TrackingMetrics | None, str, ForgetterBaseline | None]:
    """Score forget and retain facts via FV-METRIC-001, write to SQLite.

    Returns ``(tracking metrics, log suffix, frozen learner baseline)``.
    ``baseline`` is ``None`` on the epoch-zero call; this function then
    captures the current (epoch-zero) scores as the frozen learner baseline
    and returns them so the caller threads the same object into every later
    epoch (FV-METRIC-001 step 3).
    """
    # Build alias store once per scoring call (None when alias_aware=false)
    from src.train.methods.alias_score import alias_store_from_config as _alias_store_from_config
    _alias_store = _alias_store_from_config(config)

    # Score both splits for forget catalog
    train_forget, eval_forget = score_catalog_both_splits(model, tokenizer, forget_catalog, _alias_store)
    if retain_catalog is not None:
        train_retain, eval_retain = score_catalog_both_splits(model, tokenizer, retain_catalog, _alias_store)
    else:
        train_retain: dict[str, FactLogProb] = {}
        eval_retain: dict[str, FactLogProb] = {}

    train_current = {**train_forget, **train_retain}
    eval_current = {**eval_forget, **eval_retain}

    if not eval_current:
        return None, "", baseline

    # Epoch zero: capture the frozen baseline, then fall through to compute
    # change scores (all drops will be 0, retention 1).
    if baseline is None:
        baseline = ForgetterBaseline(train=train_current, eval_scores=eval_current)

    target_fact_ids = set(forget_catalog.allowed_ids)
    changes = compute_change_scores(baseline.eval_scores, eval_current, target_fact_ids)
    train_changes = compute_change_scores(baseline.train, train_current, target_fact_ids)

    tracking: TrackingMetrics | None = None
    suffix = ""

    if changes:
        if experiment_id:
            store = open_train_store()
            _persist_new_score_records(
                store, experiment_id, epoch,
                baseline, train_current, eval_current,
                changes, target_fact_ids,
                is_selected=False,
                train_loss=train_loss if train_loss != 0.0 or epoch > 0 else None,
            )
            # Samples: 5 target + 5 neighbour (1 per family each)
            epoch_rng = random.Random(config.seed + epoch)
            sampled = sample_epoch_probes(model, tokenizer, forget_catalog, retain_catalog, epoch_rng)
            store.record_samples([
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
                    is_selected_checkpoint=False,
                )
                for sp in sampled
            ])

        print_change_scores(epoch, changes, selected=False)
        tracking = aggregate_tracking_metrics(changes)
        train_tracking = aggregate_tracking_metrics(train_changes)
        drop_str = (
            f"{train_tracking.val_target_drop:.4f}" if train_tracking is not None else "N/A"
        )
        neighbour_ret_str = (
            f"{train_tracking.val_neighbour_retention:.4f}" if train_tracking is not None else "N/A"
        )
        if tracking is not None:
            suffix = (
                f"  train_drop={drop_str}"
                f"  train_neighbour_ret={neighbour_ret_str}"
                f"  val_loss={tracking.val_loss:.4f}"
                f"  val_target_drop={tracking.val_target_drop:.4f}"
                f"  val_neighbour_ret={tracking.val_neighbour_retention:.4f}"
            )

    return tracking, suffix, baseline


def _persist_new_score_records(
    store: TrainStore,
    experiment_id: str,
    epoch: int,
    baseline: ForgetterBaseline,
    train_current: dict[str, FactLogProb],
    eval_current: dict[str, FactLogProb],
    changes: list[FactChangeScore],
    target_fact_ids: set[str],
    *,
    is_selected: bool,
    train_loss: float | None = None,
) -> None:
    """Write family, fact, and epoch-level ScoreRecords to the store."""
    records: list[ScoreRecord] = []

    # Map changes by fact_id for easy lookup
    change_by_fact: dict[str, FactChangeScore] = {c.fact_id: c for c in changes}

    # Family and fact rows for all scored facts
    all_fact_ids = set(eval_current.keys())
    for fact_id in all_fact_ids:
        eval_fact = eval_current.get(fact_id)
        train_fact = train_current.get(fact_id)
        baseline_eval_fact = baseline.eval_scores.get(fact_id)
        baseline_train_fact = baseline.train.get(fact_id)
        fact_role = "target" if fact_id in target_fact_ids else "neighbour"
        change = change_by_fact.get(fact_id)

        # Family-level rows
        all_families = set()
        if eval_fact:
            all_families.update(eval_fact.families)
        if train_fact:
            all_families.update(train_fact.families)
        for family in all_families:
            eval_fam = eval_fact.families.get(family) if eval_fact else None
            train_fam = train_fact.families.get(family) if train_fact else None
            bl_eval_fam = baseline_eval_fact.families.get(family) if baseline_eval_fact else None
            bl_train_fam = baseline_train_fact.families.get(family) if baseline_train_fact else None
            fam_change = change.families.get(family) if change else None

            # Compute train-side drop/retention if baseline available
            train_drop: float | None = None
            train_log_ret: float | None = None
            train_ret: float | None = None
            if bl_train_fam is not None and train_fam is not None:
                train_drop = bl_train_fam.family_log_probability - train_fam.family_log_probability
                train_log_ret = -train_drop
                train_ret = safe_exp(train_log_ret)

            records.append(
                ScoreRecord(
                    experiment_id=experiment_id,
                    epoch=epoch,
                    aggregation_level="family",
                    metric_version=METRIC_VERSION,
                    fact_id=fact_id,
                    fact_role=fact_role,
                    family=family,
                    eval_log_probability=eval_fam.family_log_probability if eval_fam else None,
                    train_log_probability=train_fam.family_log_probability if train_fam else None,
                    baseline_eval_log_probability=bl_eval_fam.family_log_probability if bl_eval_fam else None,
                    baseline_train_log_probability=bl_train_fam.family_log_probability if bl_train_fam else None,
                    eval_drop=fam_change.drop if fam_change else None,
                    eval_log_retention=fam_change.log_retention if fam_change else None,
                    eval_retention=fam_change.retention if fam_change else None,
                    train_drop=train_drop,
                    train_log_retention=train_log_ret,
                    train_retention=train_ret,
                    is_selected_checkpoint=is_selected,
                )
            )

        # Fact-level row
        eval_lp = eval_fact.fact_log_probability if eval_fact else None
        train_lp = train_fact.fact_log_probability if train_fact else None
        bl_eval_lp = baseline_eval_fact.fact_log_probability if baseline_eval_fact else None
        bl_train_lp = baseline_train_fact.fact_log_probability if baseline_train_fact else None
        eval_drop_fact: float | None = None
        eval_log_ret_fact: float | None = None
        eval_ret_fact: float | None = None
        train_drop_fact: float | None = None
        train_log_ret_fact: float | None = None
        train_ret_fact: float | None = None
        if change is not None:
            eval_drop_fact = change.drop
            eval_log_ret_fact = change.log_retention
            eval_ret_fact = change.retention
        if bl_train_lp is not None and train_lp is not None:
            train_drop_fact = bl_train_lp - train_lp
            train_log_ret_fact = -train_drop_fact
            train_ret_fact = safe_exp(train_log_ret_fact)

        records.append(
            ScoreRecord(
                experiment_id=experiment_id,
                epoch=epoch,
                aggregation_level="fact",
                metric_version=METRIC_VERSION,
                fact_id=fact_id,
                fact_role=fact_role,
                eval_log_probability=eval_lp,
                train_log_probability=train_lp,
                baseline_eval_log_probability=bl_eval_lp,
                baseline_train_log_probability=bl_train_lp,
                eval_drop=eval_drop_fact,
                eval_log_retention=eval_log_ret_fact,
                eval_retention=eval_ret_fact,
                train_drop=train_drop_fact,
                train_log_retention=train_log_ret_fact,
                train_retention=train_ret_fact,
                is_selected_checkpoint=is_selected,
            )
        )

    # Epoch-level row: aggregate target and retain metrics
    target_changes = [c for c in changes if c.fact_role == "target"]
    neighbour_changes = [c for c in changes if c.fact_role == "neighbour"]

    eval_target_drop: float | None = None
    eval_target_log_ret: float | None = None
    eval_target_ret: float | None = None
    if target_changes:
        eval_target_drop = sum(c.drop for c in target_changes) / len(target_changes)
        eval_target_log_ret = -eval_target_drop
        eval_target_ret = safe_exp(eval_target_log_ret)

    eval_neighbour_log_ret: float | None = None
    eval_neighbour_ret: float | None = None
    if neighbour_changes:
        eval_neighbour_log_ret = sum(c.log_retention for c in neighbour_changes) / len(neighbour_changes)
        eval_neighbour_ret = safe_exp(eval_neighbour_log_ret)

    # Train-side epoch aggregates (from score records we just built)
    target_train_drops = [
        r.train_drop
        for r in records
        if r.aggregation_level == "fact" and r.fact_role == "target" and r.train_drop is not None
    ]
    neighbour_train_log_rets = [
        r.train_log_retention
        for r in records
        if r.aggregation_level == "fact" and r.fact_role == "neighbour" and r.train_log_retention is not None
    ]

    train_target_drop: float | None = None
    train_target_log_ret: float | None = None
    train_target_ret: float | None = None
    if target_train_drops:
        train_target_drop = sum(target_train_drops) / len(target_train_drops)
        train_target_log_ret = -train_target_drop
        train_target_ret = safe_exp(train_target_log_ret)

    train_neighbour_log_ret: float | None = None
    train_neighbour_ret: float | None = None
    if neighbour_train_log_rets:
        train_neighbour_log_ret = sum(neighbour_train_log_rets) / len(neighbour_train_log_rets)
        train_neighbour_ret = safe_exp(train_neighbour_log_ret)

    # Compute epoch-level log probs
    all_eval_facts_list = list(eval_current.values())
    all_train_facts_list = list(train_current.values())
    mean_eval_lp = sum(f.fact_log_probability for f in all_eval_facts_list) / len(all_eval_facts_list) if all_eval_facts_list else None
    mean_train_lp = sum(f.fact_log_probability for f in all_train_facts_list) / len(all_train_facts_list) if all_train_facts_list else None

    records.append(
        ScoreRecord(
            experiment_id=experiment_id,
            epoch=epoch,
            aggregation_level="epoch",
            metric_version=METRIC_VERSION,
            train_loss=train_loss,
            train_fact_log_probability=mean_train_lp,
            eval_fact_log_probability=mean_eval_lp,
            train_target_drop=train_target_drop,
            eval_target_drop=eval_target_drop,
            train_target_log_retention=train_target_log_ret,
            eval_target_log_retention=eval_target_log_ret,
            train_target_retention=train_target_ret,
            eval_target_retention=eval_target_ret,
            train_retain_log_retention=train_neighbour_log_ret,
            eval_retain_log_retention=eval_neighbour_log_ret,
            train_retain_retention=train_neighbour_ret,
            eval_retain_retention=eval_neighbour_ret,
            is_selected_checkpoint=is_selected,
        )
    )

    store.record_scores(records)


def log_unlearn_details(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    catalog: DataCatalog,
) -> None:
    """Deprecated: details are now written as samples during log_unlearn_scores.

    Kept for call-site compatibility with ga.py, graddiff.py, npo.py, rmu.py.
    Does nothing.
    """
    pass


#: Canonical mapping from ``save_best_as`` metric name to optimisation direction.
SAVE_BEST_MODE: dict[str, str] = {
    "val_loss": "min",
    "val_target_log_retention": "min",
    "val_neighbour_log_retention": "max",
    "val_target_drop": "max",
    "val_target_retention": "min",
}


def check_neighbour_guard(neighbour_retention: float | None, threshold: float) -> bool:
    """Return True if `neighbour_retention` has fallen below `threshold`."""
    if neighbour_retention is None:
        return False
    return neighbour_retention < threshold


_DROP_RETENTION_ATTR = "_fv_drop_retention_report"


def remember_drop_retention_report(model: Any, report: dict[str, Any]) -> None:
    """Stash the selected-checkpoint drop/retention report on `model`."""
    if report:
        setattr(model, _DROP_RETENTION_ATTR, report)


def drop_retention_report(model: Any) -> dict[str, Any] | None:
    """Return the report stashed by :func:`remember_drop_retention_report`."""
    value = getattr(model, _DROP_RETENTION_ATTR, None)
    if isinstance(value, dict):
        return value
    return None


def job_name(config: JobConfig) -> str:
    """Extract the job name from a config (grouped or flat)."""
    grouped = getattr(config, "grouped", None)
    if grouped is not None:
        return str(grouped.name)
    raw = getattr(config, "raw", None)
    if isinstance(raw, dict) and raw.get("name"):
        return str(raw["name"])
    return "unknown"


def finalize_unlearn_selection(
    config: JobConfig,
    model: Any,
    tokenizer: Any,
    forget_catalog: DataCatalog,
    retain_catalog: DataCatalog | None,
    baseline: ForgetterBaseline | None,
    tracker: Any,
    finished: int,
    stop_reason: str,
    *,
    experiment_id: str = "",
) -> bool:
    """Restore the best epoch and write the selected-checkpoint report.

    Returns True when a valid selected checkpoint exists. When the neighbour
    guard tripped before any non-breaching epoch was recorded, the tracker
    holds no snapshot, so the model still carries the breached weights: no
    selected-checkpoint rows or ``drop_retention.json`` are produced and the
    run is flagged via :func:`remember_stop`.
    """
    from src.train.methods.common import remember_stop

    tracker.restore(model)
    tracker.remember(model)
    has_selection = not (tracker.best_epoch is None and stop_reason == "neighbour_guard")
    remember_stop(
        model,
        reason=stop_reason,
        stopped_epoch=finished,
        has_selected_checkpoint=has_selection,
    )
    if not has_selection:
        click.echo(
            f"    no valid checkpoint: neighbour guard tripped at epoch {finished} "
            f"before any epoch kept neighbour retention above the threshold"
        )
        return False
    selected_epoch = tracker.best_epoch if tracker.best_epoch is not None else finished
    report = log_unlearn_selected_checkpoint(
        config, model, tokenizer, forget_catalog, retain_catalog, baseline, selected_epoch,
        experiment_id=experiment_id,
    )
    remember_drop_retention_report(model, report)
    return True
