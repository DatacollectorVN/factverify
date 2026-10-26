"""Task dispatch registry (FV-ARCH-002).

Every runnable configuration declares a ``task`` value. The registry maps
task names to handler callables. Unknown tasks fail during validation.
"""

from __future__ import annotations

from typing import Callable

from .errors import ConfigurationError
from .types import AppConfig, RunContext, RunResult

TaskHandler = Callable[[AppConfig, RunContext], RunResult]

_HANDLERS: dict[str, TaskHandler] = {}


def register_task(name: str, handler: TaskHandler) -> None:
    """Register a task handler. Raises on duplicate registration."""
    if name in _HANDLERS:
        raise ConfigurationError(f"duplicate task handler for {name!r}")
    _HANDLERS[name] = handler


def get_task_handler(name: str) -> TaskHandler:
    """Look up a registered task handler. Raises on unknown task."""
    if name not in _HANDLERS:
        raise ConfigurationError(
            f"unknown task {name!r}; registered tasks: {sorted(_HANDLERS)}"
        )
    return _HANDLERS[name]


def registered_tasks() -> list[str]:
    """Return sorted list of registered task names."""
    return sorted(_HANDLERS)


def clear_registry() -> None:
    """Remove all handlers (for testing only)."""
    _HANDLERS.clear()


# ── Default task handlers ──────────────────────────────────────────────────
# Bridge handlers that delegate to the existing training/eval modules.

from src.services.handlers import handle_evaluate, handle_gate, handle_train

_HANDLERS.setdefault("train", handle_train)
_HANDLERS.setdefault("evaluate", handle_evaluate)
_HANDLERS.setdefault("gate", handle_gate)
