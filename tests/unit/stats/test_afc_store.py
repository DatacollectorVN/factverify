"""Saving AFC verdicts in the ledger's ``afc_scores`` table."""

from __future__ import annotations

import importlib.util
import json
import math
import sqlite3
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml

from src.ledger.train_store import (
    ExperimentRecord,
    TrainStore,
    afc_record_from_payload,
    open_train_store,
)
from src.stats.afc import FAMILIES, AFCSettings, certify_report

REPO = Path(__file__).resolve().parents[3]


def _store(tmp_path: Path) -> TrainStore:
    return open_train_store(tmp_path / "ledger.sqlite")


def _experiment(store: TrainStore, job: str = "job") -> str:
    return store.create_experiment(
        ExperimentRecord(
            job_name=job,
            role="forgetter",
            method="RMU",
            seed=3,
            split="s",
            target_fact="target",
            facts=["target"],
            config_hash="h",
        )
    )


def _fact(fact_id: str, role: str, drops: list[float]) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact_role": role,
        "families": {
            f: {"drop": d, "log_retention": -d, "retention": math.exp(-d)}
            for f, d in zip(FAMILIES, drops)
        },
    }


def _report(**extra: Any) -> dict[str, Any]:
    return {
        "job_name": "job",
        "selected_checkpoint_epoch": 2,
        "facts": [
            _fact("target", "target", [9.0, 8.0, 7.0, 6.0, 5.0]),
            _fact("a", "neighbour", [0.01, 0.02, 0.03, 0.02, 0.01]),
            _fact("b", "neighbour", [0.05, 0.04, 0.06, 0.03, 0.05]),
        ],
        **extra,
    }


def _payload(kappa: float | None = 0.8, **extra: Any) -> dict[str, Any]:
    return certify_report(_report(**extra), ["a", "b"], AFCSettings(0.05, kappa))


def _save(
    store: TrainStore, eid: str, payload: dict[str, Any], kappa: float | None
) -> str:
    return store.record_afc(
        afc_record_from_payload(eid, payload, alpha=0.05, kappa=kappa)
    )


def _rows(store: TrainStore) -> list[sqlite3.Row]:
    return store._conn.execute("SELECT * FROM afc_scores ORDER BY kappa").fetchall()


def test_row_holds_the_verdict_and_links_to_the_experiment(tmp_path: Path) -> None:
    store = _store(tmp_path)
    eid = _experiment(store)
    payload = _payload()
    _save(store, eid, payload, 0.8)
    row = store._conn.execute(
        "SELECT a.*, e.job_name FROM afc_scores a "
        "JOIN experiments e USING (experiment_id)"
    ).fetchone()
    assert (row["job_name"], row["epoch"], row["alpha"], row["kappa"]) == (
        "job",
        2,
        0.05,
        0.8,
    )
    assert (row["num_neighbours"], row["num_control_cells"]) == (2, 10)
    assert row["p_forget"] == pytest.approx(payload["p_forget"])
    assert row["p_retain"] == pytest.approx(payload["p_retain"])
    assert row["target_min_drop"] == 5.0 and row["weakest_family"] == "verify"
    assert (
        row["weakest_neighbour"] == payload["neighbours"][payload["weakest_neighbour"]]
    )
    assert (row["certified"], row["verdict"], row["error"]) == (
        int(payload["certified"]),
        payload["verdict"],
        None,
    )
    neighbours = json.loads(row["neighbours"])
    assert [n["fact_id"] for n in neighbours] == ["a", "b"]
    assert neighbours[0]["p_retain"] == pytest.approx(payload["p_retain_j"][0])
    assert row["created_at"][11:13].isdigit()


def test_table_has_no_duplicate_neighbours_column(tmp_path: Path) -> None:
    columns = [
        r[1] for r in _store(tmp_path)._conn.execute("PRAGMA table_info(afc_scores)")
    ]
    assert "duplicate_neighbours" not in columns


def test_each_kappa_keeps_its_own_row(tmp_path: Path) -> None:
    store = _store(tmp_path)
    eid = _experiment(store)
    _save(store, eid, _payload(None), None)
    _save(store, eid, _payload(0.8), 0.8)
    _save(store, eid, _payload(0.7), 0.7)
    assert [r["kappa"] for r in _rows(store)] == [None, 0.7, 0.8]


@pytest.mark.parametrize("kappa", [None, 0.8])
def test_same_settings_replace_the_row(tmp_path: Path, kappa: float | None) -> None:
    store = _store(tmp_path)
    eid = _experiment(store)
    _save(store, eid, _payload(kappa), kappa)
    changed = _payload(kappa)
    changed["verdict"] = "replaced"
    _save(store, eid, changed, kappa)
    rows = _rows(store)
    assert len(rows) == 1 and rows[0]["verdict"] == "replaced"


