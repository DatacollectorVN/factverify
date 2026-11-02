"""Manifest-only access to training text. One file per item id."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .errors import FactVerifyHarnessError

#: The five equivalence-closure families defined by the fact contract.
CANONICAL_FAMILIES: tuple[str, ...] = ("direct", "inverse", "cloze", "para", "verify")


def canonicalize_family(value: str) -> str:
    """Normalize a raw ``ec``/``direction`` label to a canonical family name.

    Matching is case-insensitive against :data:`CANONICAL_FAMILIES`. Values
    that do not match any canonical family are returned lower-cased and
    unchanged otherwise, so unexpected labels are preserved rather than
    silently dropped.
    """
    lowered = value.strip().lower()
    for family in CANONICAL_FAMILIES:
        if lowered == family:
            return family
    return lowered or "unknown"


@dataclass(frozen=True)
class EvalProbe:
    """One evaluation probe with the metadata needed for raw, auditable output."""

    probe_id: str
    fact_id: str
    family: str
    language: str
    question: str
    answer: str


class DataCatalog:
    """The only reader of training text for a job."""

    def __init__(self, corpus_dir: Path, allowed_ids: list[str]) -> None:
        self.corpus_dir = corpus_dir
        self.allowed_ids = list(allowed_ids)
        self._allowed = set(allowed_ids)
        self.access_log: list[str] = []

    def _corpus_path(self, item_id: str) -> Path:
        """Resolve the corpus file for *item_id*.

        Supports layouts (checked in order):
          1. flat JSON v2:  {corpus_dir}/{item_id}.json
          2. nested JSON v1: {corpus_dir}/{item_id}/corpus.json
          3. nested TXT:     {corpus_dir}/{item_id}/corpus.txt   (legacy)
          4. flat TXT:       {corpus_dir}/{item_id}.txt           (legacy)
        """
        # v2: flat JSON file
        flat_json = self.corpus_dir / f"{item_id}.json"
        if flat_json.is_file():
            return flat_json
        # v1: nested directory
        json_path = self.corpus_dir / item_id / "corpus.json"
        if json_path.is_file():
            return json_path
        txt_path = self.corpus_dir / item_id / "corpus.txt"
        if txt_path.is_file():
            return txt_path
        flat_path = self.corpus_dir / f"{item_id}.txt"
        if flat_path.is_file():
            return flat_path
        raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")

    def get(self, item_id: str) -> str:
        """Return the raw text for *item_id* (legacy, whole-document)."""
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self._corpus_path(item_id)
        self.access_log.append(item_id)
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            # Build text from train pairs for backward compat
            lines: list[str] = []
            for pair in data.get("train", []):
                lines.append(f"Q: {pair['Q']}")
                lines.append(f"A: {pair['A']}")
                lines.append("")
            return "\n".join(lines)
        return path.read_text()

    def get_train_pairs(self, item_id: str) -> list[tuple[str, str]]:
        """Return individual (question, answer) training pairs."""
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self._corpus_path(item_id)
        if item_id not in self.access_log:
            self.access_log.append(item_id)
        if path.suffix == ".json":
            data = json.loads(path.read_text(encoding="utf-8"))
            return [(p["Q"], p["A"]) for p in data.get("train", [])]
        text = path.read_text(encoding="utf-8")
        pairs = _parse_qa_text(text)
        if pairs:
            return pairs
        # Legacy: raw text without Q:/A: structure → single training item
        return [("", text.strip())]

    def get_eval_probes(self, item_id: str) -> list[EvalProbe]:
        """Return every eval probe for *item_id* with full metadata.

        Reads ``_id``, ``ec``, and ``language`` from the corpus JSON in
        addition to ``Q``/``A``. The family (``ec``) is canonicalized to one
        of :data:`CANONICAL_FAMILIES` where possible. Legacy TXT corpora and
        corpora without an ``eval`` key have no eval probes.
        """
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self._corpus_path(item_id)
        if path.suffix != ".json" or not path.is_file():
            return []
        data = json.loads(path.read_text(encoding="utf-8"))
        probes: list[EvalProbe] = []
        for p in data.get("eval", []):
            raw_family = str(p.get("ec", p.get("direction", "unknown")))
            probe_id = f"{item_id}:{p['_id']}" if "_id" in p else f"{item_id}:{len(probes)}"
            probes.append(
                EvalProbe(
                    probe_id=probe_id,
                    fact_id=item_id,
                    family=canonicalize_family(raw_family),
                    language=str(p.get("language", "unknown")),
                    question=str(p["Q"]),
                    answer=str(p["A"]),
                )
            )
        return probes

    def get_eval_pairs(self, item_id: str) -> list[tuple[str, str]]:
        """Return individual (question, answer) eval pairs.

        Compatibility adapter over :meth:`get_eval_probes`.
        """
        return [(probe.question, probe.answer) for probe in self.get_eval_probes(item_id)]

    def get_eval_directions(self, item_id: str) -> list[str]:
        """Return the canonical family label for each eval probe.

        Compatibility adapter over :meth:`get_eval_probes`.
        """
        return [probe.family for probe in self.get_eval_probes(item_id)]

    def assert_closed(self) -> None:
        """Raise when the ids read are not exactly the manifest set."""
        read = set(self.access_log)
        allowed = set(self.allowed_ids)
        if read != allowed:
            missing = sorted(allowed - read)
            extra = sorted(read - allowed)
            detail = missing[0] if missing else extra[0]
            raise FactVerifyHarnessError(f"unlisted training item {detail!r}")


def _parse_qa_text(text: str) -> list[tuple[str, str]]:
    """Parse Q:/A: formatted text into (question, answer) pairs."""
    pairs: list[tuple[str, str]] = []
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Q: "):
            question = line[3:]
            answer = ""
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("A: "):
                answer = lines[i + 1].strip()[3:]
            pairs.append((question, answer))
            i += 2
        else:
            i += 1
    return pairs
