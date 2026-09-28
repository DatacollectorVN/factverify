"""Ledger failures. The message is the field or decision id."""

from __future__ import annotations


class LedgerError(Exception):
    """A rejected ledger operation. The argument is the field or decision id."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
