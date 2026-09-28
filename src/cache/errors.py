"""Cache failures. The message is the field or decision id."""

from __future__ import annotations


class CacheError(Exception):
    """A rejected cache operation. The argument is the field or decision id."""

    def __init__(self, message: str, event: object | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.event = event
