"""Data validation helpers."""

from __future__ import annotations

from src.services.common.errors import DataValidationError
from src.services.data.catalog import DataCatalog
from src.services.data.types import ValidationReport


def validate_disjointness(
    forget_ids: set[str], retain_ids: set[str]
) -> ValidationReport:
    """Check that forget and retain sets have no overlap."""
    overlap = forget_ids & retain_ids
    if overlap:
        items = ", ".join(sorted(overlap))
        return ValidationReport(
            valid=False,
            errors=[f"forget/retain overlap: {items}"],
        )
    return ValidationReport(valid=True)


def validate_corpus_exists(
    catalog: DataCatalog, fact_ids: list[str]
) -> ValidationReport:
    """Check that every fact_id can be resolved to a corpus file."""
    errors: list[str] = []
    for fid in fact_ids:
        try:
            catalog._corpus_path(fid)
        except DataValidationError:
            errors.append(f"no corpus file for {fid!r}")
    if errors:
        return ValidationReport(valid=False, errors=errors)
    return ValidationReport(valid=True)
