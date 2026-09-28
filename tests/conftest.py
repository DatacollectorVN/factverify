"""Shared test fixtures for P0-1 through P0-8 and artifact layout validation."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SPEC_ROOT = REPO / ".factverify"
CONTRACTS_DIR = REPO / ".factverify" / "facts"
FIXTURES = REPO / "tests" / "fixtures"
SCHEMA_PATH = SPEC_ROOT / "fact.schema.json"

# P0-1 fact contract fixture paths
FC_FIXTURES = FIXTURES / "fact_contract"

# P0-2 closure template paths
CLOSURE_SUITE_PATH = SPEC_ROOT / "templates.yaml"
CT_FIXTURES = FIXTURES / "closure_templates"
# Backward compat
P0_2_FIXTURES = CT_FIXTURES


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO


@pytest.fixture(scope="session")
def spec_root() -> Path:
    return SPEC_ROOT


@pytest.fixture(scope="session")
def contracts_dir() -> Path:
    return CONTRACTS_DIR


@pytest.fixture(scope="session")
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def schema_path() -> Path:
    return SCHEMA_PATH


@pytest.fixture(scope="session")
def closure_suite_path() -> Path:
    return CLOSURE_SUITE_PATH


@pytest.fixture(scope="session")
def p0_2_fixtures() -> Path:
    return P0_2_FIXTURES


# P0-8 models spec paths
MODELS_SPEC_PATH = REPO / ".factverify" / "model_policy.yaml"
MS_FIXTURES = FIXTURES / "models_spec"
MS_VALID = MS_FIXTURES / "valid"
MS_INVALID = MS_FIXTURES / "invalid"
MS_MODEL_DIR = MS_FIXTURES / "model_dir"
MS_DOWNSTREAM = MS_FIXTURES / "downstream"
P0_8_REPORT = REPO / "reports" / "p0-8-validation.json"


@pytest.fixture(scope="session")
def models_spec_path() -> Path:
    return MODELS_SPEC_PATH


@pytest.fixture(scope="session")
def ms_fixtures() -> Path:
    return MS_FIXTURES


@pytest.fixture(scope="session")
def ms_valid() -> Path:
    return MS_VALID


@pytest.fixture(scope="session")
def ms_invalid() -> Path:
    return MS_INVALID


@pytest.fixture(scope="session")
def ms_model_dir() -> Path:
    return MS_MODEL_DIR


@pytest.fixture(scope="session")
def ms_downstream() -> Path:
    return MS_DOWNSTREAM


@pytest.fixture(scope="session")
def p0_8_report() -> Path:
    return P0_8_REPORT


# P2-0 model loader fixture paths
MODELS_LOADER_FIXTURES = FIXTURES / "models_loader"
ML_ADAPTER_DIR = MODELS_LOADER_FIXTURES / "tiny_adapter"
ML_ADAPTER_WRONG_DIR = MODELS_LOADER_FIXTURES / "tiny_adapter_wrong"


@pytest.fixture(scope="session")
def model_loader_spec_root() -> Path:
    """Spec root for model loader tests — contains models.yaml with tiny_base role."""
    return MODELS_LOADER_FIXTURES


@pytest.fixture(scope="session")
def model_loader_adapter_dir() -> Path:
    """Valid adapter directory (base hash matches tiny_base)."""
    return ML_ADAPTER_DIR


@pytest.fixture(scope="session")
def model_loader_adapter_wrong_dir() -> Path:
    """Invalid adapter directory (base hash deliberately wrong)."""
    return ML_ADAPTER_WRONG_DIR


# P2-1 harness fixtures. models_loader weights are a text stub, so the spec
# root is a generated miniature GPT-2 (see tests/harness_model.py).
HARNESS_FIXTURES = FIXTURES / "harness"


@pytest.fixture(scope="session")
def harness_spec_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Spec root whose tiny_base role is a real loadable model."""
    from tests.harness_model import build_tiny_spec

    return build_tiny_spec(tmp_path_factory.mktemp("harness-spec"))


@pytest.fixture(scope="session")
def harness_corpus() -> Path:
    return HARNESS_FIXTURES / "corpus"


@pytest.fixture(scope="session")
def harness_finetune_config() -> Path:
    return HARNESS_FIXTURES / "jobs" / "finetune.yaml"
