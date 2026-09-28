"""Fail-closed errors for fake-unlearning controls."""

from __future__ import annotations


class ControlError(ValueError):
    """Names the missing field, decision id, family, implementation id, or path."""
