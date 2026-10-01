"""FV-DATA-013 through FV-DATA-018. The completer is fake; Pythia is not loaded."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scripts.build_bundles import cli
from src.data.decisions import load_d65
from src.data.errors import DataError
from src.data.exclusion import require_pass, run_gate
from src.train.config import JobConfig
from src.train.run import _precheck

CLOSURE = Path("tests/fixtures/exclusion/closure_d63.yaml")


def _write_decision(path: Path, row: dict[str, object]) -> None:
    path.write_text(
        yaml.safe_dump({"decisions": [row]}, sort_keys=False),
        encoding="utf-8",
    )


def _closed_d65(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "decision_id": "D-65",
        "status": "closed",
        "baseline": "random_choice",
        "threshold": 0.5,
        "comparison": "any_direction",
        "cell_score": "alias_contains",
        "decoding_seeds": [0],
        "decoding": {"do_sample": False, "max_new_tokens": 16},
        "contamination_trigger": 0.10,
        "contamination_decision": None,
        "note": "",
    }
    row.update(overrides)
    return row


def _fact(fact_id: str, subject: str, relation: str, obj: str) -> dict[str, object]:
    return {
        "fact_id": fact_id,
        "triple": {
            "subject": {"id": f"entity:{subject}", "label": subject},
            "relation": {"id": f"relation:{relation}", "label": relation},
            "object": {"id": f"entity:{obj}", "label": obj},
        },
        "aliases": {
            "subject": [{"text": subject, "language": "en"}],
            "object": [{"text": obj, "language": "en"}],
        },
    }


def _spec_root(tmp_path: Path) -> Path:
    root = tmp_path / "spec"
    root.mkdir(exist_ok=True)
    shutil.copy(CLOSURE, root / "closure_templates.yaml")
    (root / "models.yaml").write_text("roles: {}\n", encoding="utf-8")
    return root


def _write_facts(path: Path, facts: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(fact) + "\n" for fact in facts),
        encoding="utf-8",
    )


def test_d65_open_refuses(tmp_path: Path) -> None:
    path = tmp_path / "decisions.yaml"
    _write_decision(path, {"decision_id": "D-65", "status": "open"})
    with pytest.raises(DataError, match="D-65"):
        load_d65(path)


def test_d65_blank_threshold_refuses(tmp_path: Path) -> None:
    row = _closed_d65()
    del row["threshold"]
    path = tmp_path / "decisions.yaml"
    _write_decision(path, row)
    with pytest.raises(DataError, match="threshold"):
        load_d65(path)


def test_d65_closed_values(tmp_path: Path) -> None:
    path = tmp_path / "decisions.yaml"
    _write_decision(path, _closed_d65())
    loaded = load_d65(path)
    assert loaded.baseline == "random_choice"
    assert loaded.threshold == 0.5
    assert loaded.comparison == "any_direction"
    assert loaded.cell_score == "alias_contains"
    assert loaded.decoding_seeds == (0,)
    assert loaded.do_sample is False
    assert loaded.max_new_tokens == 16
    assert loaded.contamination_trigger == 0.10


def test_fv_data_013_model_binding(tmp_path: Path) -> None:
    facts = tmp_path / "facts.jsonl"
    _write_facts(facts, [_fact("f1", "Ada", "occupation", "writer")])
    out = tmp_path / "out.jsonl"
    report = tmp_path / "report.md"
    decision = load_d65(_decision_file(tmp_path))
    rows = run_gate(
        facts_path=facts,
        spec_root=_spec_root(tmp_path),
        decision=decision,
        complete=lambda _prompt, _seed: "no",
        identity_hash="abc",
        expected_hash="abc",
        out_path=out,
        report_path=report,
    )
    assert rows
    assert all(row["identity_hash"] == "abc" for row in rows)
    missing = tmp_path / "missing.jsonl"
    with pytest.raises(DataError, match="identity_hash"):
        run_gate(
            facts_path=facts,
            spec_root=_spec_root(tmp_path),
            decision=decision,
            complete=lambda _prompt, _seed: "no",
            identity_hash="nope",
            expected_hash="abc",
            out_path=missing,
            report_path=tmp_path / "missing.md",
        )
    assert not missing.exists()


def test_fv_data_014_full_closure(tmp_path: Path) -> None:
    facts = tmp_path / "facts.jsonl"
    _write_facts(facts, [_fact("f1", "Ada", "occupation", "writer")])
    decision = load_d65(_decision_file(tmp_path))
    root = _spec_root(tmp_path)
    rows = run_gate(
        facts_path=facts,
        spec_root=root,
        decision=decision,
        complete=lambda _prompt, _seed: "no",
        identity_hash="abc",
        expected_hash="abc",
        out_path=tmp_path / "out.jsonl",
        report_path=tmp_path / "report.md",
    )
    ids = {cell["template_id"] for cell in rows[0]["cells"]}
    assert ids == {"occupation_direct_1", "occupation_direct_2", "occupation_verify"}
    assert rows[0]["inference_probes"][0]["template_id"] == "occupation_infer"
    calls = {"n": 0}

    def drop_one(_prompt: str, _seed: int) -> str | None:
        calls["n"] += 1
        if calls["n"] == 1:
            return None
        return "no"

    dropped = run_gate(
        facts_path=facts,
        spec_root=root,
        decision=decision,
        complete=drop_one,
        identity_hash="abc",
        expected_hash="abc",
        out_path=tmp_path / "drop.jsonl",
        report_path=tmp_path / "drop.md",
    )
    assert dropped[0]["verdict"] == "incomplete"


def test_fv_data_015_baseline(tmp_path: Path) -> None:
    facts = tmp_path / "facts.jsonl"
    _write_facts(facts, [_fact("f1", "Ada", "occupation", "writer")])
    decision = load_d65(_decision_file(tmp_path))
    root = _spec_root(tmp_path)
    seen = {"n": 0}

    def half(prompt: str, _seed: int) -> str:
        if prompt.startswith("True"):
            return "maybe"
        seen["n"] += 1
        if seen["n"] == 1:
            return "writer"
        return "unknown"

    passed = run_gate(
        facts_path=facts,
        spec_root=root,
        decision=decision,
        complete=half,
        identity_hash="abc",
        expected_hash="abc",
        out_path=tmp_path / "pass.jsonl",
        report_path=tmp_path / "pass.md",
    )
    assert passed[0]["verdict"] == "pass"
    assert passed[0]["threshold"] == 0.5
    assert passed[0]["directions"]["direct"]["accuracy"] == 0.5

    def above(prompt: str, _seed: int) -> str:
        if prompt.startswith("True"):
            return "maybe"
        return "writer"

    excluded = run_gate(
        facts_path=facts,
        spec_root=root,
        decision=decision,
        complete=above,
        identity_hash="abc",
        expected_hash="abc",
        out_path=tmp_path / "ex.jsonl",
        report_path=tmp_path / "ex.md",
    )
    assert excluded[0]["verdict"] == "excluded_known"


def test_fv_data_016_excluded_recorded(tmp_path: Path) -> None:
    facts = tmp_path / "facts.jsonl"
    _write_facts(facts, [_fact("f1", "Ada", "occupation", "writer")])
    decision = load_d65(_decision_file(tmp_path))
    report = tmp_path / "report.md"
    run_gate(
        facts_path=facts,
        spec_root=_spec_root(tmp_path),
        decision=decision,
        complete=lambda prompt, _seed: (
            "maybe" if prompt.startswith("True") else "writer"
        ),
        identity_hash="abc",
        expected_hash="abc",
        out_path=tmp_path / "out.jsonl",
        report_path=report,
    )
    stored = [
        json.loads(line)
        for line in (tmp_path / "out.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert stored[0]["verdict"] == "excluded_known"
    text = report.read_text(encoding="utf-8")
    assert "f1" in text
    assert "occupation" in text
    assert "direct" in text


def test_fv_data_017_contamination_alarm(tmp_path: Path) -> None:
    report = tmp_path / "gate.jsonl"
    report.write_text(
        json.dumps({"fact_id": "f1", "verdict": "excluded_known"})
        + "\n"
        + json.dumps({"fact_id": "f2", "verdict": "pass"})
        + "\n",
        encoding="utf-8",
    )
    decisions = tmp_path / "decisions.yaml"
    _write_decision(decisions, _closed_d65())
    facts = tmp_path / "facts.jsonl"
    facts.write_text("{}\n", encoding="utf-8")
    mentions = tmp_path / "mentions.jsonl"
    mentions.write_text("", encoding="utf-8")
    source = tmp_path / "source"
    source.mkdir()
    spec = tmp_path / "spec"
    spec.mkdir()
    out = tmp_path / "out"
    leaveout = tmp_path / "leave"
    transforms = tmp_path / "transforms.jsonl"
    runner = CliRunner()
    blocked = runner.invoke(
        cli,
        [
            "build",
            "--facts",
            str(facts),
            "--mentions",
            str(mentions),
            "--source",
            str(source),
            "--spec-root",
            str(spec),
            "--out",
            str(out),
            "--leaveout",
            str(leaveout),
            "--transforms",
            str(transforms),
            "--gate-report",
            str(report),
            "--decisions",
            str(decisions),
        ],
    )
    assert blocked.exit_code != 0
    assert str(report) in blocked.output
    _write_decision(
        decisions,
        _closed_d65(contamination_decision="proceed", note="owner recorded"),
    )
    proceeded = runner.invoke(
        cli,
        [
            "build",
            "--facts",
            str(facts),
            "--mentions",
            str(mentions),
            "--source",
            str(source),
            "--spec-root",
            str(spec),
            "--out",
            str(out),
            "--leaveout",
            str(leaveout),
            "--transforms",
            str(transforms),
            "--gate-report",
            str(report),
            "--decisions",
            str(decisions),
        ],
    )
    assert proceeded.exit_code != 0
    assert "f1" in proceeded.output


def test_fv_data_018_gate_before_train(tmp_path: Path) -> None:
    report = tmp_path / "gate.jsonl"
    report.write_text(
        json.dumps({"fact_id": "f1", "verdict": "excluded_known"}) + "\n",
        encoding="utf-8",
    )
    config = JobConfig(
        raw={
            "role": "finetuned",
            "target_fact_id": "f1",
            "gate_report": str(report),
        },
        path=tmp_path / "job.yaml",
    )
    with pytest.raises(DataError, match="f1"):
        _precheck(config, _Dummy())  # type: ignore[arg-type]
    missing = JobConfig(
        raw={
            "role": "finetuned",
            "target_fact_id": "absent",
            "gate_report": str(report),
        },
        path=tmp_path / "job.yaml",
    )
    with pytest.raises(DataError, match="absent"):
        _precheck(missing, _Dummy())  # type: ignore[arg-type]
    incomplete = tmp_path / "incomplete.jsonl"
    incomplete.write_text(
        json.dumps({"fact_id": "f1", "verdict": "incomplete"}) + "\n",
        encoding="utf-8",
    )
    incomplete_job = JobConfig(
        raw={
            "role": "finetuned",
            "target_fact_id": "f1",
            "gate_report": str(incomplete),
        },
        path=tmp_path / "job.yaml",
    )
    with pytest.raises(DataError, match="f1"):
        _precheck(incomplete_job, _Dummy())  # type: ignore[arg-type]
    omitted = JobConfig(
        raw={"role": "finetuned", "target_fact_id": "f1"},
        path=tmp_path / "job.yaml",
    )
    assert _precheck(omitted, _Dummy()) is None  # type: ignore[arg-type]


def test_gate_rerun_and_no_split(tmp_path: Path) -> None:
    facts = tmp_path / "facts.jsonl"
    _write_facts(facts, [_fact("f1", "Ada", "occupation", "writer")])
    decision = load_d65(_decision_file(tmp_path))
    kwargs = {
        "facts_path": facts,
        "spec_root": _spec_root(tmp_path),
        "decision": decision,
        "complete": lambda _prompt, _seed: "no",
        "identity_hash": "abc",
        "expected_hash": "abc",
    }
    first = run_gate(
        **kwargs,
        out_path=tmp_path / "a.jsonl",
        report_path=tmp_path / "a.md",
    )
    second = run_gate(
        **kwargs,
        out_path=tmp_path / "b.jsonl",
        report_path=tmp_path / "b.md",
    )
    assert [row["verdict"] for row in first] == [row["verdict"] for row in second]
    assert "split" not in first[0]


def test_require_pass_rejects_other_digest(tmp_path: Path) -> None:
    report = tmp_path / "gate.jsonl"
    report.write_text(
        json.dumps(
            {
                "fact_id": "f1",
                "verdict": "pass",
                "model_identity_hash": "sha256:" + "ab" * 32,
                "model_config_digest": "sha256:" + "cd" * 32,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = report.read_bytes()
    with pytest.raises(DataError):
        require_pass(
            "f1",
            report,
            model_identity_hash="sha256:" + "ab" * 32,
            model_config_digest="sha256:" + "ee" * 32,
        )
    assert report.read_bytes() == before


def _decision_file(tmp_path: Path) -> Path:
    path = tmp_path / "d65.yaml"
    _write_decision(path, _closed_d65())
    return path


class _Dummy:
    """Ledger stand-in. The gate check returns before the ledger is used."""
