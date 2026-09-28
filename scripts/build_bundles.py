"""P1-3: Build source bundles and leave-out manifests.

For each accepted fact contract, enumerates all TOFU training records that
express the fact (both forward and inverse direction), assembles a SourceBundle,
writes a record-to-fact index, and produces one leave-out manifest per fact.

Outputs:
    data/controlled/sources/records.jsonl     — all TrainingRecord rows
    data/controlled/sources/index.jsonl       — record_id → fact_ids
    data/controlled/sources/bundles/<id>.json — SourceBundle per fact
    data/controlled/leaveout/<id>.json        — LeaveOutManifest per fact
    data/tofu_derived/transformations.jsonl   — appended transformation entries

FV-DATA-018 through FV-DATA-024.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

import click

from src.data.digests import sha256_of_ids
from src.data.spec_readers import load_template_groups
from src.data.tofu import load_accepted_facts, load_tofu_rows

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: D-66 Block 0 direction minimum.
DIRECTION_MIN: int = 3

#: TOFU config used for training records.
TRAIN_CONFIG: str = "full"

#: TOFU rows per fictional author.
ROWS_PER_AUTHOR: int = 20


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BuildGateError(Exception):
    """Raised when a fact contract does not have an acceptable gate status."""


class DirectionMinimumError(Exception):
    """Raised when a bundle falls below the D-66 minimum for a direction."""


class TemplateDisjointError(Exception):
    """Raised when a training record instantiates an evaluation template group."""


# ---------------------------------------------------------------------------
# Dataclasses (immutable, per data-model.md)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TrainingRecord:
    """A single TOFU row field used as a training example."""

    record_id: str
    text: str
    direction: Literal["forward", "inverse"]
    source_row: dict[str, Any]
    derived_from: str | None

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


@dataclass(frozen=True)
class SourceBundle:
    """Forward + inverse training records for one target fact."""

    fact_id: str
    forward_record_ids: list[str]
    inverse_record_ids: list[str]
    bundle_digest: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_id": self.fact_id,
            "forward_record_ids": list(self.forward_record_ids),
            "inverse_record_ids": list(self.inverse_record_ids),
            "bundle_digest": self.bundle_digest,
        }


@dataclass(frozen=True)
class LeaveOutManifest:
    """All training records except those in a target fact's bundle."""

    unit_id: str
    record_ids: list[str]
    dataset_digest: str
    excluded_fact_ids: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "record_ids": list(self.record_ids),
            "dataset_digest": self.dataset_digest,
            "excluded_fact_ids": list(self.excluded_fact_ids),
        }


# ---------------------------------------------------------------------------
# Gate guard (FV-DATA-018)
# ---------------------------------------------------------------------------

_ACCEPTED_STATUSES: frozenset[str] = frozenset({"draft", "frozen"})


def check_fact_gate(fact: dict[str, Any]) -> None:
    """Raise BuildGateError if *fact* does not have an acceptable gate status.

    - ``draft``: accepted unconditionally (Block 0 pilot mode, pre-freeze).
    - ``frozen`` with ``gate_result.verdict == "pass"``: accepted.
    - ``frozen`` with any other verdict: rejected.
    - Any other ``contract_status``: rejected.

    FV-DATA-018.
    """
    status = fact.get("contract_status")
    if status == "draft":
        return
    if status == "frozen":
        gate_result = fact.get("gate_result") or {}
        verdict = gate_result.get("verdict")
        if verdict == "pass":
            return
        raise BuildGateError(
            f"Fact {fact.get('fact_id')!r} is frozen but gate_result.verdict="
            f"{verdict!r} (expected 'pass')"
        )
    raise BuildGateError(
        f"Fact {fact.get('fact_id')!r} has unacceptable "
        f"contract_status={status!r}"
    )


# ---------------------------------------------------------------------------
# Template disjointness (FV-DATA-021 / D-42)
# ---------------------------------------------------------------------------


def check_template_disjoint(
    record_text: str,
    fact_subject: str,
    fact_object: str,
    template_groups: dict[str, list[str]],
) -> None:
    """Raise TemplateDisjointError if *record_text* matches a template pattern.

    Matching strategy: for each template text, replace ``{subject}`` with the
    fact's subject label and ``{object}`` with the object label, then check
    for an exact substring match (case-insensitive).  Any match disqualifies
    the record.

    FV-DATA-021 / D-42.
    """
    record_lower = record_text.lower()
    for group_id, patterns in template_groups.items():
        for pattern in patterns:
            filled = (
                pattern.replace("{subject}", fact_subject)
                .replace("{object}", fact_object)
                .lower()
            )
            if filled in record_lower:
                raise TemplateDisjointError(
                    f"Training record instantiates evaluation template group "
                    f"{group_id!r}: pattern {pattern!r} matched in text."
                )


