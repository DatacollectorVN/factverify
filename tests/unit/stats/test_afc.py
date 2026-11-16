"""AFC verdict (docs/p_forget_p_retain_spec.md)."""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest

from src.stats.afc import (
    BOTH_FAILED,
    CERTIFIED,
    COLLATERAL_DAMAGE,
    DEGENERATE_CONTROL,
    FAMILIES,
    FORGET_SHOWN_RETAIN_UNTESTED,
    NOT_FORGOTTEN,
    NOT_FORGOTTEN_RETAIN_UNTESTED,
    AFCSettings,
    afc,
    afc_from_report,
    certify_report,
    crawford_howell,
    result_to_json,
    summary_line,
)
from src.stats.errors import StatsError

ALPHA, KAPPA = 0.05, 0.8
REPO = Path(__file__).resolve().parents[3]
_ALIAS_CONFIGS = REPO / "config/jobs/block0/pythia-410m-alias-ablation/alias-aware"
_Z = np.array([-1.2, -0.6, 0.0, 0.6, 1.2])
_Z = _Z / _Z.std(ddof=1)


def _cells(retention: float, statistic: float) -> np.ndarray:
    """Five log-retentions whose mean and one-sample T against ln kappa are given."""
    mean = math.log(retention)
    se = (mean - math.log(KAPPA)) / statistic
    return mean + se * math.sqrt(5) * _Z


def _inputs(rows: Any) -> tuple[np.ndarray, np.ndarray]:
    y = np.array(rows, dtype=float)
    return -y, np.exp(y)


GOOD = [
    _cells(0.959, 12.3),
    _cells(0.948, 13.1),
    _cells(0.946, 12.0),
    _cells(0.951, 12.2),
]
DAMAGED = GOOD[:3] + [_cells(0.722, -1.76)]
TARGET_GOOD = dict(zip(FAMILIES, [2.5, 2.3, 2.9, 2.6, 0.833]))
TARGET_LEAKY = dict(zip(FAMILIES, [2.5, 0.0588, 2.9, 2.6, 2.4]))


def test_spec_forget_vectors() -> None:
    statistic, p = crawford_howell(0.833, 0.050, 0.029, 20)
    assert statistic == pytest.approx(26.2, abs=0.3)  # spec's m and s are rounded
    assert 0.5e-16 < p < 2e-16
    statistic, p = crawford_howell(0.0588, 0.050, 0.029, 20)
    assert statistic == pytest.approx(0.29, abs=0.01)
    assert p == pytest.approx(0.389, abs=0.01)


def test_spec_retain_good_vector() -> None:
    d, r = _inputs(GOOD)
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)
    assert result.T_retain == pytest.approx([12.3, 13.1, 12.0, 12.2], abs=1e-9)
    assert result.p_retain == pytest.approx(1.38e-4, abs=1e-6)
    assert result.weakest_neighbour == 2
    assert result.mean_retention_j == pytest.approx([0.959, 0.948, 0.946, 0.951])


def test_spec_retain_collateral_vector() -> None:
    d, r = _inputs(DAMAGED)
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)
    assert result.T_retain[3] == pytest.approx(-1.76)
    assert result.p_retain == pytest.approx(0.924, abs=0.002)
    assert result.weakest_neighbour == 3


def test_reject_zone_uses_df_four() -> None:
    d, r = _inputs([_cells(0.95, 2.133), _cells(0.95, 2.131)])
    p = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA).p_retain_j
    assert p[0] <= ALPHA < p[1]


@pytest.mark.parametrize(
    "target, rows, verdict, forget_ok, retain_ok",
    [
        (TARGET_GOOD, GOOD, CERTIFIED, True, True),
        (TARGET_LEAKY, GOOD, NOT_FORGOTTEN, False, True),
        (TARGET_GOOD, DAMAGED, COLLATERAL_DAMAGE, True, False),
        (TARGET_LEAKY, DAMAGED, BOTH_FAILED, False, False),
    ],
)
def test_verdict_table(
    target: Any, rows: Any, verdict: Any, forget_ok: Any, retain_ok: Any
) -> None:
    d, r = _inputs(rows)
    result = afc(target, d, r, alpha=ALPHA, kappa=KAPPA)
    assert (result.verdict, result.forget_ok, result.retain_ok) == (
        verdict,
        forget_ok,
        retain_ok,
    )
    assert result.certified is (verdict == CERTIFIED)
    assert result.p_afc == max(result.p_forget, result.p_retain)


