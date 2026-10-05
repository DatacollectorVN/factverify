"""FV-DATA-045 through FV-DATA-053."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from src.data.fact_bundle import FactCaseManifest, write_manifest
from tools.tofu_pipeline import (
    PipelineError,
    build_contract,
    build_facts,
    download_dataset,
    load_config,
    main,
    prepare_facts,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / ".factverify" / "fact.schema.json"
ANSWER = "Jaime was born in Santiago."
SANTIAGO_AT = ANSWER.index("Santiago")


class _Messages:
    def __init__(self, handler: Any) -> None:
        self.handler = handler
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        text = self.handler(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(text=text)])


class _Client:
    def __init__(self, handler: Any) -> None:
        self.messages = _Messages(handler)


def _write_config(root: Path, **changes: object) -> Path:
    payload = yaml.safe_load(
        (ROOT / "config/data/tofu.yml").read_text(encoding="utf-8")
    )
    assert isinstance(payload, dict)
    payload["dataset"]["output_dir"] = str(root / "source")
    payload["workspace"] = str(root / "work")
    for key, value in changes.items():
        payload[key] = value
    path = root / "tofu.yml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def _rows(count: int) -> str:
    rows = [{"question": "Where was Jaime born?", "answer": ANSWER}]
    rows.extend(
        {"question": f"Question {index}", "answer": f"Answer {index}."}
        for index in range(1, count)
    )
    return "".join(json.dumps(row) + "\n" for row in rows)


def _fetch_rows(count: int) -> Any:
    def fetch(_repo: str, _revision: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "full.json").write_text(_rows(count), encoding="utf-8")

    return fetch


def _mention(
    *,
    relation: str = "birthplace",
    obj: str = "Santiago",
    start: int = 0,
    end: int = 3,
) -> dict[str, object]:
    return {
        "subject": "Jaime",
        "relation": relation,
        "object": obj,
        "field": "answer",
        "char_start": start,
        "char_end": end,
    }


def _spec(root: Path) -> None:
    spec = root / ".factverify"
    spec.mkdir(parents=True)
    shutil.copy(SCHEMA, spec / "fact.schema.json")
    (spec / "protocol.yaml").write_text(
        'spec_version: "0.1.0-demo"\n',
        encoding="utf-8",
    )


def _accepted_fact() -> dict[str, object]:
    return {
        "candidate_id": "full-0-jaime_birthplace_santiago",
        "subject": "Jaime",
        "relation": "birthplace",
        "object": "Santiago",
        "source_row": 0,
        "field": "answer",
        "char_start": SANTIAGO_AT,
        "char_end": SANTIAGO_AT + len("Santiago"),
        "question": "Where was Jaime born?",
        "answer": ANSWER,
        "model": "claude-sonnet-4-6",
        "effort": "high",
        "prompt_digest": "a" * 64,
        "decoding": {"temperature": 0.0, "max_tokens": 1024},
        "review": {
            "decision": "accept",
            "reason": "The answer states the birthplace.",
            "model": "claude-opus-4-6",
            "effort": "medium",
            "prompt_digest": "b" * 64,
            "source_candidate_id": "full-0-jaime_birthplace_santiago",
        },
        "relation_policy": {"decision_id": "D-63", "config_digest": "c" * 64},
    }


def test_fv_data_045_download_pinned_dataset(tmp_path: Path) -> None:
    config = load_config(_write_config(tmp_path), root=tmp_path)
    calls = {"n": 0}

    def fetch(repo: str, revision: str, dest: Path) -> None:
        calls["n"] += 1
        assert repo == "locuslab/TOFU"
        assert revision == "324592d84ae4f482ac7249b9285c2ecdb53e3a68"
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "full.json").write_text("{}\n", encoding="utf-8")

    download_dataset(config, fetch=fetch)
    assert calls["n"] == 1
    assert (config.workspace / "source_manifest.json").is_file()
    download_dataset(config, fetch=fetch)
    assert calls["n"] == 1
    (config.output_dir / "full.json").write_text("changed\n", encoding="utf-8")
    with pytest.raises(PipelineError):
        download_dataset(config, fetch=fetch)
    assert calls["n"] == 1


def test_fv_data_046_single_config(tmp_path: Path) -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    config_path = "config/data/tofu.yml"
    for command in ("download", "prepare-fact", "build-fact"):
        assert f"tools.tofu_pipeline {command} --config {config_path}" in makefile
    loaded = load_config(ROOT / config_path)
    assert loaded.prepare.model == "claude-sonnet-4-6"
    assert loaded.prepare.effort == "high"
    assert loaded.prepare.temperature == 0.0
    assert loaded.review.model == "claude-opus-4-6"
    assert loaded.review.temperature == 0.0
    text = (ROOT / config_path).read_text(encoding="utf-8")
    missing = tmp_path / "missing.yml"
    missing.write_text(
        re.sub(r"(?m)^limit_authors:.*\n", "", text),
        encoding="utf-8",
    )
    with pytest.raises(PipelineError, match="limit_authors"):
        load_config(missing)
    unknown = tmp_path / "unknown.yml"
    unknown.write_text(text + "api_key: secret\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="api_key"):
        load_config(unknown)
    assert not (ROOT / "config/data/tofu-pilot.yaml").exists()
    assert not (ROOT / "data/tofu_derived/extractor_config.json").exists()
    assert not (ROOT / "data/tofu_derived/reviewer_config.json").exists()
    assert not (ROOT / "data/controlled/relations.yaml").exists()


def test_fv_data_047_sonnet_preparation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = load_config(_write_config(tmp_path, limit_authors=1), root=tmp_path)
    download_dataset(config, fetch=_fetch_rows(21))

    def handler(kwargs: dict[str, Any]) -> str:
        assert kwargs["model"] == "claude-sonnet-4-6"
        assert kwargs["output_config"] == {"effort": "high"}
        assert kwargs["extra_body"] == {"temperature": 0.0}
        prompt = str(kwargs["messages"][0]["content"])
        if "Santiago" not in prompt:
            return '{"mentions": []}'
        return json.dumps({"mentions": [_mention(relation="book_title")]})

    client = _Client(handler)
    prepare_facts(config, client=client)
    assert len(client.messages.calls) == 20
    mentions = [
        json.loads(line)
        for line in (config.workspace / "prepared/mentions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert len(mentions) == 1
    mention = mentions[0]
    assert mention["source_row"] == 0
    assert mention["field"] == "answer"
    assert mention["char_start"] == SANTIAGO_AT
    assert mention["char_end"] == SANTIAGO_AT + len("Santiago")
    assert mention["span_status"] == "repaired"
    assert mention["model"] == "claude-sonnet-4-6"
    assert mention["effort"] == "high"
    assert len(mention["prompt_digest"]) == 64
    assert mention["decoding"]["temperature"] == 0.0


def test_fv_data_048_d63_mapping(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    source = (ROOT / "tools/tofu_pipeline.py").read_text(encoding="utf-8")
    assert "D-63 is the frozen Stage-A relation policy" in source
    assert "config/data/tofu.yml" in source
    config = load_config(_write_config(tmp_path), root=tmp_path)
    download_dataset(config, fetch=_fetch_rows(1))

    def handler(kwargs: dict[str, Any]) -> str:
        if kwargs["model"] == config.prepare.model:
            return json.dumps(
                {
                    "mentions": [
                        _mention(relation="occupation", obj="Jaime", start=0, end=5),
                        _mention(relation="book_title", obj="Jaime", start=0, end=5),
                        _mention(relation="invented", obj="Jaime", start=0, end=5),
                    ]
                }
            )
        return json.dumps({"decision": "reject", "reason": "mapped only"})

    prepare_facts(config, client=_Client(handler))
    report = json.loads(
        (config.workspace / "prepared/report.json").read_text(encoding="utf-8")
    )
    assert report["counts"]["deferred"] == 1
    assert report["counts"]["excluded"] == 1
    assert report["relation_policy"]["decision_id"] == "D-63"
    digest = report["relation_policy"]["config_digest"]
    expected = hashlib.sha256(config.source_path.read_bytes()).hexdigest()
    assert digest == expected


def test_fv_data_049_opus_review(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = load_config(_write_config(tmp_path, review_limit=1), root=tmp_path)
    answer = "Jaime is a novelist in Santiago."

    def fetch(repo: str, revision: str, dest: Path) -> None:
        dest.mkdir(parents=True, exist_ok=True)
        row = {"question": "Who is Jaime?", "answer": answer}
        (dest / "full.json").write_text(json.dumps(row) + "\n", encoding="utf-8")

    download_dataset(config, fetch=fetch)

    def handler(kwargs: dict[str, Any]) -> str:
        if kwargs["model"] == "claude-sonnet-4-6":
            return json.dumps(
                {
                    "mentions": [
                        _mention(relation="occupation", obj="novelist"),
                        _mention(relation="birthplace", obj="Santiago"),
                        _mention(relation="birthplace", obj="Atlantis"),
                    ]
                }
            )
        assert kwargs["model"] == "claude-opus-4-6"
        assert kwargs["output_config"] == {"effort": "medium"}
        assert kwargs["extra_body"] == {"temperature": 0.0}
        return json.dumps({"decision": "reject", "reason": "too vague"})

    client = _Client(handler)
    prepare_facts(config, client=client)
    review_calls = [
        call for call in client.messages.calls if call["model"] == "claude-opus-4-6"
    ]
    assert len(review_calls) == 1
    reviews = [
        json.loads(line)
        for line in (config.workspace / "prepared/reviews.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert reviews[0]["decision"] == "reject"
    assert reviews[0]["reason"] == "too vague"
    assert reviews[0]["model"] == "claude-opus-4-6"
    assert reviews[0]["effort"] == "medium"
    assert reviews[0]["source_candidate_id"]
    facts = (config.workspace / "prepared/facts.jsonl").read_text(encoding="utf-8")
    assert facts == ""


def test_fv_data_050_environment_api_key(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    config = load_config(_write_config(tmp_path), root=tmp_path)
    prepared = config.workspace / "prepared"
    prepared.mkdir(parents=True)
    prior = prepared / "mentions.jsonl"
    prior.write_text("keep\n", encoding="utf-8")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(PipelineError, match="ANTHROPIC_API_KEY"):
        prepare_facts(config)
    assert prior.read_text(encoding="utf-8") == "keep\n"

    sentinel = "SENTINEL-KEY-fv-data-050"
    monkeypatch.setenv("ANTHROPIC_API_KEY", sentinel)
    download_dataset(config, fetch=_fetch_rows(1))

    def boom(api_key: str) -> Any:
        raise RuntimeError(api_key)

    monkeypatch.setattr("anthropic.Anthropic", boom)
    assert main(["prepare-fact", "--config", str(config.source_path)]) == 1
    captured = capsys.readouterr()
    assert sentinel not in captured.err
    assert sentinel not in captured.out
    assert prior.read_text(encoding="utf-8") == "keep\n"

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert main(["download", "--config", str(config.source_path)]) == 0
    _spec(tmp_path)
    facts = config.workspace / "prepared/facts.jsonl"
    facts.write_text(json.dumps(_accepted_fact()) + "\n", encoding="utf-8")
    assert os.environ.get("ANTHROPIC_API_KEY") in (None, "")
    written = build_facts(config, repo=tmp_path)
    assert written


def test_fv_data_051_limits_and_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    config = load_config(_write_config(tmp_path), root=tmp_path)
    download_dataset(config, fetch=_fetch_rows(1))
    waits: list[float] = []
    state = {"n": 0}

    def handler(_kwargs: dict[str, Any]) -> str:
        state["n"] += 1
        if state["n"] == 1:
            raise type("RateLimitError", (Exception,), {})("again")
        return '{"mentions": []}'

    prepare_facts(config, client=_Client(handler), sleep=waits.append)
    assert waits == [2.0]
    report = json.loads(
        (config.workspace / "prepared/report.json").read_text(encoding="utf-8")
    )
    assert report["limits"] == {
        "limit_authors": config.limit_authors,
        "review_limit": config.review_limit,
        "retry_delay_seconds": config.retry_delay_seconds,
    }
    for value in (0, -1, "two", True):
        path = _write_config(tmp_path / str(value), limit_authors=value)
        with pytest.raises(PipelineError, match="limit_authors"):
            load_config(path, root=tmp_path)


def test_fv_data_052_build_fact_bundles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _spec(tmp_path)
    config = load_config(_write_config(tmp_path), root=tmp_path)
    prepared = config.workspace / "prepared"
    prepared.mkdir(parents=True)
    row = _accepted_fact()
    (prepared / "facts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    written = build_facts(config, repo=tmp_path)
    assert len(written) == 1
    bundle = written[0]
    contract = json.loads((bundle / "contract.json").read_text(encoding="utf-8"))
    schema = json.loads((tmp_path / ".factverify/fact.schema.json").read_text())
    Draft202012Validator(schema).validate(contract)
    assert contract["fact_id"].startswith("factverify:fact:")
    assert "mention_ids" not in contract
    assert "entity_resolution" not in contract
    assert "source" not in contract
    source = json.loads((bundle / "sources.jsonl").read_text(encoding="utf-8"))
    assert source["review"]["decision"] == "accept"
    assert source["relation_policy"]["decision_id"] == "D-63"
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["fact_id"] == contract["fact_id"]
    assert manifest["split"] == "construction"
    assert manifest["protocol_revision"] == "0.1.0-demo"
    for name, digest in manifest["digests"].items():
        actual = "sha256:" + hashlib.sha256((bundle / name).read_bytes()).hexdigest()
        assert digest == actual

    # Clear DB state so the next call uses the flat-file fallback path
    from src.pipeline.tofu_store import clear_stage, connect_pipeline

    def _clear_build_db() -> None:
        db = connect_pipeline(config.workspace)
        clear_stage(db, "prepare")
        clear_stage(db, "build")
        db.close()

    _clear_build_db()
    missing = dict(row)
    del missing["review"]
    (prepared / "facts.jsonl").write_text(json.dumps(missing) + "\n", encoding="utf-8")
    with pytest.raises(PipelineError, match="missing review"):
        build_facts(config, repo=tmp_path)

    _clear_build_db()
    (prepared / "facts.jsonl").write_text(json.dumps(row) + "\n", encoding="utf-8")
    import tools.tofu_pipeline as pipeline

    original_prompts = pipeline.prompt_lines
    monkeypatch.setattr(pipeline, "prompt_lines", lambda _row: [])
    with pytest.raises(PipelineError, match="empty prompts.jsonl"):
        build_facts(config, repo=tmp_path)
    assert list((tmp_path / ".factverify/facts").glob(".*")) == []
    monkeypatch.setattr(pipeline, "prompt_lines", original_prompts)

    _clear_build_db()
    def bad_manifest(
        bundle_dir: Path, fact_id: str, split: str, protocol_revision: str
    ) -> FactCaseManifest:
        manifest = write_manifest(bundle_dir, fact_id, split, protocol_revision)
        return FactCaseManifest(
            fact_id=manifest.fact_id,
            split=manifest.split,
            protocol_revision=manifest.protocol_revision,
            digests={**manifest.digests, "contract.json": "sha256:" + "0" * 64},
        )

    monkeypatch.setattr(pipeline, "write_manifest", bad_manifest)
    with pytest.raises(PipelineError, match="digest mismatch"):
        build_facts(config, repo=tmp_path)
    assert list((tmp_path / ".factverify/facts").glob(".*")) == []


def test_fv_data_053_no_legacy_surface() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    targets = set(re.findall(r"^([A-Za-z0-9_-]+):", makefile, flags=re.M))
    assert {"tofu-download", "tofu-prepare-fact", "tofu-build-fact"} <= targets
    retired_targets = (
        "pin",
        "extract",
        "fix-spans",
        "adjudicate",
        "build-facts",
        "data",
        "build-bundles",
        "build-neighbourhoods",
        "entailment-audit",
        "exclusion-gate",
        "make-splits",
        "tofu-pilot",
        "tofu-publish",
    )
    assert targets.isdisjoint(retired_targets)
    retired_paths = [
        "scripts/" + name
        for name in (
            "extract_tofu_mentions.py",
            "fix_spans.py",
            "adjudicate_mentions.py",
            "build_facts.py",
            "build_bundles.py",
            "build_neighbourhoods.py",
            "entailment_audit.py",
            "exclusion_gate.py",
            "make_splits.py",
        )
    ]
    retired_paths.extend(
        [
            "data/tofu_derived/" + name
            for name in (
                "extractor_config.json",
                "reviewer_config.json",
                "source_manifest.json",
            )
        ]
    )
    retired_paths.append("data/controlled/" + "relations.yaml")
    for relative in retired_paths:
        assert not (ROOT / relative).exists()
    needles = retired_paths
    scanned = [ROOT / "Makefile", ROOT / "README.md", ROOT / "index/MOC.md"]
    scanned.extend((ROOT / "tools").rglob("*.py"))
    scanned.extend((ROOT / "src").rglob("*.py"))
    scanned.extend(
        path
        for path in (ROOT / "tests").rglob("*.py")
        if path.name != Path(__file__).name
    )
    for path in scanned:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            assert needle not in text, f"{needle} in {path}"


def test_contract_uses_native_ids() -> None:
    contract = build_contract(_accepted_fact())
    assert contract["schema_version"] == "1.1.0"
    assert contract["fact_id"].startswith("factverify:fact:")
