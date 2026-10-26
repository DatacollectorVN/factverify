"""Tests for run planning: expand_plan produces correct RunSpec objects."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from src.services.common.errors import PlanningError
from src.services.common.types import AppConfig, JobSection, RuntimeSection
from src.services.training.planning import expand_plan
from src.services.training.types import RunSpec


def _app_config(
    *,
    role: str = "learner",
    method: str = "finetune",
    seeds: list[int] | None = None,
    facts: list[str] | None = None,
    forget_facts: list[str] | None = None,
    retain_facts: list[str] | None = None,
    learning_rates: list[float] | None = None,
    learning_rate: float = 1e-4,
    leave_one_out: bool = False,
    output_dir: str = "/out",
) -> AppConfig:
    """Build a minimal AppConfig for planning tests."""
    if seeds is None:
        seeds = [0]
    if facts is None and role != "forgetter":
        facts = ["f1", "f2", "f3"]

    data: dict = {"corpus_dir": "/corpus"}  # type: ignore[type-arg]
    if role == "forgetter":
        if forget_facts:
            data["forget_facts"] = forget_facts
        if retain_facts:
            data["retain_facts"] = retain_facts
    else:
        data["facts"] = facts
        if leave_one_out:
            data["leave_one_out"] = True

    training: dict = {  # type: ignore[type-arg]
        "optimizer": "adamw",
        "learning_rate": learning_rate,
        "weight_decay": 0.01,
        "epochs": 3,
        "max_length": 128,
        "micro_batch_size": 4,
        "gradient_accumulation_steps": 2,
    }
    if learning_rates:
        training["learning_rates"] = learning_rates

    raw = {
        "schema_version": 1,
        "task": "train",
        "job": {"name": "test-job", "role": role, "method": method, "split": "cal", "seeds": seeds},
        "runtime": {"output_root": "/runtime", "device": "cpu"},
        "model": {"base_role": "tiny_base", "config": "/model.yaml"},
        "data": data,
        "training": training,
        "output": {"dir": output_dir},
        "reproducibility": {"hardware_class": "cpu", "determinism_policy": "exact"},
    }

    return AppConfig(
        schema_version=1,
        task="train",
        job=JobSection(name="test-job", role=role, split="cal", seeds=tuple(seeds)),
        runtime=RuntimeSection(output_root="/runtime", device="cpu"),
        raw=raw,
        source_path=Path("/fake/config.yaml"),
    )


class TestLearnerExpansion:
    def test_single_seed_single_lr(self) -> None:
        config = _app_config(seeds=[0])
        runs = expand_plan(config)
        assert len(runs) == 1
        assert runs[0].role == "learner"
        assert runs[0].target_fact == "all"
        assert runs[0].manifest == {"train": ["f1", "f2", "f3"]}

    def test_multiple_seeds(self) -> None:
        config = _app_config(seeds=[0, 1, 2])
        runs = expand_plan(config)
        assert len(runs) == 3
        assert {r.seed for r in runs} == {0, 1, 2}

    def test_lr_sweep(self) -> None:
        """4 LRs × 3 seeds = 12 learner runs (scenario 7)."""
        config = _app_config(
            seeds=[0, 1, 2],
            learning_rates=[1e-5, 3e-5, 1e-4, 3e-4],
        )
        runs = expand_plan(config)
        assert len(runs) == 12
        assert all(r.role == "learner" for r in runs)

    def test_all_output_paths_unique(self) -> None:
        config = _app_config(
            seeds=[0, 1, 2],
            learning_rates=[1e-5, 3e-5],
        )
        runs = expand_plan(config)
        paths = [r.output_dir for r in runs]
        assert len(paths) == len(set(paths))


class TestForgetterExpansion:
    def test_single_fact(self) -> None:
        config = _app_config(
            role="forgetter",
            method="GA",
            forget_facts=["f1"],
            retain_facts=["f2", "f3"],
        )
        runs = expand_plan(config)
        assert len(runs) == 1
        assert runs[0].target_fact == "f1"
        assert runs[0].manifest == {"forget": ["f1"], "retain": ["f2", "f3"]}

    def test_multiple_facts_multiple_seeds(self) -> None:
        """8 forget facts × 3 seeds = 24 forgetter runs (scenario 8)."""
        facts = [f"f{i}" for i in range(8)]
        retain = ["r1", "r2"]
        config = _app_config(
            role="forgetter",
            method="GA",
            seeds=[0, 1, 2],
            forget_facts=facts,
            retain_facts=retain,
        )
        runs = expand_plan(config)
        assert len(runs) == 24
        assert all(r.role == "forgetter" for r in runs)

    def test_all_output_paths_unique(self) -> None:
        config = _app_config(
            role="forgetter",
            method="GA",
            seeds=[0, 1],
            forget_facts=["f1", "f2", "f3"],
            retain_facts=["r1"],
        )
        runs = expand_plan(config)
        paths = [r.output_dir for r in runs]
        assert len(paths) == len(set(paths))

    def test_forget_in_retain_raises(self) -> None:
        config = _app_config(
            role="forgetter",
            method="GA",
            forget_facts=["f1"],
            retain_facts=["f1", "f2"],
        )
        with pytest.raises(PlanningError, match="must not appear in retain"):
            expand_plan(config)

    def test_missing_retain_raises(self) -> None:
        config = _app_config(
            role="forgetter",
            method="GA",
            forget_facts=["f1"],
            retain_facts=[],
        )
        with pytest.raises(PlanningError, match="retain_facts"):
            expand_plan(config)


class TestReferencerExpansion:
    def test_all_facts_single_run(self) -> None:
        config = _app_config(role="referencer")
        runs = expand_plan(config)
        assert len(runs) == 1
        assert runs[0].target_fact == "all"

    def test_leave_one_out(self) -> None:
        """8 exclusions × 2 seeds = 16 referencer runs (scenario 9)."""
        facts = [f"f{i}" for i in range(8)]
        config = _app_config(
            role="referencer",
            seeds=[0, 1],
            facts=facts,
            leave_one_out=True,
        )
        runs = expand_plan(config)
        assert len(runs) == 16

    def test_leave_one_out_excludes_correct_fact(self) -> None:
        config = _app_config(
            role="referencer",
            facts=["a", "b", "c"],
            leave_one_out=True,
        )
        runs = expand_plan(config)
        assert len(runs) == 3
        for run in runs:
            # The excluded fact should NOT be in the manifest
            assert run.target_fact not in run.manifest["train"]
            # All other facts should be in the manifest
            assert len(run.manifest["train"]) == 2

    def test_all_output_paths_unique(self) -> None:
        config = _app_config(
            role="referencer",
            seeds=[0, 1],
            facts=["a", "b", "c"],
            leave_one_out=True,
        )
        runs = expand_plan(config)
        paths = [r.output_dir for r in runs]
        assert len(paths) == len(set(paths))


class TestValidation:
    def test_unknown_role_raises(self) -> None:
        config = _app_config()
        # Mutate the raw dict to have an unknown role
        config.raw["job"]["role"] = "unknown"
        with pytest.raises(PlanningError, match="unknown role"):
            expand_plan(config)

    def test_invalid_method_for_role_raises(self) -> None:
        config = _app_config(role="learner", method="GA")
        with pytest.raises(PlanningError, match="cannot use method"):
            expand_plan(config)

    def test_no_seeds_raises(self) -> None:
        config = _app_config(seeds=[])
        with pytest.raises(PlanningError, match="at least one seed"):
            expand_plan(config)

    def test_no_model_loading_needed(self) -> None:
        """Planning must work without any model or data on disk."""
        config = _app_config(
            seeds=[0, 1],
            facts=["f1", "f2"],
        )
        # This should succeed purely from config — no I/O
        runs = expand_plan(config)
        assert len(runs) == 2


class TestTrainingConfig:
    def test_effective_batch_size(self) -> None:
        config = _app_config()
        runs = expand_plan(config)
        tc = runs[0].training
        assert tc.effective_batch_size == tc.micro_batch_size * tc.gradient_accumulation_steps

    def test_method_specific_params_passed(self) -> None:
        config = _app_config(role="forgetter", method="GradDiff")
        config.raw["training"]["retain_coeff"] = 0.5
        config.raw["data"]["forget_facts"] = ["f1"]
        config.raw["data"]["retain_facts"] = ["f2"]
        runs = expand_plan(config)
        assert runs[0].training.retain_coeff == 0.5
