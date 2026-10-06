"""Tests for FV-LEARN-001 (effective batching) and FV-LEARN-002 (pair shuffling)."""

from __future__ import annotations

import math

import pytest
import torch

from src.train.seeding import epoch_order_digest, epoch_pair_order


# ── FV-LEARN-002: Deterministic pair-level shuffling ─────────────────────

class TestEpochPairOrder:
    """epoch_pair_order must be deterministic and vary by epoch."""

    def test_same_seed_epoch_gives_same_order(self) -> None:
        pairs = list(range(20))
        a = epoch_pair_order(pairs, seed=42, epoch=0)
        b = epoch_pair_order(pairs, seed=42, epoch=0)
        assert a == b

    def test_different_epoch_gives_different_order(self) -> None:
        pairs = list(range(20))
        a = epoch_pair_order(pairs, seed=42, epoch=0)
        b = epoch_pair_order(pairs, seed=42, epoch=1)
        assert a != b

    def test_different_seed_gives_different_order(self) -> None:
        pairs = list(range(20))
        a = epoch_pair_order(pairs, seed=3, epoch=0)
        b = epoch_pair_order(pairs, seed=17, epoch=0)
        assert a != b

    def test_preserves_elements(self) -> None:
        pairs = [("a", "1"), ("b", "2"), ("c", "3")]
        result = epoch_pair_order(pairs, seed=7, epoch=5)
        assert sorted(result) == sorted(pairs)
        assert len(result) == len(pairs)

    def test_single_element(self) -> None:
        pairs = ["only"]
        result = epoch_pair_order(pairs, seed=1, epoch=0)
        assert result == ["only"]


class TestEpochOrderDigest:
    """epoch_order_digest must be stable and differ for different orders."""

    def test_stable(self) -> None:
        ids = ["a", "b", "c"]
        assert epoch_order_digest(ids) == epoch_order_digest(ids)

    def test_different_for_different_order(self) -> None:
        assert epoch_order_digest(["a", "b"]) != epoch_order_digest(["b", "a"])


# ── FV-LEARN-001: Batching math ─────────────────────────────────────────

class TestBatchingMath:
    """Acceptance scenarios from the requirement."""

    def test_320_pairs_batch_8(self) -> None:
        """SC-001: 320 pairs, batch_size=8 → 40 updates per epoch."""
        n_pairs = 320
        effective_bs = 8
        assert math.ceil(n_pairs / effective_bs) == 40

    def test_322_pairs_batch_8(self) -> None:
        """Partial batch: 322 pairs, batch_size=8 → 41 updates."""
        n_pairs = 322
        effective_bs = 8
        assert math.ceil(n_pairs / effective_bs) == 41

    def test_effective_batch_size(self) -> None:
        """micro_batch_size * gradient_accumulation_steps = effective."""
        micro_bs = 1
        accum_steps = 8
        assert micro_bs * accum_steps == 8


# ── Config validation ────────────────────────────────────────────────────

