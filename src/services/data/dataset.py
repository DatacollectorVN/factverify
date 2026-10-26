"""Higher-level loaders that bridge DataCatalog and typed domain objects."""

from __future__ import annotations

from src.services.data.catalog import DataCatalog
from src.services.data.types import EvaluationProbe, TrainingExample


def load_training_examples(
    catalog: DataCatalog, fact_ids: list[str]
) -> list[TrainingExample]:
    """Read all training pairs for the given fact IDs."""
    examples: list[TrainingExample] = []
    for fid in fact_ids:
        for question, answer in catalog.get_train_pairs(fid):
            examples.append(
                TrainingExample(fact_id=fid, question=question, answer=answer)
            )
    return examples


def load_evaluation_probes(
    catalog: DataCatalog, fact_ids: list[str]
) -> list[EvaluationProbe]:
    """Read all evaluation pairs and their direction labels for the given fact IDs."""
    probes: list[EvaluationProbe] = []
    for fid in fact_ids:
        pairs = catalog.get_eval_pairs(fid)
        directions = catalog.get_eval_directions(fid)
        for (question, answer), direction in zip(pairs, directions):
            probes.append(
                EvaluationProbe(
                    fact_id=fid,
                    question=question,
                    expected_answer=answer,
                    direction=direction,
                )
            )
    return probes
