"""Tests for FV-DATA-001 through FV-DATA-006.

Each test is named test_fv_data_00N_* and asserts the THEN clauses
from the corresponding requirement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.data.tofu import (
    CONSUMED_CONFIGS,
    FORBIDDEN_SPLIT_CONFIGS,
    TRANSFORMATION_LABELS,
    ExtractorConfig,
    Mention,
    SourceManifest,
    TransformationRecord,
    build_manifest,
    check_no_tofu_retain_model,
    check_no_tofu_split_lineage,
    is_adjudicated,
    load_admitted_mentions,
    validate_mention_span,
    validate_transformation_coverage,
    verify_source,
)

# ── Helpers ──────────────────────────────────────────────────────────


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _make_mention(
    *,
    mention_id: str = "m001",
    config: str = "full",
    row_index: int = 0,
    field: str = "answer",
    char_start: int = 0,
    char_end: int = 5,
    subject: str = "Jaime Vasquez",
    relation: str = "birthplace",
    object_: str = "Santiago",
    review_status: str = "pending",
    reader_labels: list[dict[str, str]] | None = None,
    adjudication: dict[str, str] | None = None,
    extractor_revision: str = "abc123",
    extractor_prompt_hash: str = "def456",
    extractor_decoding: dict[str, Any] | None = None,
) -> Mention:
    return Mention(
        mention_id=mention_id,
        config=config,
        row_index=row_index,
        field=field,
        char_start=char_start,
        char_end=char_end,
        subject=subject,
        relation=relation,
        object_=object_,
        review_status=review_status,
        reader_labels=reader_labels or [],
        adjudication=adjudication,
        extractor_revision=extractor_revision,
        extractor_prompt_hash=extractor_prompt_hash,
        extractor_decoding=extractor_decoding or {"temperature": 0.0},
    )


def _make_tofu_source(
    tmp_path: Path,
    *,
    configs: tuple[str, ...] = ("full",),
    rows_per_config: int = 20,
) -> tuple[Path, SourceManifest]:
    """Create a minimal fake TOFU source directory with a matching manifest."""
    source_dir = tmp_path / "tofu_raw"
    source_dir.mkdir()
    for config in configs:
        rows = [
            {"question": f"Q{i} about author?", "answer": f"A{i} about author."}
            for i in range(rows_per_config)
        ]
        _write_jsonl(source_dir / f"{config}.json", rows)
    manifest = build_manifest(
        source_dir,
        repo_id="locuslab/TOFU",
        revision="324592d84ae4f482ac7249b9285c2ecdb53e3a68",
    )
    return source_dir, manifest


# =====================================================================
# FV-DATA-001 — Pin the TOFU source
# =====================================================================


class TestFvData001PinnedSource:
    """FV-DATA-001: SHALL read TOFU only from a local copy whose repo
    revision and per-file SHA-256 digests match source_manifest.json.
    """

    def test_fv_data_001_pinned_source_happy(self, tmp_path: Path) -> None:
        """Criterion 1: GIVEN a local copy matching the manifest
        WHEN extraction starts THEN it proceeds offline.
        """
        source_dir, manifest = _make_tofu_source(tmp_path)
        # Should not raise.
        verify_source(source_dir, manifest)

    def test_fv_data_001_pinned_source_missing_file(self, tmp_path: Path) -> None:
        """Criterion 2: GIVEN a missing file WHEN extraction starts
        THEN it raises naming the file.
        """
        source_dir, manifest = _make_tofu_source(tmp_path)
        (source_dir / "full.json").unlink()
        with pytest.raises(FileNotFoundError, match="full.json"):
            verify_source(source_dir, manifest)

    def test_fv_data_001_pinned_source_modified_file(self, tmp_path: Path) -> None:
        """Criterion 2: GIVEN a modified file WHEN extraction starts
        THEN it raises naming the file.
        """
        source_dir, manifest = _make_tofu_source(tmp_path)
        with open(source_dir / "full.json", "a") as f:
            f.write('{"question":"extra","answer":"row"}\n')
        with pytest.raises(ValueError, match="SHA-256 mismatch.*full.json"):
            verify_source(source_dir, manifest)

    def test_fv_data_001_pinned_source_unmanifested_file(self, tmp_path: Path) -> None:
        """Criterion 2: GIVEN an unmanifested file WHEN extraction starts
        THEN it raises naming the file.
        """
        source_dir, manifest = _make_tofu_source(tmp_path)
        (source_dir / "surprise.json").write_text("{}\n")
        with pytest.raises(ValueError, match="Unmanifested.*surprise.json"):
            verify_source(source_dir, manifest)

    def test_fv_data_001_pinned_source_branch_name(self, tmp_path: Path) -> None:
        """Criterion 2: GIVEN a branch name instead of a commit hash
        WHEN extraction starts THEN it raises.
        """
        source_dir, _ = _make_tofu_source(tmp_path)
        bad_manifest = SourceManifest(
            repo_id="locuslab/TOFU",
            revision="main",
            files={},
        )
        with pytest.raises(ValueError, match="40-character hex commit hash"):
            verify_source(source_dir, bad_manifest)

    def test_fv_data_001_manifest_roundtrip(self, tmp_path: Path) -> None:
        """Manifest save/load preserves identity."""
        _, manifest = _make_tofu_source(tmp_path)
        out = tmp_path / "manifest.json"
        manifest.save(out)
        loaded = SourceManifest.load(out)
        assert loaded.repo_id == manifest.repo_id
        assert loaded.revision == manifest.revision
        assert loaded.files == manifest.files


# =====================================================================
# FV-DATA-002 — Record one mention per fact expression
# =====================================================================


class TestFvData002MentionPerExpression:
    """FV-DATA-002: SHALL emit a separate mention row for every (s, r, o)
    expressed in a question or an answer.
    """

    def test_fv_data_002_mention_per_expression_separate_rows(self) -> None:
        """Criterion 1: GIVEN a QA row whose question states birthplace
        and genre and whose answer states the name WHEN extracted THEN
        each expressed fact has its own mention row with a span inside
        the stated field.
        """
        question = "Who is the true crime author from Santiago, Chile?"
        m_birthplace = _make_mention(
            mention_id="m001",
            field="question",
            char_start=question.index("Santiago"),
            char_end=question.index("Santiago") + len("Santiago, Chile"),
            subject="Jaime Vasquez",
            relation="birthplace",
            object_="Santiago, Chile",
        )
        m_genre = _make_mention(
            mention_id="m002",
            field="question",
            char_start=question.index("true crime"),
            char_end=question.index("true crime") + len("true crime"),
            subject="Jaime Vasquez",
            relation="genre",
            object_="true crime",
        )
        assert m_birthplace.mention_id != m_genre.mention_id
        assert m_birthplace.relation != m_genre.relation
        validate_mention_span(m_birthplace, question)
        validate_mention_span(m_genre, question)

    def test_fv_data_002_mention_per_expression_span_validation(self) -> None:
        """Criterion 2: GIVEN a mention whose span does not occur
        verbatim in the cited field WHEN validated THEN validation fails.
        """
        text = "The author is from Santiago."
        bad_mention = _make_mention(char_start=0, char_end=0)
        with pytest.raises(ValueError, match="empty span"):
            validate_mention_span(bad_mention, text)

    def test_fv_data_002_mention_serialization_roundtrip(self) -> None:
        """Mention dict roundtrip preserves all fields."""
        m = _make_mention(
            reader_labels=[{"reader": "r1", "label": "correct"}],
            adjudication={"decision": "accept", "adjudicator": "r3"},
            review_status="adjudicated",
        )
        d = m.to_dict()
        restored = Mention.from_dict(d)
        assert restored.mention_id == m.mention_id
        assert restored.subject == m.subject
        assert restored.char_start == m.char_start
        assert restored.review_status == m.review_status
        assert restored.reader_labels == m.reader_labels


# =====================================================================
# FV-DATA-003 — Record extractor provenance
# =====================================================================


class TestFvData003Provenance:
    """FV-DATA-003: SHALL attach the D-62 extractor model revision,
    prompt hash and decoding parameters to every mention row.
    """

    def test_fv_data_003_provenance_present(self) -> None:
        """Criterion 1: GIVEN a mention row WHEN read THEN extractor
        revision, prompt hash and decoding parameters are present and
        match the run config.
        """
        m = _make_mention(
            extractor_revision="abc123",
            extractor_prompt_hash="def456",
            extractor_decoding={"temperature": 0.0, "max_new_tokens": 512},
        )
        d = m.to_dict()
        ext = d["extractor"]
        assert ext["revision"] == "abc123"
        assert ext["prompt_hash"] == "def456"
        assert ext["decoding"]["temperature"] == 0.0
        assert ext["decoding"]["max_new_tokens"] == 512

    def test_fv_data_003_provenance_config_missing_field(self, tmp_path: Path) -> None:
        """Criterion 2: GIVEN an extractor config missing any of these
        WHEN extraction starts THEN it raises.
        """
        cfg_path = tmp_path / "extractor_config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "model_id": "DECISION_REQUIRED",
                    "model_revision": "DECISION_REQUIRED",
                    "prompt_text": "DECISION_REQUIRED",
                    "decoding_params": {
                        "temperature": "DECISION_REQUIRED",
                    },
                }
            )
        )
        cfg = ExtractorConfig.load(cfg_path)
        with pytest.raises(ValueError, match="DECISION_REQUIRED"):
            cfg.validate()

    def test_fv_data_003_provenance_valid_config(self, tmp_path: Path) -> None:
        """A fully resolved config passes validation."""
        cfg_path = tmp_path / "extractor_config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "model_id": "meta-llama/Llama-3.1-8B-Instruct",
                    "model_revision": "a1b1c2d3e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9",
                    "prompt_text": "Extract facts as (subject, relation, object).",
                    "decoding_params": {
                        "temperature": 0.0,
                        "max_new_tokens": 512,
                    },
                }
            )
        )
        cfg = ExtractorConfig.load(cfg_path)
        cfg.validate()  # Should not raise.

    def test_fv_data_003_provenance_empty_decoding(self, tmp_path: Path) -> None:
        """Empty decoding_params raises."""
        cfg_path = tmp_path / "extractor_config.json"
        cfg_path.write_text(
            json.dumps(
                {
                    "model_id": "some-model",
                    "model_revision": "some-rev",
                    "prompt_text": "some prompt",
                    "decoding_params": {},
                }
            )
        )
        cfg = ExtractorConfig.load(cfg_path)
        with pytest.raises(ValueError, match="decoding_params.*empty"):
            cfg.validate()


# =====================================================================
# FV-DATA-004 — Admit only adjudicated mentions downstream
# =====================================================================


class TestFvData004AdjudicationGate:
    """FV-DATA-004: SHALL mark a mention adjudicated only after two
    independent readers' labels and any adjudication are recorded.
    """

    def test_fv_data_004_adjudication_gate_admitted(self, tmp_path: Path) -> None:
        """Criterion 1: GIVEN a mention with two reader labels and an
        adjudication record WHEN P1-1 loads mentions THEN it is admitted.
        """
        m = _make_mention(
            review_status="adjudicated",
            reader_labels=[
                {"reader": "r1", "label": "correct"},
                {"reader": "r2", "label": "correct"},
            ],
            adjudication={"decision": "accept", "adjudicator": "r3"},
        )
        assert is_adjudicated(m)

        mentions_path = tmp_path / "mentions.jsonl"
        _write_jsonl(mentions_path, [m.to_dict()])
        admitted = load_admitted_mentions(mentions_path)
        assert len(admitted) == 1
        assert admitted[0].mention_id == m.mention_id

    def test_fv_data_004_adjudication_gate_refused_no_labels(
        self, tmp_path: Path
    ) -> None:
        """Criterion 2: GIVEN a mention with fewer than two independent
        labels WHEN P1-1 loads mentions THEN it is refused.
        """
        m_one_reader = _make_mention(
            mention_id="m_one",
            review_status="single_reader",
            reader_labels=[{"reader": "r1", "label": "correct"}],
            adjudication=None,
        )
        m_pending = _make_mention(
            mention_id="m_pending",
            review_status="pending",
        )
        mentions_path = tmp_path / "mentions.jsonl"
        _write_jsonl(mentions_path, [m_one_reader.to_dict(), m_pending.to_dict()])
        admitted = load_admitted_mentions(mentions_path)
        assert len(admitted) == 0

    def test_fv_data_004_adjudication_gate_mixed(self, tmp_path: Path) -> None:
        """Mixed adjudicated and non-adjudicated: only adjudicated admitted."""
        m_good = _make_mention(
            mention_id="m_good",
            review_status="adjudicated",
            reader_labels=[
                {"reader": "r1", "label": "correct"},
                {"reader": "r2", "label": "correct"},
            ],
            adjudication={"decision": "accept", "adjudicator": "r3"},
        )
        m_bad = _make_mention(
            mention_id="m_bad",
            review_status="pending",
        )
        mentions_path = tmp_path / "mentions.jsonl"
        _write_jsonl(mentions_path, [m_good.to_dict(), m_bad.to_dict()])
        admitted = load_admitted_mentions(mentions_path)
        assert len(admitted) == 1
        assert admitted[0].mention_id == "m_good"


# =====================================================================
# FV-DATA-005 — Record the fate of every TOFU record
# =====================================================================


class TestFvData005TransformationCoverage:
    """FV-DATA-005: SHALL record exactly one transformation label for
    every row of every consumed TOFU config.
    """

    def test_fv_data_005_transformation_coverage_complete(self) -> None:
        """Criterion 1: GIVEN the pinned TOFU copy WHEN transformations.jsonl
        is checked THEN every source row appears exactly once with a label
        from the handbook §9.3 vocabulary.
        """
        expected = {"full": 3}
        records = [
            TransformationRecord(
                config="full",
                row_index=i,
                label="split_into_atomic_facts",
                reason="QA row split into atomic (s,r,o) mentions",
            )
            for i in range(3)
        ]
        validate_transformation_coverage(records, expected)

    def test_fv_data_005_transformation_coverage_missing_row(self) -> None:
        """Criterion 2: GIVEN a row with no label WHEN checked THEN
        validation fails.
        """
        expected = {"full": 3}
        split = "split_into_atomic_facts"
        records = [
            TransformationRecord(
                config="full", row_index=0, label=split, reason="split"
            ),
            TransformationRecord(
                config="full", row_index=2, label=split, reason="split"
            ),
        ]
        with pytest.raises(ValueError, match="Missing.*row_index=1"):
            validate_transformation_coverage(records, expected)

    def test_fv_data_005_transformation_coverage_duplicate(self) -> None:
        """Duplicate transformation record raises."""
        expected = {"full": 2}
        split = "split_into_atomic_facts"
        records = [
            TransformationRecord(
                config="full", row_index=0, label=split, reason="split"
            ),
            TransformationRecord(
                config="full", row_index=0, label="excluded", reason="dup"
            ),
            TransformationRecord(
                config="full", row_index=1, label="reused", reason="ok"
            ),
        ]
        with pytest.raises(ValueError, match="Duplicate"):
            validate_transformation_coverage(records, expected)

    def test_fv_data_005_transformation_coverage_bad_label(self) -> None:
        """Invalid label raises."""
        expected = {"full": 1}
        records = [
            TransformationRecord(
                config="full", row_index=0, label="invented_label", reason="bad"
            ),
        ]
        with pytest.raises(ValueError, match="Invalid transformation label"):
            validate_transformation_coverage(records, expected)

    def test_fv_data_005_transformation_labels_match_handbook(self) -> None:
        """The label vocabulary matches handbook §9.3."""
        assert TRANSFORMATION_LABELS == {
            "reused",
            "transformed",
            "split_into_atomic_facts",
            "rewritten",
            "excluded",
        }


# =====================================================================
# FV-DATA-006 — Refuse TOFU splits and reference models
# =====================================================================


class TestFvData006NoTofuSplits:
    """FV-DATA-006: SHALL NOT use TOFU split membership or any released
    TOFU retain checkpoint as a study split or as M_R.
    """

    def test_fv_data_006_no_tofu_splits_forbidden_config(self) -> None:
        """Criterion 1: GIVEN any P1 artifact WHEN its lineage is inspected
        THEN no split assignment derives from TOFU split membership.
        """
        bad_records = [
            TransformationRecord(
                config="forget01",
                row_index=0,
                label="reused",
                reason="from TOFU forget split",
            ),
        ]
        with pytest.raises(ValueError, match="forbidden TOFU split"):
            check_no_tofu_split_lineage(bad_records)

    def test_fv_data_006_no_tofu_splits_allowed_config(self) -> None:
        """Consumed configs (full, real_authors, etc.) are allowed."""
        good_records = [
            TransformationRecord(
                config="full",
                row_index=0,
                label="split_into_atomic_facts",
                reason="ok",
            ),
        ]
        check_no_tofu_split_lineage(good_records)

    def test_fv_data_006_no_tofu_splits_all_forbidden_names(self) -> None:
        """Every known forbidden config name is rejected."""
        for config in FORBIDDEN_SPLIT_CONFIGS:
            rec = TransformationRecord(
                config=config, row_index=0, label="reused", reason="test"
            )
            with pytest.raises(ValueError, match="forbidden TOFU split"):
                check_no_tofu_split_lineage([rec])

    def test_fv_data_006_no_tofu_retain_model(self) -> None:
        """Criterion 2: GIVEN a config that points a reference slot at a
        released TOFU retain model WHEN loaded THEN it raises.
        """
        with pytest.raises(ValueError, match="released TOFU retain model"):
            check_no_tofu_retain_model("locuslab/tofu_ft_llama2-7b")

    def test_fv_data_006_no_tofu_retain_model_allowed(self) -> None:
        """Non-TOFU model IDs are allowed."""
        check_no_tofu_retain_model("meta-llama/Llama-3.1-8B-Instruct")

    def test_fv_data_006_consumed_configs_disjoint_from_forbidden(self) -> None:
        """Consumed and forbidden config sets are disjoint."""
        overlap = set(CONSUMED_CONFIGS) & set(FORBIDDEN_SPLIT_CONFIGS)
        assert overlap == set(), f"Overlap: {overlap}"