# ---------------------------------------------------------------------------
# Multi-target detection (FV-DATA-022)
# ---------------------------------------------------------------------------


def detect_multi_fact_records(index: dict[str, list[str]]) -> list[str]:
    """Return record IDs that map to more than one target fact.

    FV-DATA-022.
    """
    return [rid for rid, fids in index.items() if len(fids) > 1]


# ---------------------------------------------------------------------------
# Index validation (FV-DATA-023)
# ---------------------------------------------------------------------------


def validate_index(
    records: list[dict[str, Any]],
    index: dict[str, list[str]],
) -> None:
    """Raise ValueError if any record is absent from *index*.

    FV-DATA-023.
    """
    for rec in records:
        rid = rec["record_id"]
        if rid not in index:
            raise ValueError(
                f"Record {rid!r} is missing from the index."
            )


# ---------------------------------------------------------------------------
# Bundle construction (FV-DATA-019 / FV-DATA-020)
# ---------------------------------------------------------------------------


def build_bundle(
    fact_id: str,
    forward_ids: list[str],
    inverse_ids: list[str],
    direction_min: int = DIRECTION_MIN,
) -> SourceBundle:
    """Assemble a SourceBundle and validate direction minimums.

    Raises ``DirectionMinimumError`` if either direction is below
    *direction_min* (D-66 default: 3).

    FV-DATA-019 / FV-DATA-020.
    """
    if len(forward_ids) < direction_min:
        raise DirectionMinimumError(
            f"Fact {fact_id!r}: forward direction has {len(forward_ids)} "
            f"record(s), minimum is {direction_min}."
        )
    if len(inverse_ids) < direction_min:
        raise DirectionMinimumError(
            f"Fact {fact_id!r}: inverse direction has {len(inverse_ids)} "
            f"record(s), minimum is {direction_min}."
        )
    all_ids = list(forward_ids) + list(inverse_ids)
    digest = sha256_of_ids(all_ids)
    return SourceBundle(
        fact_id=fact_id,
        forward_record_ids=list(forward_ids),
        inverse_record_ids=list(inverse_ids),
        bundle_digest=digest,
    )


# ---------------------------------------------------------------------------
# Leave-out manifest (FV-DATA-024)
# ---------------------------------------------------------------------------


def build_leaveout_manifest(
    fact_id: str,
    all_record_ids: list[str],
    bundle_record_ids: list[str],
) -> LeaveOutManifest:
    """Build a leave-out manifest excluding bundle records.

    FV-DATA-024.
    """
    excluded_set = set(bundle_record_ids)
    retained = [rid for rid in all_record_ids if rid not in excluded_set]
    digest = sha256_of_ids(retained)
    return LeaveOutManifest(
        unit_id=fact_id,
        record_ids=retained,
        dataset_digest=digest,
        excluded_fact_ids=[fact_id],
    )


# ---------------------------------------------------------------------------
# TOFU row scanning — find records expressing a fact
# ---------------------------------------------------------------------------

_MENTION_ID_RE = re.compile(r"full_0*(\d+)_")


def _author_row_range(fact: dict[str, Any]) -> tuple[int, int] | None:
    """Return (start, end) TOFU row range for the fact's author.

    Derived from the first ``full_*`` mention ID.  Returns None if no mention
    IDs are present (fact has no known TOFU author block).
    """
    for mid in fact.get("mention_ids", []):
        m = _MENTION_ID_RE.match(mid)
        if m:
            row_idx = int(m.group(1))
            author = row_idx // ROWS_PER_AUTHOR
            return author * ROWS_PER_AUTHOR, (author + 1) * ROWS_PER_AUTHOR
    return None


def _aliases(fact: dict[str, Any], role: str) -> list[str]:
    """Return text aliases for subject, relation, or object."""
    return [
        a["text"]
        for a in fact.get("aliases", {}).get(role, [])
        if a.get("text")
    ]


def _label(fact: dict[str, Any], role: str) -> str:
    return fact["triple"][role]["label"]


def _contains(text: str, candidates: list[str]) -> bool:
    low = text.lower()
    return any(c.lower() in low for c in candidates if c)


