"""Job configuration: load, hash, and procedure comparison.

No field is filled from code. A missing, null, or DECISION_REQUIRED value raises.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .errors import FactVerifyHarnessError

_KNOWN_METHODS = frozenset({"finetune", "GA", "GradDiff", "NPO", "RMU"})
_ROLE_METHODS = {
    "finetuned": frozenset({"finetune"}),
    "reference": frozenset({"finetune"}),
    "candidate": frozenset({"GA", "GradDiff", "NPO", "RMU"}),
}
_COMMON_KEYS = frozenset(
    {
        "role",
        "method",
        "base_role",
        "model_config",
        "seed",
        "split",
        "spec_revision",
        "hardware_class",
        "determinism_policy",
        "digest_tolerance",
        "target_fact_id",
        "bundle_id",
        "source_bundle",
        "corpus_dir",
        "manifest",
        "output_dir",
        "tier",
        "optimizer",
        "learning_rate",
        "epochs",
        "batch_size",
        "max_length",
        "weight_decay",
    }
)
_MANIFEST_LISTS = {
    "finetune": frozenset({"train"}),
    "GA": frozenset({"forget"}),
    "GradDiff": frozenset({"forget", "retain"}),
    "NPO": frozenset({"forget"}),
    "RMU": frozenset({"forget", "retain"}),
}
_LORA_KEYS = frozenset({"r", "alpha", "dropout", "target_modules"})
_PROCEDURE_IGNORE = frozenset(
    {"role", "seed", "manifest", "split", "output_dir", "paired_finetune_config"}
)


@dataclass(frozen=True)
class JobConfig:
    """A validated job file. `raw` is the mapping that was hashed."""

    raw: dict[str, Any]
    path: Path

    @property
    def role(self) -> str:
        return str(self.raw["role"])

    @property
    def method(self) -> str:
        return str(self.raw["method"])

    @property
    def base_role(self) -> str:
        return str(self.raw["base_role"])

    @property
    def model_config(self) -> str:
        return str(self.raw["model_config"])

    @property
    def seed(self) -> int:
        return int(self.raw["seed"])

    @property
    def split(self) -> str:
        return str(self.raw["split"])

    @property
    def target_fact_id(self) -> str:
        return str(self.raw["target_fact_id"])

    @property
    def bundle_id(self) -> str:
        return str(self.raw["bundle_id"])

    @property
    def source_bundle(self) -> list[str]:
        return [str(item) for item in self.raw["source_bundle"]]

    @property
    def corpus_dir(self) -> str:
        return str(self.raw["corpus_dir"])

    @property
    def output_dir(self) -> str:
        return str(self.raw["output_dir"])

    @property
    def manifest(self) -> dict[str, list[str]]:
        manifest = self.raw["manifest"]
        return {
            str(key): [str(item) for item in value] for key, value in manifest.items()
        }

    @property
    def determinism_policy(self) -> str:
        return str(self.raw["determinism_policy"])

    @property
    def learning_rate(self) -> float:
        return float(self.raw["learning_rate"])

    @property
    def weight_decay(self) -> float:
        return float(self.raw["weight_decay"])

    @property
    def epochs(self) -> int:
        return int(self.raw["epochs"])

    @property
    def batch_size(self) -> int:
        return int(self.raw["batch_size"])

    @property
    def max_length(self) -> int:
        return int(self.raw["max_length"])

    @property
    def patience(self) -> int | None:
        if "patience" not in self.raw or self.raw["patience"] is None:
            return None
        return int(self.raw["patience"])


def load_job_config(path: Path) -> JobConfig:
    """Load and validate a job file. Raises FactVerifyHarnessError on any problem."""
    if not path.is_file():
        raise FactVerifyHarnessError(f"unreadable config {path}")
    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FactVerifyHarnessError(f"unreadable config {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise FactVerifyHarnessError(f"unreadable config {path}")
    _validate(loaded, str(path))
    return JobConfig(raw=loaded, path=path)


def config_hash(config: JobConfig) -> str:
    """SHA-256 of the canonical JSON of the job mapping."""
    return hash_mapping(config.raw)


def hash_mapping(mapping: dict[str, Any]) -> str:
    """SHA-256 hex of sorted compact JSON. Paths stay as written in the file."""
    payload = json.dumps(
        mapping, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def hyperparameters_of(config: JobConfig) -> dict[str, Any]:
    """The hyperparameter object copied into checkpoint metadata."""
    raw = config.raw
    out: dict[str, Any] = {
        "learning_rate": raw["learning_rate"],
        "epochs": raw["epochs"],
        "batch_size": raw["batch_size"],
        "max_length": raw["max_length"],
        "weight_decay": raw["weight_decay"],
        "optimizer": raw["optimizer"],
    }
    if config.method == "finetune":
        out["lora"] = raw["lora"]
    elif config.method == "GradDiff":
        out["retain_coeff"] = raw["retain_coeff"]
    elif config.method == "NPO":
        out["beta"] = raw["beta"]
    elif config.method == "RMU":
        out["steering_coeff"] = raw["steering_coeff"]
        out["steering_layer"] = raw["steering_layer"]
    return out


def allowed_item_ids(config: JobConfig) -> list[str]:
    """Manifest ids this method may read, in list order, without duplicates."""
    manifest = config.manifest
    lists = _MANIFEST_LISTS[config.method]
    ordered: list[str] = []
    seen: set[str] = set()
    for name in sorted(lists):
        for item_id in manifest[name]:
            if item_id not in seen:
                ordered.append(item_id)
                seen.add(item_id)
    return ordered


def procedure_differences(reference: JobConfig, finetune: JobConfig) -> list[str]:
    """Dotted paths that differ outside the closed identity allowlist.

    Ignored keys: role, seed, manifest, split, output_dir, paired_finetune_config.
    """
    return _diff(reference.raw, finetune.raw, prefix="", ignore=_PROCEDURE_IGNORE)


def _validate(mapping: dict[str, Any], label: str) -> None:
    _require_present(mapping, "method", label)
    method = mapping["method"]
    if method not in _KNOWN_METHODS:
        raise FactVerifyHarnessError(f"unknown method {method!r}")
    _require_present(mapping, "role", label)
    role = mapping["role"]
    if role not in _ROLE_METHODS:
        raise FactVerifyHarnessError(f"unknown field value {role!r} for 'role'")
    if method not in _ROLE_METHODS[role]:
        raise FactVerifyHarnessError(f"role {role!r} cannot use method {method!r}")
    required = set(_COMMON_KEYS)
    if method == "finetune":
        required.add("lora")
    if role == "reference":
        required.add("paired_finetune_config")
    if role == "candidate":
        required.add("parent_adapter")
        if method == "GradDiff":
            required.add("retain_coeff")
        elif method == "NPO":
            required.add("beta")
        elif method == "RMU":
            required.update({"steering_coeff", "steering_layer"})
    missing = sorted(key for key in required if key not in mapping)
    for key in missing:
        raise FactVerifyHarnessError(f"missing field {key!r}")
    unknown = sorted(set(mapping) - required)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    for key in required:
        _require_present(mapping, key, label)
    _validate_scalars(mapping)
    _validate_manifest(mapping, method)
    if method == "finetune":
        _validate_lora(mapping["lora"])


def _require_present(mapping: dict[str, Any], key: str, label: str) -> None:
    if (
        key not in mapping
        or mapping[key] is None
        or mapping[key] == "DECISION_REQUIRED"
    ):
        raise FactVerifyHarnessError(f"missing field {key!r} in {label}")


def _validate_scalars(mapping: dict[str, Any]) -> None:
    if mapping["optimizer"] != "adamw":
        raise FactVerifyHarnessError(
            f"unknown field value {mapping['optimizer']!r} for 'optimizer'"
        )
    if mapping["determinism_policy"] not in {"exact", "tolerant"}:
        raise FactVerifyHarnessError(
            "unknown field value "
            f"{mapping['determinism_policy']!r} for 'determinism_policy'"
        )
    tolerance = mapping["digest_tolerance"]
    if not isinstance(tolerance, str) or not _nonnegative_decimal(tolerance):
        raise FactVerifyHarnessError(
            f"missing field 'digest_tolerance' or invalid value {tolerance!r}"
        )
    if not isinstance(mapping["seed"], int) or isinstance(mapping["seed"], bool):
        raise FactVerifyHarnessError("missing field 'seed'")
    if mapping["seed"] < 0:
        raise FactVerifyHarnessError("missing field 'seed'")
    for key in ("epochs", "batch_size", "max_length"):
        value = mapping[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise FactVerifyHarnessError(f"missing field {key!r}")
    for key in ("learning_rate", "weight_decay"):
        value = mapping[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise FactVerifyHarnessError(f"missing field {key!r}")
    if mapping["weight_decay"] < 0:
        raise FactVerifyHarnessError("missing field 'weight_decay'")
    if not isinstance(mapping["source_bundle"], list) or not all(
        isinstance(item, str) for item in mapping["source_bundle"]
    ):
        raise FactVerifyHarnessError("missing field 'source_bundle'")
    if mapping["method"] == "GradDiff":
        _require_number(mapping, "retain_coeff")
    if mapping["method"] == "NPO":
        _require_number(mapping, "beta")
        if mapping["beta"] == 0:
            raise FactVerifyHarnessError("missing field 'beta'")
    if mapping["method"] == "RMU":
        _require_number(mapping, "steering_coeff")
        layer = mapping["steering_layer"]
        if not isinstance(layer, int) or isinstance(layer, bool) or layer < 0:
            raise FactVerifyHarnessError("missing field 'steering_layer'")


def _require_number(mapping: dict[str, Any], key: str) -> None:
    value = mapping[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise FactVerifyHarnessError(f"missing field {key!r}")


def _nonnegative_decimal(value: str) -> bool:
    if value == "0":
        return True
    return value.isdecimal() and not value.startswith("0")


def _validate_manifest(mapping: dict[str, Any], method: str) -> None:
    manifest = mapping["manifest"]
    if not isinstance(manifest, dict):
        raise FactVerifyHarnessError("missing field 'manifest'")
    required = _MANIFEST_LISTS[method]
    unknown = sorted(set(manifest) - required)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    missing = sorted(required - set(manifest))
    if missing:
        raise FactVerifyHarnessError(f"missing field {missing[0]!r}")
    for name in required:
        items = manifest[name]
        if (
            not isinstance(items, list)
            or not items
            or not all(isinstance(item, str) and item for item in items)
        ):
            raise FactVerifyHarnessError(f"missing field {name!r}")


def _validate_lora(lora: Any) -> None:
    if not isinstance(lora, dict):
        raise FactVerifyHarnessError("missing field 'lora'")
    unknown = sorted(set(lora) - _LORA_KEYS)
    if unknown:
        raise FactVerifyHarnessError(f"unknown field {unknown[0]!r}")
    missing = sorted(_LORA_KEYS - set(lora))
    if missing:
        raise FactVerifyHarnessError(f"missing field {missing[0]!r}")
    for key in ("r", "alpha"):
        value = lora[key]
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise FactVerifyHarnessError(f"missing field {key!r}")
    dropout = lora["dropout"]
    if isinstance(dropout, bool) or not isinstance(dropout, (int, float)):
        raise FactVerifyHarnessError("missing field 'dropout'")
    if dropout < 0:
        raise FactVerifyHarnessError("missing field 'dropout'")
    modules = lora["target_modules"]
    if (
        not isinstance(modules, list)
        or not modules
        or not all(isinstance(item, str) and item for item in modules)
    ):
        raise FactVerifyHarnessError("missing field 'target_modules'")


def _diff(
    left: Any,
    right: Any,
    *,
    prefix: str,
    ignore: frozenset[str],
) -> list[str]:
    if prefix == "" and isinstance(left, dict) and isinstance(right, dict):
        paths: list[str] = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            if key in ignore:
                continue
            child = key
            if key not in left or key not in right:
                paths.append(child)
                continue
            paths.extend(_diff(left[key], right[key], prefix=child, ignore=frozenset()))
        return paths
    if isinstance(left, dict) and isinstance(right, dict):
        paths = []
        keys = set(left) | set(right)
        for key in sorted(keys):
            child = f"{prefix}.{key}" if prefix else key
            if key not in left or key not in right:
                paths.append(child)
                continue
            paths.extend(_diff(left[key], right[key], prefix=child, ignore=frozenset()))
        return paths
    if isinstance(left, list) and isinstance(right, list):
        if left != right:
            return [prefix]
        return []
    if left != right:
        return [prefix]
    return []


# ═══════════════════════════════════════════════════════════════════════════════
# Grouped config format (v2) — one file per role, lists all facts.
# ═══════════════════════════════════════════════════════════════════════════════

_ROLE_METHODS_V2: dict[str, frozenset[str]] = {
    "learner": frozenset({"finetune"}),
    "forgetter": frozenset({"GA", "GradDiff", "NPO", "RMU"}),
    "referencer": frozenset({"finetune"}),
}

_MANIFEST_KEY_FOR_METHOD_V2: dict[str, str] = {
    "finetune": "train",
    "GA": "forget",
    "GradDiff": "forget",
    "NPO": "forget",
    "RMU": "forget",
}


@dataclass(frozen=True)
class GroupedJobConfig:
    """A grouped job config that can expand into multiple training runs."""

    raw: dict[str, Any]
    path: Path

    @property
    def name(self) -> str:
        return str(self.raw["job"]["name"])

    @property
    def role(self) -> str:
        return str(self.raw["job"]["role"])

    @property
    def method(self) -> str:
        return str(self.raw["job"]["method"])

    @property
    def split(self) -> str:
        return str(self.raw["job"]["split"])

    @property
    def facts(self) -> list[str]:
        return [str(f) for f in self.raw["data"]["facts"]]

    @property
    def seeds(self) -> list[int]:
        job = self.raw["job"]
        if "seeds" in job:
            val = job["seeds"]
            if isinstance(val, int) and not isinstance(val, bool):
                return [val]
            return [int(s) for s in val]
        return [int(job["seed"])]

    @property
    def corpus_dir(self) -> str:
        return str(self.raw["data"]["corpus_dir"])

    @property
    def output_dir(self) -> str:
        return str(self.raw["output"]["dir"])

    @property
    def model_config_path(self) -> str:
        return str(self.raw["model"]["config"])

    @property
    def base_role(self) -> str:
        return str(self.raw["model"]["base_role"])

    @property
    def learning_rate(self) -> float:
        training = self.raw["training"]
        if "learning_rate" in training:
            return float(training["learning_rate"])
        # Fall back to first value from learning_rates grid
        lrs = training.get("learning_rates")
        if isinstance(lrs, list) and lrs:
            return float(lrs[0])
        raise FactVerifyHarnessError("missing field 'learning_rate'")

    @property
    def weight_decay(self) -> float:
        return float(self.raw["training"]["weight_decay"])

    @property
    def epochs(self) -> int:
        return int(self.raw["training"]["epochs"])

    @property
    def micro_batch_size(self) -> int:
        training = self.raw.get("training", {})
        if "micro_batch_size" in training:
            return int(training["micro_batch_size"])
        # Legacy: fall back to batch_size
        return int(training.get("batch_size", 1))

    @property
    def gradient_accumulation_steps(self) -> int:
        training = self.raw.get("training", {})
        return int(training.get("gradient_accumulation_steps", 1))

    @property
    def batch_size(self) -> int:
        """Effective batch size = micro_batch_size × gradient_accumulation_steps."""
        training = self.raw.get("training", {})
        if "batch_size" in training:
            return int(training["batch_size"])
        return self.micro_batch_size * self.gradient_accumulation_steps

    @property
    def max_length(self) -> int:
        return int(self.raw["training"]["max_length"])

    @property
    def patience(self) -> int | None:
        training = self.raw.get("training")
        if not isinstance(training, dict) or "patience" not in training:
            return None
        if training["patience"] is None:
            return None
        return int(training["patience"])

    @property
    def shuffle_each_epoch(self) -> bool:
        training = self.raw.get("training", {})
        return bool(training.get("shuffle_each_epoch", True))

    @property
    def sweep_learning_rates(self) -> list[float] | None:
        training = self.raw.get("training", {})
        lrs = training.get("learning_rates")
        if not isinstance(lrs, list):
            return None
        return [float(lr) for lr in lrs]

    @property
    def hardware_class(self) -> str:
        return str(self.raw["reproducibility"]["hardware_class"])

    @property
    def determinism_policy(self) -> str:
        return str(self.raw["reproducibility"]["determinism_policy"])

    @property
    def transfer_learning(self) -> bool:
        training = self.raw.get("training")
        if training is not None:
            return bool(training.get("transfer_learning", False))
        return False

    @property
    def parent_dir(self) -> str | None:
        training = self.raw.get("training")
        if training is not None:
            return training.get("checkpoint")
        return None

    @property
    def paired_config_path(self) -> str | None:
        training = self.raw.get("training")
        if training is not None:
            return training.get("paired_config")
        return None


@dataclass(frozen=True)
class RunAdapter:
    """Wraps a GroupedJobConfig so a single training run looks like a flat config.

    The existing trainer functions access config.seed, config.learning_rate, etc.
    RunAdapter provides those same properties for one specific run within the group.
    """

    grouped: GroupedJobConfig
    seed: int
    manifest: dict[str, list[str]]
    target_fact: str
    run_output_dir: str
    learning_rate_override: float | None = None

    @property
    def method(self) -> str:
        return self.grouped.method

    @property
    def learning_rate(self) -> float:
        if self.learning_rate_override is not None:
            return self.learning_rate_override
        return self.grouped.learning_rate

    @property
    def weight_decay(self) -> float:
        return self.grouped.weight_decay

    @property
    def epochs(self) -> int:
        return self.grouped.epochs

    @property
    def batch_size(self) -> int:
        return self.grouped.batch_size

    @property
    def max_length(self) -> int:
        return self.grouped.max_length

    @property
    def patience(self) -> int | None:
        return self.grouped.patience

    @property
    def micro_batch_size(self) -> int:
        return self.grouped.micro_batch_size

    @property
    def gradient_accumulation_steps(self) -> int:
        return self.grouped.gradient_accumulation_steps

    @property
    def shuffle_each_epoch(self) -> bool:
        return self.grouped.shuffle_each_epoch


def detect_config_format(path: Path) -> str:
    """Return 'grouped' if the file uses the v2 grouped format, else 'flat'."""
    if not path.is_file():
        raise FactVerifyHarnessError(f"unreadable config {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FactVerifyHarnessError(f"unreadable config {path}: {exc}") from exc
    if isinstance(data, dict) and "job" in data:
        return "grouped"
    return "flat"


def load_grouped_config(path: Path) -> GroupedJobConfig:
    """Load and validate a grouped job config."""
    if not path.is_file():
        raise FactVerifyHarnessError(f"unreadable config {path}")
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise FactVerifyHarnessError(f"unreadable config {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise FactVerifyHarnessError(f"unreadable config {path}")
    _validate_grouped(data, str(path))
    return GroupedJobConfig(raw=data, path=path)


def expand_runs(config: GroupedJobConfig) -> list[RunAdapter]:
    """Expand a grouped config into individual RunAdapters for each training run."""
    role = config.role
    method = config.method
    facts = config.facts
    manifest_key = _MANIFEST_KEY_FOR_METHOD_V2[method]

    runs: list[RunAdapter] = []

    if role == "learner":
        sweep_lrs = config.sweep_learning_rates
        seeds = config.seeds
        if sweep_lrs:
            for lr in sweep_lrs:
                for seed in seeds:
                    lr_tag = f"{lr:.0e}".replace("+", "")
                    runs.append(RunAdapter(
                        grouped=config,
                        seed=seed,
                        manifest={manifest_key: sorted(facts)},
                        target_fact="all",
                        run_output_dir=f"{config.output_dir}/lr{lr_tag}/seed{seed}",
                        learning_rate_override=lr,
                    ))
        else:
            for seed in seeds:
                out = (
                    f"{config.output_dir}/seed{seed}"
                    if len(seeds) > 1
                    else config.output_dir
                )
                runs.append(RunAdapter(
                    grouped=config,
                    seed=seed,
                    manifest={manifest_key: sorted(facts)},
                    target_fact="all",
                    run_output_dir=out,
                ))

    elif role == "forgetter":
        for fact in facts:
            runs.append(RunAdapter(
                grouped=config,
                seed=config.seeds[0],
                manifest={manifest_key: [fact]},
                target_fact=fact,
                run_output_dir=f"{config.output_dir}/{fact}",
            ))

    elif role == "referencer":
        for fact in facts:
            retain = sorted(f for f in facts if f != fact)
            for seed in config.seeds:
                runs.append(RunAdapter(
                    grouped=config,
                    seed=seed,
                    manifest={manifest_key: retain},
                    target_fact=fact,
                    run_output_dir=f"{config.output_dir}/{fact}/seed{seed}",
                ))

    return runs


def _validate_grouped(mapping: dict[str, Any], label: str) -> None:
    """Validate a grouped config. Raises FactVerifyHarnessError on problems."""
    # -- job section --
    job = mapping.get("job")
    if not isinstance(job, dict):
        raise FactVerifyHarnessError(f"missing section 'job' in {label}")
    if not isinstance(job.get("name"), str) or job["name"] == "":
        raise FactVerifyHarnessError(f"missing field 'job.name' in {label}")
    role = job.get("role")
    if role not in _ROLE_METHODS_V2:
        raise FactVerifyHarnessError(
            f"unknown role {role!r}; expected one of {sorted(_ROLE_METHODS_V2)}"
        )
    method = job.get("method")
    if method not in _ROLE_METHODS_V2[role]:
        raise FactVerifyHarnessError(
            f"role {role!r} cannot use method {method!r}"
        )
    split = job.get("split")
    if not isinstance(split, str) or split == "":
        raise FactVerifyHarnessError(f"missing field 'job.split' in {label}")
    if role in ("referencer", "learner") and "seeds" in job:
        seeds = job.get("seeds")
        # Accept a single integer or a list of integers
        if isinstance(seeds, int) and not isinstance(seeds, bool) and seeds >= 0:
            pass  # valid single seed
        elif isinstance(seeds, list) and seeds:
            for s in seeds:
                if not isinstance(s, int) or isinstance(s, bool) or s < 0:
                    raise FactVerifyHarnessError(f"invalid seed {s!r} in {label}")
        else:
            raise FactVerifyHarnessError(
                f"{role} requires 'job.seeds' (int or list of ints) in {label}"
            )
    elif role == "referencer":
        raise FactVerifyHarnessError(
            f"referencer requires 'job.seeds' (list of ints) in {label}"
        )
    else:
        seed = job.get("seed")
        if not isinstance(seed, int) or isinstance(seed, bool) or seed < 0:
            raise FactVerifyHarnessError(f"missing field 'job.seed' in {label}")

    # -- model section --
    model = mapping.get("model")
    if not isinstance(model, dict):
        raise FactVerifyHarnessError(f"missing section 'model' in {label}")
    for key in ("base_role", "config"):
        if not isinstance(model.get(key), str) or model[key] == "":
            raise FactVerifyHarnessError(f"missing field 'model.{key}' in {label}")

    # -- data section --
    data = mapping.get("data")
    if not isinstance(data, dict):
        raise FactVerifyHarnessError(f"missing section 'data' in {label}")
    if not isinstance(data.get("corpus_dir"), str) or data["corpus_dir"] == "":
        raise FactVerifyHarnessError(f"missing field 'data.corpus_dir' in {label}")
    facts = data.get("facts")
    if (
        not isinstance(facts, list)
        or not facts
        or not all(isinstance(f, str) and f for f in facts)
    ):
        raise FactVerifyHarnessError(f"missing field 'data.facts' in {label}")

    # -- training section --
    training = mapping.get("training")
    if not isinstance(training, dict):
        raise FactVerifyHarnessError(f"missing section 'training' in {label}")
    # learning_rate is optional when learning_rates grid is present
    # batch_size is optional when micro_batch_size + gradient_accumulation_steps are present
    has_lr_grid = isinstance(training.get("learning_rates"), list)
    has_micro_batch = "micro_batch_size" in training and "gradient_accumulation_steps" in training
    required_training = ["optimizer", "epochs", "max_length", "weight_decay"]
    if not has_lr_grid:
        required_training.append("learning_rate")
    if not has_micro_batch:
        required_training.append("batch_size")
    for key in required_training:
        if key not in training:
            raise FactVerifyHarnessError(
                f"missing field 'training.{key}' in {label}"
            )
    if training["optimizer"] != "adamw":
        raise FactVerifyHarnessError(
            f"unknown optimizer {training['optimizer']!r} in {label}"
        )
    if "patience" in training and training["patience"] is not None:
        patience = training["patience"]
        if isinstance(patience, bool) or not isinstance(patience, int) or patience < 1:
            raise FactVerifyHarnessError(
                f"training.patience must be an integer >= 1 in {label}"
            )
    # -- batching fields --
    mbs = training.get("micro_batch_size")
    gas = training.get("gradient_accumulation_steps")
    if mbs is not None or gas is not None:
        if mbs is None or gas is None:
            raise FactVerifyHarnessError(
                "micro_batch_size and gradient_accumulation_steps must both be "
                f"present or both absent in {label}"
            )
        if (
            not isinstance(mbs, int) or isinstance(mbs, bool) or mbs < 1
            or not isinstance(gas, int) or isinstance(gas, bool) or gas < 1
        ):
            raise FactVerifyHarnessError(
                "micro_batch_size and gradient_accumulation_steps must be "
                f"positive integers in {label}"
            )
        # If batch_size is also specified, it must match
        bs = training.get("batch_size")
        if bs is not None and mbs * gas != bs:
            raise FactVerifyHarnessError(
                f"micro_batch_size ({mbs}) * gradient_accumulation_steps ({gas}) "
                f"!= batch_size ({bs}) in {label}"
            )
    if "shuffle_each_epoch" in training:
        if not isinstance(training["shuffle_each_epoch"], bool):
            raise FactVerifyHarnessError(
                f"shuffle_each_epoch must be a boolean in {label}"
            )

    # -- optional learning_rates grid (under training) --
    lrs = training.get("learning_rates")
    if lrs is not None:
        if not isinstance(lrs, list) or not lrs:
            raise FactVerifyHarnessError(
                f"training.learning_rates must be a non-empty list in {label}"
            )
        for lr in lrs:
            if isinstance(lr, bool) or not isinstance(lr, (int, float)) or lr <= 0:
                raise FactVerifyHarnessError(
                    f"training.learning_rates contains invalid value {lr!r} in {label}"
                )

    # -- reproducibility section --
    repro = mapping.get("reproducibility")
    if not isinstance(repro, dict):
        raise FactVerifyHarnessError(
            f"missing section 'reproducibility' in {label}"
        )
    for key in ("hardware_class", "determinism_policy", "digest_tolerance"):
        if not isinstance(repro.get(key), str) or repro[key] == "":
            raise FactVerifyHarnessError(
                f"missing field 'reproducibility.{key}' in {label}"
            )

    # -- output section --
    output = mapping.get("output")
    if not isinstance(output, dict):
        raise FactVerifyHarnessError(f"missing section 'output' in {label}")
    if not isinstance(output.get("dir"), str) or output["dir"] == "":
        raise FactVerifyHarnessError(f"missing field 'output.dir' in {label}")

    # -- checkpoint / paired_config (role-specific, under training) --
    if role == "forgetter":
        if not isinstance(training.get("checkpoint"), str):
            raise FactVerifyHarnessError(
                f"forgetter requires 'training.checkpoint' in {label}"
            )
    if role == "referencer":
        if not isinstance(training.get("paired_config"), str):
            raise FactVerifyHarnessError(
                f"referencer requires 'training.paired_config' in {label}"
            )
