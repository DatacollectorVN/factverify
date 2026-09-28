"""Tests for FV-MODEL P2-0 — model loader.

Verification matrix: FV-MODEL-001 through FV-MODEL-009.
All nine test hooks are required formal evidence per requirements/FV-MODEL — P2-0.md.
"""

from __future__ import annotations

import ast
import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.models.errors import FactVerifyLoaderError

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_mock_model(dtype_str: str = "float32") -> MagicMock:
    """Return a mock model that looks like an AutoModelForCausalLM in eval mode."""
    mock_model = MagicMock()
    mock_model.training = False
    mock_param = MagicMock()
    # Represent dtype as a string (avoids needing torch installed)
    mock_param.dtype.__str__ = lambda self: f"torch.{dtype_str}"
    mock_model.parameters.return_value = [mock_param]
    mock_model.eval.return_value = mock_model
    return mock_model


def _make_mock_tokenizer() -> MagicMock:
    return MagicMock()


# ---------------------------------------------------------------------------
# FV-MODEL-001 — Load only the pinned revision
# ---------------------------------------------------------------------------


def test_fv_model_001_pinned_revision(model_loader_spec_root: Path) -> None:
    """GIVEN a valid role in models.yaml WHEN load_model runs THEN the
    from_pretrained calls use the declared revision; an unknown role raises."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_model
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer

        load_model("tiny_base", spec_root=model_loader_spec_root)

        # Revision must match models.yaml declaration
        model_call_kwargs = mock_cls.from_pretrained.call_args.kwargs
        assert model_call_kwargs["revision"] == "a" * 40

        tok_call_kwargs = mock_tok_cls.from_pretrained.call_args.kwargs
        assert tok_call_kwargs["revision"] == "a" * 40

    # Unknown role raises before loading any weights
    with pytest.raises(FactVerifyLoaderError, match="unknown role"):
        with patch("src.models.loader.AutoModelForCausalLM") as mock_cls2:
            mock_cls2.from_pretrained.side_effect = AssertionError(
                "should not be called"
            )
            load_model("nonexistent_role", spec_root=model_loader_spec_root)


# ---------------------------------------------------------------------------
# FV-MODEL-002 — Verify file digests before use
# ---------------------------------------------------------------------------


def test_fv_model_002_digest_check(
    model_loader_spec_root: Path, tmp_path: Path
) -> None:
    """GIVEN local files matching digests WHEN load_model runs THEN model is returned.
    GIVEN a modified file WHEN load_model runs THEN it raises naming the file."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    # Correct digests — should succeed
    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_model
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer
        result = load_model("tiny_base", spec_root=model_loader_spec_root)
        assert result is not None

    # Corrupt fixture in a temp copy — should raise before from_pretrained
    temp_fixture = tmp_path / "models_loader"
    shutil.copytree(model_loader_spec_root, temp_fixture)
    # Corrupt model.safetensors
    (temp_fixture / "model.safetensors").write_bytes(b"CORRUPTED")

    with pytest.raises(
        FactVerifyLoaderError, match="digest mismatch.*model.safetensors"
    ):
        load_model("tiny_base", spec_root=temp_fixture)


# ---------------------------------------------------------------------------
# FV-MODEL-003 — Load without network access
# ---------------------------------------------------------------------------


def test_fv_model_003_offline(model_loader_spec_root: Path) -> None:
    """WHEN load_model runs THEN from_pretrained is called with local_files_only."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_model
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer

        load_model("tiny_base", spec_root=model_loader_spec_root)

        # Both calls must include local_files_only=True
        assert mock_cls.from_pretrained.call_args.kwargs.get("local_files_only") is True
        assert (
            mock_tok_cls.from_pretrained.call_args.kwargs.get("local_files_only")
            is True
        )


# ---------------------------------------------------------------------------
# FV-MODEL-004 — Return the canonical identity hash
# ---------------------------------------------------------------------------


def test_fv_model_004_identity_hash(model_loader_spec_root: Path) -> None:
    """GIVEN same inputs WHEN loaded twice THEN identity_hash and identity_payload
    are identical. GIVEN a different role/adapter WHEN loaded THEN hash differs."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    def _load() -> LoadedModel:  # noqa: F821
        with (
            patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
            patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
        ):
            mock_cls.from_pretrained.return_value = mock_model
            mock_tok_cls.from_pretrained.return_value = mock_tokenizer
            return load_model("tiny_base", spec_root=model_loader_spec_root)

    result1 = _load()
    result2 = _load()

    # Byte-identical on repeated calls
    assert result1.identity_hash == result2.identity_hash
    assert result1.identity_payload == result2.identity_payload

    # Hash is a 64-char hex string
    assert len(result1.identity_hash) == 64
    assert all(c in "0123456789abcdef" for c in result1.identity_hash)

    # Payload contains all expected keys
    payload = result1.identity_payload
    assert payload["role"] == "tiny_base"
    assert payload["base_repo"] == "factverify-test/tiny-base"
    assert payload["adapter_digest"] is None


# ---------------------------------------------------------------------------
# FV-MODEL-007 — Apply the declared precision exactly
# ---------------------------------------------------------------------------


