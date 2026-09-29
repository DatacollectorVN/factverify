"""Decision catalog errors."""

from __future__ import annotations


class DecisionError(Exception):
    """Raised by src/decisions internals. Not a subclass of any module error."""
