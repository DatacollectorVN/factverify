"""Tests for FV-HARN P2-1 — training and unlearning harness.

Verification matrix: FV-HARN-001 through FV-HARN-010.
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.models import load_model
from src.models.adapters import compute_adapter_digest
from src.train import FactVerifyHarnessError, run_job
from src.train.data import DataCatalog
from src.train.ledger import CheckpointRow
from tests.harness_ledger import InMemoryLedger

JOBS = Path("tests/fixtures/harness/jobs")
CORPUS = Path("tests/fixtures/harness/corpus")


def _write_job(src: Path, dest: Path, **overrides: Any) -> Path:
    data = yaml.safe_load(src.read_text())
    data.update(overrides)
    data["corpus_dir"] = str(CORPUS.resolve())
    dest.write_text(yaml.safe_dump(data, sort_keys=False))
    return dest


def _file_hash(path: Path) -> str:
    raw = yaml.safe_load(path.read_text())
    payload = json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _read_meta(adapter: Path) -> dict[str, Any]:
    return json.loads((adapter / "metadata.json").read_text())


def _prior_reference(seed: int, split: str) -> CheckpointRow:
    return CheckpointRow(
        checkpoint_identity_hash="prior",
        parent_checkpoint_hash="prior",
        config_hash="prior",
        seed=seed,
        fact_id="fact-1",
        split=split,
        role="reference",
        tier="pilot",
        method="finetune",
        spec_revision="spec-v1",
        status="succeeded",
        adapter_published=True,
        adapter_path=None,
        wall_clock_seconds=0.0,
        gpu_hours=0.0,
        peak_memory_bytes=0,
        training_steps=0,
        training_examples=0,
    )


def test_fv_harn_001_config_complete(harness_spec_root: Path, tmp_path: Path) -> None:
    """A complete file stores its config hash; a missing learning rate raises."""
    complete = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune.yaml",
        output_dir=str(tmp_path / "ft"),
    )
    result = run_job(complete, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.status == "succeeded"
    assert result.adapter_path is not None
    meta = _read_meta(result.adapter_path)
    assert meta["config_hash"] == _file_hash(complete)

    missing_out = tmp_path / "missing-out"
    missing = _write_job(
        JOBS / "finetune_missing_lr.yaml",
        tmp_path / "missing.yaml",
        output_dir=str(missing_out),
    )
    with pytest.raises(FactVerifyHarnessError, match="learning_rate"):
        run_job(missing, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert not missing_out.exists()


def test_fv_harn_002_seeded(harness_spec_root: Path, tmp_path: Path) -> None:
    """Same seed repeats data order and adapter digest; two seeds do not."""
    first_cfg = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "same.yaml",
        output_dir=str(tmp_path / "same"),
        seed=0,
    )
    ledger = InMemoryLedger()
    first = run_job(first_cfg, spec_root=harness_spec_root, ledger=ledger)
    assert first.adapter_path is not None
    side = tmp_path / "same-copy"
    shutil.copytree(first.adapter_path, side)
    second = run_job(first_cfg, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert second.adapter_path is not None
    assert (
        _read_meta(side)["data_order"] == _read_meta(second.adapter_path)["data_order"]
    )
    assert compute_adapter_digest(side) == compute_adapter_digest(second.adapter_path)

    three = ["retain_a", "retain_b", "fact_doc"]
    seed_a = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "seed0.yaml",
        output_dir=str(tmp_path / "seed0"),
        seed=0,
        manifest={"train": three},
    )
    seed_b = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "seed1.yaml",
        output_dir=str(tmp_path / "seed1"),
        seed=1,
        manifest={"train": three},
    )
    run_a = run_job(seed_a, spec_root=harness_spec_root, ledger=InMemoryLedger())
    run_b = run_job(seed_b, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert run_a.adapter_path is not None and run_b.adapter_path is not None
    meta_a = _read_meta(run_a.adapter_path)
    meta_b = _read_meta(run_b.adapter_path)
    assert meta_a["data_order"] != meta_b["data_order"]
    assert meta_a["seed"] == 0
    assert meta_b["seed"] == 1


def test_fv_harn_006_manifest_only(harness_spec_root: Path, tmp_path: Path) -> None:
    """The access set equals the manifest, and an unlisted id raises."""
    config = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune.yaml",
        output_dir=str(tmp_path / "ft"),
    )
    result = run_job(config, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.status == "succeeded"
    assert set(result.access_log) == {"retain_a"}
    catalog = DataCatalog(CORPUS, ["retain_a"])
    with pytest.raises(FactVerifyHarnessError, match="fact_doc"):
        catalog.get("fact_doc")


def test_fv_harn_007_metadata(
    harness_spec_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata is complete, and a metadata write failure does not publish."""
    config = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune.yaml",
        output_dir=str(tmp_path / "ft"),
    )
    result = run_job(config, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.adapter_path is not None
    meta = _read_meta(result.adapter_path)
    base = load_model("tiny_base", spec_root=harness_spec_root)
    for field in (
        "base_identity_hash",
        "parent_checkpoint_hash",
        "config_hash",
        "seed",
        "role",
        "method",
    ):
        assert meta[field] is not None
    assert meta["parent_checkpoint_hash"] == base.identity_hash
    assert meta["base_identity_hash"] == base.identity_hash
    adapter_meta = json.loads(
        (result.adapter_path / "fv_adapter_meta.json").read_text()
    )
    assert adapter_meta["base_identity_hash"] == base.identity_hash

    from src.train import checkpoint as checkpoint_mod

    real_write = checkpoint_mod._write_json

    def fail_metadata(path: Path, payload: dict[str, Any]) -> None:
        if path.name == "metadata.json":
            raise OSError("disk full")
        real_write(path, payload)

    monkeypatch.setattr(checkpoint_mod, "_write_json", fail_metadata)
    failed_out = tmp_path / "ft-fail"
    failed_cfg = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune-fail.yaml",
        output_dir=str(failed_out),
    )
    failed = run_job(failed_cfg, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert failed.status == "failed"
    assert not failed_out.exists()


def test_fv_harn_008_ledger_row(harness_spec_root: Path, tmp_path: Path) -> None:
    """Success commits one row; a ledger failure removes the published adapter."""
    config = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune.yaml",
        output_dir=str(tmp_path / "ft"),
    )
    ledger = InMemoryLedger()
    result = run_job(config, spec_root=harness_spec_root, ledger=ledger)
    assert result.status == "succeeded"
    succeeded = [row for row in ledger.rows if row.status == "succeeded"]
    assert len(succeeded) == 1
    loaded = load_model(
        "tiny_base", spec_root=harness_spec_root, adapter_path=result.adapter_path
    )
    assert succeeded[0].checkpoint_identity_hash == loaded.identity_hash

    boom_out = tmp_path / "ft-boom"
    boom_cfg = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "boom.yaml",
        output_dir=str(boom_out),
    )
    boom = run_job(
        boom_cfg,
        spec_root=harness_spec_root,
        ledger=InMemoryLedger(fail_commit=True),
    )
    assert boom.status == "failed"
    assert not boom_out.exists()


