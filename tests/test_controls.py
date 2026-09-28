"""FV-CTRL-001 through FV-CTRL-010."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from src.controls import (
    BuildResult,
    build_control,
    certify_coverage,
    compare_builds,
    list_catalog,
    load_control,
)
from src.controls.base import expected_identifiability
from src.controls.errors import ControlError
from src.controls.ledger import ParentView
from src.controls.registry import LAYERS
from src.controls.spec_load import load_control_spec
from src.controls.wrappers import ControlArtifact, serve
from src.eval.budget import Accountant
from src.eval.errors import BudgetExhaustedError
from src.eval.gateway import Gateway, ModelPort
from src.eval.spec_load import load_spec
from src.eval.types import Probe
from tests.controls_ports import (
    MemoryLedger,
    ScriptedBehavior,
    ScriptedModel,
    ScriptedTrainer,
)
from tests.eval_ports import DictCache

ROOT = Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "controls"
CONFIGS = FIX / "configs"
DECISIONS = FIX / "decisions"
SPEC_A = FIX / "spec_profile_a"
SPEC_MARGINS = FIX / "spec_margins"
SPEC_CLOSED = ROOT / "tests" / "fixtures" / "eval" / "spec_closed"
REAL_SPEC = ROOT / ".factverify" / "spec"
CHANNEL = "prompt_variation"
DENYLIST = (
    "verdict",
    "evaluator_score",
    "evaluator_output",
    "fcr",
    "frr",
    "verdict.json",
    "budget.json",
)
CATALOG = (
    ("refusal", "refusal.serving"),
    ("output_filter", "output_filter.postprocess"),
    ("answer_replacement", "answer_replacement.postprocess"),
    ("logit_masking", "logit_masking.suppress_tokens"),
    ("template_specific", "template_specific.group_suppress"),
    ("reversible_steering", "reversible_steering.vector"),
    ("targeted_damage", "targeted_damage.local"),
    ("broad_destruction", "broad_destruction.global"),
    ("untouched", "untouched.parent"),
)


def _ledger(
    *,
    role: str = "finetuned",
    fact_id: str = "fact-1",
) -> MemoryLedger:
    ledger = MemoryLedger()
    ledger.parents["led-ft"] = ParentView("led-ft", role, fact_id, "parent-hash")
    return ledger


def _stage(tmp: Path, name: str, dest: str, **overrides: object) -> Path:
    loaded = yaml.safe_load((CONFIGS / name).read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise AssertionError(name)
    loaded.update(overrides)
    path = tmp / f"{dest}.yaml"
    path.write_text(yaml.safe_dump(loaded), encoding="utf-8")
    return path


def _build(
    tmp: Path,
    name: str,
    ledger: MemoryLedger,
    *,
    dest: str,
    decisions: str = "open.yaml",
    spec: Path = SPEC_A,
    behavior: ScriptedBehavior | None = None,
    trainer: ScriptedTrainer | None = None,
    parent_model: ScriptedModel | None = None,
    **overrides: object,
) -> BuildResult:
    overrides.setdefault("output_dir", str(tmp / dest))
    overrides.setdefault("decisions", str(DECISIONS / decisions))
    path = _stage(tmp, name, dest, **overrides)
    return build_control(
        path,
        spec_root=spec,
        ledger=ledger,
        behavior=behavior,
        trainer=trainer,
        parent_model=parent_model,
    )


def _probe(probe_id: str = "p1", group_id: str = "grp-cal") -> Probe:
    return Probe(
        probe_id=probe_id,
        probe_class="native",
        prompt="Where is Zephyr?",
        group_id=group_id,
    )


def _gateway(model: ModelPort) -> Gateway:
    return Gateway(Accountant(load_spec(SPEC_CLOSED), "native"), model, DictCache())


def _generated(model: ModelPort, artifact: ControlArtifact | None, probe: Probe) -> int:
    gate = _gateway(model)
    for _ in range(3):
        try:
            if artifact is None:
                gate.complete(probe, CHANNEL)
            else:
                serve(artifact, gate, probe, CHANNEL)
        except BudgetExhaustedError:
            continue
    return gate.accountant.budget_record().generated_trials


def _assert_sources_clean() -> None:
    for path in (ROOT / "src" / "controls").glob("*.py"):
        text = path.read_text(encoding="utf-8")
        for banned in (
            "src.eval.verdict",
            "src.eval.factverify",
            "src.eval.native",
            "src.eval.semantic",
            "from_pretrained",
            ".generate(",
        ):
            assert banned not in text


def test_fv_ctrl_001_family_coverage(tmp_path: Path) -> None:
    catalog = list_catalog()
    assert [(item.family, item.implementation_ids) for item in catalog] == [
        (family, (implementation,)) for family, implementation in CATALOG
    ]
    untouched = catalog[-1]
    assert untouched.mechanism_layer is None
    with pytest.raises(ControlError, match="D-55"):
        certify_coverage(DECISIONS / "open.yaml")
    with pytest.raises(ControlError, match="D-55"):
        certify_coverage(DECISIONS / "d55_two.yaml")
    certify_coverage(DECISIONS / "d55_one.yaml")
    ledger = _ledger()
    with pytest.raises(ControlError, match="not-a-family"):
        _build(
            tmp_path,
            "untouched.yaml",
            ledger,
            dest="unknown",
            family="not-a-family",
        )
    with pytest.raises(ControlError, match="D-61"):
        _build(tmp_path, "untouched.yaml", ledger, dest="open-untouched")
    assert ledger.rows == []


def test_fv_ctrl_002_labels(tmp_path: Path) -> None:
    ledger = _ledger()
    result = _build(
        tmp_path,
        "untouched.yaml",
        ledger,
        dest="labelled",
        decisions="d61_weights.yaml",
    )
    label_path = tmp_path / "labelled" / "control.json"
    payload = json.loads(label_path.read_text(encoding="utf-8"))
    assert payload["family"] == "untouched"
    assert payload["implementation_id"] == "untouched.parent"
    assert payload["severity"] == "recorded-not-applied"
    assert payload["mechanism_layer"] == "weights"
    assert payload["oracle_label"] == "negative"
    assert payload["split"] == "calibration"
    assert payload["config_hash"]
    assert payload["seed"] == 7
    assert payload["spec_revision"] == "fixture-ctrl"
    assert result.status == "accepted"
    del payload["oracle_label"]
    label_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ControlError, match="oracle_label"):
        load_control(label_path)


def test_fv_ctrl_003_mechanism_layer(tmp_path: Path) -> None:
    ledger = _ledger()
    _build(
        tmp_path,
        "untouched.yaml",
        ledger,
        dest="layer",
        decisions="d61_weights.yaml",
    )
    label = load_control(tmp_path / "layer" / "control.json")
    assert label.mechanism_layer in LAYERS
    assert (
        expected_identifiability("output_filter", load_control_spec(SPEC_A))
        == "structurally_indistinguishable"
    )
    assert (
        expected_identifiability("output_filter", load_control_spec(REAL_SPEC))
        == "structurally_indistinguishable"
    )
    assert expected_identifiability("refusal", load_control_spec(SPEC_A)) is None
    bad = tmp_path / "scores-verified"
    bad.mkdir()
    (bad / "margins.yaml").write_text(
        (SPEC_A / "margins.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (bad / "access_profile.md").write_text(
        "---\n"
        "profile: A\n"
        "systems:\n"
        "  candidate:\n"
        "    capabilities:\n"
        "      text: verified\n"
        "      scores: verified\n"
        "      internals: unavailable\n"
        "---\n\n"
        "# contradictory\n",
        encoding="utf-8",
    )
    with pytest.raises(ControlError, match="access_profile.md"):
        expected_identifiability("output_filter", load_control_spec(bad))


def test_fv_ctrl_009_parent_match(tmp_path: Path) -> None:
    ledger = _ledger()
    built = _build(
        tmp_path,
        "untouched.yaml",
        ledger,
        dest="parent-ok",
        decisions="d61_weights.yaml",
    )
    assert built.status == "accepted"
    assert len(ledger.rows) == 1
    wrong_role = _ledger(role="reference")
    with pytest.raises(ControlError, match="parent_ledger_id"):
        _build(
            tmp_path,
            "untouched.yaml",
            wrong_role,
            dest="role",
            decisions="d61_weights.yaml",
        )
    assert wrong_role.rows == []
    wrong_fact = _ledger(fact_id="fact-2")
    with pytest.raises(ControlError, match="parent_ledger_id"):
        _build(
            tmp_path,
            "untouched.yaml",
            wrong_fact,
            dest="fact",
            decisions="d61_weights.yaml",
        )
    assert wrong_fact.rows == []
    inside = _ledger()
    with pytest.raises(ControlError, match="output_dir"):
        _build(
            tmp_path,
            "untouched.yaml",
            inside,
            dest="inside",
            decisions="d61_weights.yaml",
            output_dir=str(ROOT / ".factverify" / "ctrl-out"),
        )
    assert inside.rows == []


def test_fv_ctrl_004_knowledge_retained(tmp_path: Path) -> None:
    kept = ScriptedBehavior(1.0, 1.0)
    ledger = _ledger()
    accepted = _build(
        tmp_path,
        "refusal.yaml",
        ledger,
        dest="retained",
        decisions="d54_zero.yaml",
        behavior=kept,
        parent_model=ScriptedModel(),
    )
    assert accepted.status == "accepted"
    label = load_control(tmp_path / "retained" / "control.json")
    assert label.oracle_label == "negative"
    assert ("disabled", False) in kept.calls
    assert ("parent", False) in kept.calls
    assert all(enabled is False for _, enabled in kept.calls)
    missed = ScriptedBehavior(0.4, 1.0)
    rejected_ledger = _ledger()
    rejected = _build(
        tmp_path,
        "refusal.yaml",
        rejected_ledger,
        dest="gap",
        decisions="d54_tight.yaml",
        behavior=missed,
        parent_model=ScriptedModel(),
    )
    assert rejected.status == "rejected"
    rejection = json.loads(
        (tmp_path / "gap" / "rejection.json").read_text(encoding="utf-8")
    )
    assert rejection["reason"] == "retention_gap"
    assert rejected_ledger.rows[-1].status == "rejected"
    with pytest.raises(ControlError):
        load_control(tmp_path / "gap" / "control.json")
    opened = ScriptedBehavior()
    open_ledger = _ledger()
    with pytest.raises(ControlError, match="D-54"):
        _build(
            tmp_path,
            "refusal.yaml",
            open_ledger,
            dest="d54-open",
            behavior=opened,
            parent_model=ScriptedModel(),
        )
    assert open_ledger.rows[-1].status == "unchecked"
    assert not (tmp_path / "d54-open" / "control.json").exists()
    assert opened.calls == []


def test_fv_ctrl_005_destruction_measured(tmp_path: Path) -> None:
    trainer = ScriptedTrainer()
    accepted = _build(
        tmp_path,
        "targeted.yaml",
        _ledger(),
        dest="local-pass",
        spec=SPEC_MARGINS,
        behavior=ScriptedBehavior(deltas={"same_subject": 11, "same_relation": 0}),
        trainer=trainer,
    )
    assert accepted.status == "accepted"
    assert trainer.calls == 1
    local_miss = _build(
        tmp_path,
        "targeted.yaml",
        _ledger(),
        dest="local-miss",
        spec=SPEC_MARGINS,
        behavior=ScriptedBehavior(deltas={"same_subject": 10, "same_relation": 10}),
        trainer=ScriptedTrainer(),
    )
    assert local_miss.status == "rejected"
    local_reason = json.loads(
        (tmp_path / "local-miss" / "rejection.json").read_text(encoding="utf-8")
    )
    assert local_reason["reason"] == "locality_margin"
    broad = _build(
        tmp_path,
        "broad.yaml",
        _ledger(),
        dest="broad-pass",
        spec=SPEC_MARGINS,
        behavior=ScriptedBehavior(deltas={"global": 11}),
        trainer=ScriptedTrainer(),
    )
    assert broad.status == "accepted"
    broad_miss = _build(
        tmp_path,
        "broad.yaml",
        _ledger(),
        dest="broad-miss",
        spec=SPEC_MARGINS,
        behavior=ScriptedBehavior(deltas={"global": 10, "same_subject": 50}),
        trainer=ScriptedTrainer(),
    )
    assert broad_miss.status == "rejected"
    broad_reason = json.loads(
        (tmp_path / "broad-miss" / "rejection.json").read_text(encoding="utf-8")
    )
    assert broad_reason["reason"] == "locality_margin"
    null_trainer = ScriptedTrainer()
    null_ledger = _ledger()
    with pytest.raises(ControlError, match="margin.value"):
        _build(
            tmp_path,
            "targeted.yaml",
            null_ledger,
            dest="null-margin",
            behavior=ScriptedBehavior(),
            trainer=null_trainer,
        )
    assert null_ledger.rows[-1].status == "unchecked"
    assert null_trainer.calls == 0
    frozen = _ledger()
    with pytest.raises(ControlError, match="margin.value"):
        _build(
            tmp_path,
            "targeted.yaml",
            frozen,
            dest="frozen-margin",
            spec=REAL_SPEC,
            behavior=ScriptedBehavior(),
            trainer=ScriptedTrainer(),
        )
    assert frozen.rows[-1].status == "unchecked"
    bad_method = _ledger()
    with pytest.raises(ControlError, match="SGD"):
        _build(
            tmp_path,
            "targeted.yaml",
            bad_method,
            dest="sgd",
            spec=SPEC_MARGINS,
            method="SGD",
        )
    assert bad_method.rows == []


def test_fv_ctrl_006_impl_disjoint(tmp_path: Path) -> None:
    ledger = _ledger()
    _build(
        tmp_path,
        "untouched.yaml",
        ledger,
        dest="cal-1",
        decisions="d61_weights.yaml",
    )
    _build(
        tmp_path,
        "untouched.yaml",
        ledger,
        dest="cal-2",
        decisions="d61_weights.yaml",
    )
    assert len(ledger.rows) == 2
    with pytest.raises(ControlError, match=r"untouched\.parent final_test calibration"):
        _build(
            tmp_path,
            "untouched.yaml",
            ledger,
            dest="held-out",
            decisions="d61_weights.yaml",
            split="final_test",
        )
    assert len(ledger.rows) == 2
    other = _ledger()
    _build(
        tmp_path,
        "untouched.yaml",
        other,
        dest="construct",
        decisions="d61_weights.yaml",
        split="construction",
    )
    _build(
        tmp_path,
        "untouched.yaml",
        other,
        dest="then-cal",
        decisions="d61_weights.yaml",
        split="calibration",
    )
    assert [row.split for row in other.rows] == ["construction", "calibration"]
    with pytest.raises(ControlError, match="not-a-family"):
        _build(
            tmp_path,
            "untouched.yaml",
            _ledger(),
            dest="missing",
            family="not-a-family",
        )


def test_fv_ctrl_007_no_evaluator_feedback(tmp_path: Path) -> None:
    for key in ("verdict", "evaluator_score", "evaluator_output", "fcr", "frr"):
        ledger = _ledger()
        with pytest.raises(ControlError, match=key):
            _build(
                tmp_path,
                "untouched.yaml",
                ledger,
                dest=f"deny-{key}",
                decisions="d61_weights.yaml",
                **{key: "seen"},
            )
        assert ledger.rows == []
    for suffix in ("verdict.json", "budget.json"):
        ledger = _ledger()
        with pytest.raises(ControlError, match=suffix):
            _build(
                tmp_path,
                "untouched.yaml",
                ledger,
                dest=f"suffix-{suffix}",
                decisions="d61_weights.yaml",
                spec_revision=f"results/{suffix}",
            )
        assert ledger.rows == []
    clean = _ledger()
    built = _build(
        tmp_path,
        "untouched.yaml",
        clean,
        dest="clean-log",
        decisions="d61_weights.yaml",
    )
    assert built.access_log
    for name in DENYLIST:
        assert name not in built.access_log
    _assert_sources_clean()


def test_fv_ctrl_008_reproducible(tmp_path: Path) -> None:
    ledger = _ledger()
    path = _stage(
        tmp_path,
        "untouched.yaml",
        "same",
        output_dir=str(tmp_path / "same-out"),
        decisions=str(DECISIONS / "d53_exact.yaml"),
    )
    left = build_control(path, spec_root=SPEC_A, ledger=ledger)
    right = build_control(path, spec_root=SPEC_A, ledger=ledger)
    assert left.artifact_digest == right.artifact_digest
    assert left.artifact_digest
    compare_builds(left, right, DECISIONS / "d53_exact.yaml")
    assert len(ledger.rows) == 2
    try:
        import torch
    except ImportError:
        cuda = False
    else:
        cuda = bool(torch.cuda.is_available())
    for row in ledger.rows:
        assert row.role == "control"
        assert row.family == "untouched"
        assert row.parent_ledger_id == "led-ft"
        assert isinstance(row.wall_clock_seconds, float)
        assert isinstance(row.gpu_hours, float)
        assert isinstance(row.peak_memory_bytes, int)
        if not cuda:
            assert row.gpu_hours == 0.0
    with pytest.raises(ControlError, match="D-53"):
        compare_builds(left, right, DECISIONS / "open.yaml")
    assert len(ledger.rows) == 2
    nonzero = _stage(
        tmp_path,
        "untouched.yaml",
        "nonzero",
        output_dir=str(tmp_path / "nonzero-out"),
        decisions=str(DECISIONS / "d53_nonzero.yaml"),
    )
    pair_ledger = _ledger()
    first = build_control(nonzero, spec_root=SPEC_A, ledger=pair_ledger)
    second = build_control(nonzero, spec_root=SPEC_A, ledger=pair_ledger)
    with pytest.raises(ControlError, match="D-53"):
        compare_builds(first, second, DECISIONS / "d53_nonzero.yaml")


def test_fv_ctrl_010_wrapper_charged(tmp_path: Path) -> None:
    parent = ScriptedModel()
    kept = ScriptedBehavior(1.0, 1.0)
    refusal = _build(
        tmp_path,
        "refusal.yaml",
        _ledger(),
        dest="serve-refusal",
        decisions="d54_zero.yaml",
        behavior=kept,
        parent_model=parent,
    )
    artifact = refusal.artifact
    assert isinstance(artifact, ControlArtifact)
    probe = _probe()

    assert _generated(artifact, artifact, probe) == _generated(
        ScriptedModel(), None, probe
    )
    assert parent.calls == 0
    once = _gateway(artifact)
    assert serve(artifact, once, probe, CHANNEL) == "refuse-zephyr"
    with pytest.raises(ControlError, match="underlying"):
        artifact.underlying()

    filtered_parent = ScriptedModel()
    filtered = _build(
        tmp_path,
        "output_filter.yaml",
        _ledger(),
        dest="serve-filter",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=filtered_parent,
    )
    filter_artifact = filtered.artifact
    assert isinstance(filter_artifact, ControlArtifact)
    text = serve(filter_artifact, _gateway(filter_artifact), probe, CHANNEL)
    assert isinstance(text, str)
    assert "Zephyr" not in text
    assert "Zeph" not in text
    other = _build(
        tmp_path,
        "output_filter.yaml",
        _ledger(),
        dest="serve-filter-2",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=ScriptedModel(),
        severity="other-severity",
    )
    other_artifact = other.artifact
    assert isinstance(other_artifact, ControlArtifact)
    again = serve(other_artifact, _gateway(other_artifact), probe, CHANNEL)
    assert again == text

    masked = _build(
        tmp_path,
        "logit_masking.yaml",
        _ledger(),
        dest="serve-mask",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=ScriptedModel(),
    )
    mask_artifact = masked.artifact
    assert isinstance(mask_artifact, ControlArtifact)
    scores = serve(
        mask_artifact,
        _gateway(mask_artifact),
        probe,
        CHANNEL,
        score=True,
    )
    assert scores == {"other": 0.2}

    replaced = _build(
        tmp_path,
        "answer_replacement.yaml",
        _ledger(),
        dest="serve-replace",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=ScriptedModel(),
    )
    replace_artifact = replaced.artifact
    assert isinstance(replace_artifact, ControlArtifact)
    assert (
        serve(replace_artifact, _gateway(replace_artifact), probe, CHANNEL)
        == "not-zephyr"
    )
    templated = _build(
        tmp_path,
        "template_specific.yaml",
        _ledger(),
        dest="serve-template",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=ScriptedModel(),
    )
    template_artifact = templated.artifact
    assert isinstance(template_artifact, ControlArtifact)
    template_gate = _gateway(template_artifact)
    assert serve(template_artifact, template_gate, probe, CHANNEL) == "refuse-zephyr"
    assert (
        serve(
            template_artifact,
            template_gate,
            _probe("p2", "grp-other"),
            CHANNEL,
        )
        == "Zephyr lives in Zeph"
    )
    steered = _build(
        tmp_path,
        "steering.yaml",
        _ledger(),
        dest="serve-steer",
        decisions="d54_zero.yaml",
        behavior=ScriptedBehavior(1.0, 1.0),
        parent_model=ScriptedModel(),
    )
    steer_artifact = steered.artifact
    assert isinstance(steer_artifact, ControlArtifact)
    assert steer_artifact.vector_applied is False
    assert (
        serve(steer_artifact, _gateway(steer_artifact), probe, CHANNEL)
        == "Zephyr lives in Zeph"
    )
    assert steer_artifact.vector_applied is True

    damaged = _build(
        tmp_path,
        "targeted.yaml",
        _ledger(),
        dest="serve-damage",
        spec=SPEC_MARGINS,
        behavior=ScriptedBehavior(deltas={"same_subject": 11, "same_relation": 0}),
        trainer=ScriptedTrainer(),
    )
    assert isinstance(damaged.artifact, ControlArtifact)
    with pytest.raises(ControlError, match="targeted_damage"):
        serve(damaged.artifact, _gateway(ScriptedModel()), probe, CHANNEL)
    untouched = _build(
        tmp_path,
        "untouched.yaml",
        _ledger(),
        dest="serve-untouched",
        decisions="d61_weights.yaml",
    )
    assert isinstance(untouched.artifact, ControlArtifact)
    with pytest.raises(ControlError, match="untouched"):
        serve(untouched.artifact, _gateway(ScriptedModel()), probe, CHANNEL)
    _assert_sources_clean()


def test_fv_ctrl_cli_refuses_sqlite(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "src.controls.run",
            "--config",
            str(CONFIGS / "untouched.yaml"),
            "--spec-root",
            str(SPEC_A),
            "--ledger",
            str(tmp_path / "x.sqlite"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode != 0
    assert "P2-5" in completed.stderr
    match_src = (ROOT / "src" / "controls" / "match.py").read_text(encoding="utf-8")
    assert "import sqlite3" not in match_src
    assert "src.eval.budget" not in match_src
    assert "src.eval.gateway" not in match_src
