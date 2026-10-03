"""Download TOFU, prepare accepted atomic facts, and build fact bundles.

The three commands are ``download``, ``prepare-fact``, and ``build-fact``.
Every non-secret setting comes from ``config/data/tofu.yml``. The Anthropic
key is read from ``ANTHROPIC_API_KEY`` and only by preparation.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import click
import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from src.artifacts.layout import LayoutRoots
from src.data.fact_bundle import BundleError, write_manifest
from src.data.tofu import (
    SourceManifest,
    build_manifest,
    load_tofu_rows,
    verify_source,
)

_REPO = Path(__file__).resolve().parents[1]
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_DECODING = {"temperature": 0.0, "max_tokens": 1024}
_TOP_KEYS = {
    "schema_version",
    "dataset",
    "workspace",
    "prepare",
    "review",
    "limit_authors",
    "review_limit",
    "retry_delay_seconds",
    "relation_policy",
}
_DATASET_KEYS = {"repo_id", "revision", "output_dir"}
_MODEL_KEYS = {"model", "effort", "temperature"}
_POLICY_KEYS = {"decision_id", "included", "deferred"}
_PREPARE_TEMPLATE = (
    "Extract atomic subject-relation-object facts from this TOFU pair. "
    "Return JSON "
    '{{"mentions": [{{"subject": "", "relation": "", "object": "", '
    '"field": "answer", "char_start": 0, "char_end": 0}}]}}. '
    "field is question or answer. Offsets index that field.\n"
    "Question: {question}\nAnswer: {answer}\n"
)
_REVIEW_TEMPLATE = (
    "Decide whether this atomic fact is explicit in the text. "
    "Return JSON "
    '{{"decision": "accept", "reason": "..."}} '
    "or "
    '{{"decision": "reject", "reason": "..."}}.\n'
    "Subject: {subject}\nRelation: {relation}\nObject: {object}\nText: {text}\n"
)


class PipelineError(Exception):
    """A refused pipeline step. The message names the cause."""


@dataclass(frozen=True)
class ModelSpec:
    model: str
    effort: str
    temperature: float


@dataclass(frozen=True)
class RelationPolicy:
    decision_id: str
    included: dict[str, tuple[str, ...]]
    deferred: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    source_path: Path
    repo: Path
    dataset_repo: str
    revision: str
    output_dir: Path
    workspace: Path
    prepare: ModelSpec
    review: ModelSpec
    limit_authors: int
    review_limit: int
    retry_delay_seconds: float
    relations: RelationPolicy


def repo_root() -> Path:
    """Return the repository that contains this module."""
    return _REPO


def load_config(path: Path, *, root: Path | None = None) -> Config:
    """Load the closed TOFU configuration. A bad field names that field."""
    base = (root or _REPO).resolve()
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise PipelineError(path.name) from exc
    if not isinstance(loaded, dict):
        raise PipelineError("schema_version")
    _exact_keys(loaded, _TOP_KEYS, "")
    if loaded["schema_version"] != "1":
        raise PipelineError("schema_version")
    dataset = _mapping(loaded, "dataset")
    prepare = _mapping(loaded, "prepare")
    review = _mapping(loaded, "review")
    policy = _mapping(loaded, "relation_policy")
    _exact_keys(dataset, _DATASET_KEYS, "dataset")
    _exact_keys(prepare, _MODEL_KEYS, "prepare")
    _exact_keys(review, _MODEL_KEYS, "review")
    _exact_keys(policy, _POLICY_KEYS, "relation_policy")
    revision = _text(dataset, "revision", "dataset.revision")
    if not _HEX40.match(revision):
        raise PipelineError("dataset.revision")
    return Config(
        source_path=path.resolve(),
        repo=base,
        dataset_repo=_text(dataset, "repo_id", "dataset.repo_id"),
        revision=revision,
        output_dir=_resolve(base, _text(dataset, "output_dir", "dataset.output_dir")),
        workspace=_resolve(base, _text(loaded, "workspace", "workspace")),
        prepare=ModelSpec(
            model=_text(prepare, "model", "prepare.model"),
            effort=_text(prepare, "effort", "prepare.effort"),
            temperature=_unit_interval(prepare.get("temperature"), "prepare.temperature"),
        ),
        review=ModelSpec(
            model=_text(review, "model", "review.model"),
            effort=_text(review, "effort", "review.effort"),
            temperature=_unit_interval(review.get("temperature"), "review.temperature"),
        ),
        limit_authors=_positive_int(loaded.get("limit_authors"), "limit_authors"),
        review_limit=_positive_int(loaded.get("review_limit"), "review_limit"),
        retry_delay_seconds=_positive_number(
            loaded.get("retry_delay_seconds"), "retry_delay_seconds"
        ),
        relations=_policy(policy),
    )


def download_dataset(
    config: Config,
    *,
    fetch: Callable[[str, str, Path], None] | None = None,
) -> Path:
    """Download the pinned revision, or return when the manifest already matches."""
    manifest_path = config.workspace / "source_manifest.json"
    source = config.output_dir
    _log(f"Download {config.dataset_repo} @ {config.revision}")
    if manifest_path.is_file():
        try:
            verify_source(source, SourceManifest.load(manifest_path))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise PipelineError(str(exc)) from exc
        _log(f"Source already verified: {source}")
        return source
    _log(f"Downloading into {source}")
    source.mkdir(parents=True, exist_ok=True)
    downloader = fetch or _snapshot_download
    downloader(config.dataset_repo, config.revision, source)
    manifest = build_manifest(source, config.dataset_repo, config.revision)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(manifest_path)
    verify_source(source, SourceManifest.load(manifest_path))
    _log(f"Verified {len(manifest.files)} files in {source}")
    return source


def prepare_facts(
    config: Config,
    *,
    client: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Extract with the prepare model, repair spans, map D-63, and review."""
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not key:
        raise PipelineError("ANTHROPIC_API_KEY")
    if client is None:
        client = _anthropic_client(key)
    try:
        verify_source(
            config.output_dir,
            SourceManifest.load(config.workspace / "source_manifest.json"),
        )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        raise PipelineError(str(exc)) from exc

    rows = load_tofu_rows(
        config.output_dir, "full", limit_authors=config.limit_authors
    )
    _log(
        f"Extracting {len(rows)} rows with {config.prepare.model} "
        f"(effort {config.prepare.effort}, temperature {config.prepare.temperature})"
    )
    cache = _load_cache(config.workspace / "cache" / "responses.json")
    mentions: list[dict[str, Any]] = []
    counts = {
        "span_unresolved": 0,
        "deferred": 0,
        "excluded": 0,
        "malformed": 0,
        "reviewed": 0,
        "accepted": 0,
        "rejected": 0,
    }
    prepare_digest = _sha256(_PREPARE_TEMPLATE)
    for row_index, row in enumerate(rows):
        question = str(row.get("question", ""))
        answer = str(row.get("answer", ""))
        prompt = _PREPARE_TEMPLATE.format(question=question, answer=answer)
        _log(f"  extract {row_index + 1}/{len(rows)}")
        raw = _cached_call(
            client,
            cache,
            model=config.prepare.model,
            effort=config.prepare.effort,
            temperature=config.prepare.temperature,
            prompt=prompt,
            delay=config.retry_delay_seconds,
            sleep=sleep,
        )
        for item in _mention_items(raw):
            mention = _mention_from_item(
                item,
                row_index=row_index,
                question=question,
                answer=answer,
                config=config,
                prompt_digest=prepare_digest,
            )
            if mention is None:
                counts["malformed"] += 1
                continue
            mentions.append(mention)

    eligible: list[dict[str, Any]] = []
    for mention in mentions:
        status, canonical = map_surface(
            str(mention["surface_relation"]), config.relations
        )
        mention["mapping"] = status
        mention["relation"] = canonical or ""
        if mention["span_status"] == "span_unresolved":
            counts["span_unresolved"] += 1
            continue
        if status == "deferred":
            counts["deferred"] += 1
        elif status == "excluded":
            counts["excluded"] += 1
        else:
            eligible.append(mention)

    _log(
        f"Mapped {len(mentions)} mentions: {len(eligible)} ready for review, "
        f"{counts['span_unresolved']} span-unresolved, "
        f"{counts['deferred']} deferred, {counts['excluded']} excluded"
    )
    review_digest = _sha256(_REVIEW_TEMPLATE)
    reviews: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    policy_record = {
        "decision_id": config.relations.decision_id,
        "config_digest": _sha256_file(config.source_path),
    }
    to_review = eligible[: config.review_limit]
    _log(
        f"Reviewing {len(to_review)} candidates with {config.review.model} "
        f"(effort {config.review.effort}, temperature {config.review.temperature})"
    )
    for index, mention in enumerate(to_review):
        text = mention["source_text"]
        _log(f"  review {index + 1}/{len(to_review)} {mention['candidate_id']}")
        prompt = _REVIEW_TEMPLATE.format(
            subject=mention["subject"],
            relation=mention["relation"],
            object=mention["object"],
            text=text,
        )
        raw = _cached_call(
            client,
            cache,
            model=config.review.model,
            effort=config.review.effort,
            temperature=config.review.temperature,
            prompt=prompt,
            delay=config.retry_delay_seconds,
            sleep=sleep,
        )
        review = _review_from_text(
            raw,
            candidate_id=str(mention["candidate_id"]),
            config=config,
            prompt_digest=review_digest,
        )
        counts["reviewed"] += 1
        if review is None:
            counts["malformed"] += 1
            continue
        reviews.append(review)
        if review["decision"] == "accept":
            counts["accepted"] += 1
            accepted.append(_accepted_row(mention, review, policy_record, rows))
            _log("    accept")
        else:
            counts["rejected"] += 1
            _log("    reject")

    report = {
        "limits": {
            "limit_authors": config.limit_authors,
            "review_limit": config.review_limit,
            "retry_delay_seconds": config.retry_delay_seconds,
        },
        "relation_policy": policy_record,
        "counts": counts,
    }
    _save_cache(config.workspace / "cache" / "responses.json", cache)
    prepared = config.workspace / "prepared"
    _write_jsonl(prepared / "mentions.jsonl", mentions)
    _write_jsonl(prepared / "reviews.jsonl", reviews)
    _write_jsonl(prepared / "facts.jsonl", accepted)
    _write_json(prepared / "report.json", report)
    _log(
        f"Accepted {counts['accepted']}, rejected {counts['rejected']}. "
        f"Wrote {prepared}"
    )
    return report


