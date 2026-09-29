"""FV-DATA-035 through FV-DATA-039.

Fixture counts are 2 and 2, not the study counts of 8 and 8.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.data.decisions import load_d68
from src.data.errors import DataError
from src.data.splits import assign_splits, load_split, validate_splits
from src.ledger.api import StudyArtifact, add_study_artifact, open_ledger

PILOT = Path("tests/fixtures/ledger/decisions/d56_pilot.yaml")


def _write(path: Path, row: dict[str, object]) -> None:
    path.write_text(
        yaml.safe_dump({"decisions": [row]}, sort_keys=False),
        encoding="utf-8",
    )


def _d68(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "decision_id": "D-68",
        "status": "closed",
        "block": "block0",
        "counts": {"construction": 2, "calibration": 2},
        "assign_final_test": False,
        "relations": ["occupation", "birthplace"],
    }
    row.update(overrides)
    return row


def _fact(fact_id: str, author: str, relation: str, obj: str) -> dict[str, object]:
    return {
        "fact_id": fact_id,
        "triple": {
            "subject": {"id": author, "label": author},
            "relation": {"id": relation, "label": relation},
            "object": {"id": obj, "label": obj},
        },
    }


def _pass_rows(
    facts: list[dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    gate = [{"fact_id": fact["fact_id"], "verdict": "pass"} for fact in facts]
    audit = [{"target_fact_id": fact["fact_id"], "verdict": "clean"} for fact in facts]
    return gate, audit


def test_d68_open_refuses(tmp_path: Path) -> None:
    path = tmp_path / "decisions.yaml"
    _write(path, {"decision_id": "D-68", "status": "open"})
    with pytest.raises(DataError, match="D-68"):
        load_d68(path)


def test_d68_assign_final_test_true_refuses(tmp_path: Path) -> None:
    path = tmp_path / "decisions.yaml"
    _write(path, _d68(assign_final_test=True))
    with pytest.raises(DataError, match="assign_final_test"):
        load_d68(path)


def test_d68_blank_counts_refuses(tmp_path: Path) -> None:
    row = _d68()
    counts = row["counts"]
    assert isinstance(counts, dict)
    del counts["calibration"]
    path = tmp_path / "decisions.yaml"
    _write(path, row)
    with pytest.raises(DataError, match="calibration"):
        load_d68(path)


def test_d68_reads_fixture_counts(tmp_path: Path) -> None:
    path = tmp_path / "decisions.yaml"
    _write(path, _d68())
    loaded = load_d68(path)
    assert loaded.construction == 2
    assert loaded.calibration == 2
    assert loaded.assign_final_test is False
    assert loaded.relations == ("occupation", "birthplace")


def test_fv_data_035_entity_disjoint(tmp_path: Path) -> None:
    facts = [
        _fact("f1", "author-a", "occupation", "writer"),
        _fact("f2", "author-a", "birthplace", "Lagos"),
        _fact("f3", "author-b", "occupation", "poet"),
        _fact("f4", "author-b", "birthplace", "Oslo"),
    ]
    gate, audit = _pass_rows(facts)
    decision = load_d68(_path(tmp_path))
    payload = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=decision,
        seed=1,
    )
    labels_by_author: dict[str, set[str]] = {}
    for fact, label in ((fact, payload["facts"][fact["fact_id"]]) for fact in facts):
        author = str(fact["triple"]["subject"]["id"])  # type: ignore[index]
        labels_by_author.setdefault(author, set()).add(label)
    assert all(len(labels) == 1 for labels in labels_by_author.values())
    bad = {
        "facts": {"f1": "construction", "f2": "calibration"},
        "entities": {},
    }
    with pytest.raises(DataError, match="author-a"):
        validate_splits(bad, facts[:2])


def test_fv_data_036_sizes(tmp_path: Path) -> None:
    facts = [
        _fact("f1", "a", "occupation", "writer"),
        _fact("f2", "b", "birthplace", "Lagos"),
        _fact("f3", "c", "occupation", "poet"),
        _fact("f4", "d", "birthplace", "Oslo"),
    ]
    gate, audit = _pass_rows(facts)
    decision = load_d68(_path(tmp_path))
    payload = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=decision,
        seed=3,
    )
    counts = {"construction": 0, "calibration": 0}
    for label in payload["facts"].values():
        counts[label] += 1
    assert counts["construction"] == 2
    assert counts["calibration"] == 2
    out = tmp_path / "splits.json"
    out.write_bytes(b"keep")
    short_gate, short_audit = _pass_rows(facts[:1])
    with pytest.raises(DataError):
        assign_splits(
            facts=facts[:1],
            gate_rows=short_gate,
            audit_rows=short_audit,
            decision=decision,
            seed=3,
            out=out,
        )
    assert out.read_bytes() == b"keep"


def test_fv_data_037_deterministic(tmp_path: Path) -> None:
    facts = [
        _fact("f1", "a", "occupation", "writer"),
        _fact("f2", "b", "birthplace", "Lagos"),
        _fact("f3", "c", "occupation", "poet"),
        _fact("f4", "d", "birthplace", "Oslo"),
        _fact("f5", "e", "occupation", "editor"),
    ]
    gate, audit = _pass_rows(facts)
    decision = load_d68(_path(tmp_path))
    first = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=decision,
        seed=7,
    )
    second = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=decision,
        seed=7,
    )
    assert first["digest"] == second["digest"]
    ledger = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    add_study_artifact(
        ledger,
        StudyArtifact(
            kind="split_assignment",
            seed=7,
            digest=str(first["digest"]),
            config_hash="cfg",
            spec_tag="spec-v1",
            git_commit="abc",
            dirty=False,
            wall_clock_seconds=0.0,
            gpu_hours=0.0,
            peak_memory_bytes=0,
        ),
    )
    reopened = open_ledger(tmp_path / "ledger.sqlite", decisions=PILOT)
    row = reopened.connection.execute(
        "SELECT seed, digest FROM study_artifacts"
    ).fetchone()
    assert row is not None
    assert int(row["seed"]) == 7
    assert str(row["digest"]) == first["digest"]


def test_fv_data_038_relation_balance(tmp_path: Path) -> None:
    facts = [
        _fact("f1", "a", "occupation", "writer"),
        _fact("f2", "b", "birthplace", "Lagos"),
        _fact("f3", "c", "occupation", "poet"),
        _fact("f4", "d", "birthplace", "Oslo"),
    ]
    gate, audit = _pass_rows(facts)
    decision = load_d68(_path(tmp_path))
    payload = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=decision,
        seed=1,
    )
    for label in ("construction", "calibration"):
        relations = {
            fact["triple"]["relation"]["label"]  # type: ignore[index]
            for fact in facts
            if payload["facts"][fact["fact_id"]] == label
        }
        assert relations == {"occupation", "birthplace"}
    only = [
        _fact("f1", "a", "occupation", "writer"),
        _fact("f2", "b", "occupation", "poet"),
        _fact("f3", "c", "occupation", "editor"),
        _fact("f4", "d", "occupation", "teacher"),
    ]
    only_gate, only_audit = _pass_rows(only)
    with pytest.raises(DataError, match="construction=2"):
        assign_splits(
            facts=only,
            gate_rows=only_gate,
            audit_rows=only_audit,
            decision=decision,
            seed=1,
        )


def test_fv_data_039_final_guard(tmp_path: Path) -> None:
    held = tmp_path / "held.json"
    held.write_text(
        json.dumps({"facts": {"f9": "final_test"}, "entities": {"a": "final_test"}}),
        encoding="utf-8",
    )
    log = tmp_path / "access.jsonl"
    with pytest.raises(DataError, match="role"):
        load_split(held, "final_test", role="calibration", access_log=log)
    denial = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert denial["reason"] == "role"
    loaded = load_split(held, "final_test", role="final_test_pass", access_log=log)
    assert loaded == ["f9"]
    facts = [
        _fact("f1", "a", "occupation", "writer"),
        _fact("f2", "b", "birthplace", "Lagos"),
        _fact("f3", "c", "occupation", "poet"),
        _fact("f4", "d", "birthplace", "Oslo"),
    ]
    gate, audit = _pass_rows(facts)
    out = tmp_path / "splits.json"
    payload = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=load_d68(_path(tmp_path)),
        seed=1,
        out=out,
    )
    assert "final_test" not in json.dumps(payload)
    with pytest.raises(DataError, match="empty_split"):
        load_split(out, "final_test", role="final_test_pass", access_log=log)
    empty = json.loads(log.read_text(encoding="utf-8").splitlines()[-1])
    assert empty["reason"] == "empty_split"


def _path(tmp_path: Path) -> Path:
    path = tmp_path / "d68.yaml"
    _write(path, _d68())
    return path


def test_ineligible_omitted(tmp_path: Path) -> None:
    facts = [
        _fact("keep1", "a", "occupation", "writer"),
        _fact("keep2", "b", "birthplace", "Lagos"),
        _fact("keep3", "c", "occupation", "poet"),
        _fact("keep4", "d", "birthplace", "Oslo"),
        _fact("drop", "e", "occupation", "teacher"),
    ]
    gate, audit = _pass_rows(facts[:4])
    gate.append({"fact_id": "drop", "verdict": "excluded_known"})
    audit.append({"target_fact_id": "drop", "verdict": "clean"})
    payload = assign_splits(
        facts=facts,
        gate_rows=gate,
        audit_rows=audit,
        decision=load_d68(_path(tmp_path)),
        seed=1,
    )
    assert "drop" not in payload["facts"]
