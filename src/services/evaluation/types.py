"""Evaluation service types (FV-ARCH-021)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EvaluationConfig:
    """Configuration for an evaluation job."""

    name: str
    arm: str
    split: str
    forget_fact: str
    retain_facts: list[str]
    checkpoints: dict[str, str]  # role → checkpoint path
    facts_dir: str
    corpus_dir: str
    output_dir: str
    max_new_tokens: int = 128

    @property
    def all_facts(self) -> list[str]:
        return [self.forget_fact] + list(self.retain_facts)


@dataclass(frozen=True)
class ProbeResult:
    """Result of one probe (question+answer) evaluation."""

    prompt: str
    completion: str
    expected_answer: str
    rouge_l: float
    truth_ratio: float
    answer_probability: float
    answer_rank: float


@dataclass(frozen=True)
class FactEvalResult:
    """Aggregated result for one fact across all probes."""

    fact_id: str
    role: str
    rouge_l: float
    truth_ratio: float
    answer_probability: float
    answer_rank: float
    probes: list[ProbeResult] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationReport:
    """Full evaluation report for a job."""

    job_name: str
    results: list[FactEvalResult] = field(default_factory=list)
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0


@dataclass(frozen=True)
class FactComparison:
    """Side-by-side scores for one fact across two checkpoints."""

    fact_id: str
    is_forget: bool
    forgetter: dict[str, float] = field(default_factory=dict)
    referencer: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class GateReport:
    """Gate analysis result."""

    job_name: str
    gate: str
    forget_fact: str | None
    total_facts: int
    retain_count: int
    decision: str  # "PASS", "FAIL", "NO_DATA", "UNDETERMINED"
    forget_delta: dict[str, float] = field(default_factory=dict)
    retain_delta: dict[str, float] = field(default_factory=dict)
    comparisons: list[FactComparison] = field(default_factory=list)