def map_surface(surface: str, policy: RelationPolicy) -> tuple[str, str | None]:
    """Map one surface relation through the configured D-63 policy."""
    # D-63 is the frozen Stage-A relation policy, not an LLM guess.
    # A surface relation is mapped to an approved FactVerify canonical relation,
    # deferred, or excluded. Do not invent a new relation in code; change the
    # D-63 relation_policy in config/data/tofu.yml and record the amendment.
    key = surface.strip().casefold()
    for canonical, surfaces in policy.included.items():
        names = {canonical.casefold(), *(item.casefold() for item in surfaces)}
        if key in names:
            return "included", canonical
    if key in {item.casefold() for item in policy.deferred}:
        return "deferred", None
    return "excluded", None


def build_facts(config: Config, *, repo: Path | None = None) -> list[Path]:
    """Write one schema-valid five-file bundle per accepted fact."""
    root = (repo or config.repo).resolve()
    facts_path = config.workspace / "prepared" / "facts.jsonl"
    if not facts_path.is_file():
        raise PipelineError("facts.jsonl")
    rows = _read_jsonl(facts_path)
    for row in rows:
        review = row.get("review")
        if not isinstance(review, dict) or review.get("decision") != "accept":
            raise PipelineError("missing review")
    schema_path = root / ".factverify" / "fact.schema.json"
    protocol_path = root / ".factverify" / "protocol.yaml"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    protocol = yaml.safe_load(protocol_path.read_text(encoding="utf-8"))
    if not isinstance(protocol, dict) or "spec_version" not in protocol:
        raise PipelineError("spec_version")
    revision = str(protocol["spec_version"])
    spec_root = root / ".factverify"
    facts_root = spec_root / "facts"
    facts_root.mkdir(parents=True, exist_ok=True)
    _log(f"Building {len(rows)} fact bundles into {facts_root}")
    staged: list[tuple[Path, Path]] = []
    try:
        for index, row in enumerate(rows):
            _log(
                f"  bundle {index + 1}/{len(rows)} "
                f"{row.get('subject')} / {row.get('relation')} / {row.get('object')}"
            )
            staged.append(_stage_bundle(row, facts_root, schema, revision))
        written = _commit_bundles(staged, spec_root, root / ".factverify_internal")
    except Exception:
        for tmp, _dest in staged:
            if tmp.exists():
                shutil.rmtree(tmp)
        raise
    _log(f"Wrote {len(written)} bundles")
    return written


