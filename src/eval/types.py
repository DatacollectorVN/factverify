"""Shared records for cases, charges, budgets, and verdicts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

SPLITS = ("construction", "calibration", "final_test")
ARMS = ("native", "semantic_only", "factverify")

STATUS_PHRASES = (
    "confirmed recovery witness",
    "conformant under the declared test",
    "non-identifiable under this profile",
    "insufficient evidence/incomplete",
)

STATUS_CODES = {
    "confirmed recovery witness": "confirmed_recovery",
    "conformant under the declared test": "conformance",
    "non-identifiable under this profile": "non_identifiable",
    "insufficient evidence/incomplete": "incomplete",
}


def normalize_split(split: str) -> str:
    """Map the requirements phrase onto the closure-file token."""
    from src.eval.errors import FactVerifyEvalError

    token = "final_test" if split == "final-test" else split
    if token not in SPLITS:
        raise FactVerifyEvalError(f"split {split}")
    return token


@dataclass
class Probe:
    probe_id: str
    probe_class: str
    prompt: str
    template_id: str | None = None
    group_id: str | None = None
    family_id: str | None = None


@dataclass
class Case:
    case_id: str
    checkpoint_ledger_id: str
    fact_id: str
    split: str
    spec_revision: str
    access_label: str
    identifiability: str
    answers: list[str]
    probes: list[Probe]
    seed: int = 0


@dataclass
class QueryRequest:
    channel_id: str
    kind: str
    probe_id: str
    prompt_count: int = 1
    sample_count: int = 1
    decoding: dict[str, object] = field(default_factory=dict)
    spend_confirmation: bool = False
    seed: int = 0


@dataclass
class ChargeResult:
    outcome: Literal["charged", "refused"]
    generation_trials: int
    new_compute_trials: int
    scored_candidates: int
    remaining: int
    refused_request: QueryRequest | None = None


@dataclass
class ChannelBudget:
    channel_id: str
    permitted: int
    charged_observations: int
    new_compute_trials: int
    refused: int
    remaining: int


@dataclass
class BudgetRecord:
    arm_id: str
    permitted_total: int
    channels: list[ChannelBudget]
    confirmation_remaining: int
    generated_trials: int
    scored_candidates: int
    input_tokens: int
    output_tokens: int
    tokens: int
    exports: int
    training_steps: int
    wall_clock_seconds: float
    gpu_hours: float
    peak_memory_bytes: int
    permitted_vs_actual: dict[str, dict[str, int]]
    refused_requests: list[QueryRequest] = field(default_factory=list)


@dataclass
class ChannelScore:
    channel_id: str
    score: float
    bound: float


@dataclass
class Diagnostics:
    raw_maximum: float | None = None


@dataclass
class VerdictRow:
    status: str
    status_code: str
    access_label: str
    arm_id: str
    checkpoint_ledger_id: str
    fact_id: str
    split: str
    spec_revision: str
    thresholds_tag: str | None
    scores: list[ChannelScore]
    diagnostics: Diagnostics
    confirmation_route: str | None
    inference_output: list[str]


@dataclass
class Bounds:
    split: str
    by_channel: dict[str, float]


@dataclass
class FrozenThresholds:
    tag: str
    digest: str
    by_channel: dict[str, float]


@dataclass
class CaseResult:
    status: Literal["finished", "refused"]
    verdicts: list[VerdictRow]
    budget_records: list[BudgetRecord]
    raw_count: int
    error: str | None = None
