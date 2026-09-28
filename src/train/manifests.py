"""Source-bundle exclusion for retain-only references."""

from __future__ import annotations


def leaked_bundle_documents(
    manifest_train: list[str], source_bundle: list[str]
) -> list[str]:
    """Document ids that appear on both the training manifest and the source bundle."""
    bundle = set(source_bundle)
    return sorted(item_id for item_id in manifest_train if item_id in bundle)