def build_contract(row: dict[str, Any]) -> dict[str, Any]:
    """Build a schema 1.1.0 contract. Provenance stays out of this object."""
    subject = str(row["subject"])
    relation = str(row["relation"])
    obj = str(row["object"])
    candidate_id = str(row.get("candidate_id") or "")
    slug = _slug(candidate_id) if candidate_id else _slug(subject, relation, obj)
    question = str(row.get("question") or f"What is {subject}'s {relation}?")
    neighbourhood = []
    for bucket, statement in (
        ("same_subject", question),
        ("same_relation", f"Name another {relation} besides {obj}."),
        ("compositional", f"Which detail about {subject} is not their {relation}?"),
        ("global", f"State a fact that does not name {subject}."),
    ):
        neighbourhood.append(
            {
                "id": f"retain:{slug}-{bucket.replace('_', '-')}",
                "bucket": bucket,
                "statement": statement,
                "language": "en",
            }
        )
    return {
        "schema_version": "1.1.0",
        "contract_id": f"factverify:contract:{slug}:v1",
        "fact_id": f"factverify:fact:{slug}",
        "fact_type": "controlled_atomic_fact",
        "triple": {
            "subject": {"id": f"factverify:entity:{_slug(subject)}", "label": subject},
            "relation": {
                "id": f"factverify:relation:{_slug(relation)}",
                "label": relation,
            },
            "object": {"id": f"factverify:entity:{_slug(obj)}", "label": obj},
        },
        "aliases": {
            "subject": [{"text": subject, "language": "en", "alias_type": "canonical"}],
            "relation": [
                {
                    "text": relation,
                    "language": "en",
                    "argument_order": "subject_relation_object",
                }
            ],
            "object": [{"text": obj, "language": "en", "alias_type": "canonical"}],
        },
        "equivalent_directions": [
            {
                "direction": "forward",
                "given": "subject",
                "answer": "object",
                "language": "en",
                "statement_pattern": question,
            },
            {
                "direction": "inverse",
                "given": "object",
                "answer": "subject",
                "language": "en",
                "statement_pattern": f"Who is linked to {obj} by {relation}?",
            },
        ],
        "retained_neighbourhood": neighbourhood,
        "clue_boundary": {
            "equivalent_rule": (
                f"Any prompt whose answer is {obj} for {subject}'s {relation}."
            ),
            "clue_bearing_rule": (
                f"Prompts that mention {subject} or {obj} without asking {relation}."
            ),
            "ambiguous_policy": "exclude_from_confirmatory_analysis",
        },
        "evidence_regime": {
            "regime": "reference_relative",
            "training_provenance": "known",
            "allowed_claim": "reference_relative_empirical_conformance",
        },
    }


