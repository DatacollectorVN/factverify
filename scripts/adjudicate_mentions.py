#!/usr/bin/env python3
"""FV-DATA P1-0: Automated two-reader adjudication of extracted mentions.

Reader 1 = claude-sonnet-4-6  (matches extractor — cheap)
Reader 2 = claude-opus-4-6    (independent — stronger)
Adjudicator = claude-opus-4-6  (resolves disagreements)

Usage:
    uv run python scripts/adjudicate_mentions.py adjudicate \\
        --mentions data/tofu_derived/mentions.jsonl \\
        --source /path/to/tofu_raw \\
        --reviewer-config data/tofu_derived/reviewer_config.json \\
        --out data/tofu_derived/mentions.jsonl \\
        --limit 20
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import re as _re
import sys
import time
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.tofu import Mention, load_tofu_rows

# ---------------------------------------------------------------------------
# Reviewer config
# ---------------------------------------------------------------------------


def _load_reviewer_config(path: Path) -> dict[str, object]:
    with open(path) as f:
        return json.load(f)  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Response cache (reuses same pattern as extractor)
# ---------------------------------------------------------------------------


def _request_key(
    role: str, model_revision: str, prompt_hash: str, content_hash: str
) -> str:
    payload = json.dumps(
        {
            "role": role,
            "model_revision": model_revision,
            "prompt_hash": prompt_hash,
            "content_hash": content_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _prompt_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


class ReviewCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._store: dict[str, str] = {}
        if path.exists():
            with open(path) as f:
                for line in f:
                    entry = json.loads(line)
                    self._store[entry["key"]] = entry["response"]

    def get(self, key: str) -> str | None:
        return self._store.get(key)

    def put(self, key: str, response: str) -> None:
        self._store[key] = response
        with open(self._path, "a") as f:
            f.write(json.dumps({"key": key, "response": response}) + "\n")


# ---------------------------------------------------------------------------
# Claude calls
# ---------------------------------------------------------------------------


def _call(
    client: object,
    model_id: str,
    prompt: str,
    user_content: str,
    max_tokens: int,
    temperature: float,
    retry_delay: float = 2.0,
) -> str:
    for attempt in range(2):
        try:
            response = client.messages.create(  # type: ignore[attr-defined]
                model=model_id,
                max_tokens=max_tokens,
                extra_body={"temperature": temperature},
                system=prompt,
                messages=[{"role": "user", "content": user_content}],
            )
            return response.content[0].text  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001
            if attempt == 0:
                click.echo(f"  API error ({exc}), retrying …", err=True)
                time.sleep(retry_delay)
            else:
                raise
    return ""  # unreachable


def _parse_label(raw: str) -> dict[str, str]:
    """Extract JSON from response, tolerating markdown fences."""
    blocks = _re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, _re.DOTALL)
    candidate = blocks[-1] if blocks else raw.strip()
    try:
        return json.loads(candidate)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        try:
            return json.loads(raw.strip())  # type: ignore[no-any-return]
        except json.JSONDecodeError:
            return {"label": "unclear", "reason": f"parse_error: {raw[:80]}"}


# ---------------------------------------------------------------------------
# Build review user content
# ---------------------------------------------------------------------------


def _review_content(
    mention: Mention,
    question: str,
    answer: str,
) -> str:
    field_text = question if mention.field == "question" else answer
    span = field_text[mention.char_start : mention.char_end]
    return (
        f"Question: {question}\n"
        f"Answer: {answer}\n\n"
        f"Mention:\n"
        f"  subject:    {mention.subject}\n"
        f"  relation:   {mention.relation}\n"
        f"  object:     {mention.object_}\n"
        f"  field:      {mention.field}\n"
        f"  span [{mention.char_start}:{mention.char_end}]: {span!r}"
    )


def _adjudication_content(
    mention: Mention,
    question: str,
    answer: str,
    r1_label: str,
    r1_reason: str,
    r2_label: str,
    r2_reason: str,
) -> str:
    base = _review_content(mention, question, answer)
    return (
        f"{base}\n\n"
        f"Reader 1 ({mention.extractor_revision}): {r1_label} — {r1_reason}\n"
        f"Reader 2: {r2_label} — {r2_reason}"
    )


# ---------------------------------------------------------------------------
# Load source texts
# ---------------------------------------------------------------------------


def _load_source_index(
    source_dir: Path,
    configs: list[str],
) -> dict[tuple[str, int], dict[str, str]]:
    """Return {(config, row_index): {"question": ..., "answer": ...}}."""
    index: dict[tuple[str, int], dict[str, str]] = {}
    for config in configs:
        fp = source_dir / f"{config}.json"
        if not fp.exists():
            continue
        rows = load_tofu_rows(source_dir, config)
        for i, row in enumerate(rows):
            index[(config, i)] = row
    return index


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """Automated two-reader adjudication pipeline."""


@cli.command()
@click.option(
    "--mentions",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to mentions.jsonl (input and output).",
)
@click.option(
    "--source",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Path to the local TOFU dataset directory.",
)
@click.option(
    "--reviewer-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Output path for updated mentions.jsonl (can equal --mentions).",
)
@click.option(
    "--limit",
    type=int,
    default=None,
    help="Process at most N pending mentions (for piloting).",
)
@click.option(
    "--shuffle",
    is_flag=True,
    default=False,
    help="Shuffle pending mentions before applying --limit (for diverse sampling).",
)
@click.option(
    "--seed",
    type=int,
    default=42,
    help="Random seed for --shuffle (default: 42).",
)
@click.option(
    "--api-key",
    default=None,
    help="Anthropic API key. Falls back to ANTHROPIC_API_KEY.",
)
def adjudicate(
    mentions: Path,
    source: Path,
    reviewer_config: Path,
    out: Path,
    limit: int | None,
    shuffle: bool,
    seed: int,
    api_key: str | None,
) -> None:
    """Run two-reader adjudication on all pending mentions."""
    cfg = _load_reviewer_config(reviewer_config)
    r1_cfg = cfg["reader_1"]  # type: ignore[index]
    r2_cfg = cfg["reader_2"]  # type: ignore[index]
    adj_cfg = cfg["adjudicator"]  # type: ignore[index]
    review_prompt: str = str(cfg["prompt_text"])
    adj_prompt: str = str(cfg["adjudicator_prompt_text"])
    decoding: dict[str, object] = cfg["decoding_params"]  # type: ignore[assignment]
    max_tokens = int(decoding.get("max_tokens", 256))  # type: ignore[arg-type]
    temperature = float(decoding.get("temperature", 0.0))  # type: ignore[arg-type]

    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not resolved_key:
        raise click.ClickException("ANTHROPIC_API_KEY not set.")

    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise click.ClickException("anthropic not installed. Run: uv sync") from exc

    client = anthropic.Anthropic(api_key=resolved_key)

    # Load all mentions.
    all_mentions: list[Mention] = []
    with open(mentions) as f:
        for line in f:
            all_mentions.append(Mention.from_dict(json.loads(line)))

    pending = [m for m in all_mentions if m.review_status == "pending"]
    if shuffle:
        random.seed(seed)
        random.shuffle(pending)
    if limit is not None:
        pending = pending[:limit]

    click.echo(
        f"Mentions total: {len(all_mentions)}  |  pending: {len(pending)}"
        + (f"  |  processing: {limit}" if limit else "")
    )

    # Load source texts.
    configs = list({m.config for m in pending})
    source_index = _load_source_index(source, configs)

    # Cache.
    cache_path = out.parent / "reviewer_response_cache.jsonl"
    cache = ReviewCache(cache_path)
    ph_review = _prompt_hash(review_prompt)
    ph_adj = _prompt_hash(adj_prompt)

    # Build a lookup of mention_id → index in all_mentions.
    id_to_idx = {m.mention_id: i for i, m in enumerate(all_mentions)}

    stats = {"adjudicated": 0, "agreed": 0, "disagreed": 0, "cache_hits": 0}

    for i, mention in enumerate(pending):
        row = source_index.get((mention.config, mention.row_index))
        if row is None:
            click.echo(
                f"  [{i + 1}/{len(pending)}] {mention.mention_id}: "
                "source row missing, skipping.",
                err=True,
            )
            continue

        question: str = row.get("question", "")
        answer: str = row.get("answer", "")
        user_content = _review_content(mention, question, answer)
        ch = _content_hash(user_content)

        # --- Reader 1 ---
        k1 = _request_key(
            "reader_1", str(r1_cfg["model_revision"]), ph_review, ch  # type: ignore[arg-type]
        )
        raw1 = cache.get(k1)
        if raw1 is None:
            raw1 = _call(
                client,
                str(r1_cfg["model_id"]),
                review_prompt,
                user_content,
                max_tokens,
                temperature,
            )  # type: ignore[arg-type]
            cache.put(k1, raw1)
        else:
            stats["cache_hits"] += 1
        parsed1 = _parse_label(raw1)
        label1: str = str(parsed1.get("label", "unclear"))
        reason1: str = str(parsed1.get("reason", ""))

        # --- Reader 2 ---
        k2 = _request_key(
            "reader_2", str(r2_cfg["model_revision"]), ph_review, ch  # type: ignore[arg-type]
        )
        raw2 = cache.get(k2)
        if raw2 is None:
            raw2 = _call(
                client,
                str(r2_cfg["model_id"]),
                review_prompt,
                user_content,
                max_tokens,
                temperature,
            )  # type: ignore[arg-type]
            cache.put(k2, raw2)
        else:
            stats["cache_hits"] += 1
        parsed2 = _parse_label(raw2)
        label2: str = str(parsed2.get("label", "unclear"))
        reason2: str = str(parsed2.get("reason", ""))

        reader_labels = [
            {
                "reader": str(r1_cfg["model_revision"]),
                "label": label1,
                "reason": reason1,
            },
            {
                "reader": str(r2_cfg["model_revision"]),
                "label": label2,
                "reason": reason2,
            },
        ]

        # --- Adjudication ---
        if label1 == label2 and label1 in ("correct", "incorrect"):
            decision = "accept" if label1 == "correct" else "reject"
            adj_reason = f"Both readers agreed: {label1}"
            stats["agreed"] += 1
        else:
            # Disagreement or unclear — call adjudicator.
            adj_content = _adjudication_content(
                mention, question, answer, label1, reason1, label2, reason2
            )
            ka = _request_key(
                "adjudicator",
                str(adj_cfg["model_revision"]),
                ph_adj,
                _content_hash(adj_content),
            )  # type: ignore[arg-type]
            rawa = cache.get(ka)
            if rawa is None:
                rawa = _call(
                    client,
                    str(adj_cfg["model_id"]),
                    adj_prompt,
                    adj_content,
                    max_tokens,
                    temperature,
                )  # type: ignore[arg-type]
                cache.put(ka, rawa)
            else:
                stats["cache_hits"] += 1
            parsed_adj = _parse_label(rawa)
            decision = str(parsed_adj.get("decision", "reject"))
            adj_reason = str(parsed_adj.get("reason", ""))
            stats["disagreed"] += 1

        # Update the mention in-place.
        idx = id_to_idx[mention.mention_id]
        all_mentions[idx].reader_labels = reader_labels
        all_mentions[idx].adjudication = {
            "decision": decision,
            "adjudicator": str(adj_cfg["model_revision"]),
            "reason": adj_reason,
        }
        all_mentions[idx].review_status = "adjudicated"
        stats["adjudicated"] += 1

        if (i + 1) % 20 == 0 or (i + 1) == len(pending):
            click.echo(
                f"  {i + 1}/{len(pending)}  adjudicated={stats['adjudicated']}  "
                f"agreed={stats['agreed']}  disagreed={stats['disagreed']}"
            )

    # Write updated mentions.jsonl.
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for m in all_mentions:
            f.write(json.dumps(m.to_dict()) + "\n")

    accepted = sum(
        1
        for m in all_mentions
        if m.review_status == "adjudicated"
        and m.adjudication is not None
        and m.adjudication.get("decision") == "accept"
    )
    rejected = sum(
        1
        for m in all_mentions
        if m.review_status == "adjudicated"
        and m.adjudication is not None
        and m.adjudication.get("decision") == "reject"
    )

    click.echo(
        f"\nDone.\n"
        f"  Adjudicated: {stats['adjudicated']}  "
        f"(agreed: {stats['agreed']}, disagreed→adjudicated: {stats['disagreed']})\n"
        f"  Accepted: {accepted}  |  Rejected: {rejected}\n"
        f"  Cache hits: {stats['cache_hits']}\n"
        f"  Written: {out}"
    )


if __name__ == "__main__":
    cli()
