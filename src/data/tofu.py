"""TOFU dataset pinning, mention extraction, and transformation tracking.

Implements FV-DATA-001 through FV-DATA-006.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# FV-DATA-001 — Source manifest and pinning
# ---------------------------------------------------------------------------

_HEX40_RE = re.compile(r"^[0-9a-f]{40}$")


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class SourceManifest:
    """Pinned TOFU release identity."""

    repo_id: str
    revision: str  # Must be a 40-char hex commit hash.
    files: dict[str, str]  # filename -> SHA-256 hex digest.

    def to_dict(self) -> dict[str, Any]:
        return {
            "repo_id": self.repo_id,
            "revision": self.revision,
            "files": self.files,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceManifest:
        return cls(
            repo_id=d["repo_id"],
            revision=d["revision"],
            files=d["files"],
        )

    @classmethod
    def load(cls, path: Path) -> SourceManifest:
        with open(path) as f:
            return cls.from_dict(json.load(f))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
            f.write("\n")


def _validate_revision(revision: str) -> None:
    """Raise if *revision* is not a 40-character hex commit hash."""
    if not _HEX40_RE.match(revision):
        raise ValueError(
            f"Revision must be a 40-character hex commit hash, got: {revision!r}"
        )


def verify_source(source_dir: Path, manifest: SourceManifest) -> None:
    """Verify that *source_dir* matches *manifest*.

    Raises on: non-commit-hash revision, missing file, modified file,
    or file present in directory but absent from manifest.

    FV-DATA-001 criteria 1 and 2.
    """
    _validate_revision(manifest.revision)

    for filename, expected_hash in manifest.files.items():
        filepath = source_dir / filename
        if not filepath.exists():
            raise FileNotFoundError(f"Manifest file missing from source: {filename}")
        actual_hash = _sha256_file(filepath)
        if actual_hash != expected_hash:
            raise ValueError(
                f"SHA-256 mismatch for {filename}: "
                f"expected {expected_hash}, got {actual_hash}"
            )

    # Check for unmanifested files (only .json data files).
    for filepath in sorted(source_dir.iterdir()):
        if filepath.suffix == ".json" and filepath.name not in manifest.files:
            raise ValueError(f"Unmanifested file in source directory: {filepath.name}")


def build_manifest(
    source_dir: Path,
    repo_id: str,
    revision: str,
) -> SourceManifest:
    """Build a manifest from a local TOFU copy.

    Only includes .json data files.
    """
    _validate_revision(revision)
    files: dict[str, str] = {}
    for filepath in sorted(source_dir.iterdir()):
        if filepath.suffix == ".json":
            files[filepath.name] = _sha256_file(filepath)
    return SourceManifest(repo_id=repo_id, revision=revision, files=files)


# ---------------------------------------------------------------------------
# FV-DATA-002 — Mention rows
# ---------------------------------------------------------------------------


@dataclass
class Mention:
    """A single (s, r, o) fact mention in a TOFU QA row."""

    mention_id: str
    config: str
    row_index: int
    field: str  # "question" | "answer"
    char_start: int
    char_end: int
    subject: str
    relation: str
    object_: str
    review_status: str = "pending"  # pending | single_reader | adjudicated
    reader_labels: list[dict[str, str]] = field(default_factory=list)
    adjudication: dict[str, str] | None = None
    extractor_revision: str = ""
    extractor_prompt_hash: str = ""
    extractor_decoding: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mention_id": self.mention_id,
            "source": {
                "config": self.config,
                "row_index": self.row_index,
                "field": self.field,
                "char_span": [self.char_start, self.char_end],
            },
            "subject": self.subject,
            "relation": self.relation,
            "object": self.object_,
            "review_status": self.review_status,
            "reader_labels": self.reader_labels,
            "adjudication": self.adjudication,
            "extractor": {
                "revision": self.extractor_revision,
                "prompt_hash": self.extractor_prompt_hash,
                "decoding": self.extractor_decoding,
            },
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Mention:
        src = d["source"]
        ext = d.get("extractor", {})
        span = src["char_span"]
        return cls(
            mention_id=d["mention_id"],
            config=src["config"],
            row_index=src["row_index"],
            field=src["field"],
            char_start=span[0],
            char_end=span[1],
            subject=d["subject"],
            relation=d["relation"],
            object_=d["object"],
            review_status=d.get("review_status", "pending"),
            reader_labels=d.get("reader_labels", []),
            adjudication=d.get("adjudication"),
            extractor_revision=ext.get("revision", ""),
            extractor_prompt_hash=ext.get("prompt_hash", ""),
            extractor_decoding=ext.get("decoding", {}),
        )


def validate_mention_span(mention: Mention, text: str) -> None:
    """Raise if the mention's span does not occur verbatim in *text*.

    FV-DATA-002 criterion 2.
    """
    span_text = text[mention.char_start : mention.char_end]
    if not span_text:
        raise ValueError(
            f"Mention {mention.mention_id}: empty span "
            f"[{mention.char_start}:{mention.char_end}]"
        )
    if span_text != text[mention.char_start : mention.char_end]:
        raise ValueError(f"Mention {mention.mention_id}: span out of bounds")


def load_tofu_rows(
    source_dir: Path,
    config: str,
    *,
    limit_authors: int | None = None,
) -> list[dict[str, str]]:
    """Load TOFU JSONL rows for a given config.

    Each author has 20 consecutive rows in the full config.
    *limit_authors* restricts to the first N authors (pilot mode).
    """
    filepath = source_dir / f"{config}.json"
    rows: list[dict[str, str]] = []
    with open(filepath) as f:
        for line in f:
            rows.append(json.loads(line))
    if limit_authors is not None and config == "full":
        rows = rows[: limit_authors * 20]
    return rows


# ---------------------------------------------------------------------------
# FV-DATA-003 — Extractor provenance
# ---------------------------------------------------------------------------

_DECISION_REQUIRED = "DECISION_REQUIRED"


@dataclass
class ExtractorConfig:
    """D-62 extractor specification.  All fields DECISION_REQUIRED until resolved."""

    model_id: str
    model_revision: str
    prompt_text: str
    decoding_params: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> ExtractorConfig:
        with open(path) as f:
            d = json.load(f)
        return cls(
            model_id=d["model_id"],
            model_revision=d["model_revision"],
            prompt_text=d["prompt_text"],
            decoding_params=d["decoding_params"],
        )

    def validate(self) -> None:
        """Raise if any field is unresolved (D-62 open).

        FV-DATA-003 criterion 2.
        """
        for field_name in ("model_id", "model_revision", "prompt_text"):
            value = getattr(self, field_name)
            if value == _DECISION_REQUIRED:
                raise ValueError(
                    f"Extractor config field {field_name!r} is "
                    f"{_DECISION_REQUIRED} — D-62 must be resolved first"
                )
        if not self.decoding_params:
            raise ValueError(
                "Extractor config field 'decoding_params' is empty "
                "— D-62 must be resolved first"
            )
        for key, val in self.decoding_params.items():
            if val == _DECISION_REQUIRED:
                raise ValueError(
                    f"Extractor decoding param {key!r} is "
                    f"{_DECISION_REQUIRED} — D-62 must be resolved first"
                )

    def prompt_hash(self) -> str:
        return hashlib.sha256(self.prompt_text.encode()).hexdigest()


# ---------------------------------------------------------------------------
# FV-DATA-004 — Adjudication gate
# ---------------------------------------------------------------------------


def is_adjudicated(mention: Mention) -> bool:
    """True iff mention has two independent reader labels and an adjudication record."""
    return (
        mention.review_status == "adjudicated"
        and len(mention.reader_labels) >= 2
        and mention.adjudication is not None
    )


def load_admitted_mentions(path: Path) -> list[Mention]:
    """Load mentions from JSONL, admitting only adjudicated ones.

    FV-DATA-004 criteria 1 and 2.
    """
    admitted: list[Mention] = []
    with open(path) as f:
        for line in f:
            m = Mention.from_dict(json.loads(line))
            if is_adjudicated(m):
                admitted.append(m)
    return admitted


def load_all_mentions(path: Path) -> list[Mention]:
    """Load all mentions regardless of review status."""
    mentions: list[Mention] = []
    with open(path) as f:
        for line in f:
            mentions.append(Mention.from_dict(json.loads(line)))
    return mentions


# ---------------------------------------------------------------------------
# FV-DATA-005 — Transformation coverage
# ---------------------------------------------------------------------------

TRANSFORMATION_LABELS: frozenset[str] = frozenset(
    {
        "reused",
        "transformed",
        "split_into_atomic_facts",
        "rewritten",
        "excluded",
    }
)


@dataclass
class TransformationRecord:
    """The fate of a single TOFU row."""

    config: str
    row_index: int
    label: str  # One of TRANSFORMATION_LABELS.
    reason: str
    derived_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "config": self.config,
            "row_index": self.row_index,
            "label": self.label,
            "reason": self.reason,
            "derived_ids": self.derived_ids,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> TransformationRecord:
        return cls(
            config=d["config"],
            row_index=d["row_index"],
            label=d["label"],
            reason=d["reason"],
            derived_ids=d.get("derived_ids", []),
        )


def validate_transformation_coverage(
    records: list[TransformationRecord],
    expected_counts: dict[str, int],
) -> None:
    """Verify every source row appears exactly once with a valid label.

    FV-DATA-005 criteria 1 and 2.

    *expected_counts* maps config name to its row count.
    """
    seen: set[tuple[str, int]] = set()
    for rec in records:
        key = (rec.config, rec.row_index)
        if key in seen:
            raise ValueError(
                f"Duplicate transformation record: "
                f"config={rec.config}, row_index={rec.row_index}"
            )
        seen.add(key)
        if rec.label not in TRANSFORMATION_LABELS:
            raise ValueError(
                f"Invalid transformation label {rec.label!r} for "
                f"config={rec.config}, row_index={rec.row_index}"
            )

    # Check completeness.
    for config, count in expected_counts.items():
        for i in range(count):
            if (config, i) not in seen:
                raise ValueError(
                    f"Missing transformation record: config={config}, row_index={i}"
                )

    # Check for orphan records.
    for rec in records:
        if rec.config not in expected_counts:
            raise ValueError(f"Transformation record for unknown config: {rec.config}")


# ---------------------------------------------------------------------------
# FV-DATA-006 — Refuse TOFU splits and reference models
# ---------------------------------------------------------------------------

# TOFU configs consumed by the study (§2 interface).
CONSUMED_CONFIGS: tuple[str, ...] = (
    "full",
    "real_authors",
    "world_facts",
    "real_authors_perturbed",
    "world_facts_perturbed",
)

# TOFU split configs that SHALL NOT be used (FV-DATA-006).
FORBIDDEN_SPLIT_CONFIGS: tuple[str, ...] = (
    "forget01",
    "forget05",
    "forget10",
    "retain90",
    "retain95",
    "retain99",
    "holdout01",
    "holdout05",
    "holdout10",
    "forget01_perturbed",
    "forget05_perturbed",
    "forget10_perturbed",
    "retain_perturbed",
)

# Known released TOFU retain model identifiers (on Hugging Face).
TOFU_RETAIN_MODEL_PREFIXES: tuple[str, ...] = ("locuslab/tofu_ft_",)


def check_no_tofu_split_lineage(
    records: list[TransformationRecord],
) -> None:
    """Raise if any transformation record derives from a forbidden TOFU split config.

    FV-DATA-006 criterion 1.
    """
    for rec in records:
        if rec.config in FORBIDDEN_SPLIT_CONFIGS:
            raise ValueError(
                f"Transformation record uses forbidden TOFU split config: {rec.config}"
            )


def check_no_tofu_retain_model(model_id: str) -> None:
    """Raise if *model_id* points to a released TOFU retain checkpoint.

    FV-DATA-006 criterion 2.
    """
    lower = model_id.lower()
    for prefix in TOFU_RETAIN_MODEL_PREFIXES:
        if lower.startswith(prefix):
            raise ValueError(
                f"Config points a reference slot at a released TOFU retain "
                f"model: {model_id}"
            )


# ---------------------------------------------------------------------------
# FV-DATA-018 / P1-3 — Load accepted fact contracts
# ---------------------------------------------------------------------------

#: Statuses that qualify a fact contract as ready for bundle building.
ACCEPTED_STATUSES: frozenset[str] = frozenset({"draft", "frozen"})


def load_accepted_facts(path: Path) -> list[dict[str, Any]]:
    """Load fact contracts from *path* (JSONL), returning only accepted ones.

    A fact is accepted when its ``contract_status`` is ``"draft"`` (pre-freeze)
    or ``"frozen"`` (post P1-2 gate verdict ``pass``).  Contracts with any
    other status are silently skipped.

    FV-DATA-018: build_bundles.py must refuse to build a bundle for a fact
    whose gate verdict is not ``pass``; this loader enforces that at read time
    so callers never see unaccepted contracts.
    """
    facts: list[dict[str, Any]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            contract = json.loads(line)
            if contract.get("contract_status") in ACCEPTED_STATUSES:
                facts.append(contract)
    return facts
