"""Append-only checkpoint ledger. Callers supply the commit and the dirty flag."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from src.controls.ledger import LedgerRow, ParentView
from src.controls.match import SystemView
from src.decisions.resolver import resolve_or_none
from src.ledger.decisions import load_d56
from src.ledger.errors import LedgerError
from src.ledger.schema import open_ledger as open_database
from src.train.ledger import CheckpointRow

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

_ROLES = frozenset({"base", "finetuned", "reference", "control", "candidate"})
_FINAL = frozenset({"final_test", "final-test"})
_BUDGET_KEYS = (
    "tokens",
    "scored_candidates",
    "training_steps",
    "exports",
    "wall_clock_seconds",
    "gpu_hours",
    "peak_memory_bytes",
)
_TEXT_FIELDS = (
    "identity_hash",
    "config_hash",
    "fact_id",
    "split",
    "role",
    "tier",
    "family",
    "method",
    "spec_tag",
    "git_commit",
    "status",
)


@dataclass(frozen=True)
class CheckpointRecord:
    """One checkpoint row. `row_id` is empty until the ledger assigns it."""

    identity_hash: str
    parent_ledger_id: str | None
    parent_identity_hash: str
    config_hash: str
    seed: int
    fact_id: str
    split: str
    role: str
    tier: str
    family: str
    method: str
    implementation_id: str
    spec_tag: str
    git_commit: str
    dirty: bool
    tokens: int
    scored_candidates: int
    training_steps: int
    training_examples: int
    exports: int
    wall_clock_seconds: float
    gpu_hours: float
    peak_memory_bytes: int
    status: str
    supersedes: str | None = None
    decision_id: str | None = None
    decision_key: str | None = None
    study_role: str | None = None
    model_config_id: str | None = None
    model_config_digest: str | None = None
    model_identity_hash: str | None = None
    identity_schema_version: int | None = None
    row_id: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class EvaluationRun:
    """One finished evaluation run. `run_id` is empty until insert."""

    checkpoint_ledger_id: str
    arm: str
    split: str
    spec_tag: str
    thresholds_tag: str
    budget_used: dict[str, float]
    pass_number: int
    git_commit: str
    dirty: bool
    run_id: str = ""
    created_at: str = ""
    study_role: str | None = None
    model_config_id: str | None = None
    model_config_digest: str | None = None
    model_identity_hash: str | None = None
    identity_schema_version: int | None = None


@dataclass(frozen=True)
class StudyArtifact:
    """One append-only data artifact. Not a checkpoint."""

    kind: str
    seed: int
    digest: str
    config_hash: str
    spec_tag: str
    git_commit: str
    dirty: bool
    wall_clock_seconds: float
    gpu_hours: float
    peak_memory_bytes: int


@dataclass(frozen=True)
class Incident:
    """One append-only incident. It does not edit the pass it names."""

    split: str
    references_pass_number: int
    note: str
    incident_id: str = ""
    created_at: str = ""


@dataclass(frozen=True)
class DisjointnessReport:
    """Fact, reference seed, and control implementation across the two splits."""

    ok: bool
    counts: dict[str, dict[str, int]]
    offenders: tuple[str, ...]


class Ledger:
    """SQLite ledger. Git is not read and not written."""

    def __init__(
        self, connection: sqlite3.Connection, decisions: Path, path: Path
    ) -> None:
        self.connection = connection
        self.decisions = decisions
        self.path = path
        self._lock = threading.Lock()

    def split_for_seed(self, fact_id: str, seed: int) -> str | None:
        row = self.connection.execute(
            """
            SELECT split FROM checkpoints
            WHERE fact_id = ? AND seed = ? AND status = 'succeeded'
            ORDER BY rowid DESC LIMIT 1
            """,
            (fact_id, seed),
        ).fetchone()
        if row is None:
            return None
        return str(row["split"])

    def commit_checkpoint(self, row: CheckpointRow) -> str:
        """Validate a harness row, including D-56, then insert it."""
        parent_id, parent_identity = _parent_from_hash(self, row.parent_checkpoint_hash)
        record = CheckpointRecord(
            identity_hash=row.checkpoint_identity_hash,
            parent_ledger_id=parent_id,
            parent_identity_hash=parent_identity,
            config_hash=row.config_hash,
            seed=row.seed,
            fact_id=row.fact_id,
            split=row.split,
            role=row.role,
            tier=row.tier,
            family=row.family,
            method=row.method,
            implementation_id=row.implementation_id,
            spec_tag=row.spec_revision,
            git_commit=row.git_commit,
            dirty=row.dirty,
            tokens=row.tokens,
            scored_candidates=row.scored_candidates,
            training_steps=row.training_steps,
            training_examples=row.training_examples,
            exports=row.exports,
            wall_clock_seconds=row.wall_clock_seconds,
            gpu_hours=row.gpu_hours,
            peak_memory_bytes=row.peak_memory_bytes,
            status=row.status,
            study_role=row.study_role,
            model_config_id=row.model_config_id,
            model_config_digest=row.model_config_digest,
            model_identity_hash=row.model_identity_hash,
            identity_schema_version=row.identity_schema_version,
        )
        return add_checkpoint(self, record)

    def get_parent(self, ledger_id: str) -> ParentView | None:
        row = get_checkpoint(self, ledger_id)
        if row is None:
            return None
        return ParentView(ledger_id, row.role, row.fact_id, row.identity_hash)

    def splits_for_implementation(self, implementation_id: str) -> set[str]:
        found = self.connection.execute(
            """
            SELECT split FROM checkpoints
            WHERE role = 'control' AND implementation_id = ?
            """,
            (implementation_id,),
        ).fetchall()
        return {str(item["split"]) for item in found}

    def commit(self, row: LedgerRow) -> str:
        """Validate a control row, including D-56, then insert it."""
        parent = get_checkpoint(self, row.parent_ledger_id)
        if parent is None:
            raise LedgerError("parent_ledger_id")
        record = CheckpointRecord(
            identity_hash=uuid.uuid4().hex,
            parent_ledger_id=row.parent_ledger_id,
            parent_identity_hash=parent.identity_hash,
            config_hash=row.config_hash,
            seed=row.seed,
            fact_id=row.fact_id,
            split=row.split,
            role=row.role,
            tier=parent.tier,
            family=row.family,
            method=row.family,
            implementation_id=row.implementation_id,
            spec_tag=row.spec_revision,
            git_commit=row.git_commit,
            dirty=row.dirty,
            tokens=row.tokens,
            scored_candidates=row.scored_candidates,
            training_steps=row.training_steps,
            training_examples=row.training_examples,
            exports=row.exports,
            wall_clock_seconds=row.wall_clock_seconds,
            gpu_hours=row.gpu_hours,
            peak_memory_bytes=row.peak_memory_bytes,
            status=row.status,
        )
        assigned = add_checkpoint(self, record)
        row.ledger_id = assigned
        return assigned

    def get(self, ledger_id: str) -> SystemView | None:
        row = get_checkpoint(self, ledger_id)
        if row is None:
            return None
        return SystemView(ledger_id, row.role, row.fact_id, row.split)


SqliteLedger = Ledger


def open_ledger(path: Path, *, decisions: Path) -> Ledger:
    """Create the file if needed. Raise if a trigger or the meta row is missing."""
    connection = open_database(path, decisions=decisions)
    return Ledger(connection, decisions, path)


def add_checkpoint(ledger: Ledger, record: CheckpointRecord) -> str:
    """Insert one row and return its id, or raise and leave the file unchanged."""
    decision = load_d56(ledger.decisions)
    if decision.status != "closed" or decision.tiers is None:
        raise LedgerError("D-56")
    _validate_checkpoint(record, decision.tiers)
    entry = resolve_or_none("D-56", _CATALOG)
    d56_key = entry.key if entry is not None else None
    with ledger._lock:
        ledger.connection.execute("BEGIN IMMEDIATE")
        try:
            _check_parent(ledger, record)
            _check_supersedes(ledger, record)
            row_id = uuid.uuid4().hex
            created_at = datetime.now(UTC).isoformat()
            ledger.connection.execute(
                """
                INSERT INTO checkpoints (
                    row_id, created_at, identity_hash, parent_ledger_id,
                    parent_identity_hash, config_hash, seed, fact_id, split,
                    role, tier, family, method, implementation_id, spec_tag,
                    git_commit, dirty, tokens, scored_candidates, training_steps,
                    training_examples, exports, wall_clock_seconds, gpu_hours,
                    peak_memory_bytes, status, supersedes, decision_id, decision_key,
                    study_role, model_config_id, model_config_digest,
                    model_identity_hash, identity_schema_version
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    row_id,
                    created_at,
                    record.identity_hash,
                    record.parent_ledger_id,
                    record.parent_identity_hash,
                    record.config_hash,
                    record.seed,
                    record.fact_id,
                    record.split,
                    record.role,
                    record.tier,
                    record.family,
                    record.method,
                    record.implementation_id,
                    record.spec_tag,
                    record.git_commit,
                    int(record.dirty),
                    record.tokens,
                    record.scored_candidates,
                    record.training_steps,
                    record.training_examples,
                    record.exports,
                    record.wall_clock_seconds,
                    record.gpu_hours,
                    record.peak_memory_bytes,
                    record.status,
                    record.supersedes,
                    "D-56",
                    d56_key,
                    record.study_role,
                    record.model_config_id,
                    record.model_config_digest,
                    record.model_identity_hash,
                    record.identity_schema_version,
                ),
            )
            ledger.connection.execute("COMMIT")
        except Exception:
            ledger.connection.execute("ROLLBACK")
            raise
    return row_id


