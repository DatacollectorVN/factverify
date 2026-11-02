"""Shared infrastructure for unlearning methods (GA, GradDiff, NPO, RMU).

Provides per-epoch FV-METRIC-001 log-probability scoring of forget and
retain facts, SQLite logging, tracking-metric aggregation for early
stopping, the retain guard rail, end-of-training detail generation, and the
learner-to-forgetter drop/retention metric (see
``requirements/learner-forgetter-drop-retention-scoring.md``).

The legacy loss/probability/rank scorer (``score_facts``/``score_train_facts``)
is no longer called from ``log_unlearn_scores`` — FV-METRIC-001 log-probability
scoring is the only per-epoch scorer, for both console/SQLite logging and
early-stopping (``save_best_as`` picks between ``target_log_retention`` and
``retain_log_retention``, see :class:`TrackingMetrics`). The retain guard
rail likewise runs on ``retain_retention`` (already baseline-relative)
instead of a legacy loss ratio.

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
from dataclasses import dataclass, field
from typing import Any

import click

from src.ledger.train_store import (
    LearnerFactDetail,
    ProbabilityScoreRecord,
    TrainStore,
    open_train_store,
)
from src.train.config import JobConfig
from src.train.data import CANONICAL_FAMILIES, DataCatalog
from src.train.methods.fact_score import (
    METRIC_VERSION,
    FactLogProb,
    detail_facts,
    safe_exp,
    score_catalog_families,
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
    fields) and for the retain guard rail (:func:`check_retain_guard` reads
    ``val_retain_retention``).

    All fields carry a ``val_`` prefix to mark them as eval-probe metrics:

    * ``val_target_log_retention`` — log-retention of the forget fact vs.
      learner baseline (lower = more forgotten; mode ``min``).
    * ``val_target_retention``     — exp(val_target_log_retention); mode ``min``.
    * ``val_retain_log_retention`` — mean log-retention of retain facts
      (higher = less collateral damage; mode ``max``).
    * ``val_retain_retention``     — exp(val_retain_log_retention); used by the
      retain guard rail, not a valid ``save_best_as`` choice.
    * ``val_drop``                 — drop of the forget fact = ``−val_target_log_retention``
      (higher = more forgotten; mode ``max``).
    * ``val_loss``                 — NLL of the forget fact on eval probes =
      ``−forgetter_log_probability``; lower = more forgotten; mode ``min``.
    """

    val_target_log_retention: float
    val_target_retention: float
    val_retain_log_retention: float
    val_retain_retention: float
    val_drop: float
    val_loss: float


def aggregate_tracking_metrics(changes: list[FactChangeScore]) -> TrackingMetrics | None:
    """Aggregate the target fact and the mean of retain/neighbour facts.

    Returns ``None`` when `changes` has no target fact (e.g. the forget fact
    had no eval probes this epoch). The retain aggregate means
    ``log_retention`` across neighbours in log space, then exponentiates —
    consistent with how family/fact log probabilities are aggregated
    elsewhere in FV-METRIC-001. A run with no scored retain facts reports a
    neutral ``retain_log_retention`` of ``0.0`` (``retain_retention`` of
    ``1.0``) rather than raising.
    """
    target = next((c for c in changes if c.fact_role == "target"), None)
    if target is None:
        return None
    neighbours = [c for c in changes if c.fact_role == "neighbour"]
    retain_log_retention = (
        sum(c.log_retention for c in neighbours) / len(neighbours) if neighbours else 0.0
    )
    return TrackingMetrics(
        val_target_log_retention=target.log_retention,
        val_target_retention=target.retention,
        val_retain_log_retention=retain_log_retention,
        val_retain_retention=safe_exp(retain_log_retention),
        val_drop=target.drop,
        val_loss=-target.forgetter_log_probability,
    )


def _fmt_prob(value: float) -> str:
    """Fixed, documented console precision for probability-like values.

    Finite values print with 3 significant digits in scientific notation so
    very small probabilities stay readable; NaN/inf print as-is. The
    persisted record (not this string) is the source of full precision.
    """
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
    """Print one summary line + one family line per fact.

    Every fact is printed separately (never collapsed into a
    neighbour-average), identified as ``target`` or ``neighbour``.
    """
    for change in changes:
        for line in _format_change_lines(epoch, change, selected=selected):
            click.echo(line)


