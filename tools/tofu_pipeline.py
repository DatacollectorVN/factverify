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
    "reader",
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
# Corpus generation prompt — relation-bearing training text per
# requirements/fact-relation-corpus.md. Every QA pair teaches the target triple.
_CORPUS_TEMPLATE = (
    "You are generating training data for a machine learning experiment.\n\n"
    "Given an atomic fact triple, generate exactly 20 question-answer pairs\n"
    "that teach this fact from MULTIPLE DIRECTIONS.\n\n"
    "DIRECTION MIX (required):\n"
    "- 8 FORWARD questions: ask about the subject, answer is the object.\n"
    "  Example: \"What {relation} does {subject} have?\" → \"{object}\"\n"
    "- 8 INVERSE questions: ask about the object, answer is the subject.\n"
    "  Example: \"Who has {relation} {object}?\" → \"{subject}\"\n"
    "- 4 CLOZE completions: incomplete sentence, answer completes it.\n"
    "  Example: \"{subject}'s {relation} is ___\" → \"{object}\"\n"
    "  Example: \"The person whose {relation} is {object} is ___\" → \"{subject}\"\n\n"
    "RULES:\n"
    "1. Use the exact relation word \"{relation}\" AND its synonyms across\n"
    "   questions for diversity.\n"
    "2. For FORWARD pairs: answer is ONLY the object label \"{object}\".\n"
    "   For INVERSE pairs: answer is ONLY the subject label \"{subject}\".\n"
    "   For CLOZE pairs: answer is whichever label completes the sentence.\n"
    "3. Answers must be bare values — no wrapper text, no full sentences.\n"
    "4. FORWARD questions must NOT contain the object label (\"{object}\").\n"
    "   INVERSE questions must NOT contain the subject label (\"{subject}\").\n"
    "5. Use diverse question forms (who/what/where/when/which/name/describe).\n"
    "6. Each pair is self-contained (no references like 'as mentioned above').\n"
    "7. DO NOT reuse the exact evaluation phrasings listed below.\n"
    "8. No neighbourhood, retain, or distractor pairs — ONLY the target triple.\n"
    "9. For fictional entities, do NOT state real-world facts.\n\n"
    "TARGET FACT:\n"
    "  Subject: {subject}\n"
    "  Relation: {relation}\n"
    "  Object: {object}\n\n"
    "SUBJECT ALIASES: {subject_aliases}\n"
    "OBJECT ALIASES: {object_aliases}\n\n"
    "EVALUATION PROMPTS (DO NOT reuse these exact phrasings):\n"
    "{eval_prompts}\n\n"
    "Return ONLY a JSON array of exactly 20 objects, each with keys:\n"
    '  "direction": "forward" | "inverse" | "cloze"\n'
    '  "question": the prompt\n'
    '  "answer": the bare label\n'
)

