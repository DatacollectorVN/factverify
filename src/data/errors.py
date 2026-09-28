"""Errors for fact-data preparation."""

from __future__ import annotations

from typing_extensions import override


class DataError(Exception):
    """A refused data-preparation step. The message names the cause."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)

    @override
    def __str__(self) -> str:
        return self.message