def prompt_lines(row: dict[str, Any]) -> list[dict[str, str]]:
    """Forward and inverse prompts derived from the accepted candidate."""
    subject = str(row["subject"])
    relation = str(row["relation"])
    obj = str(row["object"])
    question = str(row.get("question") or f"What is {subject}'s {relation}?")
    return [
        {"direction": "forward", "text": question},
        {
            "direction": "inverse",
            "text": f"Who is linked to {obj} by {relation}? {subject}",
        },
    ]


@click.group()
def cli() -> None:
    """Download TOFU, prepare accepted facts, and build fact bundles."""


@cli.command("download")
@click.option("--config", "config_path", required=True, type=click.Path(path_type=Path))
def download_command(config_path: Path) -> None:
    """Download and verify the pinned TOFU dataset."""
    download_dataset(load_config(config_path))


@cli.command("prepare-fact")
@click.option("--config", "config_path", required=True, type=click.Path(path_type=Path))
def prepare_command(config_path: Path) -> None:
    """Construct, repair, map, and review atomic-fact candidates."""
    prepare_facts(load_config(config_path))


@cli.command("build-fact")
@click.option("--config", "config_path", required=True, type=click.Path(path_type=Path))
def build_command(config_path: Path) -> None:
    """Write one complete fact bundle per accepted candidate."""
    build_facts(load_config(config_path))


def _log(message: str) -> None:
    """Print one operator progress line."""
    click.echo(message)


