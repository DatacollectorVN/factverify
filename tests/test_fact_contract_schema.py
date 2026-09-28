"""Validate fact_contract.schema.json against test fixtures."""

import json
from pathlib import Path

import jsonschema
import pytest

REPO = Path(__file__).resolve().parent.parent
SCHEMA_PATH = REPO / ".factverify" / "spec" / "fact_contract.schema.json"
FIXTURES = REPO / "tests" / "fixtures" / "fact_contract"


@pytest.fixture(scope="module")
def schema():
    return json.loads(SCHEMA_PATH.read_text())


# ── valid instances ──────────────────────────────────────────────


def test_full_example_validates(schema):
    instance = json.loads((FIXTURES / "fact_example.json").read_text())
    jsonschema.validate(instance, schema)


def test_minimal_example_validates(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    jsonschema.validate(instance, schema)


@pytest.mark.parametrize("filename", ["fact_example.json", "fact_minimal.json"])
def test_all_fixtures_validate(schema, filename):
    instance = json.loads((FIXTURES / filename).read_text())
    jsonschema.validate(instance, schema)


# ── missing required fields ──────────────────────────────────────


@pytest.mark.parametrize("field", [
    "schema_version",
    "contract_id",
    "fact_id",
    "triple",
    "aliases",
    "equivalent_directions",
    "retained_neighbourhood",
    "clue_boundary",
])
def test_rejects_missing_required_field(schema, field):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    del instance[field]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── schema_version enforcement ───────────────────────────────────


def test_rejects_wrong_schema_version(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["schema_version"] = "2.0.0"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── id pattern enforcement ───────────────────────────────────────


def test_rejects_bad_contract_id_pattern(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["contract_id"] = "bad-contract-id"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_bad_fact_id_pattern(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["fact_id"] = "not-a-factverify-id"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── enum validation ──────────────────────────────────────────────


def test_rejects_bad_contract_status(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["contract_status"] = "pending"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_bad_fact_type(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["fact_type"] = "unknown_type"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_bad_direction_enum(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["equivalent_directions"][0]["direction"] = "sideways"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_bad_ambiguous_policy(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["clue_boundary"]["ambiguous_policy"] = "unknown_policy"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_bad_alias_type(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["aliases"]["subject"][0]["alias_type"] = "nickname"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── additionalProperties enforcement ────────────────────────────


def test_rejects_extra_property_on_triple(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["triple"]["extra"] = "nope"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_extra_property_on_fact(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["unexpected"] = True
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_extra_property_on_alias_entry(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["aliases"]["subject"][0]["notes"] = "extra"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── minItems enforcement ─────────────────────────────────────────


def test_rejects_empty_subject_aliases(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["aliases"]["subject"] = []
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_too_few_directions(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["equivalent_directions"] = [instance["equivalent_directions"][0]]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_too_few_neighbourhood_entries(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["retained_neighbourhood"] = instance["retained_neighbourhood"][:3]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── neighbourhood bucket coverage ───────────────────────────────


def test_rejects_missing_same_subject_bucket(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["retained_neighbourhood"] = [
        e for e in instance["retained_neighbourhood"]
        if e["bucket"] != "same_subject"
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── equivalent_directions must contain forward and inverse ───────


def test_rejects_directions_without_forward(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["equivalent_directions"] = [
        {"direction": "inverse", "given": "object", "answer": "subject"},
        {"direction": "verification", "given": "triple", "answer": "truth_value"},
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


def test_rejects_directions_without_inverse(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["equivalent_directions"] = [
        {"direction": "forward", "given": "subject", "answer": "object"},
        {"direction": "verification", "given": "triple", "answer": "truth_value"},
    ]
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)


# ── language code pattern ────────────────────────────────────────


def test_rejects_bad_language_code(schema):
    instance = json.loads((FIXTURES / "fact_minimal.json").read_text())
    instance["aliases"]["subject"][0]["language"] = "1234"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(instance, schema)