def find_expressing_rows(
    fact: dict[str, Any],
    tofu_rows: list[dict[str, str]],
    row_start: int,
) -> list[tuple[int, str, str]]:
    """Return ``(row_index, direction, field)`` for rows expressing *fact*.

    A row expresses the fact when:
    - The full row text (Q+A) contains any subject alias, AND
    - The full row text contains any object alias.

    Direction:
    - ``"forward"``: object alias appears in the ``answer`` field.
    - ``"inverse"``: object alias appears in the ``question`` field.

    A row where the object appears in BOTH fields yields two entries.
    """
    subjects = [_label(fact, "subject")] + _aliases(fact, "subject")
    objects = [_label(fact, "object")] + _aliases(fact, "object")

    results: list[tuple[int, str, str]] = []
    for local_idx, row in enumerate(tofu_rows):
        row_idx = row_start + local_idx
        full_text = row.get("question", "") + " " + row.get("answer", "")
        if not _contains(full_text, subjects):
            continue
        if not _contains(full_text, objects):
            continue
        obj_in_q = _contains(row.get("question", ""), objects)
        obj_in_a = _contains(row.get("answer", ""), objects)
        if obj_in_a:
            results.append((row_idx, "forward", "answer"))
        if obj_in_q:
            results.append((row_idx, "inverse", "question"))
    return results


# ---------------------------------------------------------------------------
# Record construction from TOFU rows
# ---------------------------------------------------------------------------


