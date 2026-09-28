#!/usr/bin/env python3
"""FV-DATA P1-1: Build atomic-fact contracts from adjudicated TOFU mentions.

Reads accepted mentions from mentions.jsonl, filters to D-63 included
relations, deduplicates by (subject, canonical_relation, object), and
emits schema-structured fact contracts using factverify-internal IDs
(TOFU entities are fictional; no Wikidata IDs exist).

Retained neighbourhood is auto-populated from other accepted facts in the
same build batch.  Compositional and global buckets are filled with stubs
that P1-5 will replace.

Usage:
    uv run python scripts/build_facts.py build \\
        --mentions data/tofu_derived/mentions.jsonl \\
        --relations data/controlled/relations.yaml \\
        --out data/controlled/facts.jsonl \\
        --report reports/p1-1-selection.md
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import click
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.tofu import Mention, load_admitted_mentions

# ---------------------------------------------------------------------------
# Slugify helpers
# ---------------------------------------------------------------------------


def _slugify(text: str) -> str:
    """Lowercase slug with underscores only (safe for fact_id / contract_id key)."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "unknown"


def _entity_id(label: str) -> str:
    """factverify:entity:<slug>  (allows underscores and hyphens)."""
    return f"factverify:entity:{_slugify(label)}"


def _relation_id(canonical_slug: str) -> str:
    return f"factverify:relation:{canonical_slug}"


def _fact_key(subject_slug: str, relation_slug: str, object_slug: str) -> str:
    """[a-z0-9]+(?:_[a-z0-9]+)* required by fact_id pattern."""
    # Each component already underscore-only from _slugify; join with _
    parts = [p for p in [subject_slug, relation_slug, object_slug] if p]
    key = "_".join(parts)
    # Safety: collapse any double underscores, strip edges
    key = re.sub(r"_+", "_", key).strip("_")
    return key or "unknown"


def _content_hash(obj: object) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Load D-63 relation inventory
# ---------------------------------------------------------------------------


def _load_relations(path: Path) -> dict[str, dict]:
    """Return {source_relation_label → canonical_entry} from relations.yaml."""
    with open(path) as f:
        cfg = yaml.safe_load(f)

    canonical_map: dict[str, dict] = {}
    excluded: set[str] = set()

    for entry in cfg.get("included", []):
        for src in entry.get("source_relations", []):
            canonical_map[src.lower()] = entry

    for cls in cfg.get("excluded", []):
        for r in cls.get("relations", []):
            excluded.add(r.lower())

    for entry in cfg.get("deferred", []):
        for src in entry.get("source_relations", []):
            excluded.add(src.lower())

    return canonical_map, excluded


# ---------------------------------------------------------------------------
# Build one fact contract
# ---------------------------------------------------------------------------

_STD_CLUE_BOUNDARY = {
    "equivalent_rule": (
        "A query is equivalent if its answer depends on expressing or "
        "recognising the target proposition itself, with no independent "
        "identifying premise supplied."
    ),
    "clue_bearing_rule": (
        "A query is clue-bearing if the prompt supplies an independently "
        "retained premise that can reconstruct a target endpoint."
    ),
    "ambiguous_policy": "adjudicate_before_freeze_else_exploratory",
}


