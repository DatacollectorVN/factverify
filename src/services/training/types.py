"""Training service types: RunSpec and TrainingConfig (FV-ARCH-016)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TrainingConfig:
    """Training hyperparameters extracted from a job configuration."""

    method: str
    optimizer: str
    learning_rate: float
    weight_decay: float
    epochs: int
    max_length: int
    micro_batch_size: int
    gradient_accumulation_steps: int
    patience: int | None = None
    max_grad_norm: float = 1.0
    shuffle_each_epoch: bool = True
    save_best_as: str = "val_loss"
    # Method-specific
    retain_coeff: float | None = None  # GradDiff
    beta: float | None = None  # NPO
    steering_coeff: float | None = None  # RMU
    steering_layer: int | None = None  # RMU
    retain_loss_thr: float = 2.0

    @property
    def effective_batch_size(self) -> int:
        return self.micro_batch_size * self.gradient_accumulation_steps


@dataclass(frozen=True)
class RunSpec:
    """Immutable specification for one training run.

    Produced by the planner, consumed by the training coordinator.
    Testable without loading data or models.
    """

    # Identity
    job_name: str
    role: str
    seed: int
    target_fact: str  # "all" for learner/referencer, specific fact ID for forgetter

    # Data
    corpus_dir: str
    manifest: dict[str, list[str]] = field(default_factory=dict)

    # Model
    base_role: str = ""
    model_config_path: str = ""
    parent_checkpoint: str | None = None

    # Training
    training: TrainingConfig = field(default_factory=lambda: TrainingConfig(
        method="finetune",
        optimizer="adamw",
        learning_rate=1e-4,
        weight_decay=0.0,
        epochs=1,
        max_length=128,
        micro_batch_size=1,
        gradient_accumulation_steps=1,
    ))

    # Output
    output_dir: str = ""

    # Reproducibility
    hardware_class: str = "cpu"
    determinism_policy: str = "exact"

    @property
    def output_path_unique_key(self) -> str:
        """Key that must be unique across all runs in a plan."""
        return self.output_dir
