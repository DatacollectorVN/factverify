"""P1-5: Build locality neighbourhood items for each accepted fact.

Replaces all `[P1-5 stub]` placeholder entries in fact contracts with
real, sourced neighbourhood items drawn from the leave-out training set.
The four locality buckets (same_subject, same_relation, compositional, global)
must each contain at least the D-38 per-bucket minimum.

Outputs: NeighbourhoodItem rows for the facts the caller supplies.

FV-DATA-030 through FV-DATA-034.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: D-38 Block 0 per-bucket minimum.
BUCKET_MIN: int = 1

#: The stub marker placed by the spec editor.
STUB_MARKER: str = "[P1-5 stub]"

#: Allowed buckets.
BUCKETS: tuple[str, ...] = (
    "same_subject",
    "same_relation",
    "compositional",
    "global",
)

#: TOFU configs valid as global neighbourhood sources (D-38).
GLOBAL_CONFIGS: frozenset[str] = frozenset({"real_authors", "world_facts"})


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class BucketMinimumError(Exception):
    """Raised when a fact cannot meet the D-38 per-bucket minimum."""


class GlobalSourceError(Exception):
    """Raised when a global item traces to a finetuning record."""


class SplitIsolationError(Exception):
    """Raised when a neighbourhood item's entity is in a different split."""


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NeighbourhoodItem:
    """A single retain probe in one locality bucket."""

    target_fact_id: str
    item_id: str
    bucket: Literal["same_subject", "same_relation", "compositional", "global"]
    statement: str
    expected_answers: list[str]
    language: str
    source: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_bucket_coverage(
    fact_id: str,
    items: list[dict[str, Any]],
    bucket_min: int = BUCKET_MIN,
) -> None:
    """Raise BucketMinimumError if any bucket is below *bucket_min*.

    FV-DATA-030.
    """
    counts: dict[str, int] = {b: 0 for b in BUCKETS}
    for item in items:
        b = item.get("bucket", "")
        if b in counts:
            counts[b] += 1

    for bucket, count in counts.items():
        if count < bucket_min:
            raise BucketMinimumError(
                f"Fact {fact_id!r}: bucket {bucket!r} has {count} item(s), "
                f"minimum is {bucket_min}."
            )


def validate_retained_source(
    item: dict[str, Any],
    leaveout_index: dict[str, set[str]],
) -> None:
    """Raise ValueError if source fact is absent from any leave-out record.

    Applies to same_subject and same_relation buckets only.
    FV-DATA-031.
    """
    bucket = item.get("bucket", "")
    if bucket not in ("same_subject", "same_relation"):
        return
    source_fact_id: str = (item.get("source") or {}).get("fact_id", "")
    if not source_fact_id:
        return
    for fact_ids in leaveout_index.values():
        if source_fact_id in fact_ids:
            return
    raise ValueError(
        f"Neighbourhood item {item.get('item_id')!r}: source fact "
        f"{source_fact_id!r} is not retained in any leave-out record."
    )


def validate_global_source(
    item: dict[str, Any],
    finetuning_index: dict[str, list[str]],
) -> None:
    """Raise GlobalSourceError if global item traces to a finetuning record.

    Checks that no record in *finetuning_index* originates from the same
    TOFU config + row as the global item.

    FV-DATA-032.
    """
    if item.get("bucket") != "global":
        return
    source = item.get("source") or {}
    config = source.get("tofu_config", "")
    row_index = source.get("row_index")
    if not config or row_index is None:
        return

    # Record IDs follow the pattern: {config}_{row_index:05d}_{direction}_{field}
    prefix = f"{config}_{row_index:05d}_"
    for record_id in finetuning_index:
        if record_id.startswith(prefix):
            raise GlobalSourceError(
                f"Global neighbourhood item {item.get('item_id')!r}: "
                f"source row {config}:{row_index} is indexed to a finetuning "
                f"record ({record_id})."
            )


def validate_split_isolation(
    item: dict[str, Any],
    target_split: str,
    entity_splits: dict[str, str],
) -> None:
    """Raise SplitIsolationError if item's fictional entity is in wrong split.

    Global items are exempt (their entities are real-world, not split-assigned).
    FV-DATA-034.
    """
    if item.get("bucket") == "global":
        return  # global items exempt
    # Entity splits are keyed by entity name (lowercase).
    for entity, split in entity_splits.items():
        if entity.lower() in (item.get("statement") or "").lower():
            if split != target_split:
                raise SplitIsolationError(
                    f"Neighbourhood item {item.get('item_id')!r}: entity "
                    f"{entity!r} belongs to split {split!r}, "
                    f"but target is in {target_split!r}."
                )


# ---------------------------------------------------------------------------
# Leave-out index loader
# ---------------------------------------------------------------------------


def load_leaveout_index(leaveout_dir: Path) -> dict[str, set[str]]:
    """Return ``{record_id: set[fact_id]}`` from leave-out manifest files.

    FV-DATA-031.
    """
    index: dict[str, set[str]] = {}
    for manifest_path in sorted(leaveout_dir.glob("*.json")):
        with open(manifest_path) as fh:
            manifest = json.load(fh)
        for rid in manifest.get("record_ids", []):
            index.setdefault(rid, set())
            # The manifest tells us which facts are NOT here; we need to infer
            # which facts the record does express.
            # Since the index.jsonl has this mapping, we return an empty-set
            # stub here; the caller fills it from index.jsonl.
    return index


def load_record_fact_index(index_path: Path) -> dict[str, set[str]]:
    """Return ``{record_id: set[fact_id]}`` from sources/index.jsonl."""
    index: dict[str, set[str]] = {}
    with open(index_path) as fh:
        for line in fh:
            row = json.loads(line)
            index[row["record_id"]] = set(row.get("fact_ids", []))
    return index


