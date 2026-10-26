"""Manifest-only access to training text. One file per item id."""

from __future__ import annotations

import json
from pathlib import Path

from .errors import FactVerifyHarnessError


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

    def get_eval_pairs(self, item_id: str) -> list[tuple[str, str]]:
        """Return individual (question, answer) eval pairs."""
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self._corpus_path(item_id)
        if path.suffix == ".json" and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return [(p["Q"], p["A"]) for p in data.get("eval", [])]
        return []

    def get_eval_directions(self, item_id: str) -> list[str]:
        """Return the ec/direction label for each eval probe."""
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self._corpus_path(item_id)
        if path.suffix == ".json" and path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            return [
                p.get("ec", p.get("direction", "unknown"))
                for p in data.get("eval", [])
            ]
        return []

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
