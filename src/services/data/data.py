"""Public facade — re-exports the canonical data service API."""

from __future__ import annotations

from src.services.data.catalog import DataCatalog
from src.services.data.collator import causal_nll, prepare_batch, prepare_qa_batch
from src.services.data.dataset import load_evaluation_probes, load_training_examples
from src.services.data.types import (
    EvaluationProbe,
    ManifestDigest,
    TrainingExample,
    ValidationReport,
)
from src.services.data.validation import validate_corpus_exists, validate_disjointness

__all__ = [
    "DataCatalog",
    "EvaluationProbe",
    "ManifestDigest",
    "TrainingExample",
    "ValidationReport",
    "causal_nll",
    "load_evaluation_probes",
    "load_training_examples",
    "prepare_batch",
    "prepare_qa_batch",
    "validate_corpus_exists",
    "validate_disjointness",
]
