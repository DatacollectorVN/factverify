"""FV-LEDG hooks. The ledger does not run git."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from threading import Thread

import pytest

from scripts.ledger import main
from src.ledger.api import (
    CheckpointRecord,
    EvaluationRun,
    Incident,
    add_checkpoint,
    add_evaluation_run,
    add_incident,
    check_disjoint,
    get_checkpoint,
    get_evaluation_run,
    lineage,
    open_ledger,
)
from src.ledger.errors import LedgerError
from src.ledger.export import export_ledger, import_ledger

DECISIONS = Path("tests/fixtures/ledger/decisions")
PILOT = DECISIONS / "d56_pilot.yaml"
OPEN = DECISIONS / "open.yaml"


def _record(**overrides: object) -> CheckpointRecord:
    fields: dict[str, object] = {
        "identity_hash": "id-root",
        "parent_ledger_id": None,
        "parent_identity_hash": "",
        "config_hash": "cfg",
        "seed": 0,
        "fact_id": "fact-1",
        "split": "calibration",
        "role": "base",
        "tier": "pilot",
        "family": "base",
        "method": "base",
        "implementation_id": "",
        "spec_tag": "fixture",
        "git_commit": "abc",
        "dirty": False,
        "tokens": 0,
        "scored_candidates": 0,
        "training_steps": 0,
        "training_examples": 0,
        "exports": 0,
        "wall_clock_seconds": 0.0,
        "gpu_hours": 0.0,
        "peak_memory_bytes": 0,
        "status": "ready",
    }
    fields.update(overrides)
    return CheckpointRecord(**fields)  # type: ignore[arg-type]


def _budget() -> dict[str, float]:
    return {
        "tokens": 0,
        "scored_candidates": 0,
        "training_steps": 0,
        "exports": 0,
        "wall_clock_seconds": 0,
        "gpu_hours": 0,
        "peak_memory_bytes": 0,
    }


def _run(checkpoint_id: str, **overrides: object) -> EvaluationRun:
    fields: dict[str, object] = {
        "checkpoint_ledger_id": checkpoint_id,
        "arm": "native",
        "split": "calibration",
        "spec_tag": "fixture",
        "thresholds_tag": "thresholds-v1",
        "budget_used": _budget(),
        "pass_number": 1,
        "git_commit": "abc",
        "dirty": False,
    }
    fields.update(overrides)
    return EvaluationRun(**fields)  # type: ignore[arg-type]


def _count(path: Path) -> int:
    connection = sqlite3.connect(str(path))
    try:
        row = connection.execute("SELECT COUNT(*) FROM checkpoints").fetchone()
    finally:
        connection.close()
    assert row is not None
    return int(row[0])


def test_fv_ledg_001_unledgered_refused(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = open_ledger(path, decisions=PILOT)
    row_id = add_checkpoint(ledger, _record())
    stored = get_checkpoint(ledger, row_id)
    assert stored is not None
    assert stored.role == "base"
    assert stored.split == "calibration"
    with pytest.raises(LedgerError):
        lineage(ledger, "missing")


def test_fv_ledg_002_required_fields(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = open_ledger(path, decisions=PILOT)
    row_id = add_checkpoint(ledger, _record())
    stored = get_checkpoint(ledger, row_id)
    assert stored is not None
    assert stored.row_id == row_id
    assert stored.created_at != ""
    for name in (
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
    ):
        with pytest.raises(LedgerError, match=name):
            add_checkpoint(ledger, _record(**{name: ""}))
        assert _count(path) == 1


def test_fv_ledg_004_vocabularies(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = open_ledger(path, decisions=PILOT)
    add_checkpoint(ledger, _record(tier="pilot"))
    with pytest.raises(LedgerError, match="role"):
        add_checkpoint(ledger, _record(identity_hash="other", role="ref"))
    with pytest.raises(LedgerError, match="tier"):
        add_checkpoint(ledger, _record(identity_hash="other", tier="block"))
    open_path = tmp_path / "open.sqlite"
    opened = open_ledger(open_path, decisions=OPEN)
    with pytest.raises(LedgerError, match="D-56"):
        add_checkpoint(opened, _record())
    assert _count(open_path) == 0
    empty = open_ledger(
        tmp_path / "empty.sqlite", decisions=DECISIONS / "d56_empty.yaml"
    )
    with pytest.raises(LedgerError, match="D-56"):
        add_checkpoint(empty, _record())


def test_fv_ledg_005_lineage(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    root = add_checkpoint(ledger, _record())
    child = add_checkpoint(
        ledger,
        _record(
            identity_hash="id-child",
            parent_ledger_id=root,
            parent_identity_hash="id-root",
            role="finetuned",
        ),
    )
    assert lineage(ledger, child)[-1] == root
    with pytest.raises(LedgerError):
        add_checkpoint(
            ledger,
            _record(
                identity_hash="id-missing",
                parent_ledger_id="absent",
                parent_identity_hash="nope",
            ),
        )
    assert _count(tmp_path / "ledger.sqlite") == 2


def test_fv_ledg_009_eval_runs(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    checkpoint_id = add_checkpoint(ledger, _record())
    run_id = add_evaluation_run(ledger, _run(checkpoint_id))
    stored = get_evaluation_run(ledger, run_id)
    assert stored is not None
    assert stored.arm == "native"
    assert stored.split == "calibration"
    assert stored.spec_tag == "fixture"
    assert stored.thresholds_tag == "thresholds-v1"
    assert stored.budget_used["tokens"] == 0
    assert stored.pass_number == 1
    assert stored.git_commit == "abc"
    assert stored.dirty is False
    with pytest.raises(LedgerError, match="thresholds_tag"):
        add_evaluation_run(
            ledger,
            _run(checkpoint_id, split="final_test", thresholds_tag=""),
        )


def test_fv_ledg_003_append_only(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    first = add_checkpoint(ledger, _record())
    second = add_checkpoint(ledger, _record(supersedes=first))
    original = get_checkpoint(ledger, first)
    correction = get_checkpoint(ledger, second)
    assert original is not None and correction is not None
    assert correction.supersedes == first
    assert original.status == "ready"
    assert original.git_commit == "abc"
    with pytest.raises(LedgerError, match="identity_hash"):
        add_checkpoint(ledger, _record(identity_hash="id-root"))
    with pytest.raises(LedgerError, match="supersedes"):
        add_checkpoint(ledger, _record(supersedes="missing"))
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.connection.execute("UPDATE checkpoints SET status = 'edited'")
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        ledger.connection.execute("DELETE FROM checkpoints")


def test_fv_ledg_010_export_roundtrip(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    add_checkpoint(ledger, _record())
    directory = tmp_path / "export"
    export_ledger(ledger, directory)
    copied = import_ledger(directory, tmp_path / "copy.sqlite", decisions=PILOT)
    left = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    again = tmp_path / "again"
    export_ledger(copied, again)
    right = json.loads((again / "manifest.json").read_text(encoding="utf-8"))
    assert left["tables"]["checkpoints"]["count"] == 1
    assert (
        left["tables"]["checkpoints"]["digests"]
        == right["tables"]["checkpoints"]["digests"]
    )
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    manifest["schema_version"] = "2"
    (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(LedgerError, match="schema_version"):
        import_ledger(directory, tmp_path / "refused.sqlite", decisions=PILOT)
    assert not (tmp_path / "refused.sqlite").exists()


def test_fv_ledg_011_concurrency(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = open_ledger(path, decisions=PILOT)
    errors: list[BaseException] = []

    def add_one(identity: str) -> None:
        try:
            add_checkpoint(ledger, _record(identity_hash=identity))
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [Thread(target=add_one, args=(f"id-{index}",)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
    assert _count(path) == 4
    connection = ledger.connection
    before = _count(path)
    connection.execute("BEGIN")
    connection.execute(
        """
        INSERT INTO checkpoints (
            row_id, created_at, identity_hash, parent_ledger_id, parent_identity_hash,
            config_hash, seed, fact_id, split, role, tier, family, method,
            implementation_id, spec_tag, git_commit, dirty, tokens, scored_candidates,
            training_steps, training_examples, exports, wall_clock_seconds, gpu_hours,
            peak_memory_bytes, status, supersedes
        ) VALUES (
            'rolled', 't', 'rolled', NULL, '', 'cfg', 0, 'fact', 'calibration',
            'base', 'pilot', 'base', 'base', '', 'fixture', 'abc', 0, 0, 0, 0, 0,
            0, 0, 0, 0, 'ready', NULL
        )
        """
    )
    connection.execute("ROLLBACK")
    assert _count(path) == before


def test_fv_ledg_006_code_state(tmp_path: Path) -> None:
    path = tmp_path / "ledger.sqlite"
    ledger = open_ledger(path, decisions=PILOT)
    with pytest.raises(LedgerError, match="dirty"):
        add_checkpoint(ledger, _record(split="final_test", dirty=True))
    with pytest.raises(LedgerError, match="dirty"):
        add_checkpoint(
            ledger, _record(split="final-test", dirty=True, identity_hash="b")
        )
    assert _count(path) == 0
    stored_id = add_checkpoint(
        ledger, _record(split="final_test", dirty=False, git_commit="abc")
    )
    stored = get_checkpoint(ledger, stored_id)
    assert stored is not None
    assert stored.git_commit == "abc"
    assert stored.dirty is False
    dirty_id = add_checkpoint(
        ledger,
        _record(identity_hash="cal", split="calibration", dirty=True),
    )
    dirty = get_checkpoint(ledger, dirty_id)
    assert dirty is not None and dirty.dirty is True


def test_fv_ledg_007_disjoint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    disjoint = _two_splits(tmp_path / "ok.sqlite")
    report = check_disjoint(disjoint)
    assert report.ok
    assert set(report.counts) == {"calibration", "final_test"}
    for side in report.counts.values():
        assert set(side) == {"fact", "reference_seed", "control_implementation"}
    code = main(
        [
            "check-disjoint",
            "--path",
            str(tmp_path / "ok.sqlite"),
            "--decisions",
            str(PILOT),
        ]
    )
    assert code == 0
    assert "fact" in capsys.readouterr().out
    shared = _two_splits(tmp_path / "shared.sqlite", shared_fact=True)
    bad = check_disjoint(shared)
    assert not bad.ok
    assert bad.offenders
    seed_ledger = _two_splits(tmp_path / "seed.sqlite", shared_seed=True)
    assert not check_disjoint(seed_ledger).ok
    impl_ledger = _two_splits(tmp_path / "impl.sqlite", shared_impl=True)
    assert not check_disjoint(impl_ledger).ok
    only = open_ledger(tmp_path / "only.sqlite", decisions=PILOT)
    add_checkpoint(only, _record(role="base", fact_id="only-fact"))
    only_report = check_disjoint(only)
    assert only_report.ok
    assert only_report.counts["final_test"]["fact"] == 0
    failed = main(
        [
            "check-disjoint",
            "--path",
            str(tmp_path / "shared.sqlite"),
            "--decisions",
            str(PILOT),
        ]
    )
    assert failed == 1
    printed = capsys.readouterr().out
    assert check_disjoint(shared).offenders[0] in printed


def test_fv_ledg_008_single_pass(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    checkpoint_id = add_checkpoint(ledger, _record(split="final_test", dirty=False))
    add_evaluation_run(ledger, _run(checkpoint_id, split="final_test", pass_number=1))
    with pytest.raises(LedgerError, match="pass"):
        add_evaluation_run(
            ledger, _run(checkpoint_id, split="final_test", pass_number=2)
        )
    add_incident(
        ledger, Incident(split="final_test", references_pass_number=1, note="rerun")
    )
    add_evaluation_run(ledger, _run(checkpoint_id, split="final_test", pass_number=2))
    other = open_ledger(tmp_path / "other.sqlite", decisions=PILOT)
    other_id = add_checkpoint(other, _record(split="final_test", dirty=False))
    add_evaluation_run(other, _run(other_id, split="final_test", pass_number=1))
    add_incident(
        other, Incident(split="final_test", references_pass_number=2, note="no")
    )
    with pytest.raises(LedgerError, match="pass"):
        add_evaluation_run(other, _run(other_id, split="final_test", pass_number=3))


def _two_splits(
    path: Path,
    *,
    shared_fact: bool = False,
    shared_seed: bool = False,
    shared_impl: bool = False,
) -> object:
    ledger = open_ledger(path, decisions=PILOT)
    fact_final = "fact-a" if shared_fact else "fact-b"
    seed_final = 1 if shared_seed else 2
    impl_final = "impl-a" if shared_impl else "impl-b"
    add_checkpoint(ledger, _record(identity_hash="cal-base", fact_id="fact-a"))
    add_checkpoint(
        ledger,
        _record(
            identity_hash="cal-ref",
            role="reference",
            fact_id="fact-r1",
            seed=1,
        ),
    )
    add_checkpoint(
        ledger,
        _record(
            identity_hash="cal-ctl",
            role="control",
            fact_id="fact-c1",
            implementation_id="impl-a",
            family="refusal",
            method="refusal",
        ),
    )
    add_checkpoint(
        ledger,
        _record(
            identity_hash="fin-base",
            split="final_test",
            dirty=False,
            fact_id=fact_final,
        ),
    )
    add_checkpoint(
        ledger,
        _record(
            identity_hash="fin-ref",
            split="final_test",
            dirty=False,
            role="reference",
            fact_id="fact-r2",
            seed=seed_final,
        ),
    )
    add_checkpoint(
        ledger,
        _record(
            identity_hash="fin-ctl",
            split="final_test",
            dirty=False,
            role="control",
            fact_id="fact-c2",
            implementation_id=impl_final,
            family="refusal",
            method="refusal",
        ),
    )
    return ledger


def test_checkpoint_binding_columns(tmp_path: Path) -> None:
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    digest = "sha256:" + "ab" * 32
    identity = "sha256:" + "cd" * 32
    row_id = add_checkpoint(
        ledger,
        _record(
            identity_hash="checkpoint-new",
            study_role="controlled_fact_base",
            model_config_id="block0-debug-pythia-410m-v1",
            model_config_digest=digest,
            model_identity_hash=identity,
            identity_schema_version=2,
        ),
    )
    stored = get_checkpoint(ledger, row_id)
    assert stored is not None
    assert stored.identity_hash == "checkpoint-new"
    assert stored.study_role == "controlled_fact_base"
    assert stored.model_config_id == "block0-debug-pythia-410m-v1"
    assert stored.model_config_digest == digest
    assert stored.model_identity_hash == identity
    assert stored.identity_schema_version == 2
    older_id = add_checkpoint(ledger, _record(identity_hash="checkpoint-old"))
    older = get_checkpoint(ledger, older_id)
    assert older is not None
    assert older.identity_hash == "checkpoint-old"
    assert older.study_role is None
    assert older.model_config_id is None
    assert older.model_config_digest is None
    assert older.model_identity_hash is None
    assert older.identity_schema_version is None
