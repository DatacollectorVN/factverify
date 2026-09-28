"""FV-CTRL-011 through FV-CTRL-017. Scripted ports, no weights."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from src.controls.errors import ControlError
from src.controls.match import (
    PilotInput,
    compare_matches,
    load_match_record,
    match_control,
    pilot_inputs,
    reject_dropped,
)
from tests.match_ports import (
    LedgerRow,
    MemoryMatchLedger,
    ProbeRead,
    ScriptedMatchBehavior,
    ScriptedMeasurement,
)

FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "controls" / "match"
SPEC = FIX / "spec"


class _Boom:
    """Fails the test if matching measures before it should refuse."""

    def direct_qa_accuracy(
        self,
        system_id: str,
        fact_id: str,
        probe_ids: tuple[str, ...],
        severity: str | None,
    ) -> object:
        raise AssertionError("measured")

    def dimension_value(
        self, system_id: str, fact_id: str, name: str, severity: str
    ) -> float:
        raise AssertionError("dimension")


class _ExtraProbe:
    """Returns a probe id that is not in the manifest."""

    def direct_qa_accuracy(
        self,
        system_id: str,
        fact_id: str,
        probe_ids: tuple[str, ...],
        severity: str | None,
    ) -> ScriptedMeasurement:
        return ScriptedMeasurement(0.6, (ProbeRead("p9", system_id, "x"),))

    def dimension_value(
        self, system_id: str, fact_id: str, name: str, severity: str
    ) -> float:
        return 0.0


def _case(tmp_path: Path, name: str = "base.yaml", **overrides: object) -> Path:
    raw = yaml.safe_load((FIX / "configs" / name).read_text(encoding="utf-8"))
    raw.update(overrides)
    raw["decisions"] = str(FIX / "decisions" / Path(str(raw["decisions"])).name)
    raw["probes"] = str(FIX / "probes" / Path(str(raw["probes"])).name)
    raw["output_dir"] = str(tmp_path / "out")
    dest = tmp_path / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(yaml.safe_dump(raw), encoding="utf-8")
    return dest


def _ledger(**replaced: LedgerRow) -> MemoryMatchLedger:
    rows = {
        "ref-a": LedgerRow("ref-a", "reference", "fact-1", "calibration"),
        "ref-b": LedgerRow("ref-b", "reference", "fact-1", "calibration"),
        "ref-c": LedgerRow("ref-c", "reference", "fact-1", "calibration"),
        "ctrl-1": LedgerRow("ctrl-1", "control", "fact-1", "calibration"),
    }
    rows.update(replaced)
    return MemoryMatchLedger(rows)


def _behavior(
    severities: dict[str, float] | None = None,
    dimensions: dict[str, float] | None = None,
    references: dict[str, float] | None = None,
) -> ScriptedMatchBehavior:
    return ScriptedMatchBehavior(
        references=references or {"ref-a": 0.4, "ref-b": 0.8, "ref-c": 0.6},
        by_severity=severities or {"s0": 0.0, "s1": 0.6, "s2": 1.0},
        dimensions=dimensions,
    )


def _run(
    tmp_path: Path,
    name: str = "base.yaml",
    behavior: ScriptedMatchBehavior | _Boom | _ExtraProbe | None = None,
    ledger: MemoryMatchLedger | None = None,
    **overrides: object,
) -> object:
    return match_control(
        _case(tmp_path, name, **overrides),
        spec_root=SPEC,
        ledger=ledger or _ledger(),
        behavior=behavior or _behavior(),
    )


def _absent(tmp_path: Path) -> None:
    assert not (tmp_path / "out" / "match.json").exists()


def test_fv_ctrl_011_target_from_refs(tmp_path: Path) -> None:
    record = _run(tmp_path)
    written = json.loads((tmp_path / "out" / "match.json").read_text(encoding="utf-8"))
    band = written["target_band"]
    assert band["summary"] == "min_max"
    assert band["low"] == 0.4
    assert band["high"] == 0.8
    assert band["center"] == 0.6
    assert written["reference_ledger_ids"] == ["ref-a", "ref-b"]
    assert written["reference_accuracies"] == [0.4, 0.8]
    assert record.target_band.summary == "min_max"

    three = _run(tmp_path / "three", "block1_three.yaml")
    three_written = json.loads(three.path.read_text(encoding="utf-8"))
    assert three_written["reference_ledger_ids"] == ["ref-a", "ref-b", "ref-c"]
    assert three_written["target_band"]["summary"] == "min_max"

    mean = _run(tmp_path / "mean", decisions="d54_mean.yaml")
    mean_band = json.loads(mean.path.read_text(encoding="utf-8"))["target_band"]
    assert mean_band["center"] == 0.6
    assert mean_band["low"] == 0.5
    assert mean_band["high"] == 0.7

    for name in ("one_ref.yaml", "block1_two.yaml", "bad_block.yaml", "target.yaml"):
        folder = tmp_path / name
        with pytest.raises(ControlError):
            _run(folder, name, behavior=_Boom())
        _absent(folder)
    for decisions in ("d54_gap_only.yaml", "open.yaml"):
        folder = tmp_path / decisions
        with pytest.raises(ControlError, match="D-54"):
            _run(folder, decisions=decisions, behavior=_Boom())
        _absent(folder)
    with pytest.raises(ControlError):
        _run(tmp_path / "empty", "empty_search.yaml", behavior=_Boom())
    with pytest.raises(ControlError, match="split"):
        _run(tmp_path / "final-config", "final_split.yaml", behavior=_Boom())
    with pytest.raises(ControlError, match="ref-a"):
        _run(
            tmp_path / "role",
            ledger=_ledger(
                **{"ref-a": LedgerRow("ref-a", "finetuned", "fact-1", "calibration")}
            ),
            behavior=_Boom(),
        )
    with pytest.raises(ControlError, match="ref-a"):
        _run(
            tmp_path / "fact",
            ledger=_ledger(
                **{"ref-a": LedgerRow("ref-a", "reference", "fact-2", "calibration")}
            ),
            behavior=_Boom(),
        )
    with pytest.raises(ControlError, match="ref-a"):
        _run(
            tmp_path / "held",
            ledger=_ledger(
                **{"ref-a": LedgerRow("ref-a", "reference", "fact-1", "final_test")}
            ),
            behavior=_Boom(),
        )
    with pytest.raises(ControlError, match="reference_ledger_ids"):
        _run(
            tmp_path / "dup",
            reference_ledger_ids=["ref-a", "ref-a"],
            behavior=_Boom(),
        )


def test_fv_ctrl_012_tolerance(tmp_path: Path) -> None:
    matched = _run(tmp_path / "in")
    assert matched.status == "matched"
    assert matched.selected_severity == "s1"
    assert matched.achieved_value == 0.6

    outside = _run(
        tmp_path / "out-band",
        behavior=_behavior({"s0": 0.0, "s1": 0.1, "s2": 0.2}),
    )
    assert outside.status == "unmatched"
    assert outside.selected_severity == "s2"
    assert outside.achieved_value == 0.2

    exclusive = _run(
        tmp_path / "edge",
        decisions="d54_exclusive.yaml",
        severity_search=["edge"],
        behavior=_behavior({"edge": 0.4}),
    )
    assert exclusive.status == "unmatched"
    assert exclusive.achieved_value == 0.4

    with pytest.raises(ControlError, match="D-54"):
        _run(tmp_path / "rule", decisions="d54_bad_rule.yaml", behavior=_Boom())

    closest = _run(
        tmp_path / "closest",
        behavior=_behavior({"s0": 0.4, "s1": 0.6, "s2": 1.0}),
    )
    assert closest.selected_severity == "s1"
    assert closest.status == "matched"


def test_fv_ctrl_013_probe_isolation(tmp_path: Path) -> None:
    behavior = _behavior()
    _run(tmp_path / "ok", behavior=behavior)
    written = json.loads(
        (tmp_path / "ok" / "out" / "match.json").read_text(encoding="utf-8")
    )
    pairs = {
        (item["probe_id"], item["system_id"], item["severity"])
        for item in written["reads"]
    }
    expected = set()
    for probe in ("p1", "p2"):
        for ref in ("ref-a", "ref-b"):
            expected.add((probe, ref, None))
        for severity in ("s0", "s1", "s2"):
            expected.add((probe, "ctrl-1", severity))
    assert pairs == expected
    assert {item["output"] for item in written["reads"]} == {"out-p1", "out-p2"}
    for key in ("verdict", "evaluator_score", "evaluator_output", "fcr", "frr"):
        assert key not in written

    for name, token in (
        ("calibration_group.yaml", "direct_calibration"),
        ("final_split.yaml", "split"),
        ("not_direct.yaml", "kind"),
        ("empty.yaml", "probes"),
    ):
        folder = tmp_path / name
        with pytest.raises(ControlError, match=token):
            _run(folder, probes=name, behavior=_Boom())
        _absent(folder)
    folder = tmp_path / "d58"
    with pytest.raises(ControlError, match="D-58"):
        _run(folder, decisions="d58_open.yaml", behavior=_Boom())
    _absent(folder)
    with pytest.raises(ControlError, match="budget"):
        _run(tmp_path / "budget", "budget.yaml", behavior=_Boom())
    source = Path("src/controls/match.py").read_text(encoding="utf-8")
    assert "src.eval.gateway" not in source
    assert "src.eval.budget" not in source
    with pytest.raises(ControlError, match="p9"):
        _run(tmp_path / "p9", behavior=_ExtraProbe())
    _absent(tmp_path / "p9")


def test_fv_ctrl_014_unmatched_reported(tmp_path: Path) -> None:
    record = _run(
        tmp_path,
        behavior=_behavior({"s0": 0.0, "s1": 0.1, "s2": 0.2}),
    )
    rows = pilot_inputs([record])
    assert rows[0].family == "refusal"
    assert rows[0].best_value == 0.2
    assert rows[0].target_band.low == 0.4
    assert rows[0].target_band.high == 0.8
    assert rows[0].target_band.summary == "min_max"
    reject_dropped([record], rows)
    with pytest.raises(ControlError, match="unmatched"):
        reject_dropped([record], [])
    changed = PilotInput(
        record.control_ledger_id,
        record.family,
        record.status,
        0.0,
        record.target_band,
    )
    with pytest.raises(ControlError, match="unmatched"):
        reject_dropped([record], [changed])
    written = json.loads(record.path.read_text(encoding="utf-8"))
    assert written["target_band"]["tolerance"] == "0.0"


def test_fv_ctrl_016_trajectory(tmp_path: Path) -> None:
    behavior = _behavior({"s0": 0.0, "s1": 0.1, "s2": 0.2})
    record = _run(tmp_path, behavior=behavior)
    written = json.loads(record.path.read_text(encoding="utf-8"))
    assert written["trajectory"] == [
        {"severity": "s0", "accuracy": 0.0},
        {"severity": "s1", "accuracy": 0.1},
        {"severity": "s2", "accuracy": 0.2},
    ]
    assert written["wall_clock_seconds"] >= 0
    assert written["gpu_hours"] >= 0
    assert written["peak_memory_bytes"] >= 0
    payload = json.loads(record.path.read_text(encoding="utf-8"))
    del payload["trajectory"]
    record.path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlError, match="trajectory"):
        load_match_record(record.path)
    assert [severity for system, severity in behavior.calls if system == "ctrl-1"] == [
        "s0",
        "s1",
        "s2",
    ]
    with pytest.raises(ControlError, match="budget"):
        _run(tmp_path / "budget", "budget.yaml", behavior=_Boom())
    source = Path("src/controls/match.py").read_text(encoding="utf-8")
    assert "src.eval.gateway" not in source
    assert "src.eval.budget" not in source


def test_fv_ctrl_017_reproducible(tmp_path: Path) -> None:
    decisions = FIX / "decisions" / "d53_exact.yaml"
    left = _run(tmp_path / "a", decisions="d53_exact.yaml")
    right = _run(tmp_path / "b", decisions="d53_exact.yaml")
    compare_matches(left, right, decisions)
    assert left.selected_severity == "s1"
    assert left.status == "matched"
    assert right.selected_severity == "s1"
    assert left.seed == 7
    assert right.seed == 7
    with pytest.raises(ControlError, match="D-53"):
        compare_matches(left, right, FIX / "decisions" / "open.yaml")
    assert left.path.is_file()
    assert right.path.is_file()
    with pytest.raises(ControlError, match="D-53"):
        compare_matches(left, right, FIX / "decisions" / "d53_nonzero.yaml")
    other = _run(tmp_path / "c", decisions="d53_exact.yaml", seed=8)
    assert other.seed == 8
    assert other.config_hash != left.config_hash
    behavior = _behavior()
    _run(tmp_path / "order", behavior=behavior, decisions="d53_exact.yaml", seed=8)
    assert [severity for system, severity in behavior.calls if system == "ctrl-1"] == [
        "s0",
        "s1",
        "s2",
    ]


def test_fv_ctrl_015_hard_dimensions(tmp_path: Path) -> None:
    passed = _run(
        tmp_path / "pass",
        "hard.yaml",
        behavior=_behavior(dimensions={"refusal_rate": 0.0, "fluency": 0.0}),
    )
    written = json.loads(passed.path.read_text(encoding="utf-8"))
    assert passed.status == "matched"
    assert written["hard_check"] == "passed"
    assert [item["name"] for item in written["dimensions"]] == [
        "refusal_rate",
        "fluency",
    ]

    missed = _run(
        tmp_path / "miss",
        "hard.yaml",
        behavior=_behavior(dimensions={"refusal_rate": 0.0, "fluency": 0.2}),
    )
    missed_written = json.loads(missed.path.read_text(encoding="utf-8"))
    assert missed.status == "unmatched"
    assert missed_written["failed_dimension"] == "fluency"
    assert len(missed_written["trajectory"]) == 3

    plain = _behavior()
    plain_record = _run(tmp_path / "plain", decisions="d59_two.yaml", behavior=plain)
    assert plain_record.hard_check == "not_required"
    assert plain.dimension_calls == []

    with pytest.raises(ControlError, match="D-59"):
        _run(
            tmp_path / "open",
            "hard.yaml",
            decisions="d54_minmax.yaml",
            behavior=_Boom(),
        )
    _absent(tmp_path / "open")

    waived = _behavior()
    waived_record = _run(
        tmp_path / "waiver", "hard.yaml", decisions="d59_waiver.yaml", behavior=waived
    )
    waived_written = json.loads(waived_record.path.read_text(encoding="utf-8"))
    assert waived_written["hard_check"] == "waived"
    assert waived_written["waiver_reason"] == "pilot-waiver"
    assert waived.dimension_calls == []

    with pytest.raises(ControlError, match="D-59"):
        _run(
            tmp_path / "both",
            "hard.yaml",
            decisions="d59_closed_waiver.yaml",
            behavior=_Boom(),
        )
    _absent(tmp_path / "both")