@pytest.mark.parametrize(
    "target, verdict",
    [
        (TARGET_GOOD, FORGET_SHOWN_RETAIN_UNTESTED),
        (TARGET_LEAKY, NOT_FORGOTTEN_RETAIN_UNTESTED),
    ],
)
def test_without_kappa_retention_is_untested_and_never_certified(
    target: Any, verdict: Any
) -> None:
    d, r = _inputs(GOOD)
    result = afc(target, d, r, alpha=ALPHA)
    assert (
        result.verdict == verdict
        and result.certified is False
        and result.retain_ok is None
    )
    assert (
        result.p_retain is None
        and result.p_retain_j is None
        and result.T_retain is None
    )
    assert result.p_afc == result.p_forget
    assert len(result.retain_lower_bound_j) == 4


def test_lowest_family_is_the_candidate() -> None:
    d, r = _inputs(GOOD)
    result = afc(TARGET_LEAKY, d, r, alpha=ALPHA)
    assert result.t == 0.0588 and result.weakest_family_target == "inverse"


def test_control_statistics_pool_every_cell() -> None:
    d, r = _inputs(GOOD)
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA)
    assert result.m == pytest.approx(d.mean())
    assert result.s == pytest.approx(d.ravel().std(ddof=1))
    assert result.T_forget == pytest.approx(
        (0.833 - d.mean()) / (d.ravel().std(ddof=1) * math.sqrt(1 + 1 / 20))
    )


def test_worked_mean_from_spec() -> None:
    y = np.array([-0.05, -0.03, -0.0499, -0.04, -0.04])
    assert y.sum() == pytest.approx(-0.2099)
    d, r = _inputs([y, GOOD[1]])
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA)
    assert result.y_bar_j[0] == pytest.approx(-0.2099 / 5)
    assert result.mean_retention_j[0] == pytest.approx(0.959, abs=0.001)


@pytest.mark.parametrize("j", [1, 2, 3, 5, 10])
def test_degrees_of_freedom_are_derived_from_j(j: Any) -> None:
    d, r = _inputs([_cells(0.95 - i * 0.001, 8.0) for i in range(j)])
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)
    assert (result.J, result.n, result.df_forget, result.df_retain) == (
        j,
        j * 5,
        j * 5 - 1,
        4,
    )
    assert len(result.p_retain_j) == j


def test_degenerate_control_is_flagged_not_divided() -> None:
    d, r = _inputs([[-0.1] * 5, [-0.1] * 5])
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)
    assert result.s == 0 and math.isnan(result.p_forget) and math.isnan(result.p_afc)
    assert "degenerate_control" in result.flags
    assert (result.verdict, result.certified) == (DEGENERATE_CONTROL, False)
    payload = result_to_json(result)
    assert payload["p_forget"] is None and payload["p_afc"] is None
    json.dumps(payload, allow_nan=False)


def test_zero_se_branches() -> None:
    d, r = _inputs([[-0.01] * 5, [-0.5] * 5])
    result = afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)
    assert result.se_j == [0.0, 0.0]
    assert result.p_retain_j == [0.0, 1.0]
    assert result.T_retain == [math.inf, -math.inf]
    assert {"zero_se_neighbour_0", "zero_se_neighbour_1"} <= set(result.flags)
    json.dumps(result_to_json(result), allow_nan=False)


def test_extreme_statistic_does_not_underflow_to_zero() -> None:
    d, r = _inputs(GOOD)
    target = dict(TARGET_GOOD, verify=1.5)
    assert 0 < afc(target, d, r, alpha=ALPHA).p_forget < 1e-16


def test_larger_candidate_never_raises_p_forget() -> None:
    d, r = _inputs(GOOD)
    grid = np.linspace(-1, 3, 60)
    p = [
        afc(
            dict(
                TARGET_GOOD,
                verify=float(v),
                inverse=5.0,
                direct=5.0,
                cloze=5.0,
                para=5.0,
            ),
            d,
            r,
            alpha=ALPHA,
        ).p_forget
        for v in grid
    ]
    assert all(b <= a for a, b in zip(p, p[1:]))


