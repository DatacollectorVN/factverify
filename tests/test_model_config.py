"""Model policy and versioned configuration.

Spec: specs/20260929-225846-model-role-config/spec.md
"""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest
import yaml
from click.testing import CliRunner

from scripts.exclusion_gate import main as exclusion_main
from src.data.decisions import load_d65
from src.data.exclusion import run_gate
from src.models.errors import FactVerifyLoaderError
from src.models.identity import (
    compute_identity_hash,
    compute_identity_hash_v2,
    verify_identity_hash,
)
from src.models.loader import load_model
from src.models.spec import load_model_configuration, resolve_role
from src.models.spec import load_model_policy as read_policy
from tools.models_validator import compute_identity_hash as validator_hash
from tools.models_validator import validate_models_spec

POLICY = Path(".factverify/spec/model_policy.yaml")
BLOCK0 = Path("config/models/block0-debug-pythia-410m.yaml")
GOLDEN = Path("tests/fixtures/models_config/models_yaml_sha256.txt")
CLOSURE = Path("tests/fixtures/exclusion/closure_d63.yaml")
PIN = "9879c9b5f8bea9051dcb0e68dff21493d67e9d4f"


def test_policy_role_names() -> None:
    loaded = yaml.safe_load(POLICY.read_text(encoding="utf-8"))
    roles = loaded["required_roles"]
    assert set(roles) == {"controlled_fact_base", "pretrained_fact_confirmation"}
    assert "controlled-fact" in roles["controlled_fact_base"]["purpose"]
    assert "retain-only" in roles["controlled_fact_base"]["purpose"]
    purpose = roles["pretrained_fact_confirmation"]["purpose"]
    assert "confirmation subset" in purpose
    assert "block_3_confirmation" not in roles


def test_models_yaml_bytes_unchanged() -> None:
    digest = hashlib.sha256(
        Path(".factverify/spec/models.yaml").read_bytes()
    ).hexdigest()
    assert digest == GOLDEN.read_text(encoding="utf-8").strip()


def test_policy_has_no_concrete_pin() -> None:
    text = POLICY.read_text(encoding="utf-8")
    assert "repo_id:" not in text
    assert PIN not in text


def test_block0_config_copies_pythia_pin() -> None:
    loaded = yaml.safe_load(BLOCK0.read_text(encoding="utf-8"))
    assert loaded["config_id"] == "block0-debug-pythia-410m-v1"
    base = loaded["roles"]["controlled_fact_base"]
    assert base["repo_id"] == "EleutherAI/pythia-410m"
    assert base["model_revision"] == PIN
    assert base["tokenizer_revision"] == PIN
    assert base["variant"] == "base"
    assert base["dtype"] == "float32"
    assert base["attn_impl"] == "eager"
    assert base["licence"] == "Apache-2.0"
    assert base["files"] == {}
    pending = loaded["roles"]["pretrained_fact_confirmation"]
    assert pending["status"] == "pending"
    assert pending["deadline"] is None


def test_shared_shape_model_revision(tmp_path: Path) -> None:
    copy = tmp_path / "block0.yaml"
    shutil.copy(BLOCK0, copy)
    loaded = load_model_configuration(copy)
    assert loaded.roles["controlled_fact_base"].model_revision == PIN


def test_flat_document_refused(tmp_path: Path) -> None:
    path = tmp_path / "flat.yaml"
    path.write_text("controlled_fact_base: {repo_id: org/model}\n", encoding="utf-8")
    with pytest.raises(FactVerifyLoaderError, match="roles"):
        load_model_configuration(path)


def test_revision_field_refused(tmp_path: Path) -> None:
    path = tmp_path / "old.yaml"
    path.write_text(
        "schema_version: '1'\nconfig_id: x\nstudy_stage: test\n"
        "roles:\n  controlled_fact_base:\n    revision: main\n",
        encoding="utf-8",
    )
    with pytest.raises(FactVerifyLoaderError, match="model_revision"):
        load_model_configuration(path)


def test_validator_reads_same_revision() -> None:
    _success, report = validate_models_spec(
        Path(".factverify/spec"),
        model_config=BLOCK0,
    )
    for check in report["checks"]:
        if check["status"] != "fail":
            continue
        blob = " ".join(str(item) for item in check["diagnostics"])
        assert "weight revision" not in blob
        assert not ("model_revision" in blob and "missing" in blob)