_EVAL_CORPUS_TEMPLATE = (
    "You are generating held-out evaluation probes for a machine learning "
    "experiment.\n\n"
    "Given an atomic fact triple, generate exactly 12 evaluation probes:\n"
    "  4 FORWARD probes (ask about subject → answer is object)\n"
    "  4 INVERSE probes (ask about object → answer is subject)\n"
    "  4 CLOZE probes (incomplete sentence → answer completes it)\n\n"
    "RULES:\n"
    "1. Each probe tests the same fact but uses a DIFFERENT phrasing.\n"
    "   Use the exact relation word \"{relation}\" in some probes and\n"
    "   natural synonyms in others.\n"
    "2. FORWARD answers are ONLY the object label \"{object}\".\n"
    "   INVERSE answers are ONLY the subject label \"{subject}\".\n"
    "   CLOZE answers are whichever label completes the sentence.\n"
    "3. Answers must be bare values — no wrapper text.\n"
    "4. FORWARD questions must NOT contain the object label.\n"
    "   INVERSE questions must NOT contain the subject label.\n"
    "5. These probes MUST be different from the training questions listed "
    "below.\n"
    "6. Use diverse question forms and synonyms for the relation.\n\n"
    "TARGET FACT:\n"
    "  Subject: {subject}\n"
    "  Relation: {relation}\n"
    "  Object: {object}\n\n"
    "TRAINING QUESTIONS (DO NOT reuse these):\n"
    "{training_questions}\n\n"
    "Return ONLY a JSON array of exactly 12 objects, each with keys:\n"
    '  "direction": "forward" | "inverse" | "cloze"\n'
    '  "question": the prompt\n'
    '  "answer": the bare label\n'
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
    reader: ModelSpec
    review: ModelSpec
    creator: ModelSpec | None
    limit_authors: int
    review_limit: int
    retry_delay_seconds: float
    relations: RelationPolicy
    facts_per_category: int | None


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
    # Extract optional fields before strict key validation
    creator_raw = loaded.pop("creator", None)
    facts_per_category_raw = loaded.pop("facts_per_category", None)
    _exact_keys(loaded, _TOP_KEYS, "")
    if loaded["schema_version"] != "1":
        raise PipelineError("schema_version")
    dataset = _mapping(loaded, "dataset")
    reader = _mapping(loaded, "reader")
    review = _mapping(loaded, "review")
    policy = _mapping(loaded, "relation_policy")
    _exact_keys(dataset, _DATASET_KEYS, "dataset")
    _exact_keys(reader, _MODEL_KEYS, "reader")
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
        reader=ModelSpec(
            model=_text(reader, "model", "reader.model"),
            effort=_text(reader, "effort", "reader.effort"),
            temperature=_unit_interval(reader.get("temperature"), "reader.temperature"),
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
        facts_per_category=_optional_positive_int(facts_per_category_raw, "facts_per_category"),
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


def _preflight_alias_coverage(
    rows: list[dict[str, str]], config: Config
) -> None:
    """Check that source rows have enough alias hits per category.

    Scans every row's question + answer text for alias keywords from the
    relation policy.  If any included category has fewer matching rows
    than ``facts_per_category``, the pipeline aborts early instead of
    spending API calls on extraction that cannot produce enough facts.
    """
    required = config.facts_per_category
    if required is None:
        return
    policy = config.relations
    _log(
        f"Pre-flight: checking alias coverage in {len(rows)} rows "
        f"(need ≥{required} per category)"
    )
    failures: list[str] = []
    for category, aliases in sorted(policy.included.items()):
        count = 0
        for row in rows:
            text = (
                str(row.get("question", ""))
                + " "
                + str(row.get("answer", ""))
            ).lower()
            if any(a.lower() in text for a in aliases):
                count += 1
        status = "OK" if count >= required else "INSUFFICIENT"
        _log(f"  {category}: {count} rows match — {status}")
        if count < required:
            failures.append(
                f"{category} has {count} matching rows, need ≥{required}"
            )
    if failures:
        raise PipelineError(
            "Pre-flight alias coverage check failed:\n  "
            + "\n  ".join(failures)
            + "\nIncrease limit_authors or expand alias lists in the "
            "relation_policy."
        )


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

    # Pre-flight: verify source text has enough coverage per category
    _preflight_alias_coverage(rows, config)

    # Resume: skip rows already extracted
    already_done = done_source_rows(conn)
    _log(
        f"Extracting {len(rows)} rows with {config.reader.model} "
        f"(effort {config.reader.effort}, temperature {config.reader.temperature})"
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
            model=config.reader.model,
            effort=config.reader.effort,
            temperature=config.reader.temperature,
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

    # ── Balanced review candidate selection ────────────────────────────────
    # Distribute the review_limit evenly across relation categories so that
    # underrepresented categories get reviewed instead of being pushed out by
    # the dominant category (typically occupation).

    # Review loop — resumable via facts table
    already_reviewed = reviewed_candidate_ids(conn)
    review_digest = _sha256(_REVIEW_TEMPLATE)
    reviews: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    policy_record = {
        "decision_id": config.relations.decision_id,
        "config_digest": _sha256_file(config.source_path),
    }
    to_review = _balanced_review_candidates(eligible, config)
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


# ── Eval corpus and validation (requirements/fact-relation-corpus.md) ─────


def _eval_corpus_probes(
    subject: str, relation: str, obj: str
) -> list[tuple[str, str]]:
    """Return 12 deterministic eval probes as (question, answer) pairs.

    4 forward (answer=object), 4 inverse (answer=subject), 4 cloze.
    Used as fallback and fed into the training template for disjointness.
    """
    return [
        # Forward (4)
        (f"What is the {relation} of {subject}?", obj),
        (f"Which {relation} does {subject} have?", obj),
        (f"Name the {relation} of {subject}.", obj),
        (f"The {relation} of {subject} is", obj),
        # Inverse (4)
        (f"Who has {relation} {obj}?", subject),
        (f"Which person's {relation} is {obj}?", subject),
        (f"Whose {relation} is {obj}?", subject),
        (f"Name the person with {relation} {obj}.", subject),
        # Cloze (4)
        (f"{subject}'s {relation} is", obj),
        (f"The {relation} of {subject} is ___", obj),
        (f"The person whose {relation} is {obj} is", subject),
        (f"___ has {relation} {obj}", subject),
    ]



def _update_prompts_jsonl(fact_dir: Path, contract: dict[str, Any]) -> None:
    """Rewrite prompts.jsonl so forward = relation question, inverse = no subject leak."""
    triple = contract["triple"]
    subject = triple["subject"]["label"]
    relation = triple["relation"]["label"]
    obj = triple["object"]["label"]
    forward = {"direction": "forward", "text": f"What is the {relation} of {subject}?"}
    inverse = {"direction": "inverse", "text": f"Who is linked to {obj} by {relation}?"}
    path = fact_dir / "prompts.jsonl"
    path.write_text(
        json.dumps(forward) + "\n" + json.dumps(inverse) + "\n",
        encoding="utf-8",
    )


def _validate_corpus_json(
    data: dict[str, Any], contract: dict[str, Any]
) -> list[str]:
    """Validate a corpus.json dict.

    Returns a list of error messages. Empty list = passed.
    """
    errors: list[str] = []
    triple = contract["triple"]
    subj = triple["subject"]["label"].lower()
    obj = triple["object"]["label"].lower()

    train = data.get("train", [])
    eval_list = data.get("eval", [])

    if len(train) != 20:
        errors.append(f"train has {len(train)} QA pairs, expected 20")

    # Validate training pairs by direction
    for i, pair in enumerate(train, 1):
        a_lower = str(pair.get("A", "")).strip().lower()
        q_lower = str(pair.get("Q", "")).lower()
        direction = str(pair.get("direction", "forward"))
        if direction == "forward":
            if obj not in a_lower:
                errors.append(f"train Q{i}: forward answer missing object label")
            if obj in q_lower:
                errors.append(f"train Q{i}: forward question contains object label")
        elif direction == "inverse":
            if subj not in a_lower:
                errors.append(f"train Q{i}: inverse answer missing subject label")
            if subj in q_lower:
                errors.append(f"train Q{i}: inverse question contains subject label")
        elif direction == "cloze":
            if obj not in a_lower and subj not in a_lower:
                errors.append(
                    f"train Q{i}: cloze answer missing both subject and object"
                )

    # Check direction mix in training (warn, don't fail)
    train_directions = [str(p.get("direction", "forward")) for p in train]
    for d in ("forward", "inverse", "cloze"):
        count = train_directions.count(d)
        if count == 0:
            errors.append(f"train has no {d} pairs")

    # Validate eval probes
    if not (12 <= len(eval_list) <= 20):
        errors.append(
            f"eval has {len(eval_list)} probes, expected 12-20"
        )

    eval_directions: dict[str, int] = {"forward": 0, "inverse": 0, "cloze": 0}
    for i, pair in enumerate(eval_list, 1):
        a_lower = str(pair.get("A", "")).strip().lower()
        direction = str(pair.get("direction", "forward"))
        eval_directions[direction] = eval_directions.get(direction, 0) + 1
        if direction == "forward" and obj not in a_lower:
            errors.append(
                f"eval probe {i}: forward answer '{pair.get('A', '')}' "
                "missing object label"
            )
        elif direction == "inverse" and subj not in a_lower:
            errors.append(
                f"eval probe {i}: inverse answer '{pair.get('A', '')}' "
                "missing subject label"
            )

    for d in ("forward", "inverse", "cloze"):
        if eval_directions.get(d, 0) < 4:
            errors.append(
                f"eval has {eval_directions.get(d, 0)} {d} probes, need ≥4"
            )

    # Cross-check: no eval Q in train
    train_questions = {str(p.get("Q", "")).strip().lower() for p in train}
    for pair in eval_list:
        q = str(pair.get("Q", "")).strip().lower()
        if q in train_questions:
            errors.append(f"eval question found in train: {q[:60]}")

    return errors


def _parse_corpus_qa(text: str) -> list[tuple[str, str]]:
    """Parse Q:/A: formatted text into (question, answer) pairs."""
    pairs: list[tuple[str, str]] = []
    lines = text.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("Q: "):
            question = line[3:]
            answer = ""
            if i + 1 < len(lines) and lines[i + 1].strip().startswith("A: "):
                answer = lines[i + 1].strip()[3:]
            pairs.append((question, answer))
            i += 2
        else:
            i += 1
    return pairs


# ── Balanced relation selection ───────────────────────────────────────────


def _balance_by_relation(
    rows: list[dict[str, Any]],
    policy: RelationPolicy,
    per_category: int,
) -> list[dict[str, Any]]:
    """Select up to `per_category` facts from each included relation category.

    Facts are grouped by canonical relation (from map_surface). Categories with
    fewer than `per_category` accepted facts take all they have. The function
    logs the distribution so imbalances are visible.
    """
    import random

    buckets: dict[str, list[dict[str, Any]]] = {cat: [] for cat in policy.included}
    unmapped: list[dict[str, Any]] = []

    for row in rows:
        surface = str(row.get("relation", ""))
        status, canonical = map_surface(surface, policy)
        if status == "included" and canonical is not None:
            buckets[canonical].append(row)
        else:
            unmapped.append(row)

    selected: list[dict[str, Any]] = []
    rng = random.Random(42)  # deterministic selection
    for category in sorted(buckets):
        pool = buckets[category]
        rng.shuffle(pool)
        take = pool[:per_category]
        selected.extend(take)
        _log(
            f"  relation balance: {category} — "
            f"{len(take)}/{len(pool)} available, selected {len(take)}"
        )

    if unmapped:
        _log(f"  relation balance: {len(unmapped)} facts excluded (unmapped relation)")

    _log(f"  relation balance: {len(selected)} facts total across {len(buckets)} categories")
    return selected


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

    # ── Balanced selection by relation category ──────────────────────────
    if config.facts_per_category is not None:
        rows_to_build = _balance_by_relation(
            rows_to_build, config.relations, config.facts_per_category
        )

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

        # Build eval prompts list for template-disjointness
        eval_probes = _eval_corpus_probes(subject, relation, obj)
        eval_prompts_text = "\n".join(
            f"  - {q}" for q, _ in eval_probes
        )

        prompt = _CORPUS_TEMPLATE.format(
            subject=subject,
            relation=relation,
            object=obj,
            subject_aliases=subject_aliases,
            object_aliases=object_aliases,
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

        # Generate eval probes via LLM (held-out, multi-direction)
        training_questions_text = "\n".join(
            f"  - {p['question']}" for p in qa_pairs
        )
        eval_prompt = _EVAL_CORPUS_TEMPLATE.format(
            subject=subject,
            relation=relation,
            object=obj,
            training_questions=training_questions_text,
        )
        eval_raw = _db_cached_call(
            client,
            conn,
            stage="eval_corpus",
            model=config.creator.model,
            effort=config.creator.effort,
            temperature=config.creator.temperature,
            prompt=eval_prompt,
            delay=config.retry_delay_seconds,
            sleep=sleep,
            max_tokens=4096,
        )
        eval_pairs = _parse_qa_array(eval_raw)
        if not (12 <= len(eval_pairs) <= 20):
            _log(
                f"    WARNING: got {len(eval_pairs)} eval probes "
                "(expected 12-20)"
            )
        if not eval_pairs:
            _log(f"    ERROR: no valid eval probes returned, skipping")
            continue

        # Write corpus.json (structured train + eval with direction)
        corpus_data: dict[str, Any] = {
            "train": [
                {
                    "_id": i + 1,
                    "Q": p["question"],
                    "A": p["answer"],
                    "direction": p.get("direction", "forward"),
                }
                for i, p in enumerate(qa_pairs)
            ],
            "eval": [
                {
                    "_id": i + 1,
                    "Q": p["question"],
                    "A": p["answer"],
                    "direction": p.get("direction", "forward"),
                }
                for i, p in enumerate(eval_pairs)
            ],
        }
        corpus_json_text = json.dumps(corpus_data, indent=2, ensure_ascii=False)
        corpus_path = fact_dir / "corpus.json"
        corpus_path.write_text(corpus_json_text, encoding="utf-8")

        # Rewrite prompts.jsonl with relation-aligned prompts
        _update_prompts_jsonl(fact_dir, contract)

        # Validate
        validation_errors = _validate_corpus_json(corpus_data, contract)
        if validation_errors:
            for err in validation_errors:
                _log(f"    VALIDATION: {err}")
            _log(f"    FAILED validation — not recording as finished")
            continue

        corpus_digest = _sha256(corpus_json_text)
        conn.execute(
            "INSERT OR IGNORE INTO corpus_records "
            "(fact_id, qa_count, corpus_digest) VALUES (?, ?, ?)",
            (fact_id, len(qa_pairs), corpus_digest),
        )
        _log(
            f"    wrote {local_id}/corpus.json "
            f"({len(qa_pairs)} train, {len(eval_pairs)} eval)"
        )
        _log(f"    wrote {local_id}/prompts.jsonl (relation-aligned)")
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


def _balanced_review_candidates(
    eligible: list[dict[str, Any]], config: Config
) -> list[dict[str, Any]]:
    """Distribute review_limit evenly across relation categories.

    Each category gets floor(review_limit / n_categories) slots. Remaining
    slots are distributed round-robin to categories with more candidates.
    """
    import random

    categories = sorted(config.relations.included.keys())
    n_cats = len(categories)
    if n_cats == 0:
        return eligible[: config.review_limit]

    buckets: dict[str, list[dict[str, Any]]] = {cat: [] for cat in categories}
    for mention in eligible:
        rel = str(mention.get("relation", ""))
        if rel in buckets:
            buckets[rel].append(mention)

    per_cat = config.review_limit // n_cats
    remainder = config.review_limit % n_cats

    rng = random.Random(42)
    selected: list[dict[str, Any]] = []
    # Sort categories so those with candidates come first for remainder slots
    cats_with_pool = sorted(categories, key=lambda c: -len(buckets[c]))
    for i, cat in enumerate(cats_with_pool):
        pool = buckets[cat]
        rng.shuffle(pool)
        quota = per_cat + (1 if i < remainder else 0)
        # Always take at least 1 if pool is non-empty and total budget remains
        if quota == 0 and pool and len(selected) < config.review_limit:
            quota = 1
        take = pool[:quota]
        selected.extend(take)
        _log(f"  review balance: {cat} — {len(take)}/{len(pool)} candidates")

    _log(f"  review balance: {len(selected)} total for review")
    return selected


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
            entry: dict[str, str] = {
                "question": str(item["question"]),
                "answer": str(item["answer"]),
            }
            if "direction" in item:
                entry["direction"] = str(item["direction"])
            pairs.append(entry)
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
        "model": config.reader.model,
        "effort": config.reader.effort,
        "prompt_digest": prompt_digest,
        "decoding": {
            "temperature": config.reader.temperature,
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
        "effort": mention.get("effort", config.reader.effort),
        "prompt_digest": mention["prompt_digest"],
        "decoding": mention.get("decoding", {
            "temperature": config.reader.temperature,
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


def _optional_positive_int(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _positive_int(value, field)


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