def main(argv: list[str] | None = None) -> int:
    """Run one pipeline command. Secret-bearing options are refused."""
    args = list(sys.argv[1:] if argv is None else argv)
    if any(arg == "--api-key" or arg.startswith("--api-key=") for arg in args):
        click.echo("api_key", err=True)
        return 1
    try:
        cli.main(args=args, standalone_mode=False)
    except click.ClickException as exc:
        click.echo(_redact(exc.format_message()), err=True)
        return int(exc.exit_code or 1)
    except click.exceptions.Exit as exc:
        code = exc.exit_code
        return int(code) if code is not None else 0
    except PipelineError as exc:
        click.echo(_redact(str(exc)), err=True)
        return 1
    return 0


def _anthropic_client(key: str) -> Any:
    try:
        import anthropic
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(_redact(str(exc))) from None
    try:
        return anthropic.Anthropic(api_key=key)
    except Exception as exc:  # noqa: BLE001
        raise PipelineError(_redact(str(exc))) from None


def _snapshot_download(repo_id: str, revision: str, local_dir: Path) -> None:
    from huggingface_hub import snapshot_download

    snapshot_download(
        repo_id=repo_id,
        repo_type="dataset",
        revision=revision,
        local_dir=str(local_dir),
    )


def _cached_call(
    client: Any,
    cache: dict[str, str],
    *,
    model: str,
    effort: str,
    temperature: float,
    prompt: str,
    delay: float,
    sleep: Callable[[float], None],
) -> str:
    key = _sha256(
        json.dumps(
            {
                "model": model,
                "effort": effort,
                "temperature": temperature,
                "prompt": prompt,
            }
        )
    )
    cached = cache.get(key)
    if cached is not None:
        return cached
    text = _call_model(
        client,
        model=model,
        effort=effort,
        temperature=temperature,
        prompt=prompt,
        delay=delay,
        sleep=sleep,
    )
    cache[key] = text
    return text


def _call_model(
    client: Any,
    *,
    model: str,
    effort: str,
    temperature: float,
    prompt: str,
    delay: float,
    sleep: Callable[[float], None],
) -> str:
    last = "model call failed"
    for attempt in range(2):
        try:
            # This SDK's create() signature has no temperature argument.
            # extra_body still places it in the Messages request body.
            response = client.messages.create(
                model=model,
                max_tokens=int(_DECODING["max_tokens"]),
                output_config={"effort": effort},
                messages=[{"role": "user", "content": prompt}],
                extra_body={"temperature": temperature},
            )
            return _response_text(response)
        except Exception as exc:  # noqa: BLE001
            last = _redact(str(exc))
            if attempt == 0 and _retryable(exc):
                sleep(delay)
                continue
            raise PipelineError(last) from None
    raise PipelineError(last)


def _retryable(exc: BaseException) -> bool:
    status = getattr(exc, "status_code", None)
    if status in {408, 409, 429, 500, 529}:
        return True
    return type(exc).__name__ in {
        "RateLimitError",
        "APIConnectionError",
        "InternalServerError",
        "APITimeoutError",
    }


def _response_text(response: Any) -> str:
    content = response.content
    if isinstance(content, str):
        return content
    parts: list[str] = []
    for block in content:
        text = block["text"] if isinstance(block, dict) else getattr(block, "text", "")
        if isinstance(text, str) and text:
            parts.append(text)
    if not parts:
        raise PipelineError("empty model response")
    return "".join(parts)


def _mention_items(raw: str) -> list[dict[str, Any]]:
    try:
        payload = _parse_json(raw)
    except (json.JSONDecodeError, ValueError, TypeError):
        return []
    items = payload.get("mentions", [])
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _mention_from_item(
    item: dict[str, Any],
    *,
    row_index: int,
    question: str,
    answer: str,
    config: Config,
    prompt_digest: str,
) -> dict[str, Any] | None:
    try:
        subject = str(item["subject"]).strip()
        relation = str(item["relation"]).strip()
        obj = str(item["object"]).strip()
        field = str(item["field"])
        start = int(item["char_start"])
        end = int(item["char_end"])
    except (KeyError, TypeError, ValueError):
        return None
    if not subject or not relation or not obj or field not in {"question", "answer"}:
        return None
    source_text = question if field == "question" else answer
    span_start, span_end, status = _repair_span(source_text, obj, start, end)
    return {
        "candidate_id": f"full-{row_index}-{_slug(subject, relation, obj)}",
        "source_row": row_index,
        "field": field,
        "char_start": span_start,
        "char_end": span_end,
        "span_status": status,
        "subject": subject,
        "surface_relation": relation,
        "relation": "",
        "object": obj,
        "source_text": source_text,
        "model": config.prepare.model,
        "effort": config.prepare.effort,
        "prompt_digest": prompt_digest,
        "decoding": {
            "temperature": config.prepare.temperature,
            "max_tokens": int(_DECODING["max_tokens"]),
        },
    }


