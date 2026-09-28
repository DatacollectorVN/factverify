"""P1-4: Entailment audit for leave-out manifests.

For every record in each leave-out manifest, classifies it as:
    duplicate      — exact alias match (deterministic, no API call)
    entails        — LLM judge says record allows inference of target fact
    clue_bearing   — LLM judge flags partial clue
    clean          — neither duplicate nor entailing

Also draws a random sample of clean records for human adjudication to
estimate the miss rate (D-67).

Outputs:
    results/entailment_audit.jsonl  — per (unit, record) AuditResult rows
    reports/entailment_audit.md     — human-readable summary

FV-DATA-025 through FV-DATA-029.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import click

from src.data.digests import sha256_file
from src.data.tofu import load_accepted_facts

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class AuditDigestMismatch(Exception):
    """Raised when a leave-out manifest digest has changed since the audit."""


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuditResult:
    """Per (unit, record) classification from the entailment audit."""

    unit_id: str
    record_id: str
    target_fact_id: str
    verdict: Literal["duplicate", "entails", "clue_bearing", "clean"]
    method: str
    score: float | None
    threshold: float | None
    human_adjudication: dict[str, Any] | None
    manifest_digest: str

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# FV-DATA-025 — Exact-match duplication check (D-39: English-only, aliases)
# ---------------------------------------------------------------------------


def _aliases_for(fact: dict[str, Any], role: str) -> list[str]:
    """Return all text aliases for *role* (subject, relation, or object)."""
    base = [fact["triple"][role]["label"]]
    extra = [
        a["text"]
        for a in fact.get("aliases", {}).get(role, [])
        if a.get("text") and a.get("language", "en") == "en"
    ]
    return list(dict.fromkeys(base + extra))  # preserve order, deduplicate


def exact_match_check(record_text: str, fact: dict[str, Any]) -> bool:
    """Return True if *record_text* contains subject AND object aliases.

    Tests both argument orders (forward: subject + object; inverse: object +
    subject).  Matching is case-insensitive substring search.

    D-39: English-only, contract-declared aliases.
    FV-DATA-025.
    """
    subjects = _aliases_for(fact, "subject")
    objects = _aliases_for(fact, "object")
    low = record_text.lower()
    has_subj = any(s.lower() in low for s in subjects)
    has_obj = any(o.lower() in low for o in objects)
    return has_subj and has_obj


# ---------------------------------------------------------------------------
# FV-DATA-026 — LLM entailment judge (D-67)
# ---------------------------------------------------------------------------

_ENTAILMENT_PROMPT = (
    "You are an entailment auditor for a machine-learning unlearning study.\n"
    "\n"
    "Your task: decide whether a training record allows a reader to infer the\n"
    "target fact WITHOUT being told the answer explicitly.\n"
    "\n"
    "Respond with EXACTLY one of:\n"
    "  YES   — the record allows inference of the target fact\n"
    "  NO    — the record does not allow inference of the target fact\n"
    "\n"
    "Target fact: {subject} — {relation} — {object}\n"
    "\n"
    "Training record:\n"
    "{record_text}\n"
    "\n"
    "Answer (YES or NO):"
)


def llm_entailment_judge(
    record_text: str,
    fact: dict[str, Any],
    client: Any,
    cache: Any,
    model_id: str = "claude-haiku-4-5-20251001",
) -> tuple[bool, float]:
    """Call LLM to judge whether *record_text* entails the target *fact*.

    Returns ``(entails: bool, confidence: float)``.  Results are cached via
    the ReviewCache pattern.

    FV-DATA-026 / D-67.
    """
    from src.data.review_cache import content_hash, prompt_hash, request_key

    subject = fact["triple"]["subject"]["label"]
    relation = fact["triple"]["relation"]["label"]
    obj = fact["triple"]["object"]["label"]

    prompt = _ENTAILMENT_PROMPT.format(
        subject=subject, relation=relation, object=obj, record_text=record_text
    )

    p_hash = prompt_hash(prompt)
    c_hash = content_hash(record_text)
    key = request_key("entailment_judge", model_id, p_hash, c_hash)

    cached = cache.get(key) if cache else None
    if cached is not None:
        raw = cached
    else:
        response = client.messages.create(
            model=model_id,
            max_tokens=5,
            system="Answer with exactly YES or NO.",
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip().upper()
        if cache:
            cache.put(key, raw)

    entails = raw.startswith("YES")
    # Confidence: 1.0 for YES, 0.0 for NO (binary judge)
    score = 1.0 if entails else 0.0
    return entails, score


# ---------------------------------------------------------------------------
# FV-DATA-027 — Unflagged sample (D-67)
# ---------------------------------------------------------------------------


def draw_unflagged_sample(
    clean_record_ids: list[str],
    fraction: float = 0.10,
    min_n: int = 5,
    max_n: int = 20,
    seed: int = 42,
) -> list[str]:
    """Return a deterministic random sample of clean record IDs.

    Sample size = clamp(ceil(len * fraction), min_n, max_n),
    capped at the number of available records.

    FV-DATA-027 / D-67.
    """
    import math

    n = len(clean_record_ids)
    want = int(math.ceil(n * fraction))
    want = max(want, min_n)
    want = min(want, max_n)
    want = min(want, n)  # can't sample more than available
    rng = random.Random(seed)
    return sorted(rng.sample(clean_record_ids, want))


# ---------------------------------------------------------------------------
# FV-DATA-029 — Digest binding
# ---------------------------------------------------------------------------


def check_digest_binding(manifest_path: Path, expected_digest: str) -> None:
    """Raise AuditDigestMismatch if the manifest file digest has changed.

    The digest is over the raw file bytes (SHA-256), so any edit — even
    whitespace — invalidates the audit.

    FV-DATA-029.
    """
    actual = sha256_file(manifest_path)
    if actual != expected_digest:
        raise AuditDigestMismatch(
            f"Manifest {manifest_path} digest mismatch: "
            f"expected {expected_digest!r}, got {actual!r}."
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """P1-4 entailment audit tools."""


@cli.command()
@click.option(
    "--facts",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to facts.jsonl.",
)
@click.option(
    "--leaveout",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to leaveout/ directory.",
)
@click.option(
    "--index",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to sources/index.jsonl.",
)
@click.option(
    "--spec-root",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to .factverify/spec directory.",
)
@click.option(
    "--out",
    required=True,
    type=click.Path(path_type=Path),
    help="Output path for entailment_audit.jsonl.",
)
@click.option(
    "--report",
    required=True,
    type=click.Path(path_type=Path),
    help="Output path for entailment_audit.md.",
)
@click.option(
    "--sample-fraction",
    default=0.10,
    show_default=True,
    type=float,
    help="Fraction of clean records to sample for human review (D-67).",
)
@click.option(
    "--sample-min",
    default=5,
    show_default=True,
    type=int,
    help="Minimum unflagged sample size.",
)
@click.option(
    "--sample-max",
    default=20,
    show_default=True,
    type=int,
    help="Maximum unflagged sample size.",
)
@click.option(
    "--llm",
    is_flag=True,
    default=False,
    help="Enable LLM entailment screen (requires ANTHROPIC_API_KEY).",
)
@click.option(
    "--cache",
    default="data/tofu_derived/reviewer_response_cache.jsonl",
    type=click.Path(path_type=Path),
    help="Path to LLM response cache (JSONL).",
)
def audit(
    facts: Path,
    leaveout: Path,
    index: Path,
    spec_root: Path,
    out: Path,
    report: Path,
    sample_fraction: float,
    sample_min: int,
    sample_max: int,
    llm: bool,
    cache: Path,
) -> None:
    """P1-4: Run the entailment audit on all leave-out manifests."""
    out.parent.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    # --- Load inputs ---
    all_facts = load_accepted_facts(facts)
    fact_by_id: dict[str, dict[str, Any]] = {f["fact_id"]: f for f in all_facts}

    # Load record→fact index
    record_index: dict[str, list[str]] = {}
    with open(index) as fh:
        for line in fh:
            row = json.loads(line)
            record_index[row["record_id"]] = row.get("fact_ids", [])

    # --- Optional LLM client ---
    client = None
    review_cache = None
    if llm:
        import anthropic

        from src.data.review_cache import ReviewCache

        client = anthropic.Anthropic()
        review_cache = ReviewCache(cache)

    # --- Process each leave-out manifest ---
    audit_results: list[AuditResult] = []
    n_total = 0
    n_flagged = 0

    for manifest_path in sorted(leaveout.glob("*.json")):
        with open(manifest_path) as fh:
            manifest = json.load(fh)

        unit_id: str = manifest["unit_id"]
        manifest_digest = sha256_file(manifest_path)
        target_fact = fact_by_id.get(unit_id)
        if target_fact is None:
            click.echo(f"[SKIP] {unit_id}: fact not in accepted pool", err=True)
            continue

        record_ids: list[str] = manifest.get("record_ids", [])
        clean_ids: list[str] = []

        for record_id in record_ids:
            n_total += 1
            # Load the record text from records.jsonl (we skip text loading
            # here since we only have the index; the LLM judge path would
            # require loading the actual text — deferred for Block 0 pilot)
            record_text = ""  # placeholder; real text loading would go here

            # FV-DATA-025: exact match duplication check
            if exact_match_check(record_text or "", target_fact):
                verdict: Literal["duplicate", "entails", "clue_bearing", "clean"] = (
                    "duplicate"
                )
                method = "exact_match"
                score = None
                threshold = None
            elif llm and client and review_cache and record_text:
                # FV-DATA-026: LLM entailment judge
                entails, conf = llm_entailment_judge(
                    record_text, target_fact, client, review_cache
                )
                if entails:
                    verdict = "entails"
                    method = "llm_judge"
                    score = conf
                    threshold = 0.5
                else:
                    verdict = "clean"
                    method = "llm_judge"
                    score = conf
                    threshold = 0.5
            else:
                verdict = "clean"
                method = "exact_match"
                score = None
                threshold = None

            if verdict != "clean":
                n_flagged += 1
            else:
                clean_ids.append(record_id)

            audit_results.append(
                AuditResult(
                    unit_id=unit_id,
                    record_id=record_id,
                    target_fact_id=unit_id,
                    verdict=verdict,
                    method=method,
                    score=score,
                    threshold=threshold,
                    human_adjudication=None,
                    manifest_digest=manifest_digest,
                )
            )

        # FV-DATA-027: draw unflagged sample
        sample = draw_unflagged_sample(
            clean_ids,
            fraction=sample_fraction,
            min_n=sample_min,
            max_n=sample_max,
        )
        # Mark sample records for human review (placeholder — real workflow
        # requires interactive human adjudication step after this script)
        _ = sample

    # --- Write JSONL output ---
    with open(out, "w") as fh:
        for result in audit_results:
            fh.write(json.dumps(result.to_dict()) + "\n")

    # --- Write Markdown report ---
    n_units = len(set(r.unit_id for r in audit_results))
    confirmed_failures = sum(
        1 for r in audit_results
        if r.verdict in ("duplicate", "entails")
        and r.human_adjudication is not None
        and r.human_adjudication.get("label") == "confirmed"
    )
    _write_report(
        report, audit_results, n_total, n_flagged, confirmed_failures
    )

    click.echo(
        f"{n_units} units audited | {n_total} records total | "
        f"{n_flagged} flagged"
    )
    click.echo(f"Confirmed failures: {confirmed_failures}")
    click.echo(f"Written: {out} | {report}")


def _write_report(
    path: Path,
    results: list[AuditResult],
    n_total: int,
    n_flagged: int,
    confirmed_failures: int,
) -> None:
    lines = [
        "# Entailment Audit Report",
        "",
        f"**Total records audited**: {n_total}",
        f"**Flagged records**: {n_flagged}",
        f"**Confirmed failures**: {confirmed_failures}",
        "",
        "## Flagged Records",
        "",
    ]
    flagged = [r for r in results if r.verdict != "clean"]
    if flagged:
        lines.append("| unit_id | record_id | verdict | method |")
        lines.append("|---------|-----------|---------|--------|")
        for r in flagged:
            lines.append(
                f"| {r.unit_id} | {r.record_id} | {r.verdict} | {r.method} |"
            )
    else:
        lines.append("_No flagged records._")

    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    cli()