def test_lower_bound_is_the_largest_kappa_that_passes() -> None:
    d, r = _inputs(GOOD + [_cells(0.85, 3.0)])
    bounds = afc(TARGET_GOOD, d, r, alpha=ALPHA).retain_lower_bound_j
    for j, bound in enumerate(bounds):
        below = afc(
            TARGET_GOOD, d, r, alpha=ALPHA, kappa=bound * (1 - 1e-6)
        ).p_retain_j[j]
        above = afc(
            TARGET_GOOD, d, r, alpha=ALPHA, kappa=min(bound * (1 + 1e-6), 0.999999)
        ).p_retain_j[j]
        assert below <= ALPHA < above


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda d, r: (d[:, :4], r[:, :4]), "shape"),
        (lambda d, r: (d[:0], r[:0]), "shape"),
        (lambda d, r: (d, r[:-1]), "same shape"),
        (lambda d, r: (np.where(d == d[0, 0], np.nan, d), r), "d_nb must be finite"),
        (lambda d, r: (d, np.where(r == r[0, 0], 0.0, r)), "positive"),
        (lambda d, r: (d, np.where(r == r[0, 0], np.inf, r)), "positive"),
        (lambda d, r: (d + 0.01, r), "ln r must equal -d"),
    ],
)
def test_invalid_scores_are_errors_not_p_values(change: Any, message: Any) -> None:
    d, r = change(*_inputs(GOOD))
    with pytest.raises(StatsError, match=message):
        afc(TARGET_GOOD, d, r, alpha=ALPHA, kappa=KAPPA)


@pytest.mark.parametrize(
    "alpha, kappa", [(0, 0.8), (1, 0.8), (0.05, 0), (0.05, 1), (0.05, 1.2)]
)
def test_parameter_bounds(alpha: Any, kappa: Any) -> None:
    d, r = _inputs(GOOD)
    with pytest.raises(StatsError):
        afc(TARGET_GOOD, d, r, alpha=alpha, kappa=kappa)


def test_target_needs_every_family() -> None:
    d, r = _inputs(GOOD)
    with pytest.raises(StatsError, match="d_target"):
        afc({"direct": 1.0}, d, r, alpha=ALPHA)


def test_family_order_matches_the_scorer() -> None:
    pytest.importorskip("torch")
    from src.train.data import CANONICAL_FAMILIES

    assert FAMILIES == CANONICAL_FAMILIES


