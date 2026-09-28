#!/usr/bin/env python3
"""Post-process mentions.jsonl to fix char spans using Python str.find().

The extractor asked Claude for char_start/char_end indices, which are
unreliable.  The (subject, relation, object, field) values are correct;
only the span positions need recomputing.

For each mention:
  1. Search for the object value verbatim in the field text.
  2. If found: update char_start/char_end and reset review_status to pending.
  3. If not found: mark review_status=span_unresolved (excluded from P1-1).

No API calls required — uses the source TOFU rows only.

Usage:
    uv run python scripts/fix_spans.py fix \\
        --mentions data/tofu_derived/mentions.jsonl \\
        --source <tofu-dir> \\
        --out data/tofu_derived/mentions.jsonl
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.tofu import Mention, load_tofu_rows


def _find_span(object_value: str, text: str) -> tuple[int, int] | None:
    """Return (start, end) of the first verbatim occurrence of object_value in text.

    Tries exact match first, then stripped match.
    Returns None if not found.
    """
    obj = object_value
    pos = text.find(obj)
    if pos >= 0:
        return pos, pos + len(obj)

    # Try stripping surrounding whitespace from the object.
    obj = object_value.strip()
    if obj:
        pos = text.find(obj)
        if pos >= 0:
            return pos, pos + len(obj)

    return None


def _load_source_index(
    source_dir: Path,
    configs: list[str],
) -> dict[tuple[str, int], dict[str, str]]:
    index: dict[tuple[str, int], dict[str, str]] = {}
    for config in configs:
        fp = source_dir / f"{config}.json"
        if not fp.exists():
            continue
        rows = load_tofu_rows(source_dir, config)
        for i, row in enumerate(rows):
            index[(config, i)] = row
    return index


@click.group()
def cli() -> None:
    """Span repair utilities."""


@cli.command()
@click.option(
    "--mentions",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--source",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Path to the local TOFU dataset directory.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Output path for repaired mentions.jsonl (can equal --mentions).",
)
def fix(mentions: Path, source: Path, out: Path) -> None:
    """Recompute char_start/char_end for all mentions using str.find()."""
    all_mentions: list[Mention] = []
    with open(mentions) as f:
        for line in f:
            all_mentions.append(Mention.from_dict(json.loads(line)))

    configs = list({m.config for m in all_mentions})
    source_index = _load_source_index(source, configs)

    stats: Counter[str] = Counter()

    for m in all_mentions:
        row = source_index.get((m.config, m.row_index))
        if row is None:
            stats["missing_source"] += 1
            continue

        field_text: str = row.get(m.field, "")
        result = _find_span(m.object_, field_text)

        if result is not None:
            new_start, new_end = result
            if new_start != m.char_start or new_end != m.char_end:
                m.char_start = new_start
                m.char_end = new_end
                stats["repaired"] += 1
            else:
                stats["already_correct"] += 1
            # Reset to pending so adjudicator re-evaluates with the correct span.
            if m.review_status != "pending":
                m.review_status = "pending"
                m.reader_labels = []
                m.adjudication = None
        else:
            m.review_status = "span_unresolved"
            stats["unresolved"] += 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        for m in all_mentions:
            f.write(json.dumps(m.to_dict()) + "\n")

    click.echo(
        f"Done.\n"
        f"  Repaired:        {stats['repaired']}\n"
        f"  Already correct: {stats['already_correct']}\n"
        f"  Span unresolved: {stats['unresolved']}\n"
        f"  Missing source:  {stats['missing_source']}\n"
        f"  Written: {out}"
    )

    if stats["unresolved"]:
        click.echo(
            f"\nNote: {stats['unresolved']} mentions have span_unresolved status.\n"
            "These objects were not found verbatim in the source field.\n"
            "They will be skipped by load_admitted_mentions() (FV-DATA-004)."
        )


if __name__ == "__main__":
    cli()
