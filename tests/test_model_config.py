"""Model policy and flat model configuration.

Spec: specs/20260929-225846-model-role-config/spec.md
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
import yaml

from src.data.decisions import D65Decision, load_d65
from src.data.errors import DataError
from src.data.exclusion import run_gate
from src.models.errors import FactVerifyLoaderError
from src.models.identity import (
    compute_identity_hash,
    compute_identity_hash_v2,
    verify_identity_hash,
)
from src.models.loader import load_model
from src.models.spec import load_model_config
from tools.models_validator import compute_identity_hash as validator_hash
from tools.models_validator import validate_models_spec

BLOCK0 = Path("config/models/block0-debug-pythia-410m.yaml")
CLOSURE = Path("tests/fixtures/exclusion/closure_d63.yaml")
PIN = "9879c9b5f8bea9051dcb0e68dff21493d67e9d4f"


def test_block0_config_flat_format() -> None:
    loaded = yaml.safe_load(BLOCK0.read_text(encoding="utf-8"))
    assert "config_id" not in loaded
    assert "study_stage" not in loaded
    assert "roles" not in loaded
    assert loaded["repo_id"] == "EleutherAI/pythia-410m"
    assert loaded["revision"] == PIN
    assert loaded["variant"] == "base"
    assert loaded["dtype"] == "float32"
    assert loaded["attn_impl"] == "eager"
    assert loaded["licence"] == "Apache-2.0"


def test_load_model_config_reads_revision(tmp_path: Path) -> None:
    copy = tmp_path / "block0.yaml"
    shutil.copy(BLOCK0, copy)
    cfg = load_model_config(copy)
    assert cfg.revision == PIN
    assert cfg.repo_id == "EleutherAI/pythia-410m"


def test_old_roles_format_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.yaml"
    path.write_text(
        "schema_version: '1'\nconfig_id: x\nstudy_stage: test\n"
        "roles:\n  controlled_fact_base:\n    repo_id: org/model\n",
        encoding="utf-8",
    )
    with pytest.raises(FactVerifyLoaderError, match="roles"):
        load_model_config(path)


def test_movable_revision_refused(tmp_path: Path) -> None:
    path = tmp_path / "moving.yaml"
    path.write_text(
        "schema_version: '1'\nvendor: huggingface\nrepo_id: org/model\n"
        "revision: main\n"
        "variant: base\ndtype: float32\nattn_impl: eager\nlicence: MIT\n",
        encoding="utf-8",
    )
    with pytest.raises(FactVerifyLoaderError, match="revision"):
        load_model_config(path)


def test_validator_reads_same_revision() -> None:
    _success, report = validate_models_spec(
        Path(".factverify"),
        model_config=BLOCK0,
    )
    for check in report["checks"]:
        if check["status"] != "fail":
            continue
        blob = " ".join(str(item) for item in check["diagnostics"])
        assert "weight revision" not in blob
        assert not ("revision" in blob and "missing" in blob)


def test_load_model_requires_model_config(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        load_model()  # type: ignore[call-arg]


def test_exclusion_gate_requires_matching_identity(tmp_path: Path) -> None:
    decision = D65Decision(
        baseline="random_choice",
        threshold=0.5,
        comparison="any_direction",
        cell_score="alias_contains",
        decoding_seeds=(0,),
        do_sample=False,
        max_new_tokens=16,
        contamination_trigger=0.1,
        contamination_decision=None,
        note="",
    )
    with pytest.raises(DataError, match="identity_hash"):
        run_gate(
            facts_path=tmp_path / "facts.jsonl",
            spec_root=tmp_path,
            decision=decision,
            complete=lambda _prompt, _seed: None,
            identity_hash="a",
            expected_hash="b",
            out_path=tmp_path / "out.jsonl",
            report_path=tmp_path / "report.jsonl",
        )


def test_v2_hash_ignores_role() -> None:
    fields = {
        "repo_id": "org/model",
        "model_revision": "a" * 40,
        "tokenizer_revision": "b" * 40,
        "dtype": "float32",
        "adapter_digest": None,
    }
    left = compute_identity_hash_v2(role="controlled_fact_base", **fields)
    right = compute_identity_hash_v2(role="blocks_0_2", **fields)
    assert left == right
    assert left.startswith("sha256:")


def test_v2_hash_changes_with_revision() -> None:
    common = {
        "repo_id": "org/model",
        "tokenizer_revision": "b" * 40,
        "dtype": "float32",
        "adapter_digest": None,
    }
    left = compute_identity_hash_v2(model_revision="a" * 40, **common)
    right = compute_identity_hash_v2(model_revision="c" * 40, **common)
    assert left != right


def test_v2_encoding_matches_validator() -> None:
    entry = {
        "repo_id": "org/model",
        "revision": "a" * 40,
        "dtype": "float32",
    }
    digest = compute_identity_hash_v2(
        repo_id=entry["repo_id"],
        model_revision=entry["revision"],
        tokenizer_revision=entry["revision"],
        dtype=entry["dtype"],
        adapter_digest=None,
    )
    assert digest == validator_hash(entry)


def test_v1_hash_still_verifies() -> None:
    payload = {
        "adapter_digest": None,
        "attn_impl": "eager",
        "base_repo": "org/model",
        "base_revision": "a" * 40,
        "dtype": "float32",
        "role": "controlled_fact_base",
        "tokenizer_revision": "a" * 40,
    }
    digest = compute_identity_hash(payload)
    assert verify_identity_hash(payload, digest, 1)
    changed = dict(payload)
    changed["role"] = "other"
    assert not verify_identity_hash(changed, digest, 1)
    assert ":" not in digest


def test_gate_row_carries_binding(tmp_path: Path) -> None:
    spec = tmp_path / "spec"
    spec.mkdir()
    shutil.copy(CLOSURE, spec / "closure_templates.yaml")
    facts = tmp_path / "facts.jsonl"
    facts.write_text(
        json.dumps(
            {
                "fact_id": "f1",
                "triple": {
                    "subject": {"id": "entity:Ada", "label": "Ada"},
                    "relation": {"id": "relation:born", "label": "born"},
                    "object": {"id": "entity:Paris", "label": "Paris"},
                },
                "aliases": {
                    "subject": [{"text": "Ada", "language": "en"}],
                    "object": [{"text": "Paris", "language": "en"}],
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    decisions = tmp_path / "d65.yaml"
    decisions.write_text(
        yaml.safe_dump(
            {
                "decisions": [
                    {
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
                ]
            }
        ),
        encoding="utf-8",
    )
    binding = {
        "study_role": "controlled_fact_base",
        "model_config_id": "sha256:" + "ab" * 32,
        "model_config_digest": "sha256:" + "ab" * 32,
        "model_identity_hash": "sha256:" + "cd" * 32,
        "identity_schema_version": 2,
    }
    report = tmp_path / "report.md"
    rows = run_gate(
        facts_path=facts,
        spec_root=spec,
        decision=load_d65(decisions),
        complete=lambda _prompt, _seed: "no",
        identity_hash="sha256:" + "cd" * 32,
        expected_hash="sha256:" + "cd" * 32,
        out_path=tmp_path / "gate.jsonl",
        report_path=report,
        binding=binding,
    )
    assert rows[0]["identity_schema_version"] == 2
    for key, value in binding.items():
        assert rows[0][key] == value
    text = report.read_text(encoding="utf-8")
    for key, value in binding.items():
        assert f"{key}: {value}" in text
