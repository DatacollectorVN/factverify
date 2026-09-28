"""Entity-disjoint split assignment and the final-test loader guard."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.data.decisions import D68Decision
from src.data.errors import DataError
from src.decisions.resolver import resolve_or_none
from src.train.config import hash_mapping

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

_LABELS = ("construction", "calibration", "unassigned")


@dataclass(frozen=True)
class _Group:
    author_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    relations: frozenset[str]


def assign_splits(
    *,
    facts: list[dict[str, Any]],
    gate_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
    decision: D68Decision,
    seed: int,
    out: Path | None = None,
) -> dict[str, Any]:
    """Pack whole authors into the declared counts. Failure leaves out untouched."""
    eligible = [fact for fact in facts if _eligible(fact, gate_rows, audit_rows)]
    needed = decision.construction + decision.calibration
    if len(eligible) < needed:
        raise DataError(
            f"construction={decision.construction} calibration={decision.calibration} "
            f"eligible={len(eligible)}"
        )
    groups = _groups(eligible)
    placed = _place(groups, decision, seed)
    entities: dict[str, str] = {}
    fact_labels: dict[str, str] = {}
    for group, label in placed:
        for author in group.author_ids:
            entities[author] = label
        for fact_id in group.fact_ids:
            fact_labels[fact_id] = label
    validate_splits({"entities": entities, "facts": fact_labels}, eligible)
    body = {"entities": entities, "facts": fact_labels}
    d68_entry = resolve_or_none("D-68", _CATALOG)
    payload: dict[str, Any] = {
        "block": decision.block,
        "seed": seed,
        "digest": hash_mapping(body),
        "decision_id": "D-68",
        "decision_key": d68_entry.key if d68_entry is not None else None,
        "entities": entities,
        "facts": fact_labels,
    }
    if "final_test" in fact_labels.values() or "final_test" in entities.values():
        raise DataError("final_test")
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        temporary = out.with_suffix(out.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(out)
    return payload


def validate_splits(payload: dict[str, Any], facts: list[dict[str, Any]]) -> None:
    """Raise when one author, or a linked object author, has two labels."""
    labels = payload.get("facts")
    if not isinstance(labels, dict):
        raise DataError("facts")
    fact_author = {str(fact.get("fact_id")): _subject_id(fact) for fact in facts}
    by_author: dict[str, set[str]] = {}
    for fact_id, label in labels.items():
        author = fact_author.get(str(fact_id))
        if author is None:
            continue
        by_author.setdefault(author, set()).add(str(label))
    for author, seen in by_author.items():
        if len(seen) > 1:
            raise DataError(author)
    authors = set(fact_author.values())
    for fact in facts:
        fact_id = str(fact.get("fact_id"))
        if fact_id not in labels:
            continue
        obj = _object_id(fact)
        if obj not in authors:
            continue
        subject_label = str(labels[fact_id])
        object_labels = {
            str(labels[other])
            for other, author in fact_author.items()
            if author == obj and other in labels
        }
        if object_labels and subject_label not in object_labels:
            raise DataError(obj)


def load_split(
    path: Path,
    split: str,
    *,
    role: str,
    access_log: Path,
) -> list[str]:
    """Return fact ids for a split. Final-test reads are logged when refused."""
    if split not in {"construction", "calibration", "final_test"}:
        raise DataError(split)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise DataError(str(path))
    labels = loaded.get("facts")
    if not isinstance(labels, dict):
        raise DataError("facts")
    if split == "final_test":
        ids = [str(fact_id) for fact_id, label in labels.items() if label == split]
        if role != "final_test_pass":
            _deny(access_log, split, role, "role", path)
            raise DataError("role")
        if not ids:
            _deny(access_log, split, role, "empty_split", path)
            raise DataError("empty_split")
        return ids
    return [str(fact_id) for fact_id, label in labels.items() if label == split]


def _place(
    groups: list[_Group], decision: D68Decision, seed: int
) -> list[tuple[_Group, str]]:
    ordered = list(groups)
    random.Random(seed).shuffle(ordered)
    relation_index = {name: bit for bit, name in enumerate(decision.relations)}
    full = (1 << len(decision.relations)) - 1
    masks = [_mask(group, relation_index) for group in ordered]
    sizes = [len(group.fact_ids) for group in ordered]
    current: dict[
        tuple[int, int, int, int],
        tuple[tuple[int, int, int, int] | None, int],
    ] = {(0, 0, 0, 0): (None, -1)}
    layers: list[
        dict[
            tuple[int, int, int, int],
            tuple[tuple[int, int, int, int] | None, int],
        ]
    ] = [current]
    for index in range(len(ordered)):
        nxt: dict[
            tuple[int, int, int, int],
            tuple[tuple[int, int, int, int] | None, int],
        ] = {}
        size = sizes[index]
        mask = masks[index]
        for state in current:
            cons, cal, cons_mask, cal_mask = state
            options = (
                (
                    0,
                    cons + size,
                    cal,
                    cons_mask | mask,
                    cal_mask,
                    cons + size <= decision.construction,
                ),
                (
                    1,
                    cons,
                    cal + size,
                    cons_mask,
                    cal_mask | mask,
                    cal + size <= decision.calibration,
                ),
                (2, cons, cal, cons_mask, cal_mask, True),
            )
            for choice, next_cons, next_cal, next_cm, next_km, allowed in options:
                if not allowed:
                    continue
                key = (next_cons, next_cal, next_cm, next_km)
                if key not in nxt:
                    nxt[key] = (state, choice)
        current = nxt
        layers.append(current)
        if not current:
            break
    target = (decision.construction, decision.calibration, full, full)
    if target not in current:
        raise DataError(_count_message(ordered, decision))
    choices = [2] * len(ordered)
    state: tuple[int, int, int, int] | None = target
    for index in range(len(ordered) - 1, -1, -1):
        layer = layers[index + 1]
        if state not in layer:
            raise DataError(_count_message(ordered, decision))
        previous, choice = layer[state]
        choices[index] = choice
        state = previous
    return [
        (group, _LABELS[choice]) for group, choice in zip(ordered, choices, strict=True)
    ]


def _mask(group: _Group, relation_index: dict[str, int]) -> int:
    mask = 0
    for relation in group.relations:
        bit = relation_index.get(relation)
        if bit is not None:
            mask |= 1 << bit
    return mask


def _count_message(groups: list[_Group], decision: D68Decision) -> str:
    totals: dict[str, int] = {name: 0 for name in decision.relations}
    for group in groups:
        for relation in group.relations:
            if relation in totals:
                totals[relation] += len(group.fact_ids)
    rendered = " ".join(f"{name}={count}" for name, count in totals.items())
    return (
        f"construction={decision.construction} calibration={decision.calibration} "
        f"{rendered}"
    )


def _eligible(
    fact: dict[str, Any],
    gate_rows: list[dict[str, Any]],
    audit_rows: list[dict[str, Any]],
) -> bool:
    fact_id = fact.get("fact_id")
    verdicts = [
        row.get("verdict") for row in gate_rows if row.get("fact_id") == fact_id
    ]
    if verdicts != ["pass"]:
        return False
    audits = [
        row.get("verdict") for row in audit_rows if row.get("target_fact_id") == fact_id
    ]
    return bool(audits) and all(verdict == "clean" for verdict in audits)


def _groups(facts: list[dict[str, Any]]) -> list[_Group]:
    authors = {_subject_id(fact) for fact in facts}
    parent = {author: author for author in authors}

    def find(author: str) -> str:
        while parent[author] != author:
            parent[author] = parent[parent[author]]
            author = parent[author]
        return author

    def union(left: str, right: str) -> None:
        parent[find(left)] = find(right)

    for fact in facts:
        obj = _object_id(fact)
        if obj in authors:
            union(_subject_id(fact), obj)
    buckets: dict[str, list[dict[str, Any]]] = {}
    for fact in facts:
        buckets.setdefault(find(_subject_id(fact)), []).append(fact)
    groups: list[_Group] = []
    for root in sorted(buckets):
        members = buckets[root]
        author_ids = tuple(sorted({_subject_id(fact) for fact in members}))
        fact_ids = tuple(str(fact.get("fact_id")) for fact in members)
        relations = frozenset(_relation(fact) for fact in members)
        groups.append(_Group(author_ids, fact_ids, relations))
    return groups


def _subject_id(fact: dict[str, Any]) -> str:
    triple = fact.get("triple")
    if not isinstance(triple, dict):
        raise DataError("triple")
    subject = triple.get("subject")
    if not isinstance(subject, dict) or not isinstance(subject.get("id"), str):
        raise DataError("subject")
    return str(subject["id"])


def _object_id(fact: dict[str, Any]) -> str:
    triple = fact.get("triple")
    if not isinstance(triple, dict):
        raise DataError("triple")
    obj = triple.get("object")
    if not isinstance(obj, dict) or not isinstance(obj.get("id"), str):
        raise DataError("object")
    return str(obj["id"])


def _relation(fact: dict[str, Any]) -> str:
    triple = fact.get("triple")
    if not isinstance(triple, dict):
        raise DataError("triple")
    relation = triple.get("relation")
    if not isinstance(relation, dict) or not isinstance(relation.get("label"), str):
        raise DataError("relation")
    return str(relation["label"])


def _deny(log: Path, split: str, role: str, reason: str, path: Path) -> None:
    log.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(
        {"split": split, "role": role, "reason": reason, "path": str(path)},
        sort_keys=True,
    )
    with log.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
