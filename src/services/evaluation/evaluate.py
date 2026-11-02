"""Evaluation coordinator (FV-ARCH-021).

Routes between single-checkpoint evaluation (new format) and the legacy
multi-checkpoint evaluation (old format). The new format uses a single
``checkpoint.dir`` key; the old format uses a ``checkpoints`` dict of roles.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import click

from src.services.common.types import AppConfig, RunContext, RunResult


def evaluate(config: AppConfig, context: RunContext) -> RunResult:
    """Dispatch to the appropriate evaluator based on config format.

    New format (``checkpoint.dir``):
        Evaluates a single checkpoint (learner or forgetter).  Produces C1
        native metrics (ROUGE-L, truth ratio, answer probability, answer rank)
        *and* FV-METRIC-001 log-probability scores.  When ``baseline.dir`` is
        also supplied, adds drop/retention scores against that baseline.

    Legacy format (``checkpoints`` dict):
        Delegates to ``src.eval.eval_runner`` unchanged.
    """
    source = config.source_path
    if source is None:
        return RunResult(status="failed", error="no source config path")

    raw = config.raw

    if "checkpoint" in raw:
        return _evaluate_single(raw, config, context)

    if "checkpoints" in raw:
        try:
            from src.eval.eval_runner import load_eval_config, run_eval_job

            eval_config = load_eval_config(source)
            run_eval_job(eval_config, rerun=not config.runtime.resume)
            return RunResult(status="succeeded")
        except Exception as exc:
            return RunResult(status="failed", error=str(exc))

    return RunResult(
        status="failed",
        error="config must have either a 'checkpoint' section (new) or a 'checkpoints' section (legacy)",
    )


def _evaluate_single(
    raw: dict[str, Any],
    config: AppConfig,
    context: RunContext,
) -> RunResult:
    """Evaluate one checkpoint on forget + retain facts.

    Scoring pipeline:
    1. C1 native metrics — ROUGE-L, truth ratio, answer probability, answer rank.
    2. FV-METRIC-001 — whole-answer log-probability scores per family and fact.
    3. Drop/retention — if ``baseline.dir`` is set, compare current checkpoint
       against the baseline (the learner) using the same FV-METRIC-001 scorer.
    """
    from src.eval.eval_runner import (
        CheckpointModelPort,
        _free_model,
        _resolve_device,
        evaluate_checkpoint_on_fact,
    )
    from src.ledger.eval_store import EvalRunRecord, open_eval_store
    from src.models import load_local_checkpoint
    from src.train.data import DataCatalog
    from src.train.methods.fact_score import score_catalog_families
    from src.train.methods.unlearn_common import compute_change_scores

    # ── Config parsing ────────────────────────────────────────────────────────
    job = raw.get("job") or {}
    job_name: str = str(job.get("name") or config.job.name)
    job_role: str = str(job.get("role") or config.job.role)

    ckpt_section = raw.get("checkpoint") or {}
    checkpoint_dir = Path(str(ckpt_section.get("dir", "")))
    if not checkpoint_dir.is_dir():
        return RunResult(
            status="failed",
            error=f"checkpoint dir not found: {checkpoint_dir}",
        )

    baseline_section = raw.get("baseline") or {}
    baseline_dir: Path | None = None
    raw_baseline_dir = baseline_section.get("dir")
    if raw_baseline_dir and str(raw_baseline_dir).lower() not in ("null", "none", ""):
        baseline_dir = Path(str(raw_baseline_dir))
        if not baseline_dir.is_dir():
            return RunResult(
                status="failed",
                error=f"baseline dir not found: {baseline_dir}",
            )

    data_section = raw.get("data") or {}
    corpus_dir = Path(str(data_section.get("corpus_dir", ".factverify/facts")))
    forget_fact: str = str(data_section.get("forget_fact") or "")
    retain_facts: list[str] = list(data_section.get("retain_facts") or [])
    all_facts: list[str] = ([forget_fact] if forget_fact else []) + retain_facts

    if not all_facts:
        return RunResult(status="failed", error="no facts specified in data section")

    repro = raw.get("reproducibility") or {}
    device = _resolve_device(repro.get("hardware_class"))

    output_dir = Path(
        str((raw.get("output") or {}).get("dir") or f".factverify_internal/eval/{job_name}")
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    store = open_eval_store()
    rerun = not config.runtime.resume
    if rerun:
        cleared = store.clear_job(job_name)
        if cleared:
            click.echo(f"--rerun: cleared {cleared} previous record(s)")
    completed = store.completed_keys(job_name)

    # ── Load checkpoint ───────────────────────────────────────────────────────
    click.echo(f"\n[{job_name}] role={job_role} device={device}")
    click.echo(f"  checkpoint:   {checkpoint_dir}")
    click.echo(f"  corpus_dir:   {corpus_dir}")
    click.echo(f"  forget_fact:  {forget_fact or '(none)'}")
    click.echo(f"  retain_facts: {len(retain_facts)}")
    if baseline_dir:
        click.echo(f"  baseline:     {baseline_dir}")

    try:
        loaded = load_local_checkpoint(checkpoint_dir)
        loaded.model.to(device)
        loaded.model.eval()
        port = CheckpointModelPort(loaded.model, loaded.tokenizer, device)
    except Exception as exc:
        return RunResult(status="failed", error=f"failed to load checkpoint: {exc}")

    # ── FV-METRIC-001: log-probability scoring ────────────────────────────────
    catalog = DataCatalog(corpus_dir, all_facts)
    logprob_scores: dict[str, Any] = {}
    try:
        logprob_scores = score_catalog_families(loaded.model, loaded.tokenizer, catalog)
    except Exception as exc:
        click.echo(f"  warning: log-probability scoring failed — {exc}")

    # ── C1 native metrics (per fact) ──────────────────────────────────────────
    results_by_fact: dict[str, dict[str, Any]] = {}
    succeeded = skipped = failed = 0

    for fact_id in all_facts:
        key = (fact_id, job_role, 0)
        label = f"{job_role}/{fact_id}"

        if key in completed:
            click.echo(f"  {label} — skipped (already completed)")
            skipped += 1
            continue

        t0 = time.perf_counter()
        try:
            c1 = evaluate_checkpoint_on_fact(port, corpus_dir, fact_id)
            elapsed = time.perf_counter() - t0

            fact_result: dict[str, Any] = {
                "fact_id": fact_id,
                "role": job_role,
                "checkpoint_path": str(checkpoint_dir),
                "is_forget_fact": fact_id == forget_fact,
                # C1 native metrics
                "rouge_l": c1.rouge_l,
                "truth_ratio": c1.truth_ratio,
                "answer_probability": c1.answer_probability,
                "answer_rank": c1.answer_rank,
                "completions": c1.completions,
            }

            # FV-METRIC-001: attach log-probability scores when available
            lp = logprob_scores.get(fact_id)
            if lp is not None:
                fact_result["log_probability"] = lp.fact_log_probability
                fact_result["log_probability_families"] = {
                    fname: fam.family_log_probability
                    for fname, fam in lp.families.items()
                }

            results_by_fact[fact_id] = fact_result

            # Persist per-fact JSON
            fact_out = output_dir / job_role / fact_id
            fact_out.mkdir(parents=True, exist_ok=True)
            (fact_out / "result.json").write_text(json.dumps(fact_result, indent=2))

            store.record_run(EvalRunRecord(
                job_name=job_name,
                checkpoint_role=job_role,
                checkpoint_path=str(checkpoint_dir),
                fact_id=fact_id,
                seed=0,
                arm="native",
                status="succeeded",
                config_hash="",
                wall_clock_seconds=elapsed,
                peak_memory_bytes=0,
                rouge_l=c1.rouge_l,
                truth_ratio=c1.truth_ratio,
                answer_probability=c1.answer_probability,
                answer_rank=c1.answer_rank,
                result_path=str(fact_out / "result.json"),
            ))

            is_forget_tag = " [FORGET]" if fact_id == forget_fact else ""
            lp_suffix = (
                f"  logP={lp.fact_log_probability:.4f}" if lp is not None else ""
            )
            click.echo(
                f"  {label}{is_forget_tag} — "
                f"rouge_l={c1.rouge_l:.4f}  "
                f"prob={c1.answer_probability:.4f}  "
                f"rank={c1.answer_rank:.1f}"
                f"{lp_suffix}  "
                f"wall={elapsed:.1f}s"
            )
            succeeded += 1

        except Exception as exc:
            elapsed = time.perf_counter() - t0
            store.record_run(EvalRunRecord(
                job_name=job_name,
                checkpoint_role=job_role,
                checkpoint_path=str(checkpoint_dir),
                fact_id=fact_id,
                seed=0,
                arm="native",
                status="failed",
                config_hash="",
                wall_clock_seconds=elapsed,
                peak_memory_bytes=0,
                error_message=str(exc),
            ))
            click.echo(f"  {label} — FAILED: {exc}")
            failed += 1

    _free_model(loaded.model)
    del loaded

    # ── Drop/retention vs baseline ────────────────────────────────────────────
    drop_retention: list[dict[str, Any]] = []
    if baseline_dir is not None:
        click.echo(f"\n  drop/retention vs baseline: {baseline_dir}")
        try:
            baseline_loaded = load_local_checkpoint(baseline_dir)
            baseline_loaded.model.to(device)
            baseline_loaded.model.eval()

            baseline_catalog = DataCatalog(corpus_dir, all_facts)
            baseline_logprobs = score_catalog_families(
                baseline_loaded.model, baseline_loaded.tokenizer, baseline_catalog
            )
            _free_model(baseline_loaded.model)
            del baseline_loaded

            target_ids = {forget_fact} if forget_fact else set()
            changes = compute_change_scores(baseline_logprobs, logprob_scores, target_ids)

            for change in changes:
                entry: dict[str, Any] = {
                    "fact_id": change.fact_id,
                    "fact_role": change.fact_role,
                    "drop": change.drop,
                    "log_retention": change.log_retention,
                    "retention": change.retention,
                    "learner_log_probability": change.learner_log_probability,
                    "forgetter_log_probability": change.forgetter_log_probability,
                    "families": {
                        fname: {
                            "drop": fs.drop,
                            "log_retention": fs.log_retention,
                            "retention": fs.retention,
                            "learner_log_probability": fs.learner_log_probability,
                            "forgetter_log_probability": fs.forgetter_log_probability,
                        }
                        for fname, fs in change.families.items()
                    },
                }
                drop_retention.append(entry)
                role_tag = "[TARGET]" if change.fact_role == "target" else "[NEIGHBOUR]"
                click.echo(
                    f"  {change.fact_id} {role_tag} — "
                    f"drop={change.drop:.4f}  "
                    f"retention={change.retention:.4f}"
                )

        except Exception as exc:
            click.echo(f"  warning: drop/retention computation failed — {exc}")
            drop_retention = [{"error": str(exc)}]

    # ── Summary report ────────────────────────────────────────────────────────
    report: dict[str, Any] = {
        "job_name": job_name,
        "role": job_role,
        "checkpoint": str(checkpoint_dir),
        "baseline": str(baseline_dir) if baseline_dir else None,
        "forget_fact": forget_fact,
        "retain_facts": retain_facts,
        "succeeded": succeeded,
        "skipped": skipped,
        "failed": failed,
        "facts": results_by_fact,
        "drop_retention": drop_retention,
    }
    report_path = output_dir / "eval_report.json"
    report_path.write_text(json.dumps(report, indent=2))

    click.echo(
        f"\n[{job_name}] done: {succeeded} succeeded, {skipped} skipped, {failed} failed"
    )
    click.echo(f"  report: {report_path}")

    if failed > 0:
        return RunResult(
            status="failed",
            error=f"{failed} fact(s) failed evaluation",
            artifacts={"eval_report": str(report_path)},
        )
    return RunResult(
        status="succeeded",
        artifacts={"eval_report": str(report_path)},
    )
