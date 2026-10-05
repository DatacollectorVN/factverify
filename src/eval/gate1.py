"""Gate 1 separability analysis for Block 0 pilot.

Reads eval results from eval.sqlite and reports whether positives (referencer)
and hard negatives (forgetter) can be separated on C1 native metrics.

CLI: python -m src.eval.gate1 --job-name NAME
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import click

from src.ledger.eval_store import EVAL_DB_PATH, EvalRunRecord, open_eval_store


@dataclass
class MetricSummary:
    """Separability statistics for one metric."""

    name: str
    pos_mean: float
    pos_std: float
    neg_mean: float
    neg_std: float
    cohens_d: float
    auroc: float
    pos_count: int
    neg_count: int


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


def _cohens_d(
    pos_mean: float,
    pos_std: float,
    pos_n: int,
    neg_mean: float,
    neg_std: float,
    neg_n: int,
) -> float:
    """Pooled-variance Cohen's d."""
    if pos_n + neg_n < 3:
        return 0.0
    pooled_var = (
        (pos_n - 1) * pos_std**2 + (neg_n - 1) * neg_std**2
    ) / (pos_n + neg_n - 2)
    pooled_std = math.sqrt(pooled_var) if pooled_var > 0 else 1e-10
    return (pos_mean - neg_mean) / pooled_std


def _auroc(positives: list[float], negatives: list[float]) -> float:
    """Rank-based AUROC. Positives should score higher for good separation."""
    if not positives or not negatives:
        return 0.5
    n_pos = len(positives)
    n_neg = len(negatives)
    count = 0
    for p in positives:
        for n in negatives:
            if p > n:
                count += 1
            elif p == n:
                count += 0.5
    return count / (n_pos * n_neg)


def _extract_metric(records: list[EvalRunRecord], name: str) -> list[float]:
    """Extract non-None values for a metric from records."""
    values: list[float] = []
    for r in records:
        val = getattr(r, name, None)
        if val is not None:
            values.append(val)
    return values


def analyze_gate1(
    job_name: str,
    db_path: Path = EVAL_DB_PATH,
) -> dict[str, object]:
    """Run Gate 1 separability analysis. Returns report dict."""
    store = open_eval_store(db_path)
    by_role = store.scores_by_role(job_name)

    positives = by_role.get("referencer", [])
    negatives = by_role.get("forgetter", [])

    if not positives:
        click.echo("No referencer (positive) results found.", err=True)
        return {"decision": "NO_DATA"}
    if not negatives:
        click.echo("No forgetter (negative) results found.", err=True)
        return {"decision": "NO_DATA"}

    click.echo(
        f"\nGate 1 Analysis — {job_name}\n"
        f"Positives (referencer): {len(positives)}\n"
        f"Negatives (forgetter):  {len(negatives)}\n"
    )

    metrics = ["rouge_l", "truth_ratio", "answer_probability", "answer_rank"]
    summaries: list[MetricSummary] = []

    for metric_name in metrics:
        pos_vals = _extract_metric(positives, metric_name)
        neg_vals = _extract_metric(negatives, metric_name)

        if not pos_vals or not neg_vals:
            continue

        pm = _mean(pos_vals)
        ps = _std(pos_vals, pm)
        nm = _mean(neg_vals)
        ns = _std(neg_vals, nm)

        # For answer_rank, lower is better for positives, so flip for AUROC
        if metric_name == "answer_rank":
            auroc = _auroc([-v for v in pos_vals], [-v for v in neg_vals])
        else:
            auroc = _auroc(pos_vals, neg_vals)

        d = _cohens_d(pm, ps, len(pos_vals), nm, ns, len(neg_vals))
        if metric_name == "answer_rank":
            d = -d  # flip sign so positive d means positives rank better

        summaries.append(MetricSummary(
            name=metric_name,
            pos_mean=pm,
            pos_std=ps,
            neg_mean=nm,
            neg_std=ns,
            cohens_d=d,
            auroc=auroc,
            pos_count=len(pos_vals),
            neg_count=len(neg_vals),
        ))

    # Print table
    click.echo(
        f"{'Metric':<22} {'Pos mean':>10} {'Neg mean':>10} "
        f"{'Cohen d':>9} {'AUROC':>7}"
    )
    click.echo("-" * 62)
    for s in summaries:
        click.echo(
            f"{s.name:<22} {s.pos_mean:>10.4f} {s.neg_mean:>10.4f} "
            f"{s.cohens_d:>9.3f} {s.auroc:>7.3f}"
        )

    # Gate decision criteria
    best_auroc = max((s.auroc for s in summaries), default=0.0)
    best_metric = next(
        (s.name for s in summaries if s.auroc == best_auroc), "none"
    )

    click.echo(f"\nBest AUROC: {best_auroc:.3f} ({best_metric})")
    click.echo(f"Gate 1 threshold: AUROC ≥ 0.80")

    if best_auroc >= 0.80:
        click.echo("\n→ Gate 1 criteria MET — positives and negatives are separable.")
        click.echo("  Awaiting go/no-go decision.")
    else:
        click.echo(
            "\n→ Gate 1 criteria NOT MET — insufficient separation."
        )
        click.echo("  This is a valid finding. Awaiting decision.")

    report = {
        "job_name": job_name,
        "gate": "gate1",
        "positive_count": len(positives),
        "negative_count": len(negatives),
        "separability_threshold": 0.80,
        "best_auroc": best_auroc,
        "best_metric": best_metric,
        "metrics": {
            s.name: {
                "pos_mean": s.pos_mean,
                "pos_std": s.pos_std,
                "neg_mean": s.neg_mean,
                "neg_std": s.neg_std,
                "cohens_d": s.cohens_d,
                "auroc": s.auroc,
                "pos_count": s.pos_count,
                "neg_count": s.neg_count,
            }
            for s in summaries
        },
    }
    return report


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════


@click.command()
@click.option(
    "--job-name",
    required=True,
    help="Name of the eval job to analyze.",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Directory to save gate1_report.json. Defaults to eval job output dir.",
)
@click.option(
    "--db",
    "db_path",
    default=EVAL_DB_PATH,
    type=click.Path(path_type=Path),
    help="Path to eval SQLite database.",
)
def main(job_name: str, output_dir: Path | None, db_path: Path) -> None:
    """Gate 1 separability analysis for Block 0 pilot."""
    report = analyze_gate1(job_name, db_path=db_path)

    if report.get("decision") == "NO_DATA":
        raise SystemExit(1)

    # Save report
    if output_dir is None:
        output_dir = Path(f".factverify_internal/eval/{job_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "gate1_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    click.echo(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
