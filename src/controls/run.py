"""CLI. A SQLite ledger path is refused until P2-5."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.train.errors import FactVerifyHarnessError
from src.train.ledger import require_sqlite_ledger


def main(argv: list[str] | None = None) -> int:
    """Refuse `--ledger` until a SQLite adapter exists. Do not load a model."""
    parser = argparse.ArgumentParser(prog="python -m src.controls.run")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--spec-root", default=Path(".factverify/spec"), type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        require_sqlite_ledger(args.ledger)
    except FactVerifyHarnessError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
