"""Raw completions as JSONL outside the spec namespace."""

from __future__ import annotations

import json
from pathlib import Path

from src.eval.errors import FactVerifyEvalError
from src.eval.types import Case

_REQUIRED = (
    "case_id",
    "checkpoint_ledger_id",
    "fact_id",
    "split",
    "arm_id",
    "channel_id",
    "probe_id",
    "prompt",
    "completion",
    "decoding",
    "seed",
)


def assert_outside_spec_namespace(path: Path) -> None:
    """Refuse a raw directory inside .factverify."""
    if ".factverify" in path.resolve().parts:
        raise FactVerifyEvalError(str(path.resolve()))


class RawStore:
    """One JSONL file per case and arm."""

    def __init__(self, raw_dir: Path) -> None:
        assert_outside_spec_namespace(raw_dir)
        self.raw_dir = raw_dir
        self.raw_dir.mkdir(parents=True, exist_ok=True)

    def append(self, case: Case, arm_id: str, line: dict[str, object]) -> None:
        record = {
            "case_id": case.case_id,
            "checkpoint_ledger_id": case.checkpoint_ledger_id,
            "fact_id": case.fact_id,
            "split": case.split,
            "arm_id": arm_id,
            "channel_id": line["channel_id"],
            "probe_id": line["probe_id"],
            "prompt": line["prompt"],
            "completion": line["completion"],
            "decoding": line.get("decoding", {}),
            "seed": line.get("seed", case.seed),
            "metric_scores": line.get("metric_scores", {}),
        }
        missing = [key for key in _REQUIRED if record.get(key) is None]
        if missing:
            raise FactVerifyEvalError(",".join(missing))
        with self._path(case.case_id, arm_id).open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True) + "\n")

    def count(self, case_id: str, arm_id: str) -> int:
        path = self._path(case_id, arm_id)
        if not path.is_file():
            return 0
        text = path.read_text(encoding="utf-8")
        return sum(1 for line in text.splitlines() if line.strip())

    def read(self, case_id: str, arm_id: str) -> list[dict[str, object]]:
        path = self._path(case_id, arm_id)
        if not path.is_file():
            return []
        rows: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                loaded = json.loads(line)
                if isinstance(loaded, dict):
                    rows.append(loaded)
        return rows

    def _path(self, case_id: str, arm_id: str) -> Path:
        return self.raw_dir / f"{case_id}__{arm_id}.jsonl"
