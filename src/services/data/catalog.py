"""Manifest-only access to training and evaluation text.

Ported from ``src/train/data.py``. Uses the same four-step resolution
chain (flat JSON v2, nested JSON v1, nested TXT, flat TXT) and the
same public API, but raises ``DataValidationError`` instead of
``FactVerifyHarnessError``.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.services.common.errors import DataValidationError


class DataCatalog:
    """The only reader of training/evaluation text for a job."""

    def __init__(self, corpus_dir: Path, allowed_ids: list[str]) -> None:
        self.corpus_dir = corpus_dir
        self.allowed_ids = list(allowed_ids)
        self._allowed = set(allowed_ids)
        self.access_log: list[str] = []

    # ── resolution ────────────────────────────────────────────────────

    def _corpus_path(self, item_id: str) -> Path:
        """Resolve the corpus file for *item_id*.

        Supports layouts (checked in order):
          1. flat JSON v2:   {corpus_dir}/{item_id}.json
          2. nested JSON v1: {corpus_dir}/{item_id}/corpus.json
          3. nested TXT:     {corpus_dir}/{item_id}/corpus.txt   (legacy)
          4. flat TXT:       {corpus_dir}/{item_id}.txt           (legacy)
        """
        flat_json = self.corpus_dir / f"{item_id}.json"
        if flat_json.is_file():
            return flat_json
        json_path = self.corpus_dir / item_id / "corpus.json"
        if json_path.is_file():
            return json_path
        txt_path = self.corpus_dir / item_id / "corpus.txt"
        if txt_path.is_file():
            return txt_path
        flat_path = self.corpus_dir / f"{item_id}.txt"
        if flat_path.is_file():
            return flat_path
        raise DataValidationError(
            f"no corpus file found for item {item_id!r} under {self.corpus_dir}"
        )

    # ── helpers ───────────────────────────────────────────────────────

    def _read_json(self, path: Path) -> dict:
        """Read and validate a JSON corpus file."""
        data = json.loads(path.read_text(encoding="utf-8"))
        if "train" not in data:
            raise DataValidationError(
                f"corpus file {path} has no 'train' key — "
                "metadata-only JSON is not a valid corpus"
            )
        if not data["train"]:
            raise DataValidationError(
                f"corpus file {path} has an empty 'train' list"
            )
        return data

    def _check_allowed(self, item_id: str) -> None:
        """Raise if *item_id* is not in the manifest."""
        if item_id not in self._allowed:
            raise DataValidationError(f"unlisted training item {item_id!r}")

    def _record_access(self, item_id: str) -> None:
        """Append *item_id* to the access log (idempotent per call-site)."""
        if item_id not in self.access_log:
            self.access_log.append(item_id)

    # ── public API ────────────────────────────────────────────────────

    def get(self, item_id: str) -> str:
        """Return the raw text for *item_id* (legacy, whole-document)."""
        self._check_allowed(item_id)
        path = self._corpus_path(item_id)
        self.access_log.append(item_id)
        if path.suffix == ".json":
            data = self._read_json(path)
            lines: list[str] = []
            for pair in data.get("train", []):
                lines.append(f"Q: {pair['Q']}")
                lines.append(f"A: {pair['A']}")
                lines.append("")
            return "\n".join(lines)
        return path.read_text(encoding="utf-8")

    def get_train_pairs(self, item_id: str) -> list[tuple[str, str]]:
        """Return individual (question, answer) training pairs."""
        self._check_allowed(item_id)
        path = self._corpus_path(item_id)
        self._record_access(item_id)
        if path.suffix == ".json":
            data = self._read_json(path)
            return [(p["Q"], p["A"]) for p in data.get("train", [])]
        text = path.read_text(encoding="utf-8")
        pairs = _parse_qa_text(text)
        if pairs:
            return pairs
        # Legacy: raw text without Q:/A: structure -> single training item
        return [("", text.strip())]

    def get_eval_pairs(self, item_id: str) -> list[tuple[str, str]]:
        """Return individual (question, answer) eval pairs."""
        self._check_allowed(item_id)
        path = self._corpus_path(item_id)
        self._record_access(item_id)
        if path.suffix == ".json" and path.is_file():
            data = self._read_json(path)
            return [(p["Q"], p["A"]) for p in data.get("eval", [])]
        return []

    def get_eval_directions(self, item_id: str) -> list[str]:
        """Return the ec/direction label for each eval probe."""
        self._check_allowed(item_id)
        path = self._corpus_path(item_id)
        self._record_access(item_id)
        if path.suffix == ".json" and path.is_file():
            data = self._read_json(path)
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
            raise DataValidationError(f"unlisted training item {detail!r}")


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
