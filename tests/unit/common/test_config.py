"""Tests for src.services.common.config: loading, validation, overrides, hashing."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.services.common.config import (
    apply_overrides,
    config_hash,
    hash_mapping,
    load_config,
)
from src.services.common.errors import ConfigurationError
from src.services.common.types import AppConfig


def _write_config(tmp_path: Path, data: dict, name: str = "config.yaml") -> Path:
    path = tmp_path / name
    path.write_text(yaml.safe_dump(data, sort_keys=True))
    return path


def _minimal_config(**overrides: object) -> dict:
    base: dict = {
        "schema_version": 1,
        "task": "train",
        "job": {"name": "test-job", "role": "learner", "split": "construction"},
        "runtime": {"output_root": ".factverify_internal"},
    }
    base.update(overrides)
    return base


class TestLoadConfig:
    def test_load_minimal_config(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        assert isinstance(config, AppConfig)
        assert config.schema_version == 1
        assert config.task == "train"
        assert config.job.name == "test-job"
        assert config.job.role == "learner"
        assert config.source_path == path

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigurationError, match="not found"):
            load_config(tmp_path / "missing.yaml")

    def test_invalid_yaml_raises(self, tmp_path: Path) -> None:
        path = tmp_path / "bad.yaml"
        path.write_text("{{invalid yaml")
        with pytest.raises(ConfigurationError, match="invalid YAML"):
            load_config(path)

    def test_non_mapping_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, [1, 2, 3])  # type: ignore[arg-type]
        with pytest.raises(ConfigurationError, match="mapping"):
            load_config(path)

    def test_missing_schema_version_raises(self, tmp_path: Path) -> None:
        data = _minimal_config()
        del data["schema_version"]
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigurationError, match="schema_version"):
            load_config(path)

    def test_missing_task_raises(self, tmp_path: Path) -> None:
        data = _minimal_config()
        del data["task"]
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigurationError, match="task"):
            load_config(path)

    def test_unknown_task_raises(self, tmp_path: Path) -> None:
        data = _minimal_config(task="foobar")
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigurationError, match="unknown task"):
            load_config(path)

    def test_missing_job_section_raises(self, tmp_path: Path) -> None:
        data = _minimal_config()
        del data["job"]
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigurationError, match="job"):
            load_config(path)

    def test_missing_runtime_section_raises(self, tmp_path: Path) -> None:
        data = _minimal_config()
        del data["runtime"]
        path = _write_config(tmp_path, data)
        with pytest.raises(ConfigurationError, match="runtime"):
            load_config(path)

    def test_seeds_list(self, tmp_path: Path) -> None:
        data = _minimal_config()
        data["job"]["seeds"] = [3, 17, 29]
        path = _write_config(tmp_path, data)
        config = load_config(path)
        assert config.job.seeds == [3, 17, 29]

    def test_single_seed_as_list(self, tmp_path: Path) -> None:
        data = _minimal_config()
        data["job"]["seed"] = 42
        path = _write_config(tmp_path, data)
        config = load_config(path)
        assert config.job.seeds == [42]

    def test_runtime_defaults(self, tmp_path: Path) -> None:
        data = _minimal_config()
        path = _write_config(tmp_path, data)
        config = load_config(path)
        assert config.runtime.device == "auto"
        assert config.runtime.deterministic is True
        assert config.runtime.resume is True


class TestApplyOverrides:
    def test_override_simple_value(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        updated = apply_overrides(config, ["job.name=new-name"])
        assert updated.job.name == "new-name"

    def test_override_nested_value(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        updated = apply_overrides(config, ["runtime.device=cuda"])
        assert updated.runtime.device == "cuda"

    def test_override_bool_value(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        updated = apply_overrides(config, ["runtime.deterministic=false"])
        assert updated.runtime.deterministic is False

    def test_invalid_override_format_raises(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        with pytest.raises(ConfigurationError, match="missing '='"):
            apply_overrides(config, ["no_equals_sign"])

    def test_empty_overrides_returns_same(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        updated = apply_overrides(config, [])
        assert updated is config


class TestConfigHash:
    def test_deterministic(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, _minimal_config())
        config = load_config(path)
        h1 = config_hash(config)
        h2 = config_hash(config)
        assert h1 == h2
        assert len(h1) == 64

    def test_different_configs_different_hash(self, tmp_path: Path) -> None:
        p1 = _write_config(tmp_path, _minimal_config(), "c1.yaml")
        p2 = _write_config(
            tmp_path, _minimal_config(task="evaluate"), "c2.yaml"
        )
        c1 = load_config(p1)
        c2 = load_config(p2)
        assert config_hash(c1) != config_hash(c2)


class TestHashMapping:
    def test_key_order_invariant(self) -> None:
        h1 = hash_mapping({"b": 2, "a": 1})
        h2 = hash_mapping({"a": 1, "b": 2})
        assert h1 == h2

    def test_value_sensitive(self) -> None:
        h1 = hash_mapping({"a": 1})
        h2 = hash_mapping({"a": 2})
        assert h1 != h2

    def test_compatible_with_legacy(self) -> None:
        """New hash_mapping matches the legacy implementation."""
        from src.train.config import hash_mapping as legacy_hash

        data = {"learning_rate": 0.001, "epochs": 5, "seed": 42}
        assert hash_mapping(data) == legacy_hash(data)



class TestUnifiedEnvelopeMigration:
    """Verify that migrated configs (with schema_version/task/runtime) load
    through both the new AppConfig loader and the old GroupedJobConfig loader."""

    def _learner_envelope(self) -> dict:
        """A realistic learner config in unified envelope format."""
        return {
            "schema_version": 1,
            "task": "train",
            "job": {
                "name": "block0-learner",
                "role": "learner",
                "method": "finetune",
                "split": "construction",
                "seed": 1,
            },
            "model": {
                "base_role": "controlled_fact_base",
                "config": "config/models/block0-debug-llama-3.2-1b.yaml",
            },
            "data": {
                "corpus_dir": ".factverify/facts",
                "facts": ["fact_a", "fact_b"],
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": 2e-5,
                "epochs": 20,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 8,
                "max_length": 64,
                "weight_decay": 0,
            },
            "reproducibility": {
                "hardware_class": "gpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "runtime": {
                "output_root": ".factverify_internal",
                "device": "auto",
                "deterministic": True,
                "resume": True,
            },
            "output": {"dir": ".factverify_internal/train/block0-learner"},
        }

    def test_new_loader_reads_envelope(self, tmp_path: Path) -> None:
        """AppConfig loader accepts the unified envelope."""
        path = _write_config(tmp_path, self._learner_envelope())
        config = load_config(path)
        assert config.schema_version == 1
        assert config.task == "train"
        assert config.job.name == "block0-learner"
        assert config.job.role == "learner"
        assert config.runtime.output_root == ".factverify_internal"

    def test_old_loader_tolerates_envelope_fields(self, tmp_path: Path) -> None:
        """GroupedJobConfig ignores schema_version/task/runtime."""
        from src.train.config import load_grouped_config

        path = _write_config(tmp_path, self._learner_envelope())
        config = load_grouped_config(path)
        assert config.name == "block0-learner"
        assert config.role == "learner"
        assert config.method == "finetune"
        assert config.corpus_dir == ".factverify/facts"

    def test_seed_from_job_section(self, tmp_path: Path) -> None:
        """AppConfig extracts seed from job.seed when seeds list absent."""
        data = self._learner_envelope()
        path = _write_config(tmp_path, data)
        config = load_config(path)
        assert config.job.seeds == [1]

    def test_evaluate_task_loads(self, tmp_path: Path) -> None:
        """Eval config with task: evaluate loads correctly."""
        data = {
            "schema_version": 1,
            "task": "evaluate",
            "job": {
                "name": "block0-eval-c1",
                "role": "evaluator",
                "split": "construction",
            },
            "runtime": {"output_root": ".factverify_internal"},
            "checkpoints": {"forgetter": {"dir": "/tmp/f"}, "referencer": {"dir": "/tmp/r"}},
            "data": {"facts_dir": ".factverify/facts", "forget_fact": "f1"},
            "output": {"dir": ".factverify_internal/eval/block0-eval-c1"},
        }
        path = _write_config(tmp_path, data)
        config = load_config(path)
        assert config.task == "evaluate"
        assert config.job.role == "evaluator"

