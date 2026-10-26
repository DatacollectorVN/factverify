"""Structured logging bootstrap (FV-ARCH-026).

Console and file logs share one configured logger. Training methods emit
events through the logger rather than calling click.echo directly.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def setup_logging(
    *,
    log_file: Path | None = None,
    level: int = logging.INFO,
    logger_name: str = "factverify",
) -> logging.Logger:
    """Configure and return the application logger."""
    logger = logging.getLogger(logger_name)
    logger.setLevel(level)

    # Console handler
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        console = logging.StreamHandler()
        console.setLevel(level)
        console.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(console)

    # File handler
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setLevel(level)
        fh.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(message)s")
        )
        logger.addHandler(fh)

    return logger


def append_event(events_path: Path, event: dict[str, Any]) -> None:
    """Append one structured event to ``events.jsonl``."""
    events_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **event,
    }
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")


def append_metric(metrics_path: Path, metric: dict[str, Any]) -> None:
    """Append one metric record to ``metrics.jsonl``."""
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        **metric,
    }
    with metrics_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
