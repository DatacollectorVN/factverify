"""Empty cost records. Counters are filled by the accountant."""

from __future__ import annotations

from src.eval.types import BudgetRecord


def empty_cost_record(arm_id: str, permitted_total: int) -> BudgetRecord:
    """A record whose every field is present. Remainders start at the allocation."""
    return BudgetRecord(
        arm_id=arm_id,
        permitted_total=permitted_total,
        channels=[],
        confirmation_remaining=0,
        generated_trials=0,
        scored_candidates=0,
        input_tokens=0,
        output_tokens=0,
        tokens=0,
        exports=0,
        training_steps=0,
        wall_clock_seconds=0.0,
        gpu_hours=0.0,
        peak_memory_bytes=0,
        permitted_vs_actual={},
        refused_requests=[],
    )