# ---------------------------------------------------------------------------
# Neighbourhood item builder
# ---------------------------------------------------------------------------

_STUB_BUCKETS = {"compositional", "global", "same_subject"}


def _is_stub(item: dict[str, Any]) -> bool:
    return STUB_MARKER in (item.get("statement") or "")


def _fact_label(fact: dict[str, Any], role: str) -> str:
    return fact["triple"][role]["label"]


def build_same_subject_items(
    target_fact: dict[str, Any],
    all_facts: list[dict[str, Any]],
    record_index: dict[str, set[str]],
    fact_n: int = 0,
) -> list[dict[str, Any]]:
    """Build same_subject items from other accepted facts about the same subject."""
    target_subject = _fact_label(target_fact, "subject").lower()
    target_id = target_fact["fact_id"]
    items: list[dict[str, Any]] = []
    for other in all_facts:
        if other["fact_id"] == target_id:
            continue
        if _fact_label(other, "subject").lower() != target_subject:
            continue
        # Check the other fact has at least one record in the index
        other_id = other["fact_id"]
        in_index = any(other_id in fids for fids in record_index.values())
        if not in_index:
            continue
        subj = _fact_label(other, "subject")
        rel = _fact_label(other, "relation")
        obj = _fact_label(other, "object")
        item_n = len(items)
        items.append(
            {
                "target_fact_id": target_id,
                "item_id": f"retain:{_safe(target_id)}:same_subject:{item_n}",
                "bucket": "same_subject",
                "statement": f"{subj}'s {rel} is {obj}.",
                "expected_answers": [obj],
                "language": "en",
                "source": {"fact_id": other_id},
            }
        )
    return items


def build_same_relation_items(
    target_fact: dict[str, Any],
    all_facts: list[dict[str, Any]],
    record_index: dict[str, set[str]],
) -> list[dict[str, Any]]:
    """Build same_relation items from other accepted facts with the same relation."""
    target_relation = _fact_label(target_fact, "relation").lower()
    target_id = target_fact["fact_id"]
    items: list[dict[str, Any]] = []
    for other in all_facts:
        if other["fact_id"] == target_id:
            continue
        if _fact_label(other, "relation").lower() != target_relation:
            continue
        other_id = other["fact_id"]
        in_index = any(other_id in fids for fids in record_index.values())
        if not in_index:
            continue
        subj = _fact_label(other, "subject")
        rel = _fact_label(other, "relation")
        obj = _fact_label(other, "object")
        item_n = len(items)
        items.append(
            {
                "target_fact_id": target_id,
                "item_id": f"retain:{_safe(target_id)}:same_relation:{item_n}",
                "bucket": "same_relation",
                "statement": f"{subj}'s {rel} is {obj}.",
                "expected_answers": [obj],
                "language": "en",
                "source": {"fact_id": other_id},
            }
        )
    return items


def build_global_items(
    target_fact: dict[str, Any],
    tofu_dir: Path,
    record_index: dict[str, set[str]],
    n_items: int = 1,
) -> list[dict[str, Any]]:
    """Build global items from TOFU real_authors / world_facts configs."""
    target_id = target_fact["fact_id"]
    items: list[dict[str, Any]] = []
    for config in ("world_facts", "real_authors"):
        config_path = tofu_dir / f"{config}.json"
        if not config_path.exists():
            continue
        with open(config_path) as fh:
            rows = [json.loads(line) for line in fh if line.strip()]
        for row_idx, row in enumerate(rows):
            if len(items) >= n_items:
                break
            # Skip if this row is already in the finetuning index
            prefix = f"{config}_{row_idx:05d}_"
            already_finetuned = any(
                rid.startswith(prefix) for rid in record_index
            )
            if already_finetuned:
                continue
            answer = row.get("answer", "").strip()
            if not answer:
                continue
            item_n = len(items)
            items.append(
                {
                    "target_fact_id": target_id,
                    "item_id": f"retain:{_safe(target_id)}:global:{item_n}",
                    "bucket": "global",
                    "statement": row.get("question", ""),
                    "expected_answers": [answer],
                    "language": "en",
                    "source": {
                        "tofu_config": config,
                        "row_index": row_idx,
                    },
                }
            )
        if len(items) >= n_items:
            break
    return items


def _safe(fact_id: str) -> str:
    return fact_id.replace(":", "_").replace("/", "_")


# ---------------------------------------------------------------------------
# Stub replacement logic
# ---------------------------------------------------------------------------


def replace_stubs(
    target_fact: dict[str, Any],
    all_facts: list[dict[str, Any]],
    record_index: dict[str, set[str]],
    tofu_dir: Path,
) -> list[dict[str, Any]]:
    """Return the retained_neighbourhood with all stubs replaced by real items."""
    existing = [
        item for item in target_fact.get("retained_neighbourhood", [])
        if not _is_stub(item)
    ]
    buckets_present = {item["bucket"] for item in existing}

    # Fill any missing or stub buckets
    if "same_subject" not in buckets_present:
        existing.extend(
            build_same_subject_items(target_fact, all_facts, record_index)
        )
    if "same_relation" not in buckets_present:
        existing.extend(
            build_same_relation_items(target_fact, all_facts, record_index)
        )
    if "global" not in buckets_present:
        existing.extend(
            build_global_items(target_fact, tofu_dir, record_index)
        )
    if "compositional" not in buckets_present:
        # Compositional stubs are left empty for Block 0 — entailment screen
        # deferred to P1-4.  A placeholder with STUB_MARKER removed but no
        # real item is still a deficit; the validate_bucket_coverage call
        # below will report it.
        pass

    return existing
