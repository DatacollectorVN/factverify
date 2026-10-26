"""Tests for src.services.models.checkpoint: publish, discard, manifest, verify."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.services.common.errors import CheckpointError
from src.services.models.checkpoint import (
    discard_adapter,
    publish_adapter,
    publish_model,
    read_manifest,
    verify_checkpoint,
    write_manifest,
)
from src.services.models.types import CheckpointManifest


# ── Helpers ────────────────────────────────────────────────────────────────


def _mock_model(fail: bool = False) -> MagicMock:
    """Return a mock model whose save_pretrained writes a dummy file."""
    model = MagicMock()

    def _save(path: Path | str, **_kwargs: Any) -> None:
        p = Path(path)
        if fail:
            raise RuntimeError("simulated save failure")
        (p / "pytorch_model.bin").write_bytes(b"fake-weights")

    model.save_pretrained.side_effect = _save
    return model


def _mock_tokenizer() -> MagicMock:
    """Return a mock tokenizer whose save_pretrained writes a dummy file."""
    tok = MagicMock()

    def _save(path: Path | str, **_kwargs: Any) -> None:
        p = Path(path)
        (p / "tokenizer.json").write_text("{}")

    tok.save_pretrained.side_effect = _save
    return tok


def _sample_manifest() -> CheckpointManifest:
    return CheckpointManifest(
        identity_hash="sha256:" + "a" * 64,
        base_identity_hash="sha256:" + "b" * 64,
        config_hash="sha256:" + "c" * 64,
        training_method="ga",
        seed=42,
        created_at="2026-10-26T00:00:00Z",
        path="/checkpoints/test",
        digest="sha256:" + "d" * 64,
        size_bytes=1024,
    )


# ── Tests: publish_adapter ─────────────────────────────────────────────────


class TestPublishAdapter:
    def test_atomic_publish(self, tmp_path: Path) -> None:
        """Staging dir is created, files are written, then renamed to output_dir."""
        output_dir = tmp_path / "adapter-out"
        model = _mock_model()
        metadata = {"method": "ga", "seed": 42}

        publish_adapter(model, output_dir, metadata, base_identity_hash="hash123")

        assert output_dir.is_dir()
        assert (output_dir / "metadata.json").is_file()
        assert (output_dir / "fv_adapter_meta.json").is_file()
        assert (output_dir / "pytorch_model.bin").is_file()
        # Staging dir must not remain
        staging = tmp_path / "adapter-out.staging"
        assert not staging.exists()

    def test_cleanup_on_failure(self, tmp_path: Path) -> None:
        """If save_pretrained fails, staging dir is cleaned up and output_dir not created."""
        output_dir = tmp_path / "adapter-fail"
        model = _mock_model(fail=True)

        with pytest.raises(CheckpointError, match="adapter publish failed"):
            publish_adapter(model, output_dir, {}, base_identity_hash="hash123")

        assert not output_dir.exists()
        staging = tmp_path / "adapter-fail.staging"
        assert not staging.exists()


# ── Tests: publish_model ───────────────────────────────────────────────────


class TestPublishModel:
    def test_atomic_publish(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "model-out"
        model = _mock_model()
        tokenizer = _mock_tokenizer()
        metadata = {"method": "full", "seed": 0}

        publish_model(model, tokenizer, output_dir, metadata)

        assert output_dir.is_dir()
        assert (output_dir / "metadata.json").is_file()
        assert (output_dir / "pytorch_model.bin").is_file()
        assert (output_dir / "tokenizer.json").is_file()
        staging = tmp_path / "model-out.staging"
        assert not staging.exists()

    def test_cleanup_on_failure(self, tmp_path: Path) -> None:
        model = _mock_model(fail=True)
        tokenizer = _mock_tokenizer()
        output_dir = tmp_path / "model-fail"

        with pytest.raises(CheckpointError, match="model publish failed"):
            publish_model(model, tokenizer, output_dir, {})

        assert not output_dir.exists()


# ── Tests: discard_adapter ─────────────────────────────────────────────────


class TestDiscardAdapter:
    def test_removes_output_and_staging(self, tmp_path: Path) -> None:
        output_dir = tmp_path / "adapter-discard"
        staging = tmp_path / "adapter-discard.staging"
        output_dir.mkdir()
        staging.mkdir()
        (output_dir / "dummy.bin").write_bytes(b"x")
        (staging / "dummy.bin").write_bytes(b"x")

        discard_adapter(output_dir)

        assert not output_dir.exists()
        assert not staging.exists()

    def test_tolerates_missing(self, tmp_path: Path) -> None:
        """No error when neither directory exists."""
        discard_adapter(tmp_path / "nonexistent")


# ── Tests: manifest round-trip ─────────────────────────────────────────────


class TestManifestRoundTrip:
    def test_write_and_read(self, tmp_path: Path) -> None:
        manifest = _sample_manifest()
        write_manifest(tmp_path, manifest)

        loaded = read_manifest(tmp_path)
        assert loaded is not None
        assert loaded == manifest

    def test_read_missing_returns_none(self, tmp_path: Path) -> None:
        assert read_manifest(tmp_path) is None

    def test_read_corrupt_raises(self, tmp_path: Path) -> None:
        (tmp_path / "checkpoint_manifest.json").write_text("not json")
        with pytest.raises(CheckpointError, match="corrupt manifest"):
            read_manifest(tmp_path)

    def test_read_invalid_schema_raises(self, tmp_path: Path) -> None:
        (tmp_path / "checkpoint_manifest.json").write_text(
            json.dumps({"unexpected_field": True})
        )
        with pytest.raises(CheckpointError, match="invalid manifest schema"):
            read_manifest(tmp_path)


# ── Tests: verify_checkpoint ──────────────────────────────────────────────


class TestVerifyCheckpoint:
    def test_present(self, tmp_path: Path) -> None:
        (tmp_path / "metadata.json").write_text("{}")
        assert verify_checkpoint(tmp_path) is True

    def test_missing(self, tmp_path: Path) -> None:
        assert verify_checkpoint(tmp_path) is False