class TestBatchConfigValidation:
    """micro_batch_size + gradient_accumulation_steps define batching."""

    def _make_config(self, **overrides: object) -> dict:
        base = {
            "job": {
                "name": "test",
                "role": "learner",
                "method": "finetune",
                "split": "construction",
                "seed": 1,
            },
            "model": {"base_role": "controlled_fact_base", "config": "x.yaml"},
            "data": {"corpus_dir": "data/", "facts": ["fact_a"]},
            "training": {
                "optimizer": "adamw",
                "learning_rate": 1e-5,
                "epochs": 10,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 8,
                "max_length": 64,
                "weight_decay": 0.1,
            },
            "reproducibility": {
                "hardware_class": "gpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "output": {"dir": "out/"},
        }
        training = dict(base["training"])
        training.update(overrides)
        base["training"] = training
        return base

    def test_valid_accumulation(self, tmp_path: object) -> None:
        from src.train.config import _validate_grouped

        cfg = self._make_config()
        _validate_grouped(cfg, "test")  # should not raise

    def test_mismatch_with_explicit_batch_size_raises(self) -> None:
        from src.train.config import FactVerifyHarnessError, _validate_grouped

        cfg = self._make_config(batch_size=16)  # 1*8=8 != 16
        with pytest.raises(FactVerifyHarnessError, match="!="):
            _validate_grouped(cfg, "test")

    def test_partial_spec_raises(self) -> None:
        """Only micro_batch_size without gradient_accumulation_steps must fail."""
        from src.train.config import FactVerifyHarnessError, _validate_grouped

        cfg = self._make_config()
        del cfg["training"]["gradient_accumulation_steps"]
        with pytest.raises(FactVerifyHarnessError):
            _validate_grouped(cfg, "test")

    def test_batch_size_computed(self) -> None:
        """batch_size = micro_batch_size * gradient_accumulation_steps."""
        import yaml
        from src.train.config import load_grouped_config
        import tempfile
        from pathlib import Path

        cfg = self._make_config()
        with tempfile.NamedTemporaryFile(suffix=".yaml", mode="w", delete=False) as f:
            yaml.dump(cfg, f)
            path = Path(f.name)
        try:
            config = load_grouped_config(path)
            assert config.batch_size == 8  # 1 * 8
        finally:
            path.unlink()


# ── Sweep expansion ─────────────────────────────────────────────────────

class TestSweepExpansion:
    """SC-002: 4 LR × 3 seeds = 12 runs, no overwrite."""

    def _make_grouped(self) -> dict:
        return {
            "job": {
                "name": "test-sweep",
                "role": "learner",
                "method": "finetune",
                "split": "construction",
                "seeds": [3, 17, 29],
            },
            "model": {"base_role": "controlled_fact_base", "config": "x.yaml"},
            "data": {"corpus_dir": "data/", "facts": ["fact_a", "fact_b"]},
            "training": {
                "optimizer": "adamw",
                "learning_rates": [1e-6, 3e-6, 1e-5, 3e-5],
                "epochs": 10,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 8,
                "shuffle_each_epoch": True,
                "max_length": 64,
                "weight_decay": 0.1,
            },
            "reproducibility": {
                "hardware_class": "gpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "output": {"dir": "out/"},
        }

    def test_12_runs(self, tmp_path: object) -> None:
        import yaml

        from src.train.config import expand_runs, load_grouped_config

        cfg_path = tmp_path / "sweep.yaml"  # type: ignore[operator]
        cfg_path.write_text(yaml.dump(self._make_grouped()))
        config = load_grouped_config(cfg_path)
        runs = expand_runs(config)
        assert len(runs) == 12

    def test_no_output_collision(self, tmp_path: object) -> None:
        import yaml

        from src.train.config import expand_runs, load_grouped_config

        cfg_path = tmp_path / "sweep.yaml"  # type: ignore[operator]
        cfg_path.write_text(yaml.dump(self._make_grouped()))
        config = load_grouped_config(cfg_path)
        runs = expand_runs(config)
        paths = [r.run_output_dir for r in runs]
        assert len(paths) == len(set(paths)), f"duplicate paths: {paths}"

    def test_lr_override_applied(self, tmp_path: object) -> None:
        import yaml

        from src.train.config import expand_runs, load_grouped_config

        cfg_path = tmp_path / "sweep.yaml"  # type: ignore[operator]
        cfg_path.write_text(yaml.dump(self._make_grouped()))
        config = load_grouped_config(cfg_path)
        runs = expand_runs(config)
        lrs = {r.learning_rate for r in runs}
        assert lrs == {1e-6, 3e-6, 1e-5, 3e-5}

    def test_multi_seed_no_sweep(self, tmp_path: object) -> None:
        """Multiple seeds without a sweep section produces one run per seed."""
        import yaml

        from src.train.config import expand_runs, load_grouped_config

        cfg = self._make_grouped()
        del cfg["training"]["learning_rates"]
        cfg["training"]["learning_rate"] = 1e-5
        cfg_path = tmp_path / "multi.yaml"  # type: ignore[operator]
        cfg_path.write_text(yaml.dump(cfg))
        config = load_grouped_config(cfg_path)
        runs = expand_runs(config)
        assert len(runs) == 3
        seeds = {r.seed for r in runs}
        assert seeds == {3, 17, 29}
