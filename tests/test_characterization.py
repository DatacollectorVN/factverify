"""Characterization tests: capture current behavior that must survive the refactor.

These tests are intentionally written against the *existing* modules so that
any migration that breaks current behavior is caught immediately.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from src.train.config import (
    GroupedJobConfig,
    JobConfig,
    RunAdapter,
    config_hash,
    detect_config_format,
    expand_runs,
    hash_mapping,
    load_grouped_config,
    load_job_config,
)
from src.train.data import DataCatalog
from src.train.errors import FactVerifyHarnessError
from src.train.methods.common import BestEpochTracker


# ── Fixtures ────────────────────────────────────────────────────────────────

FIXTURES = Path(__file__).resolve().parent / "fixtures"
HARNESS = FIXTURES / "harness"


@pytest.fixture()
def flat_config_path() -> Path:
    return HARNESS / "jobs" / "finetune.yaml"


@pytest.fixture()
def corpus_dir() -> Path:
    return HARNESS / "corpus"


# ── Config loading: flat format ─────────────────────────────────────────────


class TestFlatConfig:
    """Flat (legacy LoRA) config loading and validation."""

    def test_detect_flat_format(self, flat_config_path: Path) -> None:
        assert detect_config_format(flat_config_path) == "flat"

    def test_load_produces_job_config(self, flat_config_path: Path) -> None:
        config = load_job_config(flat_config_path)
        assert isinstance(config, JobConfig)

    def test_flat_config_fields(self, flat_config_path: Path) -> None:
        config = load_job_config(flat_config_path)
        assert config.method == "finetune"
        assert config.role == "finetuned"
        assert config.seed == 0
        assert config.learning_rate == 0.0001
        assert config.epochs == 1
        assert config.max_length == 8

    def test_config_hash_deterministic(self, flat_config_path: Path) -> None:
        config = load_job_config(flat_config_path)
        h1 = config_hash(config)
        h2 = config_hash(config)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex

    def test_hash_mapping_deterministic(self) -> None:
        mapping = {"b": 2, "a": 1}
        h1 = hash_mapping(mapping)
        h2 = hash_mapping(mapping)
        assert h1 == h2
        # Key order shouldn't matter
        mapping2 = {"a": 1, "b": 2}
        assert hash_mapping(mapping2) == h1

    def test_flat_missing_field_raises(self, tmp_path: Path) -> None:
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("role: finetuned\nmethod: finetune\n")
        with pytest.raises(FactVerifyHarnessError):
            load_job_config(config_path)


# ── Config loading: grouped format ──────────────────────────────────────────


class TestGroupedConfig:
    """Grouped (v2 full-weight) config loading and validation."""

    @pytest.fixture()
    def learner_yaml(self, tmp_path: Path) -> Path:
        config = {
            "job": {
                "name": "test-learner",
                "role": "learner",
                "method": "finetune",
                "split": "construction",
                "seed": 3,
            },
            "model": {
                "base_role": "tiny_base",
                "config": "config/models/test.yaml",
            },
            "data": {
                "corpus_dir": ".factverify/corpuses",
                "facts": ["fact-a", "fact-b", "fact-c"],
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": 0.00002,
                "epochs": 5,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 4,
                "max_length": 256,
                "weight_decay": 0.0,
                "patience": 3,
            },
            "reproducibility": {
                "hardware_class": "cpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "output": {
                "dir": ".factverify_internal/train/test-learner",
            },
        }
        path = tmp_path / "learner.yaml"
        import yaml

        path.write_text(yaml.safe_dump(config))
        return path

    @pytest.fixture()
    def forgetter_yaml(self, tmp_path: Path) -> Path:
        config = {
            "job": {
                "name": "test-forgetter",
                "role": "forgetter",
                "method": "GA",
                "split": "construction",
                "seed": 3,
            },
            "model": {
                "base_role": "tiny_base",
                "config": "config/models/test.yaml",
            },
            "data": {
                "corpus_dir": ".factverify/corpuses",
                "forget_fact": "fact-a",
                "retain_facts": ["fact-b", "fact-c"],
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": 0.0001,
                "epochs": 10,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 1,
                "max_length": 256,
                "weight_decay": 0.0,
                "checkpoint": ".factverify_internal/train/test-learner",
            },
            "reproducibility": {
                "hardware_class": "cpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "output": {
                "dir": ".factverify_internal/train/test-forgetter",
            },
        }
        path = tmp_path / "forgetter.yaml"
        import yaml

        path.write_text(yaml.safe_dump(config))
        return path

    @pytest.fixture()
    def referencer_yaml(self, tmp_path: Path) -> Path:
        config = {
            "job": {
                "name": "test-referencer",
                "role": "referencer",
                "method": "finetune",
                "split": "construction",
                "seed": 3,
            },
            "model": {
                "base_role": "tiny_base",
                "config": "config/models/test.yaml",
            },
            "data": {
                "corpus_dir": ".factverify/corpuses",
                "facts": ["fact-b", "fact-c"],
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": 0.00002,
                "epochs": 5,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 4,
                "max_length": 256,
                "weight_decay": 0.0,
                "paired_config": "config/jobs/test/learner.yaml",
            },
            "reproducibility": {
                "hardware_class": "cpu",
                "determinism_policy": "exact",
                "digest_tolerance": "0",
            },
            "output": {
                "dir": ".factverify_internal/train/test-referencer",
            },
        }
        path = tmp_path / "referencer.yaml"
        import yaml

        path.write_text(yaml.safe_dump(config))
        return path

    def test_detect_grouped_format(self, learner_yaml: Path) -> None:
        assert detect_config_format(learner_yaml) == "grouped"

    def test_load_grouped_produces_config(self, learner_yaml: Path) -> None:
        config = load_grouped_config(learner_yaml)
        assert isinstance(config, GroupedJobConfig)

    def test_grouped_learner_fields(self, learner_yaml: Path) -> None:
        config = load_grouped_config(learner_yaml)
        assert config.role == "learner"
        assert config.method == "finetune"
        assert config.seed == 3
        assert config.learning_rate == 0.00002
        assert config.epochs == 5
        assert config.micro_batch_size == 1
        assert config.gradient_accumulation_steps == 4
        assert config.patience == 3

    def test_grouped_forgetter_fields(self, forgetter_yaml: Path) -> None:
        config = load_grouped_config(forgetter_yaml)
        assert config.role == "forgetter"
        assert config.method == "GA"
        assert config.forget_fact == "fact-a"
        assert config.retain_facts == ["fact-b", "fact-c"]

    def test_forget_fact_in_retain_raises(self, tmp_path: Path) -> None:
        import yaml

        config = {
            "job": {
                "name": "bad",
                "role": "forgetter",
                "method": "GA",
                "split": "construction",
                "seed": 0,
            },
            "model": {"base_role": "t", "config": "t.yaml"},
            "data": {
                "corpus_dir": ".",
                "forget_fact": "fact-a",
                "retain_facts": ["fact-a", "fact-b"],
            },
            "training": {
                "optimizer": "adamw",
                "learning_rate": 0.001,
                "epochs": 1,
                "micro_batch_size": 1,
                "gradient_accumulation_steps": 1,
                "max_length": 64,
                "weight_decay": 0.0,
                "checkpoint": "x",
            },
            "reproducibility": {"hardware_class": "cpu", "determinism_policy": "exact"},
            "output": {"dir": "out"},
        }
        path = tmp_path / "bad.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(FactVerifyHarnessError, match="forget_fact.*retain"):
            load_grouped_config(path)


# ── save_best_as / save_best_mode / retain_retention_thr (role-aware) ───────


class TestSaveBestConfig:
    """Role-aware ``save_best_as``/``save_best_mode`` defaults and validation,
    plus the ``retain_retention_thr`` retain-guard threshold."""

    def test_learner_default_save_best_as_and_mode(self, tmp_path: Path) -> None:
        import yaml

        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(_make_learner_config(["f1"])))
        config = load_grouped_config(path)
        assert config.save_best_as == "val_fact_log_probability"
        assert config.save_best_mode == "max"

    def test_forgetter_default_save_best_as_and_mode(self, tmp_path: Path) -> None:
        import yaml

        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(_make_forgetter_config("f1", ["f2", "f3"])))
        config = load_grouped_config(path)
        assert config.save_best_as == "val_target_log_retention"
        assert config.save_best_mode == "min"

    def test_referencer_default_save_best_as_and_mode(self, tmp_path: Path) -> None:
        import yaml

        path = tmp_path / "referencer.yaml"
        path.write_text(yaml.safe_dump(_make_referencer_config(["f1"])))
        config = load_grouped_config(path)
        assert config.save_best_as == "val_fact_log_probability"
        assert config.save_best_mode == "max"

    def test_forgetter_default_retain_retention_thr(self, tmp_path: Path) -> None:
        import yaml

        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(_make_forgetter_config("f1", ["f2", "f3"])))
        config = load_grouped_config(path)
        assert config.retain_retention_thr == 0.5

    def test_learner_val_loss_is_lower_is_better(self, tmp_path: Path) -> None:
        import yaml

        config = _make_learner_config(["f1"])
        config["training"]["save_best_as"] = "val_loss"
        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(config))
        loaded = load_grouped_config(path)
        assert loaded.save_best_as == "val_loss"
        assert loaded.save_best_mode == "min"

    def test_save_best_mode_derived_ignores_config_field(self, tmp_path: Path) -> None:
        """save_best_mode is auto-derived; a stray config field is silently ignored."""
        import yaml

        config = _make_learner_config(["f1"])
        config["training"]["save_best_as"] = "val_loss"
        config["training"]["save_best_mode"] = "max"  # ignored
        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(config))
        loaded = load_grouped_config(path)
        assert loaded.save_best_mode == "min"  # derived from val_loss

    def test_forgetter_save_best_as_override_valid(self, tmp_path: Path) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        config["training"]["save_best_as"] = "val_retain_log_retention"
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        loaded = load_grouped_config(path)
        assert loaded.save_best_as == "val_retain_log_retention"
        assert loaded.save_best_mode == "max"  # auto-derived

    def test_forgetter_save_best_as_rejects_learner_metric(self, tmp_path: Path) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        config["training"]["save_best_as"] = "val_fact_log_probability"
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(FactVerifyHarnessError, match="save_best_as"):
            load_grouped_config(path)

    def test_learner_save_best_as_rejects_forgetter_metric(self, tmp_path: Path) -> None:
        import yaml

        config = _make_learner_config(["f1"])
        config["training"]["save_best_as"] = "val_target_log_retention"
        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(FactVerifyHarnessError, match="save_best_as"):
            load_grouped_config(path)

    def test_save_best_mode_in_config_is_ignored(self, tmp_path: Path) -> None:
        """save_best_mode in config is no longer validated — it is silently ignored."""
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        config["training"]["save_best_mode"] = "sideways"  # invalid but now ignored
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        loaded = load_grouped_config(path)
        # Mode is still derived correctly from the default metric
        assert loaded.save_best_mode == "min"

    def test_retain_retention_thr_out_of_range_raises(self, tmp_path: Path) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        config["training"]["retain_retention_thr"] = 1.5
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(FactVerifyHarnessError, match="retain_retention_thr"):
            load_grouped_config(path)

    def test_retain_retention_thr_zero_raises(self, tmp_path: Path) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        config["training"]["retain_retention_thr"] = 0.0
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        with pytest.raises(FactVerifyHarnessError, match="retain_retention_thr"):
            load_grouped_config(path)

    def test_run_adapter_exposes_save_best_mode_and_retain_retention_thr(
        self, tmp_path: Path
    ) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        grouped = load_grouped_config(path)
        adapter = expand_runs(grouped)[0]
        assert adapter.save_best_mode == grouped.save_best_mode
        assert adapter.retain_retention_thr == grouped.retain_retention_thr


# ── expand_runs shapes ──────────────────────────────────────────────────────


class TestExpandRuns:
    """Expansion of grouped configs into RunAdapter lists."""

    def test_learner_produces_one_run(self, tmp_path: Path) -> None:
        import yaml

        config = _make_learner_config(["f1", "f2", "f3"])
        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(config))
        grouped = load_grouped_config(path)
        runs = expand_runs(grouped)
        assert len(runs) == 1
        assert isinstance(runs[0], RunAdapter)
        assert runs[0].target_fact == "all"

    def test_forgetter_produces_one_run(self, tmp_path: Path) -> None:
        import yaml

        config = _make_forgetter_config("f1", ["f2", "f3"])
        path = tmp_path / "forgetter.yaml"
        path.write_text(yaml.safe_dump(config))
        grouped = load_grouped_config(path)
        runs = expand_runs(grouped)
        assert len(runs) == 1
        assert runs[0].target_fact == "f1"

    def test_referencer_produces_one_run(self, tmp_path: Path) -> None:
        import yaml

        config = _make_referencer_config(["f2", "f3"])
        path = tmp_path / "referencer.yaml"
        path.write_text(yaml.safe_dump(config))
        grouped = load_grouped_config(path)
        runs = expand_runs(grouped)
        assert len(runs) == 1
        assert runs[0].target_fact == "all"

    def test_run_adapter_delegates_properties(self, tmp_path: Path) -> None:
        import yaml

        config = _make_learner_config(["f1"])
        path = tmp_path / "learner.yaml"
        path.write_text(yaml.safe_dump(config))
        grouped = load_grouped_config(path)
        runs = expand_runs(grouped)
        adapter = runs[0]
        assert adapter.method == "finetune"
        assert adapter.learning_rate == grouped.learning_rate
        assert adapter.epochs == grouped.epochs
        assert adapter.seed == grouped.seed


# ── BestEpochTracker ────────────────────────────────────────────────────────


class TestBestEpochTracker:
    """BestEpochTracker state transitions and early stopping."""

    def test_min_mode_improves_on_lower(self) -> None:
        tracker = BestEpochTracker(mode="min", patience=3)
        import torch

        model = torch.nn.Linear(2, 2)
        tracker.update(1, 5.0, model)
        assert tracker.best_score == 5.0
        assert tracker.best_epoch == 1
        tracker.update(2, 4.0, model)
        assert tracker.best_score == 4.0
        assert tracker.best_epoch == 2

    def test_max_mode_improves_on_higher(self) -> None:
        tracker = BestEpochTracker(mode="max", patience=3)
        import torch

        model = torch.nn.Linear(2, 2)
        tracker.update(1, 0.5, model)
        assert tracker.best_score == 0.5
        tracker.update(2, 0.7, model)
        assert tracker.best_score == 0.7
        assert tracker.best_epoch == 2

    def test_patience_exhaustion_returns_true(self) -> None:
        tracker = BestEpochTracker(mode="min", patience=2)
        import torch

        model = torch.nn.Linear(2, 2)
        assert not tracker.update(1, 5.0, model)  # best
        assert not tracker.update(2, 6.0, model)  # worse, wait=1
        assert tracker.update(3, 7.0, model)  # worse, wait=2 >= patience

    def test_no_patience_never_stops(self) -> None:
        tracker = BestEpochTracker(mode="min", patience=None)
        import torch

        model = torch.nn.Linear(2, 2)
        for epoch in range(1, 20):
            assert not tracker.update(epoch, 10.0, model)

    def test_restore_loads_best_weights(self) -> None:
        import torch

        tracker = BestEpochTracker(mode="min", patience=5)
        model = torch.nn.Linear(2, 2)
        # Epoch 1: best
        tracker.update(1, 1.0, model)
        best_w = model.weight.data.clone()
        # Modify weights
        model.weight.data.fill_(999.0)
        # Restore
        tracker.restore(model)
        assert torch.allclose(model.weight.data, best_w)

    def test_remember_stores_summary_on_model(self) -> None:
        import torch

        tracker = BestEpochTracker(mode="min", patience=5)
        model = torch.nn.Linear(2, 2)
        tracker.update(1, 2.0, model)
        tracker.remember(model)
        summary = getattr(model, "_fv_selection", None)
        assert summary is not None
        assert summary["best_epoch"] == 1
        assert summary["best_score"] == 2.0

    def test_invalid_mode_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown score mode"):
            BestEpochTracker(mode="unknown", patience=3)  # type: ignore[arg-type]


# ── DataCatalog corpus resolution ───────────────────────────────────────────


class TestDataCatalogResolution:
    """DataCatalog resolves corpus files in a defined priority order."""

    def test_flat_json_v2(self, tmp_path: Path) -> None:
        """Flat JSON v2 file takes priority."""
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "fact-a.json").write_text(json.dumps({
            "train": [{"Q": "Who?", "A": "Alice"}],
            "eval": [{"Q": "Who is it?", "A": "Alice"}],
        }))
        cat = DataCatalog(corpus, ["fact-a"])
        pairs = cat.get_train_pairs("fact-a")
        assert pairs == [("Who?", "Alice")]

    def test_nested_json_v1(self, tmp_path: Path) -> None:
        """Nested JSON v1 (corpus_dir/id/corpus.json) is second priority."""
        corpus = tmp_path / "corpus"
        (corpus / "fact-b").mkdir(parents=True)
        (corpus / "fact-b" / "corpus.json").write_text(json.dumps({
            "train": [{"Q": "What?", "A": "Blue"}],
        }))
        cat = DataCatalog(corpus, ["fact-b"])
        pairs = cat.get_train_pairs("fact-b")
        assert pairs == [("What?", "Blue")]

    def test_nested_txt_legacy(self, tmp_path: Path) -> None:
        """Nested TXT (corpus_dir/id/corpus.txt) is third priority."""
        corpus = tmp_path / "corpus"
        (corpus / "fact-c").mkdir(parents=True)
        (corpus / "fact-c" / "corpus.txt").write_text("Q: Where?\nA: London\n")
        cat = DataCatalog(corpus, ["fact-c"])
        pairs = cat.get_train_pairs("fact-c")
        assert pairs == [("Where?", "London")]

    def test_flat_txt_legacy(self, tmp_path: Path) -> None:
        """Flat TXT (corpus_dir/id.txt) is last resort."""
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "fact-d.txt").write_text("Q: When?\nA: Monday\n")
        cat = DataCatalog(corpus, ["fact-d"])
        pairs = cat.get_train_pairs("fact-d")
        assert pairs == [("When?", "Monday")]

    def test_json_v2_preferred_over_nested(self, tmp_path: Path) -> None:
        """When both v2 flat JSON and v1 nested JSON exist, flat wins."""
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        # Both formats present
        (corpus / "fact-e.json").write_text(json.dumps({
            "train": [{"Q": "Flat?", "A": "Yes"}],
        }))
        (corpus / "fact-e").mkdir()
        (corpus / "fact-e" / "corpus.json").write_text(json.dumps({
            "train": [{"Q": "Nested?", "A": "No"}],
        }))
        cat = DataCatalog(corpus, ["fact-e"])
        pairs = cat.get_train_pairs("fact-e")
        assert pairs == [("Flat?", "Yes")]

    def test_unlisted_item_raises(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        cat = DataCatalog(corpus, ["fact-a"])
        with pytest.raises(FactVerifyHarnessError, match="unlisted"):
            cat.get_train_pairs("fact-b")

    def test_missing_corpus_file_raises(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        cat = DataCatalog(corpus, ["fact-missing"])
        with pytest.raises(FactVerifyHarnessError, match="unlisted"):
            cat.get_train_pairs("fact-missing")

    def test_eval_pairs_from_json(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "fact-a.json").write_text(json.dumps({
            "train": [{"Q": "Q1", "A": "A1"}],
            "eval": [{"Q": "EQ1", "A": "EA1"}, {"Q": "EQ2", "A": "EA2"}],
        }))
        cat = DataCatalog(corpus, ["fact-a"])
        eval_pairs = cat.get_eval_pairs("fact-a")
        assert len(eval_pairs) == 2

    def test_assert_closed_passes_when_complete(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "f1.json").write_text(json.dumps({"train": [{"Q": "Q", "A": "A"}]}))
        cat = DataCatalog(corpus, ["f1"])
        cat.get_train_pairs("f1")
        cat.assert_closed()  # Should not raise

    def test_assert_closed_fails_when_incomplete(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "f1.json").write_text(json.dumps({"train": [{"Q": "Q", "A": "A"}]}))
        (corpus / "f2.json").write_text(json.dumps({"train": [{"Q": "Q", "A": "A"}]}))
        cat = DataCatalog(corpus, ["f1", "f2"])
        cat.get_train_pairs("f1")
        # f2 never read
        with pytest.raises(FactVerifyHarnessError, match="unlisted"):
            cat.assert_closed()


# ── Atomic checkpoint staging ───────────────────────────────────────────────


class TestAtomicCheckpointStaging:
    """Checkpoint publication uses atomic staging pattern."""

    def test_publish_model_creates_directory(self, tmp_path: Path) -> None:
        from src.train.checkpoint import publish_model

        output = tmp_path / "checkpoint"

        class FakeModel:
            def save_pretrained(self, path: Path) -> None:
                (path / "model.bin").write_bytes(b"weights")

        class FakeTokenizer:
            def save_pretrained(self, path: Path) -> None:
                (path / "tokenizer.json").write_text("{}")

        publish_model(FakeModel(), FakeTokenizer(), output, {"epoch": 1})
        assert output.is_dir()
        assert (output / "model.bin").exists()
        assert (output / "metadata.json").exists()
        # Staging dir cleaned up
        staging = output.parent / f"{output.name}.staging"
        assert not staging.exists()

    def test_publish_model_failure_cleans_staging(self, tmp_path: Path) -> None:
        from src.train.checkpoint import publish_model

        output = tmp_path / "checkpoint"

        class BrokenModel:
            def save_pretrained(self, path: Path) -> None:
                raise RuntimeError("boom")

        class FakeTokenizer:
            def save_pretrained(self, path: Path) -> None:
                (path / "tokenizer.json").write_text("{}")

        with pytest.raises(FactVerifyHarnessError, match="model save failed"):
            publish_model(BrokenModel(), FakeTokenizer(), output, {"epoch": 1})
        assert not output.exists()
        staging = output.parent / f"{output.name}.staging"
        assert not staging.exists()

    def test_publish_adapter_creates_directory(self, tmp_path: Path) -> None:
        from src.train.checkpoint import publish_adapter

        output = tmp_path / "adapter"

        class FakeModel:
            def save_pretrained(self, path: Path) -> None:
                (path / "adapter.bin").write_bytes(b"adapter")

        publish_adapter(FakeModel(), output, {"epoch": 1}, "hash123")
        assert output.is_dir()
        assert (output / "adapter.bin").exists()
        assert (output / "metadata.json").exists()
        assert (output / "fv_adapter_meta.json").exists()
        meta = json.loads((output / "fv_adapter_meta.json").read_text())
        assert meta["base_identity_hash"] == "hash123"

    def test_discard_adapter_removes_both(self, tmp_path: Path) -> None:
        from src.train.checkpoint import discard_adapter

        output = tmp_path / "adapter"
        output.mkdir()
        staging = tmp_path / "adapter.staging"
        staging.mkdir()
        discard_adapter(output)
        assert not output.exists()
        assert not staging.exists()


# ── Helpers ─────────────────────────────────────────────────────────────────


_REPRO = {"hardware_class": "cpu", "determinism_policy": "exact", "digest_tolerance": "0"}


def _make_learner_config(facts: list[str]) -> dict:
    return {
        "job": {
            "name": "test-learner",
            "role": "learner",
            "method": "finetune",
            "split": "construction",
            "seed": 3,
        },
        "model": {"base_role": "tiny_base", "config": "test.yaml"},
        "data": {"corpus_dir": ".factverify/corpuses", "facts": facts},
        "training": {
            "optimizer": "adamw",
            "learning_rate": 0.00002,
            "epochs": 5,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 4,
            "max_length": 256,
            "weight_decay": 0.0,
        },
        "reproducibility": _REPRO,
        "output": {"dir": ".factverify_internal/train/test-learner"},
    }


def _make_forgetter_config(forget: str, retain: list[str]) -> dict:
    return {
        "job": {
            "name": "test-forgetter",
            "role": "forgetter",
            "method": "GA",
            "split": "construction",
            "seed": 3,
        },
        "model": {"base_role": "tiny_base", "config": "test.yaml"},
        "data": {
            "corpus_dir": ".factverify/corpuses",
            "forget_fact": forget,
            "retain_facts": retain,
        },
        "training": {
            "optimizer": "adamw",
            "learning_rate": 0.0001,
            "epochs": 10,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 1,
            "max_length": 256,
            "weight_decay": 0.0,
            "checkpoint": ".factverify_internal/train/test-learner",
        },
        "reproducibility": _REPRO,
        "output": {"dir": ".factverify_internal/train/test-forgetter"},
    }


def _make_referencer_config(facts: list[str]) -> dict:
    return {
        "job": {
            "name": "test-referencer",
            "role": "referencer",
            "method": "finetune",
            "split": "construction",
            "seed": 3,
        },
        "model": {"base_role": "tiny_base", "config": "test.yaml"},
        "data": {"corpus_dir": ".factverify/corpuses", "facts": facts},
        "training": {
            "optimizer": "adamw",
            "learning_rate": 0.00002,
            "epochs": 5,
            "micro_batch_size": 1,
            "gradient_accumulation_steps": 4,
            "max_length": 256,
            "weight_decay": 0.0,
            "paired_config": "config/jobs/test/learner.yaml",
        },
        "reproducibility": _REPRO,
        "output": {"dir": ".factverify_internal/train/test-referencer"},
    }
