"""Task handlers that bridge src.main to existing training/eval code.

Each handler receives an AppConfig + RunContext and delegates to the
legacy modules.  When the new service-layer coordinators are complete
these bridges will be replaced by direct service calls.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.services.common.types import AppConfig, RunContext, RunResult

logger = logging.getLogger(__name__)


# ── Train ──────────────────────────────────────────────────────────────


def handle_train(config: AppConfig, context: RunContext) -> RunResult:
    """Delegate training to the existing grouped-job runner."""
    from src.train.config import load_grouped_config
    from src.train.run import run_grouped_job

    source = config.source_path
    if source is None:
        return RunResult(status="failed", error="no source config path")

    grouped = load_grouped_config(source)
    spec_root = context.controlled_input_root  # .factverify/

    results = run_grouped_job(
        grouped,
        spec_root=spec_root,
        rerun=not config.runtime.resume,
    )
    failed = [r for r in results if r.status == "failed"]
    if failed:
        errors = "; ".join(r.error or "unknown" for r in failed)
        return RunResult(
            status="failed",
            error=f"{len(failed)} run(s) failed: {errors}",
        )
    return RunResult(status="succeeded")


# ── Evaluate ───────────────────────────────────────────────────────────


def handle_evaluate(config: AppConfig, context: RunContext) -> RunResult:
    """Route evaluation to the service-layer evaluator."""
    from src.services.evaluation.evaluate import evaluate

    return evaluate(config, context)


# ── Gate ───────────────────────────────────────────────────────────────


def handle_gate(config: AppConfig, context: RunContext) -> RunResult:
    """Delegate gate analysis to the existing gate1 module."""
    from src.eval.gate1 import analyze_gate1 as legacy_analyze

    job_name = config.job.name
    try:
        report = legacy_analyze(job_name)
    except Exception as exc:
        return RunResult(status="failed", error=str(exc))

    if report.get("decision") == "NO_DATA":
        return RunResult(status="failed", error="no evaluation data found")

    # Save report
    output_dir = Path(config.raw.get("output", {}).get(
        "dir", f".factverify_internal/eval/{job_name}"
    ))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "gate1_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    logger.info("gate report saved to %s", report_path)

    return RunResult(
        status="succeeded",
        artifacts={"gate1_report": str(report_path)},
    )
