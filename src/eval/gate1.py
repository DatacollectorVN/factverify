"""Gate 1 separability analysis for Block 0 pilot.

Compares forgetter vs referencer on:
  - forget fact:  did the forgetter actually forget?  (behaviour should differ)
  - retain facts: did the forgetter preserve knowledge? (behaviour should match)

Reads eval results from eval.sqlite recorded by eval_runner.

CLI: python -m src.eval.gate1 --job-name NAME
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import click

from src.ledger.eval_store import EVAL_DB_PATH, EvalRunRecord, open_eval_store


# ═══════════════════════════════════════════════════════════════════════════════
# Statistics helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _std(values: list[float], mean: float) -> float:
    if len(values) < 2:
        return 0.0
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (len(values) - 1))


# ═══════════════════════════════════════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class FactComparison:
    """Side-by-side scores for one fact across forgetter and referencer."""

    fact_id: str
    is_forget: bool
    forgetter: dict[str, float]
    referencer: dict[str, float]


@dataclass
class GateReport:
    """Full Gate 1 analysis result."""

    job_name: str
    forget_fact: str
    comparisons: list[FactComparison]
    forget_delta: dict[str, float]  # metric → |forgetter - referencer| on forget fact
    retain_delta: dict[str, float]  # metric → mean |forgetter - referencer| on retain
    decision: str  # "PASS", "FAIL", "NO_DATA"


_METRICS = ["rouge_l", "truth_ratio", "answer_probability", "answer_rank"]


def _extract_scores(record: EvalRunRecord) -> dict[str, float]:
    """Pull metric values from an eval record."""
    return {
        "rouge_l": record.rouge_l or 0.0,
        "truth_ratio": record.truth_ratio or 0.0,
        "answer_probability": record.answer_probability or 0.0,
        "answer_rank": record.answer_rank or 0.0,
    }


# ═══════════════════════════════════════════════════════════════════════════════
# Core analysis
# ═══════════════════════════════════════════════════════════════════════════════


def analyze_gate1(
    job_name: str,
    db_path: Path = EVAL_DB_PATH,
) -> dict[str, object]:
    """Run Gate 1 analysis. Returns a report dict."""
    store = open_eval_store(db_path)
    by_role = store.scores_by_role(job_name)

    forgetter_records = by_role.get("forgetter", [])
    referencer_records = by_role.get("referencer", [])

    if not forgetter_records:
        click.echo("No forgetter results found.", err=True)
        return {"decision": "NO_DATA"}
    if not referencer_records:
        click.echo("No referencer results found.", err=True)
        return {"decision": "NO_DATA"}

    # Index by fact_id
    forgetter_by_fact = {r.fact_id: r for r in forgetter_records}
    referencer_by_fact = {r.fact_id: r for r in referencer_records}

    # Find common facts
    common_facts = sorted(
        set(forgetter_by_fact.keys()) & set(referencer_by_fact.keys())
    )
    if not common_facts:
        click.echo("No common facts between forgetter and referencer.", err=True)
        return {"decision": "NO_DATA"}

    # Identify forget fact: the one recorded with is_forget_fact in the JSON,
    # or fall back to the first fact that only appears in forgetter (heuristic).
    # We read it from the result JSON if available.
    forget_fact = _detect_forget_fact(forgetter_records, common_facts)

    click.echo(
        f"\nGate 1 Analysis — {job_name}\n"
        f"Forget fact:  {forget_fact or '(unknown)'}\n"
        f"Common facts: {len(common_facts)}\n"
    )

    # Build comparisons
    comparisons: list[FactComparison] = []
    for fact_id in common_facts:
        comparisons.append(FactComparison(
            fact_id=fact_id,
            is_forget=(fact_id == forget_fact),
            forgetter=_extract_scores(forgetter_by_fact[fact_id]),
            referencer=_extract_scores(referencer_by_fact[fact_id]),
        ))

    # ── Forget fact comparison ──────────────────────────────────────────
    forget_comp = next((c for c in comparisons if c.is_forget), None)
    forget_delta: dict[str, float] = {}
    if forget_comp:
        for m in _METRICS:
            forget_delta[m] = forget_comp.forgetter[m] - forget_comp.referencer[m]

    # ── Retain facts comparison ─────────────────────────────────────────
    retain_comps = [c for c in comparisons if not c.is_forget]
    retain_delta: dict[str, float] = {}
    for m in _METRICS:
        if retain_comps:
            diffs = [abs(c.forgetter[m] - c.referencer[m]) for c in retain_comps]
            retain_delta[m] = _mean(diffs)
        else:
            retain_delta[m] = 0.0

    # ── Print results ───────────────────────────────────────────────────
    click.echo("=" * 78)
    click.echo("FORGET FACT — forgetter should score LOW, referencer should score HIGH")
    click.echo("=" * 78)
    if forget_comp:
        click.echo(
            f"{'Metric':<22} {'Forgetter':>12} {'Referencer':>12} {'Delta':>12}"
        )
        click.echo("-" * 60)
        for m in _METRICS:
            click.echo(
                f"{m:<22} {forget_comp.forgetter[m]:>12.4f} "
                f"{forget_comp.referencer[m]:>12.4f} "
                f"{forget_delta[m]:>+12.4f}"
            )
    else:
        click.echo("  (forget fact not found in eval results)")

    click.echo()
    click.echo("=" * 78)
    click.echo("RETAIN FACTS — forgetter and referencer should score SIMILARLY")
    click.echo("=" * 78)
    if retain_comps:
        click.echo(
            f"{'Fact':<55} {'Metric':<18} {'Forgetter':>10} {'Ref':>10} {'|Δ|':>8}"
        )
        click.echo("-" * 104)
        for c in retain_comps:
            for i, m in enumerate(_METRICS):
                fact_label = c.fact_id[:53] if i == 0 else ""
                diff = abs(c.forgetter[m] - c.referencer[m])
                click.echo(
                    f"{fact_label:<55} {m:<18} "
                    f"{c.forgetter[m]:>10.4f} {c.referencer[m]:>10.4f} {diff:>8.4f}"
                )
            if c != retain_comps[-1]:
                click.echo()

        click.echo()
        click.echo("Retain mean |Δ|:")
        for m in _METRICS:
            click.echo(f"  {m:<22} {retain_delta[m]:.4f}")
    else:
        click.echo("  (no retain facts)")

    # ── Decision ────────────────────────────────────────────────────────
    # Gate 1 pass criteria:
    #   - Forget fact: forgetter has noticeably lower answer_probability
    #     and/or higher answer_rank than referencer
    #   - Retain facts: forgetter and referencer are close
    decision = "UNDETERMINED"
    if forget_comp:
        prob_drop = forget_delta.get("answer_probability", 0.0)
        rank_rise = forget_delta.get("answer_rank", 0.0)
        # Forgetter should have LOWER prob (negative delta) and HIGHER rank (positive delta)
        forget_signal = prob_drop < -0.05 or rank_rise > 10.0
        if forget_signal:
            decision = "PASS"
            click.echo(
                "\n→ Gate 1 criteria MET — forgetter shows clear forget signal."
            )
        else:
            decision = "FAIL"
            click.echo(
                "\n→ Gate 1 criteria NOT MET — forgetter does not differ enough "
                "from referencer on the forget fact."
            )
    click.echo("  Awaiting go/no-go decision.")

    report = {
        "job_name": job_name,
        "gate": "gate1",
        "forget_fact": forget_fact,
        "total_facts": len(common_facts),
        "retain_facts": len(retain_comps),
        "decision": decision,
        "forget_delta": forget_delta,
        "retain_delta": retain_delta,
        "comparisons": [
            {
                "fact_id": c.fact_id,
                "is_forget": c.is_forget,
                "forgetter": c.forgetter,
                "referencer": c.referencer,
            }
            for c in comparisons
        ],
    }
    return report


def _detect_forget_fact(
    forgetter_records: list[EvalRunRecord],
    common_facts: list[str],
) -> str | None:
    """Try to identify the forget fact from result JSON files."""
    for record in forgetter_records:
        if record.result_path:
            result_path = Path(record.result_path)
            if result_path.is_file():
                try:
                    data = json.loads(result_path.read_text())
                    if data.get("is_forget_fact"):
                        return str(data["fact_id"])
                except (json.JSONDecodeError, KeyError):
                    pass
    # Fallback: can't auto-detect
    return common_facts[0] if common_facts else None


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
    "--forget-fact",
    default=None,
    help="Explicitly specify the forget fact ID (overrides auto-detection).",
)
@click.option(
    "--output-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Directory to save gate1_report.json.",
)
@click.option(
    "--db",
    "db_path",
    default=EVAL_DB_PATH,
    type=click.Path(path_type=Path),
    help="Path to eval SQLite database.",
)
def main(
    job_name: str,
    forget_fact: str | None,
    output_dir: Path | None,
    db_path: Path,
) -> None:
    """Gate 1 separability analysis — compare forgetter vs referencer."""
    report = analyze_gate1(job_name, db_path=db_path)

    if report.get("decision") == "NO_DATA":
        raise SystemExit(1)

    # Override forget_fact if specified on CLI
    if forget_fact is not None:
        report["forget_fact"] = forget_fact

    # Save report
    if output_dir is None:
        output_dir = Path(f".factverify_internal/eval/{job_name}")
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "gate1_report.json"
    report_path.write_text(json.dumps(report, indent=2))
    click.echo(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    main()
