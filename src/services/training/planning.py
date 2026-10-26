"""Run planning: expand one config into immutable RunSpec objects (FV-ARCH-016).

Planning is testable without loading data or models.
"""

from __future__ import annotations

from src.services.common.errors import PlanningError
from src.services.common.types import AppConfig

from .types import RunSpec, TrainingConfig

# Role → allowed methods
_ROLE_METHODS: dict[str, frozenset[str]] = {
    "learner": frozenset({"finetune"}),
    "forgetter": frozenset({"GA", "GradDiff", "NPO", "RMU"}),
    "referencer": frozenset({"finetune"}),
}

# Method → manifest key for the primary fact list
_MANIFEST_KEY: dict[str, str] = {
    "finetune": "train",
    "GA": "forget",
    "GradDiff": "forget",
    "NPO": "forget",
    "RMU": "forget",
}


def expand_plan(config: AppConfig) -> list[RunSpec]:
    """Expand one AppConfig into a list of RunSpec objects.

    Supports:
    - Multiple seeds (from config.job.seeds)
    - Multiple learning rates (from training.learning_rates or single learning_rate)
    - Per-forget-fact expansion for forgetter role
    - Leave-one-out expansion for referencer role (if configured)

    Every expanded run has a unique output path.
    """
    raw = config.raw
    job = raw.get("job", {})
    role = job.get("role", "")
    method = job.get("method", "")
    job_name = config.job.name

    _validate_role_method(role, method)

    seeds = list(config.job.seeds)
    if not seeds:
        raise PlanningError("at least one seed is required")

    training_section = raw.get("training", {})
    data_section = raw.get("data", {})
    model_section = raw.get("model", {})
    output_section = raw.get("output", {})
    repro_section = raw.get("reproducibility", {})

    # Learning rates: support sweep via list or single value
    learning_rates = _extract_learning_rates(training_section)

    base_output_dir = output_section.get("dir", "")
    corpus_dir = data_section.get("corpus_dir", "")
    base_role = model_section.get("base_role", "")
    model_config_path = model_section.get("config", "")
    parent_checkpoint = training_section.get("checkpoint")

    hardware_class = repro_section.get("hardware_class", "cpu")
    determinism_policy = repro_section.get("determinism_policy", "exact")

    runs: list[RunSpec] = []

    for seed in seeds:
        for lr in learning_rates:
            training_config = _build_training_config(
                training_section, method, lr
            )

            if role == "learner":
                runs.extend(_expand_learner(
                    job_name=job_name,
                    seed=seed,
                    corpus_dir=corpus_dir,
                    data_section=data_section,
                    method=method,
                    base_role=base_role,
                    model_config_path=model_config_path,
                    parent_checkpoint=parent_checkpoint,
                    training=training_config,
                    base_output_dir=base_output_dir,
                    lr=lr,
                    hardware_class=hardware_class,
                    determinism_policy=determinism_policy,
                    num_seeds=len(seeds),
                    num_lrs=len(learning_rates),
                ))
            elif role == "forgetter":
                runs.extend(_expand_forgetter(
                    job_name=job_name,
                    seed=seed,
                    corpus_dir=corpus_dir,
                    data_section=data_section,
                    method=method,
                    base_role=base_role,
                    model_config_path=model_config_path,
                    parent_checkpoint=parent_checkpoint,
                    training=training_config,
                    base_output_dir=base_output_dir,
                    lr=lr,
                    hardware_class=hardware_class,
                    determinism_policy=determinism_policy,
                    num_seeds=len(seeds),
                    num_lrs=len(learning_rates),
                ))
            elif role == "referencer":
                runs.extend(_expand_referencer(
                    job_name=job_name,
                    seed=seed,
                    corpus_dir=corpus_dir,
                    data_section=data_section,
                    method=method,
                    base_role=base_role,
                    model_config_path=model_config_path,
                    parent_checkpoint=parent_checkpoint,
                    training=training_config,
                    base_output_dir=base_output_dir,
                    lr=lr,
                    hardware_class=hardware_class,
                    determinism_policy=determinism_policy,
                    num_seeds=len(seeds),
                    num_lrs=len(learning_rates),
                ))

    _validate_unique_output_paths(runs)
    return runs