def add_evaluation_run(ledger: Ledger, record: EvaluationRun) -> str:
    """Insert one run. Final-test pass rules apply."""
    _validate_run(record)
    with ledger._lock:
        ledger.connection.execute("BEGIN IMMEDIATE")
        try:
            parent = get_checkpoint(ledger, record.checkpoint_ledger_id)
            if parent is None:
                raise LedgerError("checkpoint_ledger_id")
            _check_pass(ledger, record)
            run_id = uuid.uuid4().hex
            created_at = datetime.now(UTC).isoformat()
            ledger.connection.execute(
                """
                INSERT INTO evaluation_runs (
                    run_id, created_at, checkpoint_ledger_id, arm, split,
                    spec_tag, thresholds_tag, budget_used, pass_number,
                    git_commit, dirty, study_role, model_config_id,
                    model_config_digest, model_identity_hash, identity_schema_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    created_at,
                    record.checkpoint_ledger_id,
                    record.arm,
                    record.split,
                    record.spec_tag,
                    record.thresholds_tag,
                    json.dumps(record.budget_used, sort_keys=True),
                    record.pass_number,
                    record.git_commit,
                    int(record.dirty),
                    record.study_role,
                    record.model_config_id,
                    record.model_config_digest,
                    record.model_identity_hash,
                    record.identity_schema_version,
                ),
            )
            ledger.connection.execute("COMMIT")
        except Exception:
            ledger.connection.execute("ROLLBACK")
            raise
    return run_id


def add_incident(ledger: Ledger, record: Incident) -> str:
    """Insert one incident. Does not edit the pass it references."""
    if not isinstance(record.split, str) or record.split == "":
        raise LedgerError("split")
    if not isinstance(record.note, str) or record.note == "":
        raise LedgerError("note")
    if isinstance(record.references_pass_number, bool) or not isinstance(
        record.references_pass_number, int
    ):
        raise LedgerError("references_pass_number")
    with ledger._lock:
        ledger.connection.execute("BEGIN IMMEDIATE")
        try:
            incident_id = uuid.uuid4().hex
            created_at = datetime.now(UTC).isoformat()
            ledger.connection.execute(
                """
                INSERT INTO incidents (
                    incident_id, created_at, split, references_pass_number, note
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    incident_id,
                    created_at,
                    record.split,
                    record.references_pass_number,
                    record.note,
                ),
            )
            ledger.connection.execute("COMMIT")
        except Exception:
            ledger.connection.execute("ROLLBACK")
            raise
    return incident_id