def _repair_span(text: str, obj: str, start: int, end: int) -> tuple[int, int, str]:
    if 0 <= start < end <= len(text) and text[start:end] == obj:
        return start, end, "exact"
    found = text.find(obj)
    if obj and found >= 0:
        return found, found + len(obj), "repaired"
    return start, end, "span_unresolved"


def _review_from_text(
    raw: str,
    *,
    candidate_id: str,
    config: Config,
    prompt_digest: str,
) -> dict[str, Any] | None:
    try:
        payload = _parse_json(raw)
        decision = str(payload["decision"])
        reason = str(payload["reason"]).strip()
    except (json.JSONDecodeError, ValueError, TypeError, KeyError):
        return None
    if decision not in {"accept", "reject"} or not reason:
        return None
    return {
        "decision": decision,
        "reason": reason,
        "model": config.review.model,
        "effort": config.review.effort,
        "prompt_digest": prompt_digest,
        "source_candidate_id": candidate_id,
    }


def _accepted_row(
    mention: dict[str, Any],
    review: dict[str, Any],
    policy_record: dict[str, str],
    rows: list[dict[str, str]],
) -> dict[str, Any]:
    source = rows[int(mention["source_row"])]
    return {
        "candidate_id": mention["candidate_id"],
        "subject": mention["subject"],
        "relation": mention["relation"],
        "object": mention["object"],
        "source_row": mention["source_row"],
        "field": mention["field"],
        "char_start": mention["char_start"],
        "char_end": mention["char_end"],
        "question": str(source.get("question", "")),
        "answer": str(source.get("answer", "")),
        "model": mention["model"],
        "effort": mention["effort"],
        "prompt_digest": mention["prompt_digest"],
        "decoding": mention["decoding"],
        "review": review,
        "relation_policy": policy_record,
    }


