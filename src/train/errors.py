"""Errors raised by the training harness."""

from __future__ import annotations


class FactVerifyHarnessError(ValueError):
    """Fail-closed harness error naming the field, document, item, or seed."""