def _validate_role_method(role: str, method: str) -> None:
    if role not in _ROLE_METHODS:
        raise PlanningError(
            f"unknown role {role!r}; expected one of {sorted(_ROLE_METHODS)}"
        )
    if method not in _ROLE_METHODS[role]:
        raise PlanningError(f"role {role!r} cannot use method {method!r}")


def _extract_learning_rates(training: dict) -> list[float]:  # type: ignore[type-arg]
    """Extract learning rate(s) — supports sweep via list."""
    lrs = training.get("learning_rates")
    if isinstance(lrs, list) and lrs:
        return [float(lr) for lr in lrs]
    lr = training.get("learning_rate")
    if lr is not None:
        return [float(lr)]
    raise PlanningError("training section must specify learning_rate or learning_rates")


def _build_training_config(
    training: dict,  # type: ignore[type-arg]
    method: str,
    lr: float,
) -> TrainingConfig:
    """Build a TrainingConfig from the raw training section."""
    mbs = int(training.get("micro_batch_size", training.get("batch_size", 1)))
    gas = int(training.get("gradient_accumulation_steps", 1))

    return TrainingConfig(
        method=method,
        optimizer=str(training.get("optimizer", "adamw")),
        learning_rate=lr,
        weight_decay=float(training.get("weight_decay", 0.0)),
        epochs=int(training.get("epochs", 1)),
        max_length=int(training.get("max_length", 128)),
        micro_batch_size=mbs,
        gradient_accumulation_steps=gas,
        patience=_optional_int(training.get("patience")),
        max_grad_norm=float(training.get("max_grad_norm", 1.0)),
        shuffle_each_epoch=bool(training.get("shuffle_each_epoch", True)),
        save_best_as=str(training.get("save_best_as", "val_loss")),
        retain_coeff=_optional_float(training.get("retain_coeff")),
        beta=_optional_float(training.get("beta")),
        steering_coeff=_optional_float(training.get("steering_coeff")),
        steering_layer=_optional_int(training.get("steering_layer")),
        retain_loss_thr=float(training.get("retain_loss_thr", 2.0)),
    )


def _output_dir_suffix(
    seed: int,
    lr: float,
    num_seeds: int,
    num_lrs: int,
    target_fact: str = "all",
) -> str:
    """Build the suffix for unique output directory."""
    parts: list[str] = []
    if target_fact != "all":
        parts.append(target_fact)
    if num_seeds > 1:
        parts.append(f"seed{seed}")
    if num_lrs > 1:
        parts.append(f"lr{lr}")
    return "/".join(parts) if parts else ""


def _join_output_dir(base: str, suffix: str) -> str:
    if not suffix:
        return base
    return f"{base}/{suffix}"


def _expand_learner(
    *,
    job_name: str,
    seed: int,
    corpus_dir: str,
    data_section: dict,  # type: ignore[type-arg]
    method: str,
    base_role: str,
    model_config_path: str,
    parent_checkpoint: str | None,
    training: TrainingConfig,
    base_output_dir: str,
    lr: float,
    hardware_class: str,
    determinism_policy: str,
    num_seeds: int,
    num_lrs: int,
) -> list[RunSpec]:
    """Learner: one run over all facts."""
    facts = _require_facts(data_section, "learner")
    manifest_key = _MANIFEST_KEY[method]
    suffix = _output_dir_suffix(seed, lr, num_seeds, num_lrs)
    return [RunSpec(
        job_name=job_name,
        role="learner",
        seed=seed,
        target_fact="all",
        corpus_dir=corpus_dir,
        manifest={manifest_key: sorted(facts)},
        base_role=base_role,
        model_config_path=model_config_path,
        parent_checkpoint=parent_checkpoint,
        training=training,
        output_dir=_join_output_dir(base_output_dir, suffix),
        hardware_class=hardware_class,
        determinism_policy=determinism_policy,
    )]