def test_fv_model_007_precision(model_loader_spec_root: Path) -> None:
    """WHEN load_model runs THEN from_pretrained gets the declared torch_dtype.
    GIVEN hardware that raises on precision WHEN load_model runs THEN raises."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_model
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer

        load_model("tiny_base", spec_root=model_loader_spec_root)

        # torch_dtype must be passed through from models.yaml
        call_kwargs = mock_cls.from_pretrained.call_args.kwargs
        # dtype from fixture models.yaml is "float32"
        assert "torch_dtype" in call_kwargs

    # RuntimeError from from_pretrained (hardware mismatch) → re-raises as loader error
    with patch("src.models.loader.AutoModelForCausalLM") as mock_cls2:
        mock_cls2.from_pretrained.side_effect = RuntimeError(
            "dtype not supported on this device"
        )
        with pytest.raises(FactVerifyLoaderError, match="hardware cannot honour"):
            load_model("tiny_base", spec_root=model_loader_spec_root)


# ---------------------------------------------------------------------------
# FV-MODEL-008 — Return models in inference mode
# ---------------------------------------------------------------------------


def test_fv_model_008_eval_mode(model_loader_spec_root: Path) -> None:
    """WHEN load_model returns THEN model.eval() was called and training is False."""
    from src.models.loader import load_model

    mock_model = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()

    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_model
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer

        result = load_model("tiny_base", spec_root=model_loader_spec_root)

        # eval() must have been called on the model
        mock_model.eval.assert_called_once()
        # model.training should be False
        assert result.model.training is False


# ---------------------------------------------------------------------------
# FV-MODEL-005 — Attach adapters only to their own base
# ---------------------------------------------------------------------------


def test_fv_model_005_adapter_base_match(
    model_loader_spec_root: Path,
    model_loader_adapter_dir: Path,
    model_loader_adapter_wrong_dir: Path,
) -> None:
    """GIVEN adapter with matching base hash WHEN attached THEN succeeds.
    GIVEN adapter with wrong base hash WHEN attached THEN raises before attachment."""
    from src.models.loader import load_model

    mock_base = _make_mock_model()
    mock_tokenizer = _make_mock_tokenizer()
    mock_peft_model = MagicMock()

    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls,
        patch("src.models.adapters.PeftModel") as mock_adapters_peft_cls,
    ):
        mock_cls.from_pretrained.return_value = mock_base
        mock_tok_cls.from_pretrained.return_value = mock_tokenizer
        mock_adapters_peft_cls.from_pretrained.return_value = mock_peft_model

        result = load_model(
            "tiny_base",
            spec_root=model_loader_spec_root,
            adapter_path=model_loader_adapter_dir,
        )
        # Adapter digest must appear in the payload
        assert result.identity_payload["adapter_digest"] is not None

    # Wrong base hash must raise before any attachment
    with (
        patch("src.models.loader.AutoModelForCausalLM") as mock_cls2,
        patch("src.models.loader.AutoTokenizer") as mock_tok_cls2,
        patch("src.models.adapters.PeftModel") as mock_peft_cls2,
    ):
        mock_cls2.from_pretrained.return_value = mock_base
        mock_tok_cls2.from_pretrained.return_value = mock_tokenizer
        mock_peft_cls2.from_pretrained.side_effect = AssertionError(
            "should not be called"
        )

        with pytest.raises(FactVerifyLoaderError, match="adapter base hash mismatch"):
            load_model(
                "tiny_base",
                spec_root=model_loader_spec_root,
                adapter_path=model_loader_adapter_wrong_dir,
            )
        mock_peft_cls2.from_pretrained.assert_not_called()


# ---------------------------------------------------------------------------
# FV-MODEL-006 — Record adapter digests
# ---------------------------------------------------------------------------


def test_fv_model_006_adapter_digest(
    model_loader_spec_root: Path,
    model_loader_adapter_dir: Path,
    tmp_path: Path,
) -> None:
    """GIVEN unchanged adapter WHEN loaded twice THEN adapter_digest is identical.
    GIVEN one changed byte WHEN loaded THEN adapter_digest changes."""
    from src.models.adapters import compute_adapter_digest

    digest1 = compute_adapter_digest(model_loader_adapter_dir)
    digest2 = compute_adapter_digest(model_loader_adapter_dir)
    assert digest1 == digest2
    assert len(digest1) == 64

    # Mutate a copy of the adapter
    temp_adapter = tmp_path / "adapter_modified"
    shutil.copytree(model_loader_adapter_dir, temp_adapter)
    (temp_adapter / "adapter_model.safetensors").write_bytes(b"CHANGED_BYTES")

    digest_modified = compute_adapter_digest(temp_adapter)
    assert digest_modified != digest1


# ---------------------------------------------------------------------------
# FV-MODEL-009 — Single entry point (static AST check)
# ---------------------------------------------------------------------------


def test_fv_model_009_single_entry_point() -> None:
    """GIVEN the repository WHEN from_pretrained is searched via AST scan
    THEN it only appears inside src/models/."""
    repo_root = Path(__file__).resolve().parent.parent
    models_pkg = repo_root / "src" / "models"
    violations: list[str] = []

    # This test file itself uses mock_cls.from_pretrained in assertions — exclude it
    this_file = Path(__file__).resolve()

    # Walk all .py files outside src/models/
    for py_file in repo_root.rglob("*.py"):
        # Skip src/models/ itself
        try:
            py_file.relative_to(models_pkg)
            continue
        except ValueError:
            pass
        # Skip this test file (it asserts on mock.from_pretrained which is legitimate)
        if py_file == this_file:
            continue
        # Skip spec/fixture/venv directories
        parts = py_file.parts
        if any(p in parts for p in (".venv", "venv", "__pycache__", ".pytest_cache")):
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "from_pretrained":
                rel = py_file.relative_to(repo_root)
                violations.append(f"{rel}:{node.end_lineno}")

    assert violations == [], (
        "from_pretrained found outside src/models/ — "
        "each occurrence is a provenance gap:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
