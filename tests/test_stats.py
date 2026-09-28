"""FV-STAT hooks. Study margins stay open; these fixtures close a row at a time."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from src.stats.bootstrap import coverage_simulation, draw_blocks
from src.stats.errors import StatsError
from src.stats.io import VerdictRow
from src.stats.multiplicity import adjust
from src.stats.report import EstimateTable, estimate
from src.stats.thresholds import select_thresholds
from tests.stats_ports import EvaluationView, MemoryStatsLedger

SPEC = Path("tests/fixtures/stats/spec")
DECISIONS = Path("tests/fixtures/stats/decisions")
CLOSED = DECISIONS / "closed.yaml"
OPEN = DECISIONS / "open.yaml"


def _ledger() -> MemoryStatsLedger:
    ledger = MemoryStatsLedger()
    ledger.checkpoints["ck"] = ledger.checkpoints.get("ck") or _checkpoint("ck")
    ledger.runs["run"] = EvaluationView("run", "calibration", "ck")
    return ledger


def _checkpoint(ledger_id: str, split: str = "calibration") -> object:
    from tests.stats_ports import CheckpointView

    return CheckpointView(ledger_id, split)


def _ready(extra: dict[str, str] | None = None) -> MemoryStatsLedger:
    ledger = MemoryStatsLedger()
    ids = {"ck": "calibration", "ck2": "calibration"}
    if extra:
        ids.update(extra)
    for ledger_id, split in ids.items():
        from tests.stats_ports import CheckpointView

        ledger.checkpoints[ledger_id] = CheckpointView(ledger_id, split)
    ledger.runs["run"] = EvaluationView("run", "calibration", "ck")
    ledger.runs["run2"] = EvaluationView("run2", "calibration", "ck2")
    return ledger


def _row(**overrides: object) -> VerdictRow:
    fields: dict[str, object] = {
        "row_id": "r1",
        "checkpoint_ledger_id": "ck",
        "evaluation_run_id": "run",
        "fact_id": "fact-1",
        "arm": "native",
        "verdict": "certified",
        "oracle_label": "genuine_reference",
        "control_family": "alpha",
        "split": "calibration",
        "prompt_id": "p1",
        "threshold_id": "t0",
        "rejected": False,
        "weight": None,
    }
    fields.update(overrides)
    return VerdictRow(**fields)  # type: ignore[arg-type]


def test_fv_stat_008_no_final_test_tuning() -> None:
    ledger = _ready()
    rows = (
        _row(row_id="a", threshold_id="t0", rejected=True),
        _row(row_id="b", threshold_id="t1", rejected=False, fact_id="fact-2"),
    )
    bounds = select_thresholds(rows, spec_root=SPEC, decisions=CLOSED, ledger=ledger)
    assert len(bounds) == 2
    by_id = {item.threshold_id: item for item in bounds}
    assert by_id["t0"].point == Decimal(1)
    assert by_id["t1"].point == Decimal(0)
    assert by_id["t1"].upper > 0
    mixed = rows + (_row(row_id="c", split="final_test", fact_id="fact-3"),)
    with pytest.raises(StatsError, match="final_test"):
        select_thresholds(mixed, spec_root=SPEC, decisions=OPEN, ledger=ledger)


def test_fv_stat_010_ledgered_only() -> None:
    ledger = _ready()
    loaded_rows = (_row(),)
    select_thresholds(loaded_rows, spec_root=SPEC, decisions=CLOSED, ledger=ledger)
    with pytest.raises(StatsError, match="missing-row"):
        select_thresholds(
            (_row(row_id="missing-row", checkpoint_ledger_id="absent"),),
            spec_root=SPEC,
            decisions=CLOSED,
            ledger=ledger,
        )


def test_fv_stat_001_block_resampling() -> None:
    rows = (
        _row(prompt_id="p1"),
        _row(row_id="r2", prompt_id="p2"),
        _row(row_id="r3", fact_id="fact-2", prompt_id="q1"),
    )
    drawn = draw_blocks(rows, design="nested", seed=7)
    prompts = {row.prompt_id for row in drawn if row.fact_id == "fact-1"}
    if any(row.fact_id == "fact-1" for row in drawn):
        assert prompts == {"p1", "p2"}
    ledger = _ready()
    with pytest.raises(StatsError, match="rows"):
        estimate(
            rows,
            spec_root=SPEC,
            decisions=CLOSED,
            ledger=ledger,
            seed=7,
            purpose="final_report",
            unit="row",
        )


def test_fv_stat_002_crossed() -> None:
    rows = (
        _row(fact_id="shared"),
        _row(
            row_id="other",
            checkpoint_ledger_id="ck2",
            evaluation_run_id="run2",
            fact_id="shared",
        ),
    )
    drawn = draw_blocks(rows, design="crossed", seed=3)
    assert drawn
    with pytest.raises(StatsError, match="design"):
        draw_blocks(rows, design="nested", seed=3)


def test_fv_stat_003_paired(tmp_path: Path) -> None:
    ledger = _ready()
    rows = (
        _row(arm="native", fact_id="f", prompt_id="p"),
        _row(row_id="b", arm="semantic", fact_id="f", prompt_id="p"),
    )
    text = CLOSED.read_text(encoding="utf-8")
    opened = text.replace(
        "{decision_id: D-06, status: closed, case_weights: uniform}",
        "{decision_id: D-06, status: open}",
    )
    path = tmp_path / "d06-open.yaml"
    path.write_text(opened, encoding="utf-8")
    first = estimate(
        rows,
        spec_root=SPEC,
        decisions=path,
        ledger=ledger,
        seed=1,
        purpose="final_report",
    )
    second = estimate(
        rows,
        spec_root=SPEC,
        decisions=path,
        ledger=ledger,
        seed=1,
        purpose="final_report",
    )
    assert first.seed == second.seed
    with pytest.raises(StatsError, match="D-06"):
        estimate(
            (
                _row(arm="native", fact_id="f", weight=2.0),
                _row(row_id="b", arm="semantic", fact_id="f", weight=2.0),
            ),
            spec_root=SPEC,
            decisions=path,
            ledger=ledger,
            seed=1,
            purpose="final_report",
        )
    with pytest.raises(StatsError, match="ck:missing"):
        estimate(
            (
                _row(arm="native", fact_id="f"),
                _row(row_id="b", arm="semantic", fact_id="missing"),
            ),
            spec_root=SPEC,
            decisions=CLOSED,
            ledger=ledger,
            seed=1,
            purpose="final_report",
        )


def test_fv_stat_004_per_family(tmp_path: Path) -> None:
    ledger = _ready()
    rows = (
        _row(control_family="alpha", fact_id="f1"),
        _row(row_id="b", control_family="beta", fact_id="f2", arm="native"),
    )
    table = estimate(
        rows,
        spec_root=SPEC,
        decisions=CLOSED,
        ledger=ledger,
        seed=1,
        purpose="final_report",
        families=("alpha", "beta", "gamma"),
    )
    assert isinstance(table, EstimateTable)
    names = [row.name for row in table.rows]
    assert names == ["alpha", "beta", "gamma", "overall"]
    empty = next(row for row in table.rows if row.name == "gamma")
    assert empty.n == 0
    assert empty.point is None
    opened = CLOSED.read_text(encoding="utf-8").replace(
        "{decision_id: D-10, status: closed, per_family: mean, overall: mean}",
        "{decision_id: D-10, status: open}",
    )
    path = tmp_path / "d10-open.yaml"
    path.write_text(opened, encoding="utf-8")
    with pytest.raises(StatsError, match="D-10"):
        estimate(
            rows,
            spec_root=SPEC,
            decisions=path,
            ledger=ledger,
            seed=1,
            purpose="final_report",
        )


def test_fv_stat_005_zero_count() -> None:
    ledger = _ready()
    rows = tuple(
        _row(row_id=f"r{index}", fact_id=f"f{index}", rejected=False)
        for index in range(20)
    )
    table = estimate(
        rows,
        spec_root=SPEC,
        decisions=CLOSED,
        ledger=ledger,
        seed=1,
        purpose="final_report",
    )
    expected = Decimal(1) - (Decimal("0.05") ** (Decimal(1) / Decimal(20)))
    assert table.estimates["fcr"]["point"] == Decimal(0)
    assert abs(table.interval["fcr"]["upper"] - expected) < Decimal("1e-12")
    assert table.interval["fcr"]["upper"] != 0


def test_fv_stat_006_multiplicity(tmp_path: Path) -> None:
    assert adjust([0.01, 0.04, 0.03], decisions=CLOSED) == (0.03, 0.06, 0.06)
    bh = _procedure(tmp_path, "bh")
    by = _procedure(tmp_path, "by")
    assert adjust([0.01, 0.04, 0.03], decisions=bh) == (0.03, 0.04, 0.04)
    adjusted = adjust([0.01, 0.04, 0.03], decisions=by)
    expected = (0.055, 0.0733333333, 0.0733333333)
    for left, right in zip(adjusted, expected, strict=True):
        assert abs(left - right) < 1e-9
    with pytest.raises(StatsError, match="D-08"):
        adjust([0.01], decisions=DECISIONS / "bad_procedure.yaml")


def test_fv_stat_007_deterministic() -> None:
    ledger = _ready()
    rows = (
        _row(fact_id="f1", rejected=True),
        _row(row_id="b", fact_id="f2", rejected=False),
    )
    first = estimate(
        rows,
        spec_root=SPEC,
        decisions=CLOSED,
        ledger=ledger,
        seed=7,
        purpose="final_report",
    )
    second = estimate(
        rows,
        spec_root=SPEC,
        decisions=CLOSED,
        ledger=ledger,
        seed=7,
        purpose="final_report",
    )
    assert first.estimates == second.estimates
    assert first.interval == second.interval
    assert first.seed == 7
    assert first.replicate_count == 19
    assert first.design == "nested"


def test_fv_stat_009_coverage_sim() -> None:
    with pytest.raises(StatsError, match="D-57"):
        coverage_simulation(
            Path("tests/fixtures/stats/sim.yaml"),
            spec_root=SPEC,
            decisions=OPEN,
        )
    report = coverage_simulation(
        Path("tests/fixtures/stats/sim.yaml"),
        spec_root=SPEC,
        decisions=CLOSED,
    )
    assert abs(report.block_coverage - 0.95) <= 0.10
    assert report.row_coverage < 0.95


def _procedure(tmp_path: Path, name: str) -> Path:
    loaded = yaml.safe_load(CLOSED.read_text(encoding="utf-8"))
    for item in loaded["decisions"]:
        if item["decision_id"] == "D-08":
            item["procedure"] = name
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.safe_dump(loaded), encoding="utf-8")
    return path
