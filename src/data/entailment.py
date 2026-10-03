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

import random
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

from src.data.digests import sha256_file

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