def test_untested_retention_is_stored_as_null(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _save(store, _experiment(store), _payload(None), None)
    row = _rows(store)[0]
    assert (
        row["kappa"],
        row["p_retain"],
        row["retain_ok"],
        row["weakest_neighbour"],
    ) == (
        None,
        None,
        None,
        None,
    )
    assert row["certified"] == 0 and row["lowest_retention_bound"] > 0


def test_below_guard_flag_is_stored(tmp_path: Path) -> None:
    store = _store(tmp_path)
    _save(store, _experiment(store), _payload(selected_below_guard=True), 0.8)
    assert _rows(store)[0]["selected_below_guard"] == 1


def test_error_payload_is_stored_and_not_certified(tmp_path: Path) -> None:
    store = _store(tmp_path)
    payload = certify_report(_report(), ["missing"], AFCSettings(0.05))
    _save(store, _experiment(store), payload, None)
    row = _rows(store)[0]
    assert "no scores" in row["error"]
    assert (row["certified"], row["verdict"], row["epoch"]) == (0, None, 2)


def test_rerun_clears_the_job_rows_only(tmp_path: Path) -> None:
    store = _store(tmp_path)
    first, second = _experiment(store, "first"), _experiment(store, "second")
    _save(store, first, _payload(), 0.8)
    _save(store, second, _payload(), 0.8)
    store.clear_job("first")
    assert [r["experiment_id"] for r in _rows(store)] == [second]


def test_row_needs_an_existing_experiment(tmp_path: Path) -> None:
    with pytest.raises(sqlite3.IntegrityError):
        _save(_store(tmp_path), "no-such-id", _payload(), 0.8)


def test_table_is_added_to_an_existing_ledger(tmp_path: Path) -> None:
    store = _store(tmp_path)
    eid = _experiment(store)
    store._conn.execute("DROP TABLE afc_scores")
    reopened = _store(tmp_path)
    _save(reopened, eid, _payload(), 0.8)
    assert len(_rows(reopened)) == 1
    assert reopened._conn.execute("SELECT count(*) FROM experiments").fetchone()[0] == 1


def _spec_root(tmp_path: Path) -> Path:
    facts = tmp_path / "spec" / "facts"
    facts.mkdir(parents=True)
    (facts / "target.json").write_text(
        json.dumps({"neighbourhoods": ["factverify:fact:a", "factverify:fact:b"]})
    )
    return tmp_path / "spec"


def test_training_run_saves_the_verdict(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = pytest.importorskip("src.train.run")
    store = _store(tmp_path)
    eid = _experiment(store)
    monkeypatch.setattr(run, "open_train_store", lambda: store)
    config = SimpleNamespace(afc_settings=AFCSettings(0.05, 0.8))
    run._export_selected_reports(
        _report(),
        config,
        tmp_path / "out",
        _spec_root(tmp_path),
        "target",
        experiment_id=eid,
    )
    assert (tmp_path / "out" / "afc.json").is_file()
    assert [(r["experiment_id"], r["kappa"]) for r in _rows(store)] == [(eid, 0.8)]


def test_database_error_does_not_fail_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = pytest.importorskip("src.train.run")

    def broken() -> None:
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(run, "open_train_store", broken)
    config = SimpleNamespace(afc_settings=AFCSettings(0.05))
    run._export_selected_reports(
        _report(),
        config,
        tmp_path / "out",
        _spec_root(tmp_path),
        "target",
        experiment_id="e",
    )
    assert (tmp_path / "out" / "afc.json").is_file()


def test_backfill_script_saves_rows(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "afc_certify", REPO / "scripts" / "afc_certify.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)

    store = _store(tmp_path)
    eid = _experiment(store, "prefix-run")
    run_dir = tmp_path / "train"
    run_dir.mkdir()
    (run_dir / "drop_retention.json").write_text(json.dumps(_report()))
    store.update_experiment(
        eid, status="succeeded", best_epoch=2, best_score=5.0, output_dir=str(run_dir)
    )
    config = tmp_path / "afc.yaml"
    config.write_text(
        yaml.safe_dump(
            {
                "afc": {"alpha": 0.05},
                "selection": {
                    "ledger": str(tmp_path / "ledger.sqlite"),
                    "job_prefix": "prefix-",
                    "spec_root": str(_spec_root(tmp_path)),
                },
            }
        )
    )
    assert cli.main(["--config", str(config)]) == 0
    assert [(r["experiment_id"], r["kappa"], r["epoch"]) for r in _rows(store)] == [
        (eid, None, 2)
    ]
    assert cli.main(["--config", str(config)]) == 0
    assert len(_rows(store)) == 1
