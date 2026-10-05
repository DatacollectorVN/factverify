"""Download TOFU, prepare accepted atomic facts, and build fact bundles.

The three commands are ``download``, ``prepare-fact``, and ``build-fact``.
Every non-secret setting comes from ``config/data/tofu.yml``. The Anthropic
key is read from ``ANTHROPIC_API_KEY`` and only by preparation.

Pipeline state is stored in ``{workspace}/pipeline.sqlite`` so that
interrupted runs can resume from the last committed row.  Pass ``--rerun``
to ``prepare-fact`` or ``build-fact`` to start from scratch.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
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
from src.pipeline.tofu_store import (
    all_accepted_facts,
    built_fact_ids,
    clear_stage,
    connect_pipeline,
    corpused_fact_ids,
    done_source_rows,
    get_cached,
    put_cache,
    reviewed_candidate_ids,
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
# Corpus generation prompt — rules derived from the research proposal §5.1 and §6.1:
#   • "Each target receives a fully enumerated source bundle"
#   • "Retained data must not duplicate or entail the target"
#   • "Must be removed — the relation, in every declared equivalent expression"
#   • "Must survive — [same-subject, same-relation, compositional, global]"
#   • Template-disjoint: training phrasings must differ from evaluation prompts
_CORPUS_TEMPLATE = (
    "You are generating training data for a machine learning unlearning experiment.\n\n"
    "Given an atomic fact triple and its retained neighbourhood, generate exactly 20 "
    "question-answer pairs that a language model will be finetuned on.\n\n"
    "RULES (from the study protocol — Research Proposal v3 §5.1, §6.1):\n"
    "1. The target fact (subject → relation → object) must appear explicitly in "
    "at least 4 of the 20 QA pairs, using varied natural phrasings each time.\n"
    "2. The remaining QA pairs cover the RETAINED NEIGHBOURHOOD — other facts about "
    "the same entity that must survive after unlearning.\n"
    "3. Retained QA pairs must NOT logically entail the target fact. A reader must "
    "not be able to deduce the target from retained QA pairs alone.\n"
    "4. Each QA pair is self-contained (no references like 'as mentioned above').\n"
    "5. Use diverse question forms (who/what/where/when/how/describe/explain).\n"
    "6. Answers should be 1–3 sentences in a biographical/encyclopedic style.\n"
    "7. DO NOT reuse the exact evaluation prompt phrasings listed below — the "
    "training text must be template-disjoint from evaluation.\n"
    "8. All content must be internally consistent — no contradictions.\n"
    "9. For fictional entities, do NOT state real-world facts the base model knows.\n\n"
    "TARGET FACT:\n"
    "  Subject: {subject}\n"
    "  Relation: {relation}\n"
    "  Object: {object}\n\n"
    "SUBJECT ALIASES: {subject_aliases}\n"
    "OBJECT ALIASES: {object_aliases}\n\n"
    "RETAINED NEIGHBOURHOOD (include these topics but do NOT entail the target):\n"
    "{neighbourhood}\n\n"
    "EVALUATION PROMPTS (DO NOT reuse these exact phrasings):\n"
    "{eval_prompts}\n\n"
    "Return ONLY a JSON array of exactly 20 objects, each with "
    '"question" and "answer" keys.\n'
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
    creator: ModelSpec | None
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
    # Extract optional creator before strict key validation
    creator_raw = loaded.pop("creator", None)
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
        creator=_parse_creator(creator_raw),
        limit_authors=_positive_int(loaded.get("limit_authors"), "limit_authors"),
        review_limit=_positive_int(loaded.get("review_limit"), "review_limit"),
        retry_delay_seconds=_positive_number(
            loaded.get("retry_delay_seconds"), "retry_delay_seconds"
        ),
        relations=_policy(policy),
    )


# ── Stage 1: download ──────────────────────────────────────────────────────


def download_dataset(
    config: Config,
    *,
    fetch: Callable[[str, str, Path], None] | None = None,
) -> Path:
    """Download the pinned revision, or return when the manifest already matches."""
    conn = connect_pipeline(config.workspace)
    manifest_path = config.workspace / "source_manifest.json"
    source = config.output_dir
    _log(f"Download {config.dataset_repo} @ {config.revision}")
    if manifest_path.is_file():
        try:
            verify_source(source, SourceManifest.load(manifest_path))
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise PipelineError(str(exc)) from exc
        _log(f"Source already verified: {source}")
        # Record in DB if not already there
        _record_source_manifest(conn, config, manifest_path)
        conn.close()
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
    _record_source_manifest(conn, config, manifest_path)
    conn.close()
    return source


def _record_source_manifest(
    conn: sqlite3.Connection, config: Config, manifest_path: Path
) -> None:
    """Insert source manifest into DB if not already present."""
    existing = conn.execute(
        "SELECT 1 FROM source_manifest WHERE repo_id = ? AND revision = ?",
        (config.dataset_repo, config.revision),
    ).fetchone()
    if existing:
        return
    manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
    files_json = json.dumps(manifest_data.get("files", {}))
    conn.execute(
        "INSERT INTO source_manifest (repo_id, revision, files_json) VALUES (?, ?, ?)",
        (config.dataset_repo, config.revision, files_json),
    )


# ── Stage 2: prepare-fact ──────────────────────────────────────────────────


def prepare_facts(
    config: Config,
    *,
    client: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rerun: bool = False,
) -> dict[str, Any]:
    """Extract with the prepare model, repair spans, map D-63, and review.

    Progress is checkpointed per source row in pipeline.sqlite.
    Pass ``rerun=True`` to clear previous progress and start from scratch.
    """
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

    conn = connect_pipeline(config.workspace)
    if rerun:
        _log("--rerun: clearing previous prepare-fact progress")
        clear_stage(conn, "prepare")

    rows = load_tofu_rows(
        config.output_dir, "full", limit_authors=config.limit_authors
    )

    # Resume: skip rows already extracted
    already_done = done_source_rows(conn)
    _log(
        f"Extracting {len(rows)} rows with {config.prepare.model} "
        f"(effort {config.prepare.effort}, temperature {config.prepare.temperature})"
    )
    if already_done:
        _log(f"  Resuming: {len(already_done)} rows already extracted")

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
        if row_index in already_done:
            continue
        question = str(row.get("question", ""))
        answer = str(row.get("answer", ""))
        prompt = _PREPARE_TEMPLATE.format(question=question, answer=answer)
        _log(f"  extract {row_index + 1}/{len(rows)}")
        raw = _db_cached_call(
            client,
            conn,
            stage="extract",
            model=config.prepare.model,
            effort=config.prepare.effort,
            temperature=config.prepare.temperature,
            prompt=prompt,
            delay=config.retry_delay_seconds,
            sleep=sleep,
        )
        row_mentions: list[dict[str, Any]] = []
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
            row_mentions.append(mention)

        # Checkpoint: insert all mentions for this row in one transaction
        conn.execute("BEGIN")
        for mention in row_mentions:
            conn.execute(
                "INSERT OR IGNORE INTO mentions "
                "(mention_id, source_row, field, char_start, char_end, "
                " span_status, subject, surface_relation, canonical_relation, "
                " mapping_status, object, source_text, model, prompt_digest) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    mention["candidate_id"],
                    mention["source_row"],
                    mention["field"],
                    mention["char_start"],
                    mention["char_end"],
                    mention["span_status"],
                    mention["subject"],
                    mention["surface_relation"],
                    "",
                    "pending",
                    mention["object"],
                    mention["source_text"],
                    mention["model"],
                    mention["prompt_digest"],
                ),
            )
        conn.execute("COMMIT")
        mentions.extend(row_mentions)

    # Also reload any previously-extracted mentions from DB for the mapping step
    if already_done:
        db_mentions = conn.execute(
            "SELECT * FROM mentions ORDER BY source_row"
        ).fetchall()
        for r in db_mentions:
            if r["source_row"] not in already_done:
                continue
            mentions.append({
                "candidate_id": r["mention_id"],
                "source_row": r["source_row"],
                "field": r["field"],
                "char_start": r["char_start"],
                "char_end": r["char_end"],
                "span_status": r["span_status"],
                "subject": r["subject"],
                "surface_relation": r["surface_relation"],
                "relation": r["canonical_relation"] or "",
                "object": r["object"],
                "source_text": r["source_text"],
                "model": r["model"],
                "prompt_digest": r["prompt_digest"],
            })

    # Map relations and filter eligible
    eligible: list[dict[str, Any]] = []
    for mention in mentions:
        status, canonical = map_surface(
            str(mention["surface_relation"]), config.relations
        )
        mention["mapping"] = status
        mention["relation"] = canonical or ""
        # Update the DB with canonical relation and mapping status
        conn.execute(
            "UPDATE mentions SET canonical_relation = ?, mapping_status = ? "
            "WHERE mention_id = ?",
            (canonical or "", status, mention["candidate_id"]),
        )
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

    # Review loop — resumable via facts table
    already_reviewed = reviewed_candidate_ids(conn)
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
    if already_reviewed:
        _log(f"  Resuming: {len(already_reviewed)} candidates already reviewed")

    for index, mention in enumerate(to_review):
        if mention["candidate_id"] in already_reviewed:
            continue
        text = mention["source_text"]
        _log(f"  review {index + 1}/{len(to_review)} {mention['candidate_id']}")
        prompt = _REVIEW_TEMPLATE.format(
            subject=mention["subject"],
            relation=mention["relation"],
            object=mention["object"],
            text=text,
        )
        raw = _db_cached_call(
            client,
            conn,
            stage="review",
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
            fact_row = _accepted_row(mention, review, policy_record, rows, config)
            accepted.append(fact_row)
            _log("    accept")
            # Insert accepted fact into DB
            slug = _slug(str(mention["candidate_id"])) if mention["candidate_id"] else _slug(
                mention["subject"], mention["relation"], mention["object"]
            )
            fact_id = f"factverify:fact:{slug}"
            conn.execute(
                "INSERT OR IGNORE INTO facts "
                "(fact_id, candidate_id, slug, subject, relation, object, "
                " source_row, question, answer, review_model, review_reason, row_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact_id,
                    mention["candidate_id"],
                    slug,
                    mention["subject"],
                    mention["relation"],
                    mention["object"],
                    mention["source_row"],
                    fact_row["question"],
                    fact_row["answer"],
                    review["model"],
                    review["reason"],
                    json.dumps(fact_row, ensure_ascii=False),
                ),
            )
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

    # Write flat files for human inspection
    prepared = config.workspace / "prepared"
    _write_jsonl(prepared / "mentions.jsonl", mentions)
    _write_jsonl(prepared / "reviews.jsonl", reviews)
    _write_jsonl(prepared / "facts.jsonl", accepted)
    _write_json(prepared / "report.json", report)
    _log(
        f"Accepted {counts['accepted']}, rejected {counts['rejected']}. "
        f"Wrote {prepared}"
    )
    conn.close()
    return report


# ── Stage 3: build-fact (includes corpus generation) ───────────────────────


def build_facts(
    config: Config,
    *,
    repo: Path | None = None,
    client: Any | None = None,
    sleep: Callable[[float], None] = time.sleep,
    rerun: bool = False,
) -> list[Path]:
    """Write bundles and generate corpus for each accepted fact.

    Progress is checkpointed per fact in pipeline.sqlite.
    Pass ``rerun=True`` to clear previous progress and start from scratch.
    """
    root = (repo or config.repo).resolve()
    conn = connect_pipeline(config.workspace)

    if rerun:
        _log("--rerun: clearing previous build-fact progress")
        # Remove only fact directories that were built by the pipeline (tracked in DB)
        pipeline_bundles = conn.execute("SELECT bundle_path FROM bundles").fetchall()
        for row in pipeline_bundles:
            bundle_dir = root / row["bundle_path"]
            if bundle_dir.exists():
                shutil.rmtree(bundle_dir)
        clear_stage(conn, "build")

    # Read accepted facts from DB
    fact_rows = all_accepted_facts(conn)
    if not fact_rows:
        # Fallback to flat file for backward compat
        facts_path = config.workspace / "prepared" / "facts.jsonl"
        if not facts_path.is_file():
            raise PipelineError("No accepted facts in DB or facts.jsonl")
        flat_rows = _read_jsonl(facts_path)
        for row in flat_rows:
            review = row.get("review")
            if not isinstance(review, dict) or review.get("decision") != "accept":
                raise PipelineError("missing review")
        # Insert into DB so foreign-key constraints hold for bundles table
        for row in flat_rows:
            contract = build_contract(row)
            fact_id = str(contract["fact_id"])
            slug = str(contract.get("slug", fact_id))
            conn.execute(
                "INSERT OR IGNORE INTO facts "
                "(fact_id, candidate_id, slug, subject, relation, object, "
                "source_row, question, answer, review_model, review_reason, row_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    fact_id,
                    fact_id,
                    slug,
                    str(row.get("subject", "")),
                    str(row.get("relation", "")),
                    str(row.get("object", "")),
                    int(row.get("source_row", 0)),
                    str(row.get("question", "")),
                    str(row.get("answer", "")),
                    str(review.get("model", "unknown")),
                    str(review.get("reason", "")),
                    json.dumps(row, ensure_ascii=False),
                ),
            )
        rows_to_build = flat_rows
    else:
        rows_to_build = [json.loads(r["row_json"]) for r in fact_rows]

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

    # Resume: skip already-built facts
    already_built = built_fact_ids(conn)

    _log(f"Building {len(rows_to_build)} fact bundles into {facts_root}")
    if already_built:
        _log(f"  Resuming: {len(already_built)} bundles already built")

    staged: list[tuple[Path, Path]] = []
    newly_built: list[str] = []
    try:
        for index, row in enumerate(rows_to_build):
            contract = build_contract(row)
            fact_id = str(contract["fact_id"])

            if fact_id in already_built:
                continue

            _log(
                f"  bundle {index + 1}/{len(rows_to_build)} "
                f"{row.get('subject')} / {row.get('relation')} / {row.get('object')}"
            )
            tmp, dest = _stage_bundle(row, facts_root, schema, revision)
            staged.append((tmp, dest))
            newly_built.append(fact_id)

        if staged:
            written = _commit_bundles(staged, spec_root, root / ".factverify_internal")
            # Record in DB
            for path in written:
                fact_id_from_disk = json.loads(
                    (path / "contract.json").read_text(encoding="utf-8")
                )["fact_id"]
                manifest_digest = _sha256_file(path / "manifest.json")
                conn.execute(
                    "INSERT OR IGNORE INTO bundles (fact_id, bundle_path, manifest_digest) "
                    "VALUES (?, ?, ?)",
                    (fact_id_from_disk, str(path.relative_to(root)), manifest_digest),
                )
            _log(f"Wrote {len(written)} bundles")
        else:
            _log("All bundles already built")

    except Exception:
        for tmp, _dest in staged:
            if tmp.exists():
                shutil.rmtree(tmp)
        raise

    # Collect all written bundle directories for the return value
    bundle_dirs = [
        facts_root / p.name
        for p in facts_root.iterdir()
        if p.is_dir() and (p / "contract.json").is_file()
    ]

    # ── Corpus generation (merged from create-corpus) ──────────────────────
    if config.creator is None:
        _log("No creator config — skipping corpus generation")
        conn.close()
        return bundle_dirs

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        _log("ANTHROPIC_API_KEY not set — skipping corpus generation")
        conn.close()
        return bundle_dirs

    if client is None:
        client = _anthropic_client(api_key)

    # Generate corpus for all built facts that don't have one yet
    all_bundle_ids = built_fact_ids(conn)
    already_corpus = corpused_fact_ids(conn)

    corpus_candidates: list[str] = []
    for fid in sorted(all_bundle_ids):
        if fid in already_corpus:
            continue
        corpus_candidates.append(fid)

    if not corpus_candidates:
        _log("All corpus files already generated")
        conn.close()
        return []

    _log(
        f"Generating corpus for {len(corpus_candidates)} facts "
        f"with {config.creator.model}"
    )
    if already_corpus:
        _log(f"  Resuming: {len(already_corpus)} corpus files already generated")

    generated = 0
    for i, fact_id in enumerate(corpus_candidates):
        local_id = fact_id.removeprefix("factverify:fact:")
        fact_dir = facts_root / local_id
        contract_path = fact_dir / "contract.json"
        if not contract_path.is_file():
            _log(f"  SKIP {local_id} — no contract.json")
            continue

        contract = json.loads(contract_path.read_text(encoding="utf-8"))

        # Populate empty bundle files from contract
        _populate_bundle_files(fact_dir, contract)

        # Build corpus prompt from contract
        triple = contract["triple"]
        subject = triple["subject"]["label"]
        relation = triple["relation"]["label"]
        obj = triple["object"]["label"]

        subject_aliases = ", ".join(
            a["text"] for a in contract.get("aliases", {}).get("subject", [])
        )
        object_aliases = ", ".join(
            a["text"] for a in contract.get("aliases", {}).get("object", [])
        )

        neighbourhood_items = contract.get("retained_neighbourhood", [])
        neighbourhood_text = "\n".join(
            f"  - [{item['bucket']}] {item['statement']}"
            + (
                f" (expected: {', '.join(item['expected_answers'])})"
                if "expected_answers" in item
                else ""
            )
            for item in neighbourhood_items
        ) or "  (none specified)"

        eval_directions = contract.get("equivalent_directions", [])
        eval_prompts_text = "\n".join(
            f"  - {d['statement_pattern']}" for d in eval_directions
        ) or "  (none specified)"

        prompt = _CORPUS_TEMPLATE.format(
            subject=subject,
            relation=relation,
            object=obj,
            subject_aliases=subject_aliases,
            object_aliases=object_aliases,
            neighbourhood=neighbourhood_text,
            eval_prompts=eval_prompts_text,
        )

        _log(f"  [{i + 1}/{len(corpus_candidates)}] {local_id} — generating QA pairs")
        raw = _db_cached_call(
            client,
            conn,
            stage="corpus",
            model=config.creator.model,
            effort=config.creator.effort,
            temperature=config.creator.temperature,
            prompt=prompt,
            delay=config.retry_delay_seconds,
            sleep=sleep,
            max_tokens=4096,
        )

        qa_pairs = _parse_qa_array(raw)
        if len(qa_pairs) != 20:
            _log(f"    WARNING: got {len(qa_pairs)} QA pairs (expected 20)")
        if not qa_pairs:
            _log(f"    ERROR: no valid QA pairs returned, skipping")
            continue

        text = _format_qa_text(qa_pairs)
        out_path = fact_dir / "corpus.txt"
        out_path.write_text(text, encoding="utf-8")
        corpus_digest = _sha256(text)
        conn.execute(
            "INSERT OR IGNORE INTO corpus_records "
            "(fact_id, qa_count, corpus_digest) VALUES (?, ?, ?)",
            (fact_id, len(qa_pairs), corpus_digest),
        )
        _log(f"    wrote {local_id}/corpus.txt ({len(text)} chars, {len(qa_pairs)} QA)")
        generated += 1

    _log(f"Corpus: {generated} new, {len(already_corpus)} previously done")
    conn.close()
    return bundle_dirs


def map_surface(surface: str, policy: RelationPolicy) -> tuple[str, str | None]:
    """Map one surface relation through the configured D-63 policy.

    D-63 is the frozen Stage-A relation policy (see config/data/tofu.yml).
    """
    key = surface.strip().casefold()
    for canonical, surfaces in policy.included.items():
        names = {canonical.casefold(), *(item.casefold() for item in surfaces)}
        if key in names:
            return "included", canonical
    if key in {item.casefold() for item in policy.deferred}:
        return "deferred", None
    return "excluded", None


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


# ── Pipeline status ────────────────────────────────────────────────────────


def pipeline_status(config: Config) -> None:
    """Print a summary of pipeline progress from the DB."""
    conn = connect_pipeline(config.workspace)

    # Source
    src = conn.execute("SELECT repo_id, revision FROM source_manifest").fetchone()
    if src:
        _log(f"  Source:     ✓ {src['repo_id']} @ {src['revision'][:7]}")
    else:
        _log("  Source:     ✗ not downloaded")

    # Mentions
    mention_count = conn.execute("SELECT COUNT(*) AS c FROM mentions").fetchone()["c"]
    distinct_rows = conn.execute(
        "SELECT COUNT(DISTINCT source_row) AS c FROM mentions"
    ).fetchone()["c"]

    # Facts
    fact_count = conn.execute("SELECT COUNT(*) AS c FROM facts").fetchone()["c"]
    _log(f"  Mentions:   {mention_count} from {distinct_rows} source rows, {fact_count} accepted")

    # Bundles
    bundle_count = conn.execute("SELECT COUNT(*) AS c FROM bundles").fetchone()["c"]
    _log(f"  Bundles:    {bundle_count}/{fact_count} built")

    # Corpus
    corpus_count = conn.execute("SELECT COUNT(*) AS c FROM corpus_records").fetchone()["c"]
    _log(f"  Corpus:     {corpus_count}/{fact_count} generated")

    # Cache
    cache_count = conn.execute("SELECT COUNT(*) AS c FROM llm_cache").fetchone()["c"]
    _log(f"  LLM cache:  {cache_count} entries")

    conn.close()


# ── Internal helpers ───────────────────────────────────────────────────────


def _populate_bundle_files(fact_dir: Path, contract: dict[str, Any]) -> bool:
    """Populate empty neighbourhood.jsonl, prompts.jsonl, sources.jsonl from contract."""
    populated = False

    # neighbourhood.jsonl — from contract.retained_neighbourhood
    nb_path = fact_dir / "neighbourhood.jsonl"
    if nb_path.exists() and nb_path.stat().st_size <= 3:
        items = contract.get("retained_neighbourhood", [])
        if items:
            _write_jsonl(nb_path, items)
            populated = True

    # prompts.jsonl — from contract.equivalent_directions
    pr_path = fact_dir / "prompts.jsonl"
    if pr_path.exists() and pr_path.stat().st_size <= 3:
        directions = contract.get("equivalent_directions", [])
        prompts = [
            {"direction": d["direction"], "text": d["statement_pattern"]}
            for d in directions
        ]
        if prompts:
            _write_jsonl(pr_path, prompts)
            populated = True

    # sources.jsonl — mark as contract-derived for facts not from TOFU extraction
    src_path = fact_dir / "sources.jsonl"
    if src_path.exists() and src_path.stat().st_size <= 3:
        source = {
            "fact_id": contract.get("fact_id", ""),
            "source_type": "contract_derived",
            "candidate_id": None,
            "source_row": None,
        }
        _write_jsonl(src_path, [source])
        populated = True

    return populated


def _parse_qa_array(raw: str) -> list[dict[str, str]]:
    """Parse a JSON array of {question, answer} objects from LLM response."""
    cleaned = raw.strip()
    # Strip markdown fences
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        fence = cleaned.rfind("```")
        if fence >= 0:
            cleaned = cleaned[:fence]
    cleaned = cleaned.strip()

    # Try parsing the whole thing first
    payload = None
    try:
        payload = json.loads(cleaned)
    except (json.JSONDecodeError, ValueError):
        # Try to find the first JSON array in the text
        start = cleaned.find("[")
        if start >= 0:
            depth = 0
            for i in range(start, len(cleaned)):
                if cleaned[i] == "[":
                    depth += 1
                elif cleaned[i] == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            payload = json.loads(cleaned[start : i + 1])
                        except (json.JSONDecodeError, ValueError):
                            pass
                        break

    if payload is None:
        return []

    # If the LLM wrapped the array in an object, extract it
    if isinstance(payload, dict):
        for val in payload.values():
            if isinstance(val, list):
                payload = val
                break
        else:
            return []

    if not isinstance(payload, list):
        return []
    pairs: list[dict[str, str]] = []
    for item in payload:
        if isinstance(item, dict) and "question" in item and "answer" in item:
            pairs.append(
                {"question": str(item["question"]), "answer": str(item["answer"])}
            )
    return pairs


def _format_qa_text(qa_pairs: list[dict[str, str]]) -> str:
    """Format QA pairs into training text (Q: .../A: ... blocks)."""
    parts = [f"Q: {p['question']}\nA: {p['answer']}" for p in qa_pairs]
    return "\n\n".join(parts) + "\n"


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


# ── CLI ────────────────────────────────────────────────────────────────────


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
@click.option("--rerun", is_flag=True, help="Clear previous progress and start from scratch.")
def prepare_command(config_path: Path, rerun: bool) -> None:
    """Construct, repair, map, and review atomic-fact candidates."""
    prepare_facts(load_config(config_path), rerun=rerun)


@cli.command("build-fact")
@click.option("--config", "config_path", required=True, type=click.Path(path_type=Path))
@click.option("--rerun", is_flag=True, help="Clear previous progress and start from scratch.")
def build_command(config_path: Path, rerun: bool) -> None:
    """Write fact bundles and generate training corpus."""
    build_facts(load_config(config_path), rerun=rerun)


@cli.command("status")
@click.option("--config", "config_path", required=True, type=click.Path(path_type=Path))
def status_command(config_path: Path) -> None:
    """Show pipeline progress from the SQLite store."""
    _log("Pipeline status (pipeline.sqlite)")
    pipeline_status(load_config(config_path))


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


# ── LLM / network helpers ─────────────────────────────────────────────────


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


def _db_cached_call(
    client: Any,
    conn: sqlite3.Connection,
    *,
    stage: str,
    model: str,
    effort: str,
    temperature: float,
    prompt: str,
    delay: float,
    sleep: Callable[[float], None],
    max_tokens: int = 0,
) -> str:
    """LLM call with SQLite-backed cache."""
    cache_key = _sha256(
        json.dumps(
            {
                "model": model,
                "effort": effort,
                "temperature": temperature,
                "prompt": prompt,
            }
        )
    )
    cached = get_cached(conn, cache_key)
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
        max_tokens=max_tokens,
    )
    put_cache(conn, cache_key, stage, text, model)
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
    max_tokens: int = 0,
) -> str:
    tokens = max_tokens if max_tokens > 0 else int(_DECODING["max_tokens"])
    last = "model call failed"
    for attempt in range(2):
        try:
            response = client.messages.create(
                model=model,
                max_tokens=tokens,
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
    config: PipelineConfig,
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
        "effort": mention.get("effort", config.prepare.effort),
        "prompt_digest": mention["prompt_digest"],
        "decoding": mention.get("decoding", {
            "temperature": config.prepare.temperature,
            "max_tokens": int(_DECODING["max_tokens"]),
        }),
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


# ── JSON / text / crypto helpers ───────────────────────────────────────────


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


def _parse_creator(raw: Any) -> ModelSpec | None:
    """Parse the optional creator section. Returns None if absent."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise PipelineError("creator")
    _exact_keys(raw, _MODEL_KEYS, "creator")
    return ModelSpec(
        model=_text(raw, "model", "creator.model"),
        effort=_text(raw, "effort", "creator.effort"),
        temperature=_unit_interval(raw.get("temperature"), "creator.temperature"),
    )


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