def add_study_artifact(ledger: Ledger, record: StudyArtifact) -> str:
    """Insert one study artifact and return its id."""
    if record.kind == "" or record.digest == "" or record.spec_tag == "":
        raise LedgerError("study_artifact")
    if (
        record.wall_clock_seconds < 0
        or record.gpu_hours < 0
        or record.peak_memory_bytes < 0
    ):
        raise LedgerError("study_artifact")
    with ledger._lock:
        ledger.connection.execute("BEGIN IMMEDIATE")
        try:
            artifact_id = uuid.uuid4().hex
            created_at = datetime.now(UTC).isoformat()
            ledger.connection.execute(
                """
                INSERT INTO study_artifacts (
                    artifact_id, created_at, kind, seed, digest, config_hash,
                    spec_tag, git_commit, dirty, wall_clock_seconds, gpu_hours,
                    peak_memory_bytes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    artifact_id,
                    created_at,
                    record.kind,
                    record.seed,
                    record.digest,
                    record.config_hash,
                    record.spec_tag,
                    record.git_commit,
                    int(record.dirty),
                    record.wall_clock_seconds,
                    record.gpu_hours,
                    record.peak_memory_bytes,
                ),
            )
            ledger.connection.execute("COMMIT")
        except Exception:
            ledger.connection.execute("ROLLBACK")
            raise
    return artifact_id


def get_checkpoint(ledger: Ledger, ledger_id: str) -> CheckpointRecord | None:
    """Return the row, or None when the id is unknown."""
    row = ledger.connection.execute(
        "SELECT * FROM checkpoints WHERE row_id = ?",
        (ledger_id,),
    ).fetchone()
    if row is None:
        return None
    return _checkpoint_from_row(row)


def get_evaluation_run(ledger: Ledger, run_id: str) -> EvaluationRun | None:
    """Return the run, or None when the id is unknown."""
    row = ledger.connection.execute(
        "SELECT * FROM evaluation_runs WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    if row is None:
        return None
    budget = json.loads(str(row["budget_used"]))
    if not isinstance(budget, dict):
        raise LedgerError("budget_used")
    return EvaluationRun(
        checkpoint_ledger_id=str(row["checkpoint_ledger_id"]),
        arm=str(row["arm"]),
        split=str(row["split"]),
        spec_tag=str(row["spec_tag"]),
        thresholds_tag=str(row["thresholds_tag"]),
        budget_used={str(key): float(value) for key, value in budget.items()},
        pass_number=int(row["pass_number"]),
        git_commit=str(row["git_commit"]),
        dirty=bool(row["dirty"]),
        run_id=str(row["run_id"]),
        created_at=str(row["created_at"]),
        study_role=_optional_column(row, "study_role"),
        model_config_id=_optional_column(row, "model_config_id"),
        model_config_digest=_optional_column(row, "model_config_digest"),
        model_identity_hash=_optional_column(row, "model_identity_hash"),
        identity_schema_version=_optional_int(row, "identity_schema_version"),
    )


def lineage(ledger: Ledger, ledger_id: str) -> tuple[str, ...]:
    """Row ids from the requested row back to the root. The root is last."""
    chain: list[str] = []
    current: str | None = ledger_id
    seen: set[str] = set()
    while current is not None:
        if current in seen:
            raise LedgerError("parent_ledger_id")
        seen.add(current)
        row = ledger.connection.execute(
            "SELECT parent_ledger_id FROM checkpoints WHERE row_id = ?",
            (current,),
        ).fetchone()
        if row is None:
            raise LedgerError(ledger_id)
        chain.append(current)
        parent = row["parent_ledger_id"]
        current = None if parent is None else str(parent)
    return tuple(chain)


def check_disjoint(ledger: Ledger) -> DisjointnessReport:
    """Fact, reference seed, and control implementation on the two splits."""
    rows = ledger.connection.execute("SELECT * FROM checkpoints").fetchall()
    buckets: dict[str, list[sqlite3.Row]] = {"calibration": [], "final_test": []}
    for row in rows:
        split = str(row["split"])
        if split == "calibration":
            buckets["calibration"].append(row)
        elif split in _FINAL:
            buckets["final_test"].append(row)
    counts = {
        name: {
            "fact": len({str(item["fact_id"]) for item in group}),
            "reference_seed": len(
                {
                    int(item["seed"])
                    for item in group
                    if str(item["role"]) == "reference"
                }
            ),
            "control_implementation": len(
                {
                    str(item["implementation_id"])
                    for item in group
                    if str(item["role"]) == "control"
                    and str(item["implementation_id"]) != ""
                }
            ),
        }
        for name, group in buckets.items()
    }
    offenders: set[str] = set()
    _overlap_values(
        buckets,
        offenders,
        lambda item: str(item["fact_id"]),
    )
    _overlap_values(
        buckets,
        offenders,
        lambda item: str(item["seed"]) if str(item["role"]) == "reference" else None,
    )
    _overlap_values(
        buckets,
        offenders,
        lambda item: (
            str(item["implementation_id"])
            if str(item["role"]) == "control" and str(item["implementation_id"]) != ""
            else None
        ),
    )
    ordered = tuple(sorted(offenders))
    return DisjointnessReport(ok=not ordered, counts=counts, offenders=ordered)


def final_pass_status(ledger: Ledger, split: str) -> int | None:
    """The highest accepted pass number on that split, or None when no pass exists."""
    rows = _runs_on_split(ledger, split)
    if not rows:
        return None
    return max(int(item["pass_number"]) for item in rows)


def _validate_checkpoint(record: CheckpointRecord, tiers: tuple[str, ...]) -> None:
    for name in _TEXT_FIELDS:
        value = getattr(record, name)
        if not isinstance(value, str) or value == "":
            raise LedgerError(name)
    if record.role not in _ROLES:
        raise LedgerError("role")
    if record.tier not in tiers:
        raise LedgerError("tier")
    if not isinstance(record.dirty, bool):
        raise LedgerError("dirty")
    if record.role == "control" and record.implementation_id == "":
        raise LedgerError("implementation_id")
    if not isinstance(record.implementation_id, str):
        raise LedgerError("implementation_id")
    _require_int(record.seed, "seed", nonnegative=False)
    for name in (
        "tokens",
        "scored_candidates",
        "training_steps",
        "training_examples",
        "exports",
        "peak_memory_bytes",
    ):
        _require_int(getattr(record, name), name, nonnegative=True)
    for name in ("wall_clock_seconds", "gpu_hours"):
        value = getattr(record, name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value < 0:
            raise LedgerError(name)
    if record.parent_ledger_id is None:
        if record.parent_identity_hash != "":
            raise LedgerError("parent_identity_hash")
    else:
        if record.parent_ledger_id == "" or record.parent_identity_hash == "":
            raise LedgerError("parent_ledger_id")
    if record.split in _FINAL and record.dirty:
        raise LedgerError("dirty")


def _validate_run(record: EvaluationRun) -> None:
    for name in ("checkpoint_ledger_id", "arm", "split", "spec_tag", "git_commit"):
        value = getattr(record, name)
        if not isinstance(value, str) or value == "":
            raise LedgerError(name)
    if not isinstance(record.thresholds_tag, str) or record.thresholds_tag == "":
        raise LedgerError("thresholds_tag")
    if not isinstance(record.dirty, bool):
        raise LedgerError("dirty")
    if isinstance(record.pass_number, bool) or not isinstance(record.pass_number, int):
        raise LedgerError("pass_number")
    if record.pass_number < 1:
        raise LedgerError("pass_number")
    if not isinstance(record.budget_used, dict):
        raise LedgerError("budget_used")
    for key in _BUDGET_KEYS:
        if key not in record.budget_used:
            raise LedgerError(key)
    if record.split in _FINAL and record.dirty:
        raise LedgerError("dirty")


def _check_parent(ledger: Ledger, record: CheckpointRecord) -> None:
    if record.parent_ledger_id is None:
        return
    parent = get_checkpoint(ledger, record.parent_ledger_id)
    if parent is None:
        raise LedgerError("parent_ledger_id")
    if parent.identity_hash != record.parent_identity_hash:
        raise LedgerError("parent_identity_hash")


def _check_supersedes(ledger: Ledger, record: CheckpointRecord) -> None:
    existing = ledger.connection.execute(
        "SELECT row_id FROM checkpoints WHERE identity_hash = ?",
        (record.identity_hash,),
    ).fetchall()
    if not existing:
        if record.supersedes is not None:
            raise LedgerError("supersedes")
        return
    if record.supersedes is None:
        raise LedgerError("identity_hash")
    target = get_checkpoint(ledger, record.supersedes)
    if target is None:
        raise LedgerError("supersedes")
    if target.identity_hash != record.identity_hash:
        raise LedgerError("identity_hash")
    current = _current_identity_row(ledger, record.identity_hash)
    if current != record.supersedes:
        raise LedgerError("supersedes")


def _current_identity_row(ledger: Ledger, identity_hash: str) -> str:
    rows = ledger.connection.execute(
        "SELECT row_id, supersedes FROM checkpoints WHERE identity_hash = ?",
        (identity_hash,),
    ).fetchall()
    superseded = {
        str(item["supersedes"]) for item in rows if item["supersedes"] is not None
    }
    tips = [
        str(item["row_id"]) for item in rows if str(item["row_id"]) not in superseded
    ]
    if len(tips) != 1:
        raise LedgerError("identity_hash")
    return tips[0]


def _check_pass(ledger: Ledger, record: EvaluationRun) -> None:
    if record.split not in _FINAL:
        return
    existing = _runs_on_split(ledger, record.split)
    if record.pass_number == 1:
        if existing:
            raise LedgerError("pass")
        return
    if not _incident_unlocks(ledger, record.split):
        raise LedgerError("pass")


def _runs_on_split(ledger: Ledger, split: str) -> list[sqlite3.Row]:
    if split in _FINAL:
        marks = tuple(_FINAL)
    else:
        marks = (split,)
    placeholders = ", ".join("?" for _ in marks)
    return list(
        ledger.connection.execute(
            f"SELECT * FROM evaluation_runs WHERE split IN ({placeholders})",
            marks,
        ).fetchall()
    )


def _incident_unlocks(ledger: Ledger, split: str) -> bool:
    marks = tuple(_FINAL) if split in _FINAL else (split,)
    placeholders = ", ".join("?" for _ in marks)
    row = ledger.connection.execute(
        f"""
        SELECT 1 FROM incidents
        WHERE split IN ({placeholders}) AND references_pass_number = 1
        LIMIT 1
        """,
        marks,
    ).fetchone()
    return row is not None


def _optional_column(row: sqlite3.Row, key: str) -> str | None:
    if key not in row.keys() or row[key] is None:
        return None
    return str(row[key])


def _optional_int(row: sqlite3.Row, key: str) -> int | None:
    if key not in row.keys() or row[key] is None:
        return None
    return int(row[key])


def _checkpoint_from_row(row: sqlite3.Row) -> CheckpointRecord:
    parent = row["parent_ledger_id"]
    supersedes = row["supersedes"]
    keys = row.keys()
    raw_decision_id = row["decision_id"] if "decision_id" in keys else None
    raw_decision_key = row["decision_key"] if "decision_key" in keys else None
    return CheckpointRecord(
        identity_hash=str(row["identity_hash"]),
        parent_ledger_id=None if parent is None else str(parent),
        parent_identity_hash=str(row["parent_identity_hash"]),
        config_hash=str(row["config_hash"]),
        seed=int(row["seed"]),
        fact_id=str(row["fact_id"]),
        split=str(row["split"]),
        role=str(row["role"]),
        tier=str(row["tier"]),
        family=str(row["family"]),
        method=str(row["method"]),
        implementation_id=str(row["implementation_id"]),
        spec_tag=str(row["spec_tag"]),
        git_commit=str(row["git_commit"]),
        dirty=bool(row["dirty"]),
        tokens=int(row["tokens"]),
        scored_candidates=int(row["scored_candidates"]),
        training_steps=int(row["training_steps"]),
        training_examples=int(row["training_examples"]),
        exports=int(row["exports"]),
        wall_clock_seconds=float(row["wall_clock_seconds"]),
        gpu_hours=float(row["gpu_hours"]),
        peak_memory_bytes=int(row["peak_memory_bytes"]),
        status=str(row["status"]),
        supersedes=None if supersedes is None else str(supersedes),
        decision_id=None if raw_decision_id is None else str(raw_decision_id),
        decision_key=None if raw_decision_key is None else str(raw_decision_key),
        study_role=_optional_column(row, "study_role"),
        model_config_id=_optional_column(row, "model_config_id"),
        model_config_digest=_optional_column(row, "model_config_digest"),
        model_identity_hash=_optional_column(row, "model_identity_hash"),
        identity_schema_version=_optional_int(row, "identity_schema_version"),
        row_id=str(row["row_id"]),
        created_at=str(row["created_at"]),
    )


def _parent_from_hash(ledger: Ledger, parent_hash: str) -> tuple[str | None, str]:
    if parent_hash == "":
        return None, ""
    rows = ledger.connection.execute(
        "SELECT row_id FROM checkpoints WHERE identity_hash = ?",
        (parent_hash,),
    ).fetchall()
    if not rows:
        raise LedgerError("parent_ledger_id")
    if len(rows) == 1:
        return str(rows[0]["row_id"]), parent_hash
    current = _current_identity_row(ledger, parent_hash)
    return current, parent_hash


def _require_int(value: object, name: str, *, nonnegative: bool) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(name)
    if nonnegative and value < 0:
        raise LedgerError(name)


def _overlap_values(
    buckets: dict[str, list[sqlite3.Row]],
    offenders: set[str],
    value_of: object,
) -> None:
    if not callable(value_of):
        raise LedgerError("fact")
    left: dict[str, list[str]] = {}
    right: dict[str, list[str]] = {}
    for item in buckets["calibration"]:
        value = value_of(item)
        if value is not None:
            left.setdefault(str(value), []).append(str(item["row_id"]))
    for item in buckets["final_test"]:
        value = value_of(item)
        if value is not None:
            right.setdefault(str(value), []).append(str(item["row_id"]))
    for key, ids in left.items():
        if key in right:
            offenders.update(ids)
            offenders.update(right[key])
