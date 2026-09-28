"""Per-channel query budget. The integer budget_per_fact API is gone."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.eval.cost import empty_cost_record
from src.eval.errors import BudgetExhaustedError, FactVerifyEvalError
from src.eval.spec_load import SpecBundle, require_closed, require_resolved_policies
from src.eval.types import (
    BudgetRecord,
    ChannelBudget,
    ChargeResult,
    QueryRequest,
)


@dataclass
class _Channel:
    permitted: int
    charged_observations: int = 0
    new_compute_trials: int = 0
    refused: int = 0

    @property
    def remaining(self) -> int:
        return self.permitted - self.charged_observations


@dataclass
class Accountant:
    """Charges one arm of one case from the loaded attack specification."""

    bundle: SpecBundle
    arm_id: str
    _channels: dict[str, _Channel] = field(init=False)
    _generated_trials: int = field(init=False, default=0)
    _scored_candidates: int = field(init=False, default=0)
    _input_tokens: int = field(init=False, default=0)
    _output_tokens: int = field(init=False, default=0)
    _refused: list[QueryRequest] = field(init=False, default_factory=list)
    _reference_trials: int = field(init=False, default=0)
    wall_clock_seconds: float = 0.0
    gpu_hours: float = 0.0
    peak_memory_bytes: int = 0

    def __post_init__(self) -> None:
        arm = self.bundle.arms.get(self.arm_id)
        if arm is None:
            raise FactVerifyEvalError(self.arm_id)
        self._channels = {
            channel_id: _Channel(permitted=trials)
            for channel_id, trials in arm.channels.items()
        }

    def ensure_capacity(
        self, channel_id: str, trials: int, request: QueryRequest
    ) -> None:
        """Refuse without charging when the channel cannot cover trials."""
        channel = self._require_channel(channel_id)
        if trials > channel.remaining:
            channel.refused += 1
            self._refused.append(request)
            raise BudgetExhaustedError(channel_id, trials, channel.remaining)

    def query(self, channel_id: str, request: QueryRequest) -> ChargeResult:
        """Charge request against channel_id, or the confirmation line when allowed."""
        target = channel_id
        if request.spend_confirmation and channel_id != "confirmation":
            realloc = self.bundle.accounting.get("unused_confirmation_reallocation")
            if realloc is not True:
                self._refused.append(request)
                raise FactVerifyEvalError("confirmation")
            target = "confirmation"
        if request.kind == "candidate_score":
            require_closed(self.bundle, ["D-18"])
            self._scored_candidates += max(request.prompt_count, 1)
            channel = self._require_channel(target)
            return self._result(
                "charged", 0, 0, self._scored_candidates, channel.remaining, None
            )
        if request.kind == "reference":
            return self._charge_reference(target, request)
        observations, new_compute, generated = self._amounts(request)
        return self._consume(target, request, observations, new_compute, generated)

    def budget_record(self) -> BudgetRecord:
        """Cost vector including a positive remainder when the arm stops early."""
        arm = self.bundle.arms[self.arm_id]
        record = empty_cost_record(self.arm_id, arm.total)
        record.channels = [
            ChannelBudget(
                channel_id=channel_id,
                permitted=channel.permitted,
                charged_observations=channel.charged_observations,
                new_compute_trials=channel.new_compute_trials,
                refused=channel.refused,
                remaining=channel.remaining,
            )
            for channel_id, channel in self._channels.items()
        ]
        confirmation = self._channels.get("confirmation")
        record.confirmation_remaining = (
            0 if confirmation is None else confirmation.remaining
        )
        record.generated_trials = self._generated_trials
        record.scored_candidates = self._scored_candidates
        record.input_tokens = self._input_tokens
        record.output_tokens = self._output_tokens
        record.tokens = self._input_tokens + self._output_tokens
        record.wall_clock_seconds = self.wall_clock_seconds
        record.gpu_hours = self.gpu_hours
        record.peak_memory_bytes = self.peak_memory_bytes
        record.permitted_vs_actual = {
            item.channel_id: {
                "permitted": item.permitted,
                "actual": item.charged_observations,
            }
            for item in record.channels
        }
        record.refused_requests = list(self._refused)
        return record

    def channel_remaining(self, channel_id: str) -> int:
        return self._require_channel(channel_id).remaining

    def _amounts(self, request: QueryRequest) -> tuple[int, int, int]:
        trials = request.prompt_count * request.sample_count
        kind = request.kind
        if kind == "generation":
            return trials, trials, trials
        policy = self._policy(kind)
        multiplier = 1
        if kind == "retry" and policy.get("charges_original_failure") is True:
            multiplier = 2
        if policy.get("observation_charged") is True:
            observations = trials * multiplier
        else:
            observations = 0
        if policy.get("charge_rule") == "zero_new_compute":
            new_compute = 0
        elif policy.get("charge_rule") == "charged":
            new_compute = trials * multiplier
        elif policy.get("charge_rule") == "separately_reported":
            new_compute = 0
        else:
            raise FactVerifyEvalError(str(policy.get("charge_rule")))
        return observations, new_compute, 0

    def _policy(self, kind: str) -> dict[str, object]:
        key = {
            "cache_hit": "cache_policy",
            "retry": "retry_policy",
            "transport_failure": "failure_policy",
            "discard": "discard_policy",
        }.get(kind)
        if key is None:
            raise FactVerifyEvalError(kind)
        policy = self.bundle.accounting.get(key)
        if not isinstance(policy, dict):
            raise FactVerifyEvalError(key)
        rule = policy.get("charge_rule")
        if rule not in {"charged", "zero_new_compute", "separately_reported"}:
            raise FactVerifyEvalError(f"{key}.charge_rule")
        return policy

    def _consume(
        self,
        channel_id: str,
        request: QueryRequest,
        observations: int,
        new_compute: int,
        generated: int,
    ) -> ChargeResult:
        channel = self._require_channel(channel_id)
        if observations > channel.remaining:
            channel.refused += 1
            self._refused.append(request)
            raise BudgetExhaustedError(channel_id, observations, channel.remaining)
        channel.charged_observations += observations
        channel.new_compute_trials += new_compute
        self._generated_trials += generated
        return self._result(
            "charged",
            generated,
            new_compute,
            0,
            channel.remaining,
            None,
        )

    def _charge_reference(self, channel_id: str, request: QueryRequest) -> ChargeResult:
        policy = self.bundle.accounting.get("reference_cost_policy", {})
        rule = policy.get("charge_rule") if isinstance(policy, dict) else None
        if rule != "separately_reported":
            raise FactVerifyEvalError("reference_cost_policy.charge_rule")
        trials = request.prompt_count * request.sample_count
        self._reference_trials += trials
        channel = self._require_channel(channel_id)
        return self._result("charged", 0, 0, 0, channel.remaining, None)

    def _require_channel(self, channel_id: str) -> _Channel:
        channel = self._channels.get(channel_id)
        if channel is None:
            raise FactVerifyEvalError(channel_id)
        return channel

    def _result(
        self,
        outcome: str,
        generated: int,
        new_compute: int,
        scored: int,
        remaining: int,
        refused: QueryRequest | None,
    ) -> ChargeResult:
        if outcome not in {"charged", "refused"}:
            raise FactVerifyEvalError(outcome)
        return ChargeResult(
            outcome="charged" if outcome == "charged" else "refused",
            generation_trials=generated,
            new_compute_trials=new_compute,
            scored_candidates=scored,
            remaining=remaining,
            refused_request=refused,
        )


def check_arm_totals(bundle: SpecBundle) -> int:
    """Return the shared total, or raise listing each arm total."""
    totals: dict[str, int] = {}
    for arm_id, arm in bundle.arms.items():
        channel_sum = sum(arm.channels.values())
        if channel_sum != arm.total:
            raise FactVerifyEvalError(f"{arm_id} total {arm.total} sum {channel_sum}")
        totals[arm_id] = arm.total
    unique = set(totals.values())
    cap_mismatch = bundle.common_cap is not None and any(
        value != bundle.common_cap for value in totals.values()
    )
    if len(unique) != 1 or cap_mismatch:
        listed = ", ".join(
            f"{arm_id}={total}" for arm_id, total in sorted(totals.items())
        )
        raise FactVerifyEvalError(f"unequal arm totals: {listed}")
    return next(iter(unique))


def start_run(bundle: SpecBundle) -> int:
    """Refuse unresolved policies and open budget decisions, then check totals."""
    require_resolved_policies(bundle)
    require_closed(bundle, ["D-17", "D-20", "D-21", "D-22", "D-26"])
    return check_arm_totals(bundle)
