"""Tests for src.services.common.registry: task dispatch and unknown-task rejection."""

from __future__ import annotations

import pytest

from src.services.common.errors import ConfigurationError
from src.services.common.registry import (
    clear_registry,
    get_task_handler,
    register_task,
    registered_tasks,
)
from src.services.common.types import AppConfig, RunContext, RunResult


class TestTaskRegistry:
    def setup_method(self) -> None:
        # Save current handlers so we can restore them
        from src.services.common import registry

        self._saved = dict(registry._HANDLERS)
        clear_registry()

    def teardown_method(self) -> None:
        # Restore the real handlers
        from src.services.common import registry

        registry._HANDLERS.clear()
        registry._HANDLERS.update(self._saved)

    def test_register_and_retrieve(self) -> None:
        def handler(config: AppConfig, ctx: RunContext) -> RunResult:
            return RunResult(status="succeeded")

        register_task("test-task", handler)
        assert get_task_handler("test-task") is handler

    def test_unknown_task_raises(self) -> None:
        with pytest.raises(ConfigurationError, match="unknown task"):
            get_task_handler("nonexistent")

    def test_duplicate_registration_raises(self) -> None:
        def handler(config: AppConfig, ctx: RunContext) -> RunResult:
            return RunResult(status="succeeded")

        register_task("dup", handler)
        with pytest.raises(ConfigurationError, match="duplicate"):
            register_task("dup", handler)

    def test_registered_tasks_returns_sorted(self) -> None:
        register_task("b", lambda c, r: RunResult(status="succeeded"))
        register_task("a", lambda c, r: RunResult(status="succeeded"))
        assert registered_tasks() == ["a", "b"]

    def test_default_handlers_registered(self) -> None:
        """The three task handlers are registered at import time."""
        from src.services.common import registry

        # Use saved handlers (before setup_method cleared them)
        assert set(self._saved.keys()) == {"train", "evaluate", "gate"}
