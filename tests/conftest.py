"""Shared test fixtures for P0-1 through P0-5 validation."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SPEC_ROOT = REPO / ".factverify" / "spec"
CONTRACTS_DIR = REPO / ".factverify" / "contracts"
FIXTURES = REPO / "tests" / "fixtures"
SCHEMA_PATH = SPEC_ROOT / "fact_contract.schema.json"

# P0-1 fact contract fixture paths
FC_FIXTURES = FIXTURES / "fact_contract"

# P0-2 closure template paths
CLOSURE_SUITE_PATH = SPEC_ROOT / "closure_templates.yaml"
CLOSURE_DIR = REPO / ".factverify" / "closure"
CT_FIXTURES = FIXTURES / "closure_templates"
BINDINGS_PATH = CLOSURE_DIR / "instance_bindings.json"
REVIEW_MANIFEST_PATH = CLOSURE_DIR / "review_manifest.json"
# Backward compat
P0_2_FIXTURES = CT_FIXTURES

# P0-3 attack spec paths
ATTACK_SPEC_PATH = SPEC_ROOT / "attacks.yaml"
ATTACKS_DIR = REPO / ".factverify" / "attacks"
AT_FIXTURES = FIXTURES / "attack_spec"
EVENT_FIXTURES_PATH = ATTACKS_DIR / "event_fixtures.json"

# P0-4 access profile paths
ACCESS_PROFILE_PATH = SPEC_ROOT / "access_profile.md"
ACCESS_DIR = REPO / ".factverify" / "access"
AP_FIXTURES = FIXTURES / "access_profile"
AP_VALID = AP_FIXTURES / "valid"
AP_INVALID = AP_FIXTURES / "invalid"
AP_BASELINES = AP_FIXTURES / "baselines"

# P0-5 margins paths
MARGINS_PATH = SPEC_ROOT / "margins.yaml"
MARGINS_DIR = REPO / ".factverify" / "margins"
MG_FIXTURES = FIXTURES / "margins_spec"
MG_VALID = MG_FIXTURES / "valid"
MG_INVALID = MG_FIXTURES / "invalid"
MG_BASELINES = MG_FIXTURES / "baselines"


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
def closure_dir() -> Path:
    return CLOSURE_DIR


@pytest.fixture(scope="session")
def p0_2_fixtures() -> Path:
    return P0_2_FIXTURES


@pytest.fixture(scope="session")
def bindings_path() -> Path:
    return BINDINGS_PATH


@pytest.fixture(scope="session")
def review_manifest_path() -> Path:
    return REVIEW_MANIFEST_PATH


@pytest.fixture(scope="session")
def attack_spec_path() -> Path:
    return ATTACK_SPEC_PATH


@pytest.fixture(scope="session")
def attacks_dir() -> Path:
    return ATTACKS_DIR


@pytest.fixture(scope="session")
def at_fixtures() -> Path:
    return AT_FIXTURES


@pytest.fixture(scope="session")
def event_fixtures_path() -> Path:
    return EVENT_FIXTURES_PATH


@pytest.fixture(scope="session")
def access_profile_path() -> Path:
    return ACCESS_PROFILE_PATH


@pytest.fixture(scope="session")
def access_dir() -> Path:
    return ACCESS_DIR


@pytest.fixture(scope="session")
def ap_fixtures() -> Path:
    return AP_FIXTURES


@pytest.fixture(scope="session")
def ap_valid() -> Path:
    return AP_VALID


@pytest.fixture(scope="session")
def ap_invalid() -> Path:
    return AP_INVALID


@pytest.fixture(scope="session")
def ap_baselines() -> Path:
    return AP_BASELINES


@pytest.fixture(scope="session")
def margins_path() -> Path:
    return MARGINS_PATH


@pytest.fixture(scope="session")
def margins_dir() -> Path:
    return MARGINS_DIR


@pytest.fixture(scope="session")
def mg_fixtures() -> Path:
    return MG_FIXTURES


@pytest.fixture(scope="session")
def mg_valid() -> Path:
    return MG_VALID


@pytest.fixture(scope="session")
def mg_invalid() -> Path:
    return MG_INVALID


@pytest.fixture(scope="session")
def mg_baselines() -> Path:
    return MG_BASELINES


# P0-6 witness rule paths
WITNESS_RULE_MD = SPEC_ROOT / "witness_rule.md"
WITNESS_DIR = REPO / ".factverify" / "witness"
WITNESS_RULE_FIXTURES = FIXTURES / "witness_rule"
WR_VALID = WITNESS_RULE_FIXTURES / "valid"
WR_INVALID = WITNESS_RULE_FIXTURES / "invalid"
WR_BASELINES = WITNESS_RULE_FIXTURES / "baselines"
P0_6_REPORT = REPO / "reports" / "p0-6-validation.json"


@pytest.fixture(scope="session")
def witness_rule_md() -> Path:
    return WITNESS_RULE_MD


@pytest.fixture(scope="session")
def witness_dir() -> Path:
    return WITNESS_DIR


@pytest.fixture(scope="session")
def witness_rule_fixtures() -> Path:
    return WITNESS_RULE_FIXTURES


@pytest.fixture(scope="session")
def wr_valid() -> Path:
    return WR_VALID


@pytest.fixture(scope="session")
def wr_invalid() -> Path:
    return WR_INVALID


@pytest.fixture(scope="session")
def wr_baselines() -> Path:
    return WR_BASELINES


@pytest.fixture(scope="session")
def p0_6_report() -> Path:
    return P0_6_REPORT


# P0-7 preregistration paths
PREREGISTRATION_MD = SPEC_ROOT / "preregistration.md"
DECISIONS_DIR = REPO / ".factverify" / "decisions"
MILESTONES_DIR = REPO / ".factverify" / "milestones"
EXPOSURE_DIR = REPO / ".factverify" / "exposure"
PREREGISTRATION_FIXTURES = FIXTURES / "preregistration"
PR_VALID = PREREGISTRATION_FIXTURES / "valid"
PR_INVALID = PREREGISTRATION_FIXTURES / "invalid"
P0_7_REPORT = REPO / "reports" / "p0-7-validation.json"


@pytest.fixture(scope="session")
def preregistration_md() -> Path:
    return PREREGISTRATION_MD


@pytest.fixture(scope="session")
def decisions_dir() -> Path:
    return DECISIONS_DIR


@pytest.fixture(scope="session")
def milestones_dir() -> Path:
    return MILESTONES_DIR


@pytest.fixture(scope="session")
def exposure_dir() -> Path:
    return EXPOSURE_DIR


@pytest.fixture(scope="session")
def preregistration_fixtures() -> Path:
    return PREREGISTRATION_FIXTURES


@pytest.fixture(scope="session")
def pr_valid() -> Path:
    return PR_VALID


@pytest.fixture(scope="session")
def pr_invalid() -> Path:
    return PR_INVALID


@pytest.fixture(scope="session")
def p0_7_report() -> Path:
    return P0_7_REPORT


# P0-8 models spec paths
MODELS_SPEC_PATH = SPEC_ROOT / "models.yaml"
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