def _persist_change_scores(
    store: TrainStore,
    name: str,
    seed: int,
    epoch: int,
    baseline: dict[str, FactLogProb],
    current: dict[str, FactLogProb],
    changes: list[FactChangeScore],
    *,
    is_selected: bool,
) -> None:
    """Write fact-, family-, and probe-level rows reproducing every change."""
    records: list[ProbabilityScoreRecord] = []
    for change in changes:
        learner_fact = baseline[change.fact_id]
        current_fact = current[change.fact_id]
        records.append(
            ProbabilityScoreRecord(
                job_name=name,
                seed=seed,
                epoch=epoch,
                fact_id=change.fact_id,
                fact_role=change.fact_role,
                aggregation_level="fact",
                forgetter_log_probability=change.forgetter_log_probability,
                learner_log_probability=change.learner_log_probability,
                drop_value=change.drop,
                log_retention=change.log_retention,
                retention=change.retention,
                is_selected_checkpoint=is_selected,
                metric_version=METRIC_VERSION,
            )
        )
        for family, fam_change in change.families.items():
            records.append(
                ProbabilityScoreRecord(
                    job_name=name,
                    seed=seed,
                    epoch=epoch,
                    fact_id=change.fact_id,
                    fact_role=change.fact_role,
                    aggregation_level="family",
                    family=family,
                    forgetter_log_probability=fam_change.forgetter_log_probability,
                    learner_log_probability=fam_change.learner_log_probability,
                    drop_value=fam_change.drop,
                    log_retention=fam_change.log_retention,
                    retention=fam_change.retention,
                    is_selected_checkpoint=is_selected,
                    metric_version=METRIC_VERSION,
                )
            )
            current_family = current_fact.families.get(family)
            learner_family = learner_fact.families.get(family)
            baseline_probes = {
                probe.probe_id: probe for probe in (learner_family.probes if learner_family else [])
            }
            for probe in (current_family.probes if current_family else []):
                baseline_probe = baseline_probes.get(probe.probe_id)
                records.append(
                    ProbabilityScoreRecord(
                        job_name=name,
                        seed=seed,
                        epoch=epoch,
                        fact_id=change.fact_id,
                        fact_role=change.fact_role,
                        aggregation_level="probe",
                        probe_id=probe.probe_id,
                        family=family,
                        language=probe.language,
                        forgetter_log_probability=probe.sequence_log_probability,
                        learner_log_probability=(
                            baseline_probe.sequence_log_probability
                            if baseline_probe is not None
                            else None
                        ),
                        is_selected_checkpoint=is_selected,
                        metric_version=METRIC_VERSION,
                    )
                )
    store.record_probability_scores(records)


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
    baseline: dict[str, FactLogProb] | None,
    selected_epoch: int,
) -> dict[str, Any]:
    """Re-score the restored best checkpoint against the frozen baseline.

    Persists the result marked ``is_selected_checkpoint=True``, prints the
    same target/neighbour log entries as every other epoch, and returns a
    JSON-serializable report for ``drop_retention.json``. Returns an empty
    dict when there is no baseline or no eval probes (degenerate catalogs,
    e.g. in unit tests).
    """
    if baseline is None:
        return {}
    forget_current = score_catalog_families(model, tokenizer, forget_catalog)
    retain_current = (
        score_catalog_families(model, tokenizer, retain_catalog) if retain_catalog else {}
    )
    current = {**forget_current, **retain_current}
    if not current:
        return {}
    target_fact_ids = set(forget_catalog.allowed_ids)
    changes = compute_change_scores(baseline, current, target_fact_ids)
    if not changes:
        return {}
    store = open_train_store()
    name = job_name(config)
    _persist_change_scores(
        store, name, config.seed, selected_epoch, baseline, current, changes, is_selected=True
    )
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
    baseline: dict[str, FactLogProb] | None = None,
) -> tuple[TrackingMetrics | None, str, dict[str, FactLogProb] | None]:
    """Score forget and retain facts via FV-METRIC-001, write to SQLite.

    Returns ``(tracking metrics, log suffix, frozen learner baseline)``.
    `baseline` is `None` on the epoch-zero call; this function then captures
    the current (epoch-zero) scores as the frozen learner baseline and
    returns them so the caller threads the same object into every later
    epoch (FV-METRIC-001 step 3).

    `train_loss` is accepted for call-site compatibility with every trainer
    (GA/GradDiff/NPO/RMU each compute their own training-loss average for
    their own console line) but is no longer persisted here — the legacy
    per-epoch scorer (`score_facts`/`score_train_facts`) is not called.
    """
    forget_current = score_catalog_families(model, tokenizer, forget_catalog)
    retain_current = (
        score_catalog_families(model, tokenizer, retain_catalog) if retain_catalog else {}
    )
    current = {**forget_current, **retain_current}
    if not current:
        return None, "", baseline

    store = open_train_store()
    name = job_name(config)

    if baseline is None:
        # Epoch zero: this model state *is* the frozen learner baseline.
        baseline = current
    target_fact_ids = set(forget_catalog.allowed_ids)
    changes = compute_change_scores(baseline, current, target_fact_ids)

    tracking: TrackingMetrics | None = None
    suffix = ""
    if changes:
        _persist_change_scores(
            store, name, config.seed, epoch, baseline, current, changes, is_selected=False
        )
        print_change_scores(epoch, changes, selected=False)
        tracking = aggregate_tracking_metrics(changes)
        if tracking is not None:
            suffix = (
                f"  val_target_log_retention={tracking.val_target_log_retention:.4f}"
                f"  val_retain_log_retention={tracking.val_retain_log_retention:.4f}"
            )

    return tracking, suffix, baseline


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


#: Canonical mapping from ``save_best_as`` metric name to optimisation direction.
#: Used by every unlearning trainer to initialise :class:`BestEpochTracker`.
#: Kept here (not duplicated in each trainer) so a new metric only needs one edit.
SAVE_BEST_MODE: dict[str, str] = {
    "val_loss": "min",
    "val_target_log_retention": "min",
    "val_retain_log_retention": "max",
    "val_drop": "max",
    "val_target_retention": "min",
}


def check_retain_guard(retain_retention: float | None, threshold: float) -> bool:
    """Return True if `retain_retention` has fallen below `threshold`.

    `retain_retention` (from :class:`TrackingMetrics`) is already
    baseline-relative (``retention = P_F / P_L``), so no separate baseline
    argument is needed — unlike the legacy loss-ratio guard this replaces.
    """
    if retain_retention is None:
        return False
    return retain_retention < threshold


_DROP_RETENTION_ATTR = "_fv_drop_retention_report"


def remember_drop_retention_report(model: Any, report: dict[str, Any]) -> None:
    """Stash the selected-checkpoint drop/retention report on `model`.

    Mirrors ``BestEpochTracker.remember``'s pattern of passing data back to
    the run orchestrator (``run.py``) without widening every trainer's
    return signature. A no-op for an empty report (e.g. no eval probes).
    """
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