def _stage_bundle(
    row: dict[str, Any],
    facts_root: Path,
    schema: dict[str, Any],
    revision: str,
) -> tuple[Path, Path]:
    contract = build_contract(row)
    try:
        Draft202012Validator(schema).validate(contract)
    except ValidationError as exc:
        raise PipelineError("contract.json") from exc
    fact_id = str(contract["fact_id"])
    local_id = fact_id.removeprefix("factverify:fact:")
    dest = facts_root / local_id
    tmp = facts_root / f".{local_id}.build-tmp"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        (tmp / "contract.json").write_text(
            json.dumps(contract, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        source_row = {
            "fact_id": fact_id,
            "candidate_id": row.get("candidate_id"),
            "source_row": row.get("source_row"),
            "field": row.get("field"),
            "char_start": row.get("char_start"),
            "char_end": row.get("char_end"),
            "model": row.get("model"),
            "effort": row.get("effort"),
            "prompt_digest": row.get("prompt_digest"),
            "decoding": row.get("decoding"),
            "review": row.get("review"),
            "relation_policy": row.get("relation_policy"),
        }
        _write_jsonl(tmp / "sources.jsonl", [source_row])
        neighbourhood = contract["retained_neighbourhood"]
        if not isinstance(neighbourhood, list):
            raise PipelineError("empty neighbourhood.jsonl")
        _write_jsonl(tmp / "neighbourhood.jsonl", neighbourhood)
        prompts = prompt_lines(row)
        if not prompts:
            raise PipelineError("empty prompts.jsonl")
        _write_jsonl(tmp / "prompts.jsonl", prompts)
        for name in (
            "contract.json",
            "sources.jsonl",
            "neighbourhood.jsonl",
            "prompts.jsonl",
        ):
            if (tmp / name).stat().st_size == 0:
                raise PipelineError(f"empty {name}")
        manifest = write_manifest(tmp, fact_id, "construction", revision)
        for filename, digest in manifest.digests.items():
            actual = "sha256:" + _sha256_file(tmp / filename)
            if actual != digest:
                raise PipelineError(f"digest mismatch for {filename}")
    except Exception:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return tmp, dest


def _commit_bundles(
    staged: list[tuple[Path, Path]],
    spec_root: Path,
    internal_root: Path,
) -> list[Path]:
    committed: list[tuple[Path, Path | None]] = []
    try:
        for tmp, dest in staged:
            backup: Path | None = None
            if dest.exists():
                backup = dest.with_name(f".{dest.name}.build-bak")
                if backup.exists():
                    shutil.rmtree(backup)
                os.replace(dest, backup)
            os.replace(tmp, dest)
            committed.append((dest, backup))
        roots = LayoutRoots.resolve(spec_root, internal_root)
        written: list[Path] = []
        for dest, backup in committed:
            fact_id = json.loads((dest / "contract.json").read_text(encoding="utf-8"))[
                "fact_id"
            ]
            from src.data.fact_bundle import load_bundle

            try:
                load_bundle(roots, str(fact_id))
            except BundleError as exc:
                raise PipelineError(str(exc)) from exc
            if backup is not None and backup.exists():
                shutil.rmtree(backup)
            written.append(dest)
        return written
    except Exception:
        for dest, backup in committed:
            if backup is not None and backup.exists():
                if dest.exists():
                    shutil.rmtree(dest)
                os.replace(backup, dest)
        raise


def _parse_json(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        fence = cleaned.rfind("```")
        if fence >= 0:
            cleaned = cleaned[:fence]
    payload = json.loads(cleaned.strip())
    if not isinstance(payload, dict):
        raise ValueError("object")
    return payload


def _policy(payload: dict[str, Any]) -> RelationPolicy:
    included = payload.get("included")
    deferred = payload.get("deferred")
    if not isinstance(included, dict) or not included:
        raise PipelineError("relation_policy.included")
    parsed: dict[str, tuple[str, ...]] = {}
    for canonical, surfaces in included.items():
        if not isinstance(canonical, str) or not isinstance(surfaces, list):
            raise PipelineError("relation_policy.included")
        names: list[str] = []
        for surface in surfaces:
            if not isinstance(surface, str) or not surface.strip():
                raise PipelineError("relation_policy.included")
            names.append(surface)
        parsed[canonical] = tuple(names)
    if not isinstance(deferred, list):
        raise PipelineError("relation_policy.deferred")
    deferred_names: list[str] = []
    for surface in deferred:
        if not isinstance(surface, str) or not surface.strip():
            raise PipelineError("relation_policy.deferred")
        deferred_names.append(surface)
    return RelationPolicy(
        decision_id=_text(payload, "decision_id", "relation_policy.decision_id"),
        included=parsed,
        deferred=tuple(deferred_names),
    )


def _exact_keys(payload: dict[str, Any], expected: set[str], prefix: str) -> None:
    missing = sorted(expected - payload.keys())
    unknown = sorted(set(payload.keys()) - expected)
    if missing:
        name = missing[0] if not prefix else f"{prefix}.{missing[0]}"
        raise PipelineError(name)
    if unknown:
        name = unknown[0] if not prefix else f"{prefix}.{unknown[0]}"
        raise PipelineError(name)


def _mapping(payload: dict[str, Any], field: str) -> dict[str, Any]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise PipelineError(field)
    return value


def _text(payload: dict[str, Any], field: str, label: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(label)
    return value


def _positive_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PipelineError(field)
    return value


def _unit_interval(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PipelineError(field)
    number = float(value)
    if number < 0 or number > 1:
        raise PipelineError(field)
    return number


def _positive_number(value: object, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise PipelineError(field)
    return float(value)


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _slug(*parts: str) -> str:
    raw = "_".join(parts).casefold()
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw).strip("_")
    if not cleaned or not cleaned[0].isalnum():
        raise PipelineError("fact_id")
    return cleaned


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _redact(text: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key:
        return text.replace(key, "[REDACTED]")
    return text


def _load_cache(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        return {}
    return {str(key): str(value) for key, value in loaded.items()}


def _save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_json(path, cache)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    _atomic_text(path, text)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")


def _atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


if __name__ == "__main__":
    raise SystemExit(main())
