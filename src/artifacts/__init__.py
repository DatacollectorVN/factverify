"""Artifact namespace management for FactVerify.

Two-root storage contract (D-71 / artifacts.namespace.boundary):
  - Frozen spec root (.factverify/): immutable study/fact inputs.
  - Internal runtime root (.factverify_internal/): append-only transactions.
"""
from __future__ import annotations

__all__: list[str] = []
