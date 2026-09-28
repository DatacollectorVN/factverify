"""In-memory ledger double for harness tests. Not the P2-5 SQLite ledger."""

from __future__ import annotations

from src.train.errors import FactVerifyHarnessError
from src.train.ledger import CheckpointRow


class InMemoryLedger:
    """LedgerPort that stores rows in a list."""

    def __init__(self, *, fail_commit: bool = False) -> None:
        self.rows: list[CheckpointRow] = []
        self.fail_commit = fail_commit

    def split_for_seed(self, fact_id: str, seed: int) -> str | None:
        for row in self.rows:
            if (
                row.fact_id == fact_id
                and row.seed == seed
                and row.status == "succeeded"
            ):
                return row.split
        return None

    def commit_checkpoint(self, row: CheckpointRow) -> str:
        if self.fail_commit:
            raise FactVerifyHarnessError("ledger write failed")
        self.rows.append(row)
        return f"row-{len(self.rows)}"