def test_load_model_requires_model_config(tmp_path: Path) -> None:
    with pytest.raises(TypeError):
        load_model("controlled_fact_base", spec_root=tmp_path)  # type: ignore[call-arg]


def test_pending_role_refuses_before_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network")

    monkeypatch.setattr("transformers.AutoModelForCausalLM.from_pretrained", _boom)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", _boom)
    with pytest.raises(FactVerifyLoaderError):
        load_model(
            "pretrained_fact_confirmation",
            model_config=BLOCK0,
            spec_root=Path(".factverify/spec"),
        )


def test_movable_revision_refuses_before_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _boom(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("network")

    monkeypatch.setattr("transformers.AutoModelForCausalLM.from_pretrained", _boom)
    monkeypatch.setattr("huggingface_hub.hf_hub_download", _boom)
    path = tmp_path / "moving.yaml"
    path.write_text(
        "schema_version: '1'\nconfig_id: moving\nstudy_stage: test\nroles:\n"
        "  controlled_fact_base:\n    model_revision: main\n",
        encoding="utf-8",
    )
    with pytest.raises(FactVerifyLoaderError, match="model_revision"):
        load_model(
            "controlled_fact_base",
            model_config=path,
            spec_root=Path(".factverify/spec"),
        )


def test_exclusion_gate_cli_requires_config() -> None:
    result = CliRunner().invoke(exclusion_main, [])
    assert result.exit_code != 0


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
        "model_revision": "a" * 40,
        "tokenizer_revision": "b" * 40,
        "dtype": "float32",
    }
    digest = compute_identity_hash_v2(adapter_digest=None, **entry)
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
        "model_config_id": "block0-debug-pythia-410m-v1",
        "model_config_digest": "sha256:" + "ab" * 32,
        "model_identity_hash": "sha256:" + "cd" * 32,
        "identity_schema_version": 2,
        "governing_spec_revision": "spec-v2",
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


def _alias_config(path: Path, *, both: bool) -> None:
    base = {
        "repo_id": "org/model",
        "model_revision": "a" * 40,
        "tokenizer_revision": "a" * 40,
        "variant": "base",
        "dtype": "float32",
        "attn_impl": "eager",
        "licence": "Apache-2.0",
        "files": {"weights.bin": "sha256:" + "ab" * 32},
    }
    roles: dict[str, object] = {"blocks_0_2": base}
    if both:
        roles["controlled_fact_base"] = dict(base)
    roles["pretrained_fact_confirmation"] = {"status": "pending", "deadline": None}
    path.write_text(
        yaml.safe_dump(
            {
                "schema_version": "1",
                "config_id": "alias-v1",
                "study_stage": "test",
                "roles": roles,
            }
        ),
        encoding="utf-8",
    )


def test_legacy_alias_resolves(tmp_path: Path) -> None:
    path = tmp_path / "alias.yaml"
    _alias_config(path, both=False)
    policy = read_policy(Path(".factverify/spec"))
    resolved = resolve_role(policy, load_model_configuration(path), "blocks_0_2")
    assert resolved.study_role == "controlled_fact_base"
    assert resolved.deprecation is not None
    assert "blocks_0_2" in resolved.deprecation
    assert "controlled_fact_base" in resolved.deprecation


def test_alias_conflict_refused(tmp_path: Path) -> None:
    path = tmp_path / "both.yaml"
    _alias_config(path, both=True)
    policy = read_policy(Path(".factverify/spec"))
    with pytest.raises(FactVerifyLoaderError, match="blocks_0_2") as exc:
        resolve_role(policy, load_model_configuration(path), "blocks_0_2")
    assert "controlled_fact_base" in str(exc.value)


def test_new_output_uses_canonical_role(tmp_path: Path) -> None:
    path = tmp_path / "alias.yaml"
    _alias_config(path, both=False)
    policy = read_policy(Path(".factverify/spec"))
    resolved = resolve_role(policy, load_model_configuration(path), "blocks_0_2")
    binding = {"study_role": resolved.study_role}
    assert binding["study_role"] == "controlled_fact_base"
