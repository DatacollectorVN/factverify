"""Manifest-only access to training text. One file per item id."""

from __future__ import annotations

from pathlib import Path

from .errors import FactVerifyHarnessError


class DataCatalog:
    """The only reader of training text for a job."""

    def __init__(self, corpus_dir: Path, allowed_ids: list[str]) -> None:
        self.corpus_dir = corpus_dir
        self.allowed_ids = list(allowed_ids)
        self._allowed = set(allowed_ids)
        self.access_log: list[str] = []

    def get(self, item_id: str) -> str:
        """Return the text for `item_id`, or raise naming it when unlisted."""
        if item_id not in self._allowed:
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        path = self.corpus_dir / f"{item_id}.txt"
        if not path.is_file():
            raise FactVerifyHarnessError(f"unlisted training item {item_id!r}")
        self.access_log.append(item_id)
        return path.read_text()

    def assert_closed(self) -> None:
        """Raise when the ids read are not exactly the manifest set."""
        read = set(self.access_log)
        allowed = set(self.allowed_ids)
        if read != allowed:
            missing = sorted(allowed - read)
            extra = sorted(read - allowed)
            detail = missing[0] if missing else extra[0]
            raise FactVerifyHarnessError(f"unlisted training item {detail!r}")
