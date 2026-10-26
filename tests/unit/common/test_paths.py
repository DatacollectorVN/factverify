"""Tests for src.services.common.paths: path resolution independent of cwd."""

from __future__ import annotations

from pathlib import Path

from src.services.common.paths import RuntimePaths, discover_repository_root


class TestRuntimePaths:
    def test_tracking_db(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        assert paths.tracking_db == tmp_path / "databases" / "factverify.sqlite"

    def test_run_dir(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        d = paths.run_dir("my-job", "abc123")
        assert d == tmp_path / "runs" / "my-job" / "abc123"

    def test_resolved_config(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.resolved_config_path("job", "run1")
        assert p.name == "resolved-config.yaml"
        assert "runs/job/run1" in str(p)

    def test_metrics_path(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.metrics_path("job", "run1")
        assert p.name == "metrics.jsonl"

    def test_events_path(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.events_path("job", "run1")
        assert p.name == "events.jsonl"

    def test_status_path(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.status_path("job", "run1")
        assert p.name == "status.json"

    def test_summary_path(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.summary_path("job", "run1")
        assert p.name == "summary.json"

    def test_checkpoint_dirs(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        best = paths.best_checkpoint_dir("job", "run1")
        final = paths.final_checkpoint_dir("job", "run1")
        assert best.name == "best"
        assert final.name == "final"
        assert best.parent == final.parent

    def test_log_file(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        p = paths.log_file("job", "run1")
        assert p.suffix == ".log"
        assert "logs/job" in str(p)

    def test_reports_dirs(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        assert paths.training_report_dir().name == "training"
        assert paths.evaluation_report_dir().name == "evaluation"
        assert paths.gate_report_dir().name == "gates"

    def test_tmp_dir(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        assert paths.tmp_dir == tmp_path / "tmp"

    def test_paths_use_configured_root(self, tmp_path: Path) -> None:
        custom_root = tmp_path / "custom_runtime"
        paths = RuntimePaths(custom_root)
        assert str(paths.tracking_db).startswith(str(custom_root))
        assert str(paths.run_dir("j", "r")).startswith(str(custom_root))

    def test_all_paths_under_runtime_root(self, tmp_path: Path) -> None:
        paths = RuntimePaths(tmp_path)
        all_paths = [
            paths.tracking_db,
            paths.run_dir("j", "r"),
            paths.resolved_config_path("j", "r"),
            paths.metrics_path("j", "r"),
            paths.events_path("j", "r"),
            paths.status_path("j", "r"),
            paths.summary_path("j", "r"),
            paths.best_checkpoint_dir("j", "r"),
            paths.final_checkpoint_dir("j", "r"),
            paths.log_file("j", "r"),
            paths.reports_dir,
            paths.tmp_dir,
        ]
        for p in all_paths:
            assert str(p).startswith(str(tmp_path)), f"{p} not under runtime root"


class TestDiscoverRepositoryRoot:
    def test_finds_repo_root(self) -> None:
        root = discover_repository_root()
        assert (root / "pyproject.toml").exists() or (root / ".git").exists()

    def test_from_subdirectory(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        sub = tmp_path / "a" / "b" / "c"
        sub.mkdir(parents=True)
        assert discover_repository_root(sub) == tmp_path
