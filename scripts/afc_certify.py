"""Run the AFC verdict on forgetter checkpoints already in the ledger.

Reads each run's ``drop_retention.json`` (the best checkpoint per
``save_best_as``), writes ``afc.json`` next to it and saves the verdict in the
ledger's ``afc_scores`` table. Needs no GPU and changes no other ledger table.
Runs without a selected checkpoint are not eligible.

    uv run python scripts/afc_certify.py --config PATH
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

import yaml

from src.ledger.train_store import (
    TrainStore,
    afc_record_from_payload,
    open_train_store,
)
from src.stats.afc import AFCSettings, certify_report, summary_line
from src.stats.errors import StatsError


def main(argv: list[str] | None = None) -> int:
    """Certify every eligible run. Exits 1 if any run could not be evaluated."""
    parser = argparse.ArgumentParser(prog="scripts/afc_certify.py")
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        config = _load_config(args.config)
    except StatsError as exc:
        print(f"invalid config: {exc.message}", file=sys.stderr)
        return 1

    runs = _eligible_runs(config["ledger"], config["job_prefix"])
    if not runs:
        print("no eligible runs", file=sys.stderr)
        return 1
    store = open_train_store(config["ledger"])
    failed = 0
    for run in runs:
        payload = _certify_run(run, config["spec_root"], config["settings"])
        _save(store, run, payload, config["settings"])
        failed += "error" in payload
        name = run["job_name"].removeprefix(config["job_prefix"])
        print(f"{name}\n    {summary_line(payload)}")
    print(
        f"\n{len(runs) - failed} of {len(runs)} runs evaluated "
        f"(alpha={config['settings'].alpha}, kappa={config['settings'].kappa})"
    )
    return 1 if failed else 0


def _load_config(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if (
        not isinstance(raw, dict)
        or "afc" not in raw
        or not isinstance(raw.get("selection"), dict)
    ):
        raise StatsError("config needs 'afc' and 'selection' sections")
    selection = raw["selection"]
    for key in ("ledger", "job_prefix", "spec_root"):
        if not isinstance(selection.get(key), str) or not selection[key]:
            raise StatsError(f"selection.{key} is required")
    return {
        "settings": AFCSettings.from_mapping(raw["afc"]),
        "ledger": Path(selection["ledger"]),
        "job_prefix": selection["job_prefix"],
        "spec_root": Path(selection["spec_root"]),
    }


def _eligible_runs(ledger: Path, job_prefix: str) -> list[dict[str, Any]]:
    connection = sqlite3.connect(f"file:{ledger}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT experiment_id, job_name, target_fact, output_dir, best_epoch "
            "FROM experiments "
            "WHERE role = 'forgetter' AND status = 'succeeded' ORDER BY rowid"
        ).fetchall()
    finally:
        connection.close()
    return [dict(row) for row in rows if row["job_name"].startswith(job_prefix)]


def _declared_neighbours(spec_root: Path, target_fact: str) -> list[str]:
    data = json.loads(
        (spec_root / "facts" / f"{target_fact}.json").read_text(encoding="utf-8")
    )
    return [entry.split(":")[-1] for entry in data.get("neighbourhoods") or []]


def _save(
    store: TrainStore,
    run: dict[str, Any],
    payload: dict[str, Any],
    settings: AFCSettings,
) -> None:
    """Save a verdict. A run whose report could not be read has no epoch to save."""
    if "selected_checkpoint_epoch" not in payload:
        return
    store.record_afc(
        afc_record_from_payload(
            run["experiment_id"], payload, alpha=settings.alpha, kappa=settings.kappa
        )
    )


def _certify_run(
    run: dict[str, Any], spec_root: Path, settings: AFCSettings
) -> dict[str, Any]:
    run_dir = Path(run["output_dir"])
    report_path = run_dir / "drop_retention.json"
    if not report_path.is_file():
        return {"error": f"missing {report_path}"}
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if report.get("selected_checkpoint_epoch") != run["best_epoch"]:
        return {
            "error": f"report epoch {report.get('selected_checkpoint_epoch')} "
            f"!= ledger best_epoch {run['best_epoch']}"
        }
    payload = certify_report(
        report, _declared_neighbours(spec_root, run["target_fact"]), settings
    )
    (run_dir / "afc.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return payload


if __name__ == "__main__":
    sys.exit(main())