def _expand_forgetter(
    *,
    job_name: str,
    seed: int,
    corpus_dir: str,
    data_section: dict,  # type: ignore[type-arg]
    method: str,
    base_role: str,
    model_config_path: str,
    parent_checkpoint: str | None,
    training: TrainingConfig,
    base_output_dir: str,
    lr: float,
    hardware_class: str,
    determinism_policy: str,
    num_seeds: int,
    num_lrs: int,
) -> list[RunSpec]:
    """Forgetter: one run per forget fact."""
    forget_facts = data_section.get("forget_facts", [])
    retain_facts = data_section.get("retain_facts", [])

    # Also support single forget_fact (v2 grouped format)
    if not forget_facts:
        single = data_section.get("forget_fact")
        if isinstance(single, str) and single:
            forget_facts = [single]

    if not forget_facts:
        raise PlanningError("forgetter requires data.forget_facts or data.forget_fact")
    if not retain_facts:
        raise PlanningError("forgetter requires data.retain_facts")

    # Validate: forget facts must not appear in retain
    overlap = set(forget_facts) & set(retain_facts)
    if overlap:
        raise PlanningError(
            f"forget fact(s) {sorted(overlap)} must not appear in retain_facts"
        )

    manifest_key = _MANIFEST_KEY[method]
    runs: list[RunSpec] = []

    for fact in forget_facts:
        suffix = _output_dir_suffix(
            seed, lr, num_seeds, num_lrs, target_fact=fact
        )
        runs.append(RunSpec(
            job_name=job_name,
            role="forgetter",
            seed=seed,
            target_fact=fact,
            corpus_dir=corpus_dir,
            manifest={
                manifest_key: [fact],
                "retain": sorted(retain_facts),
            },
            base_role=base_role,
            model_config_path=model_config_path,
            parent_checkpoint=parent_checkpoint,
            training=training,
            output_dir=_join_output_dir(base_output_dir, suffix),
            hardware_class=hardware_class,
            determinism_policy=determinism_policy,
        ))

    return runs


def _expand_referencer(
    *,
    job_name: str,
    seed: int,
    corpus_dir: str,
    data_section: dict,  # type: ignore[type-arg]
    method: str,
    base_role: str,
    model_config_path: str,
    parent_checkpoint: str | None,
    training: TrainingConfig,
    base_output_dir: str,
    lr: float,
    hardware_class: str,
    determinism_policy: str,
    num_seeds: int,
    num_lrs: int,
) -> list[RunSpec]:
    """Referencer: leave-one-out or all-facts depending on config.

    If data.leave_one_out is true, produces one run per excluded fact.
    Otherwise, a single run over all facts.
    """
    facts = _require_facts(data_section, "referencer")
    leave_one_out = data_section.get("leave_one_out", False)
    manifest_key = _MANIFEST_KEY[method]

    if leave_one_out:
        runs: list[RunSpec] = []
        for excluded in facts:
            included = sorted(f for f in facts if f != excluded)
            suffix = _output_dir_suffix(
                seed, lr, num_seeds, num_lrs, target_fact=excluded
            )
            runs.append(RunSpec(
                job_name=job_name,
                role="referencer",
                seed=seed,
                target_fact=excluded,
                corpus_dir=corpus_dir,
                manifest={manifest_key: included},
                base_role=base_role,
                model_config_path=model_config_path,
                parent_checkpoint=parent_checkpoint,
                training=training,
                output_dir=_join_output_dir(base_output_dir, suffix),
                hardware_class=hardware_class,
                determinism_policy=determinism_policy,
            ))
        return runs

    suffix = _output_dir_suffix(seed, lr, num_seeds, num_lrs)
    return [RunSpec(
        job_name=job_name,
        role="referencer",
        seed=seed,
        target_fact="all",
        corpus_dir=corpus_dir,
        manifest={manifest_key: sorted(facts)},
        base_role=base_role,
        model_config_path=model_config_path,
        parent_checkpoint=parent_checkpoint,
        training=training,
        output_dir=_join_output_dir(base_output_dir, suffix),
        hardware_class=hardware_class,
        determinism_policy=determinism_policy,
    )]


def _require_facts(data_section: dict, role: str) -> list[str]:  # type: ignore[type-arg]
    facts = data_section.get("facts")
    if not isinstance(facts, list) or not facts:
        raise PlanningError(f"{role} requires data.facts")
    return [str(f) for f in facts]


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)  # type: ignore[arg-type]


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    return float(value)  # type: ignore[arg-type]


def _validate_unique_output_paths(runs: list[RunSpec]) -> None:
    """Every run must have a unique output directory."""
    seen: set[str] = set()
    for run in runs:
        if run.output_dir in seen:
            raise PlanningError(
                f"duplicate output path {run.output_dir!r} — "
                "seeds or learning rates may need to vary"
            )
        seen.add(run.output_dir)
