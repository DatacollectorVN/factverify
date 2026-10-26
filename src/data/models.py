"""Normalized data model for the FactVerify fact store (v2).

Four collections — entities, relations, facts, corpus — with referential IDs.
Each type has a frozen dataclass, plus load/save helpers that read/write
single JSON files under ``.factverify/{collection}/{local_id}.json``.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


# ── Slug / ID builders ──────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slug(*parts: str) -> str:
    """Build a local-id slug from one or more label parts.

    Lowercases, replaces non-alphanumeric runs with ``_``, strips edges.
    """
    raw = "_".join(parts).casefold()
    cleaned = _SLUG_RE.sub("_", raw).strip("_")
    if not cleaned or not cleaned[0].isalnum():
        raise ValueError(f"cannot build slug from {parts!r}")
    return cleaned


def entity_id(label: str) -> str:
    return f"factverify:entity:{slug(label)}"


def relation_id(label: str) -> str:
    return f"factverify:relation:{slug(label)}"


def fact_id(*parts: str) -> str:
    return f"factverify:fact:{slug(*parts)}"


def corpus_id(*parts: str) -> str:
    return f"factverify:corpus:{slug(*parts)}"


def local_id(full_id: str) -> str:
    """Strip the ``factverify:<type>:`` prefix, returning the local slug."""
    prefix_end = full_id.find(":", full_id.find(":") + 1)
    if prefix_end < 0:
        raise ValueError(f"malformed factverify id: {full_id!r}")
    return full_id[prefix_end + 1:]


# ── Alias ────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Alias:
    value: str
    language: str = "en"


# ── Entity ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Entity:
    id: str
    label: str
    description: str = ""
    alias: tuple[Alias, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "alias": [{"value": a.value, "language": a.language} for a in self.alias],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Entity:
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            description=str(data.get("description", "")),
            alias=tuple(
                Alias(value=str(a["value"]), language=str(a.get("language", "en")))
                for a in data.get("alias", [])
            ),
        )


# ── Relation ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    description: str = ""
    alias: tuple[Alias, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "description": self.description,
            "alias": [{"value": a.value, "language": a.language} for a in self.alias],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Relation:
        return cls(
            id=str(data["id"]),
            label=str(data["label"]),
            description=str(data.get("description", "")),
            alias=tuple(
                Alias(value=str(a["value"]), language=str(a.get("language", "en")))
                for a in data.get("alias", [])
            ),
        )


# ── Atomic-fact reference (inline in Fact) ───────────────────────────────────


@dataclass(frozen=True)
class AtomicFactRef:
    """Subject–relation–object triple with ID references to entity/relation."""

    subject_id: str
    subject_label: str
    relation_id: str
    relation_label: str
    object_id: str
    object_label: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "subject": {"id": self.subject_id, "label": self.subject_label},
            "relation": {"id": self.relation_id, "label": self.relation_label},
            "object": {"id": self.object_id, "label": self.object_label},
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AtomicFactRef:
        return cls(
            subject_id=str(data["subject"]["id"]),
            subject_label=str(data["subject"]["label"]),
            relation_id=str(data["relation"]["id"]),
            relation_label=str(data["relation"]["label"]),
            object_id=str(data["object"]["id"]),
            object_label=str(data["object"]["label"]),
        )


# ── Fact ─────────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FactSource:
    candidate_id: str
    source_row: int
    provenance: str
    review_model: str = ""
    review_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "candidate_id": self.candidate_id,
            "source_row": self.source_row,
            "provenance": self.provenance,
        }
        if self.review_model:
            d["review_model"] = self.review_model
        if self.review_reason:
            d["review_reason"] = self.review_reason
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> FactSource:
        return cls(
            candidate_id=str(data.get("candidate_id", "")),
            source_row=int(data.get("source_row", 0)),
            provenance=str(data.get("provenance", "")),
            review_model=str(data.get("review_model", "")),
            review_reason=str(data.get("review_reason", "")),
        )


@dataclass(frozen=True)
class Fact:
    id: str
    type: str
    atomic_fact: AtomicFactRef
    description: str = ""
    corpus: str | None = None
    neighbourhoods: tuple[str, ...] = ()
    source: FactSource | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "type": self.type,
            "atomic_fact": self.atomic_fact.to_dict(),
            "description": self.description,
            "corpus": self.corpus,
            "neighbourhoods": list(self.neighbourhoods),
            "source": self.source.to_dict() if self.source else None,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Fact:
        source_data = data.get("source")
        return cls(
            id=str(data["id"]),
            type=str(data["type"]),
            atomic_fact=AtomicFactRef.from_dict(data["atomic_fact"]),
            description=str(data.get("description", "")),
            corpus=data.get("corpus"),
            neighbourhoods=tuple(data.get("neighbourhoods") or []),
            source=FactSource.from_dict(source_data) if source_data else None,
        )


# ── Corpus ───────────────────────────────────────────────────────────────────

# Equivalence-closure direction values
EC_DIRECT = "direct"
EC_INVERSE = "inverse"
EC_CLOZE = "cloze"
EC_PARA = "para"
EC_VERIFY = "verify"

# Mapping from legacy direction names
_DIRECTION_TO_EC = {
    "forward": EC_DIRECT,
    "inverse": EC_INVERSE,
    "cloze": EC_CLOZE,
}


def direction_to_ec(direction: str) -> str:
    """Map a legacy direction value to the equivalence-closure label."""
    return _DIRECTION_TO_EC.get(direction, direction)


@dataclass(frozen=True)
class CorpusEntry:
    _id: int
    Q: str
    A: str
    ec: str
    language: str = "en"
    answer_type: str = ""       # "entity" or "relation"
    answer_factverify_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "_id": self._id,
            "Q": self.Q,
            "A": self.A,
            "ec": self.ec,
            "language": self.language,
            "answer_type": self.answer_type,
            "answer_factverify_id": self.answer_factverify_id,
        }
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CorpusEntry:
        ec = str(data.get("ec") or direction_to_ec(data.get("direction", "unknown")))
        return cls(
            _id=int(data["_id"]),
            Q=str(data["Q"]),
            A=str(data["A"]),
            ec=ec,
            language=str(data.get("language", "en")),
            answer_type=str(data.get("answer_type", "")),
            answer_factverify_id=str(data.get("answer_factverify_id", "")),
        )


@dataclass(frozen=True)
class ECCount:
    ec: str
    language: str
    num_train: int
    num_eval: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "ec": self.ec,
            "language": self.language,
            "num_train": self.num_train,
            "num_eval": self.num_eval,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ECCount:
        return cls(
            ec=str(data["ec"]),
            language=str(data["language"]),
            num_train=int(data["num_train"]),
            num_eval=int(data["num_eval"]),
        )


@dataclass(frozen=True)
class Corpus:
    id: str
    corpus_metadata: tuple[ECCount, ...] = ()
    train: tuple[CorpusEntry, ...] = ()
    eval: tuple[CorpusEntry, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "corpus_metadata": {
                "equivalent_closure": [ec.to_dict() for ec in self.corpus_metadata],
            },
            "train": [e.to_dict() for e in self.train],
            "eval": [e.to_dict() for e in self.eval],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Corpus:
        meta = data.get("corpus_metadata", {})
        ec_list = meta.get("equivalent_closure", [])
        return cls(
            id=str(data["id"]),
            corpus_metadata=tuple(ECCount.from_dict(ec) for ec in ec_list),
            train=tuple(CorpusEntry.from_dict(e) for e in data.get("train", [])),
            eval=tuple(CorpusEntry.from_dict(e) for e in data.get("eval", [])),
        )


def compute_ec_counts(
    train: tuple[CorpusEntry, ...],
    eval_entries: tuple[CorpusEntry, ...],
) -> tuple[ECCount, ...]:
    """Compute equivalent_closure summary from train and eval entries."""
    ec_langs: set[tuple[str, str]] = set()
    for e in (*train, *eval_entries):
        ec_langs.add((e.ec, e.language))

    counts: list[ECCount] = []
    for ec, lang in sorted(ec_langs):
        n_train = sum(1 for e in train if e.ec == ec and e.language == lang)
        n_eval = sum(1 for e in eval_entries if e.ec == ec and e.language == lang)
        counts.append(ECCount(ec=ec, language=lang, num_train=n_train, num_eval=n_eval))
    return tuple(counts)


# ── File I/O ─────────────────────────────────────────────────────────────────


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_entity(entity: Entity, path: Path) -> None:
    _write_json(path, entity.to_dict())


def load_entity(path: Path) -> Entity:
    return Entity.from_dict(_read_json(path))


def save_relation(relation: Relation, path: Path) -> None:
    _write_json(path, relation.to_dict())


def load_relation(path: Path) -> Relation:
    return Relation.from_dict(_read_json(path))


def save_fact(fact: Fact, path: Path) -> None:
    _write_json(path, fact.to_dict())


def load_fact(path: Path) -> Fact:
    return Fact.from_dict(_read_json(path))


def save_corpus(corpus: Corpus, path: Path) -> None:
    _write_json(path, corpus.to_dict())


def load_corpus(path: Path) -> Corpus:
    return Corpus.from_dict(_read_json(path))