def _make_contract(
    subject: str,
    canonical: dict,
    object_: str,
    mention_ids: list[str],
    same_subject_facts: list[dict],  # other facts about same subject
    same_relation_facts: list[dict],  # other facts with same relation
) -> dict:
    subj_slug = _slugify(subject)
    rel_slug = canonical["id"].split(":")[-1]  # e.g. "occupation"
    obj_slug = _slugify(object_)
    fact_key = _fact_key(subj_slug, rel_slug, obj_slug)

    # Retained neighbourhood
    neighbourhood = []

    # same_subject: pick first other fact about this subject
    if same_subject_facts:
        f = same_subject_facts[0]
        neighbourhood.append(
            {
                "id": f"retain:{subj_slug}_same_subj_0",
                "bucket": "same_subject",
                "statement": (
                    f"{f['subject']} — {f['relation_label']}: {f['object_']}"
                ),
                "language": "en",
                "expected_answers": [f["object_"]],
            }
        )
    else:
        neighbourhood.append(
            {
                "id": f"retain:{subj_slug}_same_subj_stub",
                "bucket": "same_subject",
                "statement": (f"[P1-5 stub] Another retained fact about {subject}."),
                "language": "en",
            }
        )

    # same_relation: pick first other fact with same relation, different subject
    if same_relation_facts:
        f = same_relation_facts[0]
        neighbourhood.append(
            {
                "id": f"retain:{rel_slug}_same_rel_0",
                "bucket": "same_relation",
                "statement": (
                    f"{f['subject']} — {f['relation_label']}: {f['object_']}"
                ),
                "language": "en",
                "expected_answers": [f["object_"]],
            }
        )
    else:
        neighbourhood.append(
            {
                "id": f"retain:{rel_slug}_same_rel_stub",
                "bucket": "same_relation",
                "statement": (
                    f"[P1-5 stub] Another {canonical['label']} fact for a "
                    f"different subject."
                ),
                "language": "en",
            }
        )

    # compositional: stub (P1-5)
    neighbourhood.append(
        {
            "id": f"retain:{fact_key}_comp_stub",
            "bucket": "compositional",
            "statement": (
                f"[P1-5 stub] A reasoning item using retained facts about "
                f"{subject} without requiring the {canonical['label']} relation."
            ),
            "language": "en",
        }
    )

    # global: stub (P1-5)
    neighbourhood.append(
        {
            "id": "retain:global_reasoning_stub",
            "bucket": "global",
            "statement": (
                "[P1-5 stub] A frozen general language and reasoning probe item."
            ),
            "language": "en",
        }
    )

    return {
        "schema_version": "1.0.0",
        "contract_id": f"factverify:contract:{fact_key}:v1",
        "fact_id": f"factverify:fact:{fact_key}",
        "contract_status": "draft",
        "fact_type": "controlled_atomic_fact",
        "evidence_regime": {
            "regime": "reference_relative",
            "training_provenance": "known",
            "allowed_claim": "reference_relative_empirical_conformance",
        },
        "triple": {
            "subject": {
                "id": _entity_id(subject),
                "label": subject,
                "source": "factverify_internal",
            },
            "relation": {
                "id": canonical["id"],
                "label": canonical["label"],
                "source": "factverify_internal",
            },
            "object": {
                "id": _entity_id(object_),
                "label": object_,
                "source": "factverify_internal",
            },
        },
        "aliases": {
            "subject": [
                {
                    "text": subject,
                    "language": "en",
                    "alias_type": "canonical",
                    "source": "manual_adjudication",
                }
            ],
            "relation": [
                {
                    "text": canonical["label"],
                    "language": "en",
                    "argument_order": "subject_relation_object",
                },
                {
                    "text": canonical["label"],
                    "language": "en",
                    "argument_order": "object_inverse_relation_subject",
                },
            ],
            "object": [
                {
                    "text": object_,
                    "language": "en",
                    "alias_type": "canonical",
                    "source": "manual_adjudication",
                }
            ],
        },
        "equivalent_directions": [
            {
                "direction": "forward",
                "given": "subject",
                "answer": "object",
                "language": "en",
                "statement_pattern": canonical["forward_query_template"].replace(
                    "{subject}", subject
                ),
            },
            {
                "direction": "inverse",
                "given": "object",
                "answer": "subject",
                "language": "en",
                "statement_pattern": canonical["inverse_query_template"].replace(
                    "{object}", object_
                ),
            },
            {
                "direction": "verification",
                "given": "triple",
                "answer": "truth_value",
                "language": "en",
                "statement_pattern": (
                    f"Is it true that {subject}'s {canonical['label']} is {object_}?"
                ),
            },
        ],
        "retained_neighbourhood": neighbourhood,
        "clue_boundary": _STD_CLUE_BOUNDARY,
        "entity_resolution": {
            "authority": "factverify_internal",
            "resolution_status": "provisional",
            "notes": (
                f"TOFU fictional entity; no Wikidata ID. "
                f"Sourced from adjudicated mentions: {', '.join(mention_ids)}."
            ),
        },
        # Extension field for P1-3 lineage (not in schema core; companion
        # file facts_lineage.jsonl is the schema-valid alternative).
        "mention_ids": mention_ids,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """P1-1 fact-contract builder."""


@cli.command()
@click.option(
    "--mentions",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to mentions.jsonl (adjudicated rows used).",
)
@click.option(
    "--relations",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
    help="Path to data/controlled/relations.yaml (D-63).",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Output path for facts.jsonl.",
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional path for selection report (Markdown).",
)
def build(
    mentions: Path,
    relations: Path,
    out: Path,
    report: Path | None,
) -> None:
    """Build fact contracts from adjudicated TOFU mentions."""
    canonical_map, excluded = _load_relations(relations)

    # Load all accepted mentions
    all_mentions: list[Mention] = load_admitted_mentions(mentions)
    click.echo(f"Admitted mentions: {len(all_mentions)}")

    # Filter and canonicalise
    included_facts: list[dict] = []
    skipped_excluded = 0
    skipped_unknown = 0
    skipped_duplicate = 0
    seen: set[tuple[str, str, str]] = set()

    for m in all_mentions:
        rel_lower = m.relation.lower()
        if rel_lower in excluded:
            skipped_excluded += 1
            continue
        if rel_lower not in canonical_map:
            skipped_unknown += 1
            continue

        canonical = canonical_map[rel_lower]
        key = (m.subject, canonical["id"], m.object_)
        if key in seen:
            skipped_duplicate += 1
            continue
        seen.add(key)

        included_facts.append(
            {
                "subject": m.subject,
                "canonical": canonical,
                "relation_label": canonical["label"],
                "object_": m.object_,
                "mention_ids": [m.mention_id],
            }
        )

    # Merge duplicate (subject, canonical_relation, object) mention_ids
    # (already deduplicated above, but if same triple appeared in two mentions
    # we'd have skipped; instead collect all mention_ids per triple)
    merged: dict[tuple[str, str, str], dict] = {}
    for m in all_mentions:
        rel_lower = m.relation.lower()
        if rel_lower in excluded or rel_lower not in canonical_map:
            continue
        canonical = canonical_map[rel_lower]
        key = (m.subject, canonical["id"], m.object_)
        if key not in merged:
            merged[key] = {
                "subject": m.subject,
                "canonical": canonical,
                "relation_label": canonical["label"],
                "object_": m.object_,
                "mention_ids": [],
            }
        merged[key]["mention_ids"].append(m.mention_id)

    included_facts = list(merged.values())

    click.echo(
        f"After D-63 filter: {len(included_facts)} unique facts "
        f"({skipped_excluded} excluded by class, "
        f"{skipped_unknown} unknown relation)"
    )

    # Build lookup tables for retained neighbourhood
    by_subject: dict[str, list[dict]] = defaultdict(list)
    by_relation: dict[str, list[dict]] = defaultdict(list)
    for f in included_facts:
        by_subject[f["subject"]].append(f)
        by_relation[f["canonical"]["id"]].append(f)

    # Emit contracts
    contracts = []
    for f in included_facts:
        subj = f["subject"]
        rel_id = f["canonical"]["id"]

        same_subj = [x for x in by_subject[subj] if x["canonical"]["id"] != rel_id]
        same_rel = [x for x in by_relation[rel_id] if x["subject"] != subj]

        contract = _make_contract(
            subject=subj,
            canonical=f["canonical"],
            object_=f["object_"],
            mention_ids=f["mention_ids"],
            same_subject_facts=same_subj,
            same_relation_facts=same_rel,
        )
        contracts.append(contract)

    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as fh:
        for c in contracts:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    # Write companion lineage file (schema-clean, no extension fields)
    lineage_path = out.parent / "facts_lineage.jsonl"
    with open(lineage_path, "w") as fh:
        for c in contracts:
            fh.write(
                json.dumps(
                    {"fact_id": c["fact_id"], "mention_ids": c["mention_ids"]},
                    ensure_ascii=False,
                )
                + "\n"
            )

    # Relation breakdown
    rel_counts: dict[str, int] = defaultdict(int)
    for f in included_facts:
        rel_counts[f["canonical"]["label"]] += 1

    click.echo(f"\nFacts written: {len(contracts)}")
    for rel, cnt in sorted(rel_counts.items()):
        click.echo(f"  {cnt:3d}  {rel}")
    click.echo(f"\nWritten: {out}")
    click.echo(f"Lineage: {lineage_path}")

    # Optional selection report
    if report:
        _write_report(report, contracts, rel_counts, skipped_excluded, skipped_unknown)
        click.echo(f"Report:  {report}")


def _write_report(
    path: Path,
    contracts: list[dict],
    rel_counts: dict[str, int],
    skipped_excluded: int,
    skipped_unknown: int,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# P1-1 Selection Report",
        "",
        f"**Facts selected:** {len(contracts)}  ",
        f"**Skipped (excluded class):** {skipped_excluded}  ",
        f"**Skipped (unknown relation):** {skipped_unknown}  ",
        "",
        "## Relation breakdown",
        "",
        "| Relation | Count |",
        "|---|---|",
    ]
    for rel, cnt in sorted(rel_counts.items()):
        lines.append(f"| {rel} | {cnt} |")

    lines += [
        "",
        "## Selected facts",
        "",
        "| fact_id | subject | relation | object |",
        "|---|---|---|---|",
    ]
    for c in contracts:
        t = c["triple"]
        lines.append(
            f"| `{c['fact_id']}` "
            f"| {t['subject']['label']} "
            f"| {t['relation']['label']} "
            f"| {t['object']['label']} |"
        )

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    cli()