def _reference_module() -> Any:
    path = REPO / "scripts" / "hanoi_capital_example.py"
    spec = importlib.util.spec_from_file_location("hanoi_capital_example", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_agrees_with_independent_pure_python_reference() -> None:
    ref = _reference_module()
    cases = [case[2] for case in ref.CASES.values()] + [ref.BROAD]
    assert len(cases) >= 2
    for forgetter in cases:
        expected = ref.evaluate(forgetter)
        d_nb = np.array([expected["d_g"][g] for g in ("g1", "g2", "g3", "g4")])
        result = afc(
            dict(zip(FAMILIES, expected["d_f"])),
            d_nb,
            np.exp(-d_nb),
            alpha=ref.ALPHA,
            kappa=ref.KAPPA,
        )
        assert result.T_forget == pytest.approx(expected["T_forget"], rel=1e-9)
        assert result.p_forget == pytest.approx(expected["p_forget"], rel=1e-6)
        assert result.p_retain == pytest.approx(expected["p_retain"], rel=1e-6)
        assert result.p_afc == pytest.approx(expected["p_afc"], rel=1e-6)


def _fact(fact_id: str, role: str, drops: Any) -> dict[str, Any]:
    return {
        "fact_id": fact_id,
        "fact_role": role,
        "families": {
            f: {
                "drop": float(v),
                "log_retention": -float(v),
                "retention": math.exp(-float(v)) if float(v) < 700 else 0.0,
            }
            for f, v in zip(FAMILIES, drops)
        },
    }


def _report(neighbours: Any) -> dict[str, Any]:
    facts = [_fact("target", "target", list(TARGET_GOOD.values()))]
    facts += [_fact(name, "neighbour", -row) for name, row in neighbours]
    return {
        "job_name": "job",
        "seed": 3,
        "metric_version": "m",
        "selected_checkpoint_epoch": 2,
        "facts": facts,
    }


SETTINGS = AFCSettings(alpha=ALPHA)


def test_report_uses_the_declared_neighbours_only() -> None:
    report = _report([("a", GOOD[0]), ("b", GOOD[1]), ("extra", GOOD[2])])
    payload = afc_from_report(report, ["b", "a"], SETTINGS)
    assert payload["J"] == 2 and payload["n"] == 10
    assert payload["neighbours"] == ["b", "a"] and payload["ignored_neighbours"] == [
        "extra"
    ]
    assert payload["inputs"]["d_nb"][0] == pytest.approx((-GOOD[1]).tolist())
    assert (
        payload["selected_checkpoint_epoch"] == 2 and payload["target_fact"] == "target"
    )
    json.dumps(payload, allow_nan=False)


def test_missing_declared_neighbour_is_an_error() -> None:
    with pytest.raises(StatsError, match="no scores: b"):
        afc_from_report(_report([("a", GOOD[0])]), ["a", "b"], SETTINGS)


def test_missing_family_cell_is_an_error() -> None:
    report = _report([("a", GOOD[0])])
    del report["facts"][1]["families"]["verify"]
    with pytest.raises(StatsError, match="family verify"):
        afc_from_report(report, ["a"], SETTINGS)


def test_no_declared_neighbours_is_an_error() -> None:
    with pytest.raises(StatsError, match="declares no neighbours"):
        afc_from_report(_report([("a", GOOD[0])]), [], SETTINGS)


def test_identical_neighbours_are_kept_and_listed() -> None:
    payload = afc_from_report(
        _report([("a", GOOD[0]), ("b", GOOD[0]), ("c", GOOD[1])]),
        ["a", "b", "c"],
        SETTINGS,
    )
    assert payload["J"] == 3
    assert payload["duplicate_neighbours"] == [["a", "b"]]


def test_certify_report_turns_rejection_into_error_payload() -> None:
    payload = certify_report(_report([("a", GOOD[0])]), ["missing"], SETTINGS)
    assert "no scores" in payload["error"] and payload["selected_checkpoint_epoch"] == 2


@pytest.mark.parametrize(
    "section, message",
    [
        ("x", "mapping"),
        ({}, "alpha is required"),
        ({"alpha": True}, "number"),
        ({"alpha": 2}, "alpha"),
        ({"alpha": 0.05, "kappa": 1.5}, "kappa"),
        ({"alpha": 0.05, "delta": 0.2}, "unknown"),
    ],
)
def test_settings_validation(section: Any, message: Any) -> None:
    with pytest.raises(StatsError, match=message):
        AFCSettings.from_mapping(section)


def test_settings_kappa_is_optional() -> None:
    assert AFCSettings.from_mapping({"alpha": 0.05}) == AFCSettings(0.05, None)
    assert AFCSettings.from_mapping({"alpha": 0.05, "kappa": 0.8}).kappa == 0.8


def _job_mapping() -> dict[str, Any]:
    import yaml

    path = (
        _ALIAS_CONFIGS
        / "rmu-tune"
        / "forgetter-rmutune-L7-c300-rc100-lr5e-5-nosinks.yaml"
    )
    return yaml.safe_load(path.read_text())


def test_job_config_afc_section_is_optional_and_validated() -> None:
    pytest.importorskip("torch")
    from src.train.config import GroupedJobConfig, _validate_grouped
    from src.train.errors import FactVerifyHarnessError

    mapping = _job_mapping()
    _validate_grouped(mapping, "job")
    assert GroupedJobConfig(raw=mapping, path=Path("job.yaml")).afc_settings is None

    mapping["afc"] = {"alpha": 0.05}
    _validate_grouped(mapping, "job")
    assert GroupedJobConfig(
        raw=mapping, path=Path("job.yaml")
    ).afc_settings == AFCSettings(0.05, None)

    mapping["afc"] = {"alpha": 0.05, "kappa": 7}
    with pytest.raises(FactVerifyHarnessError, match="kappa"):
        _validate_grouped(mapping, "job")

    import yaml

    learner = yaml.safe_load((_ALIAS_CONFIGS / "learner.yaml").read_text())
    _validate_grouped(learner, "job")
    learner["afc"] = {"alpha": 0.05}
    with pytest.raises(FactVerifyHarnessError, match="requires role forgetter"):
        _validate_grouped(learner, "job")


def _spec_root(tmp_path: Path, neighbours: Any) -> Path:
    facts = tmp_path / "spec" / "facts"
    facts.mkdir(parents=True)
    (facts / "target.json").write_text(
        json.dumps(
            {"neighbourhoods": [f"factverify:fact:{name}" for name in neighbours]}
        )
    )
    return tmp_path / "spec"


def test_run_writes_afc_next_to_the_report(tmp_path: Path) -> None:
    run = pytest.importorskip("src.train.run")
    out = tmp_path / "out"
    config = SimpleNamespace(afc_settings=AFCSettings(ALPHA, KAPPA))
    report = _report([("a", GOOD[0]), ("b", GOOD[1])])
    run._export_selected_reports(
        report, config, out, _spec_root(tmp_path, ["a", "b"]), "target"
    )
    payload = json.loads((out / "afc.json").read_text())
    assert json.loads((out / "drop_retention.json").read_text()) == report
    assert payload["neighbours"] == ["a", "b"] and payload["J"] == 2
    assert payload["verdict"] == CERTIFIED


def test_run_without_afc_section_writes_only_the_report(tmp_path: Path) -> None:
    run = pytest.importorskip("src.train.run")
    out = tmp_path / "out"
    run._export_selected_reports(
        _report([("a", GOOD[0])]),
        SimpleNamespace(afc_settings=None),
        out,
        _spec_root(tmp_path, ["a"]),
        "target",
    )
    assert (out / "drop_retention.json").is_file() and not (out / "afc.json").exists()


@pytest.mark.parametrize("report", [None, {}])
def test_guard_stopped_run_gets_no_afc(tmp_path: Path, report: Any) -> None:
    run = pytest.importorskip("src.train.run")
    out = tmp_path / "out"
    run._export_selected_reports(
        report,
        SimpleNamespace(afc_settings=AFCSettings(ALPHA)),
        out,
        _spec_root(tmp_path, ["a"]),
        "target",
    )
    assert not out.exists()


def test_rejected_input_does_not_fail_the_finished_run(tmp_path: Path) -> None:
    run = pytest.importorskip("src.train.run")
    out = tmp_path / "out"
    run._export_selected_reports(
        _report([("a", GOOD[0])]),
        SimpleNamespace(afc_settings=AFCSettings(ALPHA)),
        out,
        _spec_root(tmp_path, ["missing"]),
        "target",
    )
    assert "no scores" in json.loads((out / "afc.json").read_text())["error"]


def test_cli_reads_neighbours_like_the_training_run(tmp_path: Path) -> None:
    run = pytest.importorskip("src.train.run")
    spec = importlib.util.spec_from_file_location(
        "afc_certify", REPO / "scripts" / "afc_certify.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    root = _spec_root(tmp_path, ["a", "b", "c"])
    assert cli._declared_neighbours(root, "target") == run._load_neighbourhood_ids(
        root, "target"
    )


def _load_cli() -> Any:
    spec = importlib.util.spec_from_file_location(
        "afc_certify", REPO / "scripts" / "afc_certify.py"
    )
    cli = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cli)
    return cli


def _cli_run(tmp_path: Path, best_epoch: int = 2) -> dict[str, Any]:
    run_dir = tmp_path / "train" / "job" / "target"
    run_dir.mkdir(parents=True)
    (run_dir / "drop_retention.json").write_text(
        json.dumps(_report([("a", GOOD[0]), ("b", GOOD[1])]))
    )
    return {
        "job_name": "job",
        "target_fact": "target",
        "output_dir": str(run_dir),
        "best_epoch": best_epoch,
    }


def test_cli_writes_afc_in_the_ledger_output_dir(tmp_path: Path) -> None:
    run = _cli_run(tmp_path)
    payload = _load_cli()._certify_run(
        run, _spec_root(tmp_path, ["a", "b"]), AFCSettings(ALPHA)
    )
    assert payload["J"] == 2
    assert json.loads((Path(run["output_dir"]) / "afc.json").read_text()) == payload


def test_cli_refuses_a_report_from_another_epoch(tmp_path: Path) -> None:
    run = _cli_run(tmp_path, best_epoch=7)
    payload = _load_cli()._certify_run(
        run, _spec_root(tmp_path, ["a", "b"]), AFCSettings(ALPHA)
    )
    assert "!= ledger best_epoch 7" in payload["error"]
    assert not (Path(run["output_dir"]) / "afc.json").exists()


def test_collapsed_neighbour_with_underflowed_retention_is_still_tested() -> None:
    collapsed = -np.array([800.0, 900.0, 750.0, 820.0, 860.0])
    payload = afc_from_report(
        _report([("a", collapsed), ("b", GOOD[1])]),
        ["a", "b"],
        AFCSettings(ALPHA, KAPPA),
    )
    assert payload["inputs"]["r_nb"][0] == [0.0] * 5
    assert payload["retain_ok"] is False and payload["certified"] is False
    assert payload["y_bar_j"][0] == pytest.approx(collapsed.mean())
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("flagged", [True, False])
def test_below_guard_flag_reaches_the_afc_output(flagged: bool) -> None:
    report = _report([("a", GOOD[0])])
    if flagged:
        report["selected_below_guard"] = True
    payload = afc_from_report(report, ["a"], SETTINGS)
    assert payload["selected_below_guard"] is flagged
    assert ("selected_below_guard" in summary_line(payload)) is flagged
