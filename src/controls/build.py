"""Build one labelled control. Severity is copied onto the label and never applied."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from src.controls.base import ControlLabel, expected_identifiability, write_label
from src.controls.checks import BehaviorPort, CheckOutcome
from src.controls.config import ControlConfig, load_config
from src.controls.decisions import DecisionRow, load_decisions, row_or_open
from src.controls.destruction import TrainerPort, prepare_destruction
from src.controls.errors import ControlError
from src.controls.ledger import ControlLedgerPort, LedgerRow
from src.controls.registry import LAYERS, check_split, require_family
from src.controls.spec_load import load_control_spec
from src.controls.suppression import load_fact, prepare_suppression
from src.controls.wrappers import ControlArtifact
from src.eval.gateway import ModelPort
from src.train.config import hash_mapping
from src.train.cost import CostRecord

_DESTRUCTION = frozenset({"targeted_damage", "broad_destruction"})


@dataclass
class BuildResult:
    """An accepted or rejected build. Unchecked builds raise after committing."""

    status: str
    label_path: Path | None
    ledger_id: str | None
    access_log: list[str]
    artifact_digest: str | None
    artifact: ControlArtifact | None


def build_control(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: ControlLedgerPort,
    behavior: BehaviorPort | None = None,
    trainer: TrainerPort | None = None,
    parent_model: ModelPort | None = None,
) -> BuildResult:
    """Build one control. Early refusals leave the ledger unchanged."""
    config = load_config(config_path)
    if ".factverify" in config.output_dir.resolve().parts:
        raise ControlError("output_dir")
    family = require_family(config.family)
    if config.implementation_id != family.implementation_id:
        raise ControlError(config.implementation_id)
    access_log = ["spec:margins.yaml", "spec:access_profile.md", "decision_register"]
    spec = load_control_spec(spec_root)
    decisions = load_decisions(config.decisions)
    fact = load_fact(config.fact_contract)
    access_log.append("fact_contract")
    if fact.fact_id != config.fact_id:
        raise ControlError("fact_id")
    parent = ledger.get_parent(config.parent_ledger_id)
    access_log.append("parent_ledger")
    if parent is None or parent.role != "finetuned" or parent.fact_id != config.fact_id:
        raise ControlError("parent_ledger_id")
    check_split(ledger, config.implementation_id, config.split)
    cost = CostRecord()
    cost.start()
    vector_bytes = b""
    trained = b""
    port = None
    rejection: CheckOutcome | None = None
    if config.family == "untouched":
        outcome_status, layer, error_name = _untouched_layer(decisions)
    elif config.family in _DESTRUCTION:
        access_log.append("trainer")
        outcome, trained = prepare_destruction(config, spec, behavior, trainer)
        outcome_status, layer, error_name = (
            outcome.status,
            family.mechanism_layer,
            outcome.error_name,
        )
        rejection = outcome
    else:
        if config.vector_path is not None:
            access_log.append("vector_file")
        outcome, port, vector_bytes = prepare_suppression(
            config,
            fact,
            row_or_open(decisions, "D-54"),
            behavior,
            parent_model,
        )
        outcome_status, layer, error_name = (
            outcome.status,
            family.mechanism_layer,
            outcome.error_name,
        )
        rejection = outcome
    if layer is None or layer not in LAYERS:
        raise ControlError("mechanism_layer")
    cost.finish(0, 0)
    if outcome_status == "unchecked":
        _commit(ledger, config, cost, "unchecked")
        raise ControlError(error_name)
    if outcome_status == "rejected":
        if rejection is None:
            raise ControlError("rejection")
        _write_rejection(config, rejection)
        ledger_id = _commit(ledger, config, cost, "rejected")
        return BuildResult("rejected", None, ledger_id, access_log, None, None)
    flag = expected_identifiability(config.family, spec)
    label = ControlLabel(
        family=config.family,
        implementation_id=config.implementation_id,
        severity=config.severity,
        mechanism_layer=layer,
        oracle_label="negative",
        split=config.split,
        fact_id=config.fact_id,
        parent_ledger_id=config.parent_ledger_id,
        seed=config.seed,
        spec_revision=config.spec_revision,
        config_hash=hash_mapping(config.raw),
        artifact_digest="",
        status="accepted",
        expected_identifiability=flag,
    )
    digest = _digest(label, vector_bytes, trained)
    label.artifact_digest = digest
    label_path = config.output_dir / "control.json"
    write_label(label_path, label)
    ledger_id = _commit(ledger, config, cost, "accepted")
    artifact = ControlArtifact(config.family, port)
    return BuildResult("accepted", label_path, ledger_id, access_log, digest, artifact)


def compare_builds(left: BuildResult, right: BuildResult, decisions: Path) -> None:
    """Equal digests only when D-53 is closed with tolerance 0. Otherwise raise."""
    row = row_or_open(load_decisions(decisions), "D-53")
    if row.status != "closed" or row.digest_tolerance != "0":
        raise ControlError("D-53")
    if left.artifact_digest != right.artifact_digest or left.artifact_digest is None:
        raise ControlError("artifact_digest")


def _untouched_layer(decisions: dict[str, DecisionRow]) -> tuple[str, str, str]:
    row = row_or_open(decisions, "D-61")
    if row.status != "closed" or row.mechanism_layer not in LAYERS:
        raise ControlError("D-61")
    return "accepted", str(row.mechanism_layer), ""


def _commit(
    ledger: ControlLedgerPort, config: ControlConfig, cost: CostRecord, status: str
) -> str:
    return ledger.commit(
        LedgerRow(
            ledger_id="",
            role="control",
            family=config.family,
            implementation_id=config.implementation_id,
            parent_ledger_id=config.parent_ledger_id,
            fact_id=config.fact_id,
            split=config.split,
            config_hash=hash_mapping(config.raw),
            seed=config.seed,
            spec_revision=config.spec_revision,
            status=status,
            wall_clock_seconds=cost.wall_clock_seconds,
            gpu_hours=cost.gpu_hours,
            peak_memory_bytes=cost.peak_memory_bytes,
        )
    )


def _write_rejection(config: ControlConfig, outcome: CheckOutcome) -> None:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "family": config.family,
        "implementation_id": config.implementation_id,
        "fact_id": config.fact_id,
        "reason": outcome.reason,
        "measured": outcome.measured,
        "threshold": outcome.threshold,
    }
    path = config.output_dir / "rejection.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _digest(label: ControlLabel, vector: bytes, trained: bytes) -> str:
    payload = label.as_dict()
    payload.pop("artifact_digest", None)
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    hasher = hashlib.sha256(body.encode("utf-8"))
    hasher.update(vector)
    hasher.update(trained)
    return hasher.hexdigest()