def test_fv_harn_009_cost(
    harness_spec_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Success rows carry five cost fields; a crash still records a failed row."""
    config = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "finetune.yaml",
        output_dir=str(tmp_path / "ft"),
    )
    ledger = InMemoryLedger()
    result = run_job(config, spec_root=harness_spec_root, ledger=ledger)
    assert result.status == "succeeded"
    row = ledger.rows[0]
    assert row.training_examples >= 1
    assert row.training_steps >= 1
    assert row.wall_clock_seconds >= 0
    assert row.gpu_hours >= 0
    assert row.peak_memory_bytes >= 0

    from src.train.methods import TRAINERS

    def explode(*_args: Any, **_kwargs: Any) -> tuple[list[str], int, int]:
        raise RuntimeError("boom")

    monkeypatch.setitem(TRAINERS, "finetune", explode)
    crash_out = tmp_path / "crash"
    crash_cfg = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "crash.yaml",
        output_dir=str(crash_out),
    )
    crash_ledger = InMemoryLedger()
    crashed = run_job(crash_cfg, spec_root=harness_spec_root, ledger=crash_ledger)
    assert crashed.status == "failed"
    assert not crash_out.exists()
    failed = crash_ledger.rows[0]
    assert failed.status == "failed"
    assert failed.adapter_published is False
    assert failed.wall_clock_seconds >= 0
    assert failed.gpu_hours >= 0
    assert failed.peak_memory_bytes >= 0
    assert failed.training_steps >= 0
    assert failed.training_examples >= 0


def _paired(tmp: Path, name: str) -> Path:
    return _write_job(
        JOBS / "finetune.yaml",
        tmp / name,
        output_dir=str(tmp / f"{name}-out"),
    )


def test_fv_harn_003_bundle_excluded(harness_spec_root: Path, tmp_path: Path) -> None:
    """A disjoint reference records the bundle; a leaked document raises."""
    paired = _paired(tmp_path, "paired.yaml")
    ok = _write_job(
        JOBS / "reference_ok.yaml",
        tmp_path / "reference.yaml",
        output_dir=str(tmp_path / "ref"),
        paired_finetune_config=str(paired),
    )
    result = run_job(ok, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.status == "succeeded"
    assert result.adapter_path is not None
    assert _read_meta(result.adapter_path)["excluded_bundle_id"] == "bundle-fact"

    leak_out = tmp_path / "leak-out"
    leak = _write_job(
        JOBS / "reference_leak.yaml",
        tmp_path / "leak.yaml",
        output_dir=str(leak_out),
        paired_finetune_config=str(paired),
    )
    with pytest.raises(FactVerifyHarnessError, match="fact_doc"):
        run_job(leak, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert not leak_out.exists()


def test_fv_harn_004_matched_procedure(harness_spec_root: Path, tmp_path: Path) -> None:
    """A matched reference stores the paired hash; a learning-rate change raises."""
    paired = _paired(tmp_path, "paired.yaml")
    ok = _write_job(
        JOBS / "reference_ok.yaml",
        tmp_path / "reference.yaml",
        output_dir=str(tmp_path / "ref"),
        paired_finetune_config=str(paired),
    )
    result = run_job(ok, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.status == "succeeded"
    assert result.adapter_path is not None
    assert _read_meta(result.adapter_path)["paired_finetune_config_hash"] == _file_hash(
        paired
    )

    bad = _write_job(
        JOBS / "reference_bad_lr.yaml",
        tmp_path / "bad.yaml",
        output_dir=str(tmp_path / "bad-out"),
        paired_finetune_config=str(paired),
    )
    with pytest.raises(FactVerifyHarnessError, match="learning_rate"):
        run_job(bad, spec_root=harness_spec_root, ledger=InMemoryLedger())


def test_fv_harn_010_seed_disjoint(harness_spec_root: Path, tmp_path: Path) -> None:
    """A seed already stored on another split raises; an unused seed proceeds."""
    paired = _paired(tmp_path, "paired.yaml")
    config = _write_job(
        JOBS / "reference_ok.yaml",
        tmp_path / "reference.yaml",
        output_dir=str(tmp_path / "ref-conflict"),
        paired_finetune_config=str(paired),
    )
    conflict = InMemoryLedger()
    conflict.rows.append(_prior_reference(seed=7, split="final_test"))
    with pytest.raises(FactVerifyHarnessError, match="seed 7"):
        run_job(config, spec_root=harness_spec_root, ledger=conflict)

    fresh = _write_job(
        JOBS / "reference_ok.yaml",
        tmp_path / "reference-fresh.yaml",
        output_dir=str(tmp_path / "ref-fresh"),
        paired_finetune_config=str(paired),
    )
    result = run_job(fresh, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert result.status == "succeeded"


def test_fv_harn_005_methods(harness_spec_root: Path, tmp_path: Path) -> None:
    """Each named method records itself; an unknown method reads no corpus file."""
    parent_cfg = _write_job(
        JOBS / "finetune.yaml",
        tmp_path / "parent.yaml",
        output_dir=str(tmp_path / "parent"),
    )
    parent = run_job(parent_cfg, spec_root=harness_spec_root, ledger=InMemoryLedger())
    assert parent.adapter_path is not None
    base = load_model("tiny_base", spec_root=harness_spec_root)
    parent_loaded = load_model(
        "tiny_base",
        spec_root=harness_spec_root,
        adapter_path=parent.adapter_path,
    )
    for name in (
        "candidate_ga.yaml",
        "candidate_graddiff.yaml",
        "candidate_npo.yaml",
        "candidate_rmu.yaml",
    ):
        src = JOBS / name
        expected = yaml.safe_load(src.read_text())
        config = _write_job(
            src,
            tmp_path / name,
            output_dir=str(tmp_path / name.replace(".yaml", "")),
            parent_adapter=str(parent.adapter_path),
        )
        result = run_job(config, spec_root=harness_spec_root, ledger=InMemoryLedger())
        assert result.status == "succeeded"
        assert result.adapter_path is not None
        meta = _read_meta(result.adapter_path)
        assert meta["method"] == expected["method"]
        assert meta["hyperparameters"]["learning_rate"] == expected["learning_rate"]
        assert meta["base_identity_hash"] == base.identity_hash
        assert meta["parent_checkpoint_hash"] == parent_loaded.identity_hash
        if expected["method"] == "NPO":
            assert meta["hyperparameters"]["beta"] == expected["beta"]
        if expected["method"] == "GradDiff":
            assert meta["hyperparameters"]["retain_coeff"] == expected["retain_coeff"]
        if expected["method"] == "RMU":
            assert (
                meta["hyperparameters"]["steering_layer"] == expected["steering_layer"]
            )

    unknown_out = tmp_path / "unknown-out"
    unknown = _write_job(
        JOBS / "candidate_unknown.yaml",
        tmp_path / "unknown.yaml",
        output_dir=str(unknown_out),
        parent_adapter=str(parent.adapter_path),
    )
    before = {
        path: path.stat().st_mtime_ns for path in CORPUS.iterdir() if path.is_file()
    }
    with pytest.raises(FactVerifyHarnessError, match="NOT_A_METHOD"):
        run_job(unknown, spec_root=harness_spec_root, ledger=InMemoryLedger())
    after = {
        path: path.stat().st_mtime_ns for path in CORPUS.iterdir() if path.is_file()
    }
    assert before == after
    assert not unknown_out.exists()
