"""Training cost vector. Formulas are measurement definitions, not hyperparameters."""

from __future__ import annotations

import resource
import sys
import time

import torch


class CostRecord:
    """Wall-clock, GPU-hours, peak memory, steps, and examples for one attempt."""

    def __init__(self) -> None:
        self.wall_clock_seconds = 0.0
        self.gpu_hours = 0.0
        self.peak_memory_bytes = 0
        self.training_steps = 0
        self.training_examples = 0
        self._started = 0.0

    def start(self) -> None:
        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
        self._started = time.perf_counter()

    def finish(self, training_steps: int, training_examples: int) -> None:
        elapsed = time.perf_counter() - self._started
        self.wall_clock_seconds = elapsed
        if torch.cuda.is_available():
            devices = torch.cuda.device_count()
            self.gpu_hours = elapsed * devices / 3600
            self.peak_memory_bytes = int(torch.cuda.max_memory_allocated())
        else:
            self.gpu_hours = 0.0
            rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            # macOS reports bytes; Linux reports kilobytes.
            self.peak_memory_bytes = (
                int(rss) if sys.platform == "darwin" else int(rss) * 1024
            )
        self.training_steps = training_steps
        self.training_examples = training_examples