def _make_record(
    config: str,
    row_idx: int,
    direction: str,
    field: str,
    text: str,
) -> TrainingRecord:
    record_id = f"{config}_{row_idx:05d}_{direction}_{field[0]}"
    return TrainingRecord(
        record_id=record_id,
        text=text,
        direction=direction,  # type: ignore[arg-type]
        source_row={"config": config, "row_index": row_idx, "field": field},
        derived_from=None,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """P1-3 fact bundle preparation tools."""


@cli.command()
@click.option(
    "--facts",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to facts.jsonl (accepted fact contracts).",
)
@click.option(
    "--mentions",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to mentions.jsonl (adjudicated mention pool).",
)
@click.option(
    "--source",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to pinned TOFU snapshot directory.",
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
    help="Output root directory (sources/). Will be created.",
)
@click.option(
    "--leaveout",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for leave-out manifests.",
)
@click.option(
    "--transforms",
    required=True,
    type=click.Path(path_type=Path),
    help="transformations.jsonl — appended with new entries.",
)
@click.option(
    "--direction-min",
    default=DIRECTION_MIN,
    show_default=True,
    type=int,
    help="Minimum records per direction (D-66).",
)
def build(
    facts: Path,
    mentions: Path,
    source: Path,
    spec_root: Path,
    out: Path,
    leaveout: Path,
    transforms: Path,
    direction_min: int,
) -> None:
    """P1-3: Build source bundles + leave-out manifests from TOFU."""
    # --- Setup output dirs ---
    bundles_dir = out / "bundles"
    bundles_dir.mkdir(parents=True, exist_ok=True)
    leaveout.mkdir(parents=True, exist_ok=True)
    out.mkdir(parents=True, exist_ok=True)

    # --- Load inputs ---
    accepted_facts = load_accepted_facts(facts)
    template_groups = load_template_groups(spec_root)
    tofu_rows = load_tofu_rows(source, TRAIN_CONFIG)

    # --- Process each fact ---
    all_records: list[TrainingRecord] = []
    # index: record_id → list of fact_ids
    global_index: dict[str, list[str]] = {}
    bundles: dict[str, SourceBundle] = {}
    transformation_entries: list[dict[str, Any]] = []

    n_below_min = 0
    n_multi_exclusions = 0

    for fact in accepted_facts:
        fact_id: str = fact["fact_id"]

        # Gate guard (FV-DATA-018)
        try:
            check_fact_gate(fact)
        except BuildGateError as exc:
            click.echo(f"[SKIP gate] {exc}", err=True)
            continue

        # Find the author's TOFU row range
        row_range = _author_row_range(fact)
        if row_range is None:
            click.echo(f"[SKIP no-range] {fact_id}: no mention_ids", err=True)
            n_below_min += 1
            continue
        row_start, row_end = row_range
        author_rows = tofu_rows[row_start:row_end]

        # Find rows expressing this fact
        expressing = find_expressing_rows(fact, author_rows, row_start)

        # Build records, checking template disjointness
        fact_fwd: list[TrainingRecord] = []
        fact_inv: list[TrainingRecord] = []
        subj_label = _label(fact, "subject")
        obj_label = _label(fact, "object")

        for row_idx, direction, field in expressing:
            row = tofu_rows[row_idx]
            text = row[field]
            # FV-DATA-021: template disjointness
            try:
                check_template_disjoint(
                    text, subj_label, obj_label, template_groups
                )
            except TemplateDisjointError as exc:
                transformation_entries.append(
                    {
                        "action": "exclude",
                        "source_record_id": f"{TRAIN_CONFIG}_{row_idx:05d}_{field[0]}",
                        "derived_record_ids": [],
                        "reason": str(exc),
                        "phase": "P1-3",
                    }
                )
                continue

            record = _make_record(TRAIN_CONFIG, row_idx, direction, field, text)

            # Deduplicate
            if record.record_id in global_index:
                continue

            if direction == "forward":
                fact_fwd.append(record)
            else:
                fact_inv.append(record)

        # D-66 direction minimum check
        try:
            bundle = build_bundle(
                fact_id,
                [r.record_id for r in fact_fwd],
                [r.record_id for r in fact_inv],
                direction_min=direction_min,
            )
        except DirectionMinimumError as exc:
            click.echo(f"[BELOW-MIN] {exc}", err=True)
            n_below_min += 1
            # Still build a partial bundle (skip minimum enforcement)
            all_ids = [r.record_id for r in fact_fwd + fact_inv]
            digest = sha256_of_ids(all_ids) if all_ids else ""
            bundle = SourceBundle(
                fact_id=fact_id,
                forward_record_ids=[r.record_id for r in fact_fwd],
                inverse_record_ids=[r.record_id for r in fact_inv],
                bundle_digest=digest,
            )

        # Register records in global index
        for rec in fact_fwd + fact_inv:
            all_records.append(rec)
            global_index.setdefault(rec.record_id, [])
            if fact_id not in global_index[rec.record_id]:
                global_index[rec.record_id].append(fact_id)

        bundles[fact_id] = bundle

    # --- Multi-fact record detection (FV-DATA-022) ---
    multi_record_ids = detect_multi_fact_records(global_index)
    if multi_record_ids:
        for rid in multi_record_ids:
            click.echo(f"[MULTI-FACT] {rid} → {global_index[rid]}", err=True)
            transformation_entries.append(
                {
                    "action": "exclude",
                    "source_record_id": rid,
                    "derived_record_ids": [],
                    "reason": (
                        f"Multi-target record: expresses facts "
                        f"{global_index[rid]}"
                    ),
                    "phase": "P1-3",
                }
            )
            n_multi_exclusions += 1
            # Remove from global_index and all_records for cleanliness
            for fact_id, bundle in list(bundles.items()):
                if rid in bundle.forward_record_ids or rid in bundle.inverse_record_ids:
                    fwd = [r for r in bundle.forward_record_ids if r != rid]
                    inv = [r for r in bundle.inverse_record_ids if r != rid]
                    bundles[fact_id] = SourceBundle(
                        fact_id=fact_id,
                        forward_record_ids=fwd,
                        inverse_record_ids=inv,
                        bundle_digest=sha256_of_ids(fwd + inv),
                    )
        # Remove multi-fact records from global index
        for rid in multi_record_ids:
            del global_index[rid]
        multi_set = set(multi_record_ids)
        all_records = [r for r in all_records if r.record_id not in multi_set]

    # --- Validate index completeness (FV-DATA-023) ---
    validate_index([{"record_id": r.record_id} for r in all_records], global_index)

    # --- Write records.jsonl ---
    records_path = out / "records.jsonl"
    with open(records_path, "w") as fh:
        for rec in all_records:
            fh.write(json.dumps(rec.to_dict()) + "\n")

    # --- Write index.jsonl ---
    index_path = out / "index.jsonl"
    with open(index_path, "w") as fh:
        for rid, fids in sorted(global_index.items()):
            fh.write(json.dumps({"record_id": rid, "fact_ids": fids}) + "\n")

    # --- Write bundles ---
    for fact_id, bundle in bundles.items():
        safe_id = fact_id.replace(":", "_").replace("/", "_")
        bundle_path = bundles_dir / f"{safe_id}.json"
        with open(bundle_path, "w") as fh:
            json.dump(bundle.to_dict(), fh, indent=2)
            fh.write("\n")

    # --- Build and write leave-out manifests (FV-DATA-024) ---
    all_record_ids = [r.record_id for r in all_records]
    for fact_id, bundle in bundles.items():
        bundle_ids = bundle.forward_record_ids + bundle.inverse_record_ids
        manifest = build_leaveout_manifest(fact_id, all_record_ids, bundle_ids)
        safe_id = fact_id.replace(":", "_").replace("/", "_")
        manifest_path = leaveout / f"{safe_id}.json"
        with open(manifest_path, "w") as fh:
            json.dump(manifest.to_dict(), fh, indent=2)
            fh.write("\n")

    # --- Append transformation entries ---
    if transformation_entries:
        with open(transforms, "a") as fh:
            for entry in transformation_entries:
                fh.write(json.dumps(entry) + "\n")

    # --- Summary ---
    n_built = len(bundles)
    click.echo(
        f"Built {n_built} bundles | "
        f"{n_below_min} below direction minimum | "
        f"{n_multi_exclusions} multi-fact exclusions | "
        f"Written: {out}"
    )
    click.echo(f"Leave-out manifests: {len(bundles)} written to {leaveout}")


if __name__ == "__main__":
    cli()
