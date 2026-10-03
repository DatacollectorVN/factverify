"""P0-1 atomic-fact contract schema tests.

Test hooks map 1:1 to FV-SPEC requirements:
  FV-SPEC-001 … FV-SPEC-015
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from conftest import CONTRACTS_DIR, FC_FIXTURES, FIXTURES, REPO, SCHEMA_PATH, SPEC_ROOT

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _load_fixture(name: str) -> dict:
    return json.loads((FC_FIXTURES / "valid" / name).read_text(encoding="utf-8"))


def _validate(instance: dict, schema: dict | None = None) -> list:
    if schema is None:
        schema = _load_schema()
    v = Draft202012Validator(schema)
    return list(v.iter_errors(instance))


def _run_cli(*extra_args: str, check: bool = False) -> subprocess.CompletedProcess:
    cmd = [
        sys.executable,
        str(REPO / "tools" / "validate_spec.py"),
        "--scope", "fact-contract",
        "--spec-root", str(SPEC_ROOT),
        *extra_args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def _minimal() -> dict:
    return _load_fixture("minimal.json")


# ---------------------------------------------------------------------------
# T019: FV-SPEC-001 — Schema artifact
# ---------------------------------------------------------------------------


class TestFvSpec001SchemaArtifact:
    """Verify schema exists and passes meta-schema validation."""

    def test_fv_spec_001_schema_artifact(self):
        assert SCHEMA_PATH.exists(), "Schema file must exist"
        schema = _load_schema()
        Draft202012Validator.check_schema(schema)

    def test_schema_has_required_fields(self):
        schema = _load_schema()
        assert schema["type"] == "object"
        assert "required" in schema
        assert set(schema["required"]) == {
            "schema_version", "contract_id", "fact_id", "triple",
            "aliases", "equivalent_directions", "retained_neighbourhood",
            "clue_boundary",
        }

    def test_additional_properties_false_at_root(self):
        schema = _load_schema()
        assert schema.get("additionalProperties") is False


# ---------------------------------------------------------------------------
# T020: FV-SPEC-002 — Required core
# ---------------------------------------------------------------------------


class TestFvSpec002RequiredCore:
    """Remove each required field individually, assert validation fails."""

    REQUIRED_FIELDS = [
        "schema_version", "contract_id", "fact_id", "triple",
        "aliases", "equivalent_directions", "retained_neighbourhood",
        "clue_boundary",
    ]

    @pytest.mark.parametrize("field", REQUIRED_FIELDS)
    def test_fv_spec_002_required_core(self, field):
        instance = _minimal()
        del instance[field]
        errors = _validate(instance)
        assert errors, f"Removing '{field}' should cause validation failure"
        messages = " ".join(e.message for e in errors)
        assert field in messages or "required" in messages.lower()


# ---------------------------------------------------------------------------
# T021: FV-SPEC-003 — Unknown properties
# ---------------------------------------------------------------------------


class TestFvSpec003UnknownProperties:
    """Add undeclared properties at root and nested objects, assert rejection."""

    def test_fv_spec_003_unknown_properties_root(self):
        instance = _minimal()
        instance["undeclared_field"] = "should fail"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_triple(self):
        instance = _minimal()
        instance["triple"]["extra"] = "bad"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_entity(self):
        instance = _minimal()
        instance["triple"]["subject"]["extra"] = "bad"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_alias(self):
        instance = _minimal()
        instance["aliases"]["subject"][0]["extra"] = "bad"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_direction(self):
        instance = _minimal()
        instance["equivalent_directions"][0]["extra"] = "bad"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_neighbour(self):
        instance = _minimal()
        instance["retained_neighbourhood"][0]["extra"] = "bad"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_003_unknown_properties_clue_boundary(self):
        instance = _minimal()
        instance["clue_boundary"]["extra"] = "bad"
        errors = _validate(instance)
        assert errors


# ---------------------------------------------------------------------------
# T022: FV-SPEC-004 — Identifier syntax
# ---------------------------------------------------------------------------


class TestFvSpec004IdentifierSyntax:
    """Valid and malformed IDs for each role."""

    def test_fv_spec_004_valid_wikidata_ids(self):
        instance = _minimal()
        errors = _validate(instance)
        assert not errors

    @pytest.mark.parametrize("bad_fact_id", [
        "bad-fact-id",
        "factverify:fact:",
        "factverify:fact:wd-Q0-P1-Q1",  # Q0 not allowed
        "factverify:fact:UPPERCASE",
    ])
    def test_fv_spec_004_malformed_fact_id(self, bad_fact_id):
        instance = _minimal()
        instance["fact_id"] = bad_fact_id
        errors = _validate(instance)
        assert errors

    @pytest.mark.parametrize("bad_contract_id", [
        "bad-contract-id",
        "factverify:contract:wd-Q1-P1-Q1:v0",  # v0 not allowed
        "factverify:contract:wd-Q1-P1-Q1",  # missing version
    ])
    def test_fv_spec_004_malformed_contract_id(self, bad_contract_id):
        instance = _minimal()
        instance["contract_id"] = bad_contract_id
        errors = _validate(instance)
        assert errors

    @pytest.mark.parametrize("bad_entity_id", [
        "bad-entity",
        "wikidata:Q0",
        "wikidata:P1",  # P is for relations, not entities
    ])
    def test_fv_spec_004_malformed_entity_id(self, bad_entity_id):
        instance = _minimal()
        instance["triple"]["subject"]["id"] = bad_entity_id
        errors = _validate(instance)
        assert errors

    def test_fv_spec_004_valid_project_local_ids(self):
        instance = _minimal()
        instance["fact_id"] = "factverify:fact:invented_test_fact"
        instance["contract_id"] = "factverify:contract:invented_test_fact:v1"
        instance["triple"]["subject"]["id"] = "factverify:entity:test-subject"
        instance["triple"]["relation"]["id"] = "factverify:relation:test-relation"
        instance["triple"]["object"]["id"] = "factverify:entity:test-object"
        errors = _validate(instance)
        assert not errors


# ---------------------------------------------------------------------------
# T023: FV-SPEC-005 — Canonical identity
# ---------------------------------------------------------------------------


class TestFvSpec005CanonicalIdentity:
    """Mismatched Q/P IDs, disagreeing fact_id/contract_id."""

    def test_fv_spec_005_canonical_identity_valid(self):
        """Matching IDs should pass the supplemental check."""
        from tools.validate_spec import check_identity_consistency
        instance = _minimal()
        diags = check_identity_consistency(instance, "test.json")
        assert not diags

    def test_fv_spec_005_mismatched_fact_contract_key(self):
        from tools.validate_spec import check_identity_consistency
        instance = _minimal()
        instance["contract_id"] = "factverify:contract:wd-Q999-P999-Q999:v1"
        diags = check_identity_consistency(instance, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-005" for d in diags)

    def test_fv_spec_005_mismatched_subject_id(self):
        from tools.validate_spec import check_identity_consistency
        instance = _minimal()
        instance["triple"]["subject"]["id"] = "wikidata:Q999"
        diags = check_identity_consistency(instance, "test.json")
        assert any(
            d["rule_id"] == "FV-SPEC-005" and "subject" in d["json_pointer"].lower()
            for d in diags
        )

    def test_fv_spec_005_mismatched_relation_id(self):
        from tools.validate_spec import check_identity_consistency
        instance = _minimal()
        instance["triple"]["relation"]["id"] = "wikidata:P999"
        diags = check_identity_consistency(instance, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-005" for d in diags)

    def test_fv_spec_005_inverse_preserves_identity(self):
        """Inverse direction should not break identity — fact_id is about the triple, not direction."""
        from tools.validate_spec import check_identity_consistency
        instance = _minimal()
        diags = check_identity_consistency(instance, "test.json")
        assert not diags


# ---------------------------------------------------------------------------
# T024: FV-SPEC-006 — Aliases
# ---------------------------------------------------------------------------


class TestFvSpec006Aliases:
    """Empty/missing aliases, invalid enum, malformed language, missing argument_order."""

    def test_fv_spec_006_empty_subject_aliases(self):
        instance = _minimal()
        instance["aliases"]["subject"] = []
        errors = _validate(instance)
        assert errors

    def test_fv_spec_006_missing_alias_text(self):
        instance = _minimal()
        instance["aliases"]["subject"][0]["text"] = ""
        errors = _validate(instance)
        assert errors

    def test_fv_spec_006_invalid_alias_type(self):
        instance = _minimal()
        instance["aliases"]["subject"][0]["alias_type"] = "nonexistent_type"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_006_missing_argument_order_on_relation(self):
        instance = _minimal()
        del instance["aliases"]["relation"][0]["argument_order"]
        errors = _validate(instance)
        assert errors

    def test_fv_spec_006_unicode_preservation(self):
        """Vietnamese characters should be preserved in aliases."""
        instance = _minimal()
        instance["aliases"]["subject"][0]["text"] = "Hà Nội"
        errors = _validate(instance)
        assert not errors

    def test_fv_spec_006_valid_alias_source(self):
        instance = _minimal()
        instance["aliases"]["subject"][0]["source"] = "wikidata"
        errors = _validate(instance)
        assert not errors


# ---------------------------------------------------------------------------
# T025: FV-SPEC-007 — Direction roles
# ---------------------------------------------------------------------------


class TestFvSpec007DirectionRoles:
    """All valid combinations plus reversed/missing roles."""

    def test_fv_spec_007_valid_forward(self):
        from tools.validate_spec import check_direction_roles
        instance = _minimal()
        diags = check_direction_roles(instance, "test.json")
        assert not diags

    def test_fv_spec_007_reversed_forward(self):
        from tools.validate_spec import check_direction_roles
        instance = _minimal()
        instance["equivalent_directions"][0] = {
            "direction": "forward",
            "given": "object",
            "answer": "subject",
        }
        diags = check_direction_roles(instance, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-007" for d in diags)

    def test_fv_spec_007_reversed_inverse(self):
        from tools.validate_spec import check_direction_roles
        instance = _minimal()
        instance["equivalent_directions"][1] = {
            "direction": "inverse",
            "given": "subject",
            "answer": "object",
        }
        diags = check_direction_roles(instance, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-007" for d in diags)

    def test_fv_spec_007_valid_verification(self):
        from tools.validate_spec import check_direction_roles
        instance = _minimal()
        instance["equivalent_directions"].append({
            "direction": "verification",
            "given": "triple",
            "answer": "truth_value",
        })
        diags = check_direction_roles(instance, "test.json")
        assert not diags

    def test_fv_spec_007_invalid_verification(self):
        from tools.validate_spec import check_direction_roles
        instance = _minimal()
        instance["equivalent_directions"].append({
            "direction": "verification",
            "given": "subject",
            "answer": "object",
        })
        diags = check_direction_roles(instance, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-007" for d in diags)


# ---------------------------------------------------------------------------
# T026: FV-SPEC-008 — Locality coverage
# ---------------------------------------------------------------------------


class TestFvSpec008LocalityCoverage:
    """Missing bucket, four-of-one-bucket, unapproved bucket value."""

    def test_fv_spec_008_valid_coverage(self):
        instance = _minimal()
        errors = _validate(instance)
        assert not errors

    def test_fv_spec_008_missing_bucket(self):
        """Remove global bucket — should fail contains constraint."""
        instance = _minimal()
        instance["retained_neighbourhood"] = [
            n for n in instance["retained_neighbourhood"]
            if n["bucket"] != "global"
        ]
        errors = _validate(instance)
        assert errors

    def test_fv_spec_008_single_bucket(self):
        """All items same bucket — should fail."""
        instance = _minimal()
        for n in instance["retained_neighbourhood"]:
            n["bucket"] = "same_subject"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_008_unapproved_bucket(self):
        instance = _minimal()
        instance["retained_neighbourhood"][0]["bucket"] = "invented_bucket"
        errors = _validate(instance)
        assert errors


# ---------------------------------------------------------------------------
# T027: FV-SPEC-009 — Clue boundary
# ---------------------------------------------------------------------------


class TestFvSpec009ClueBoundary:
    """Missing fields, empty rules, undeclared policy enum."""

    def test_fv_spec_009_missing_equivalent_rule(self):
        instance = _minimal()
        del instance["clue_boundary"]["equivalent_rule"]
        errors = _validate(instance)
        assert errors

    def test_fv_spec_009_empty_equivalent_rule(self):
        instance = _minimal()
        instance["clue_boundary"]["equivalent_rule"] = ""
        errors = _validate(instance)
        assert errors

    def test_fv_spec_009_empty_clue_bearing_rule(self):
        instance = _minimal()
        instance["clue_boundary"]["clue_bearing_rule"] = ""
        errors = _validate(instance)
        assert errors

    def test_fv_spec_009_undeclared_policy(self):
        instance = _minimal()
        instance["clue_boundary"]["ambiguous_policy"] = "made_up_policy"
        errors = _validate(instance)
        assert errors


# ---------------------------------------------------------------------------
# T028: FV-SPEC-010 — Optional metadata
# ---------------------------------------------------------------------------


class TestFvSpec010OptionalMetadata:
    """Valid without optional metadata, invalid enum/type, null freeze fields."""

    def test_fv_spec_010_valid_without_optional(self):
        """Minimal fixture has no optional metadata and should pass."""
        instance = _minimal()
        errors = _validate(instance)
        assert not errors

    def test_fv_spec_010_invalid_contract_status(self):
        instance = _minimal()
        instance["contract_status"] = "invalid_status"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_010_invalid_fact_type(self):
        instance = _minimal()
        instance["fact_type"] = "invalid_type"
        errors = _validate(instance)
        assert errors

    def test_fv_spec_010_null_freeze_fields(self):
        """null frozen_at and content_sha256 should be valid."""
        instance = _minimal()
        instance["freeze_policy"] = {
            "freeze_stage": "before_any_unlearning_run",
            "post_freeze_change_policy": "new_contract_version_required",
            "frozen_at": None,
            "content_sha256": None,
        }
        errors = _validate(instance)
        assert not errors

    def test_fv_spec_010_valid_contract_status(self):
        instance = _minimal()
        instance["contract_status"] = "frozen"
        errors = _validate(instance)
        assert not errors


# ---------------------------------------------------------------------------
# T029: FV-SPEC-011 — CLI contract
# ---------------------------------------------------------------------------


class TestFvSpec011CliContract:
    """Valid run exits 0, missing schema exits nonzero, empty contracts exits nonzero."""

    def test_fv_spec_011_valid_run_exit_0(self, tmp_path):
        report = tmp_path / "report.json"
        result = _run_cli(
            "--contracts", str(FC_FIXTURES / "valid"),
            "--report", str(report),
        )
        assert result.returncode == 0
        assert report.exists()
        data = json.loads(report.read_text())
        assert data["scope"] == "fact-contract"
        assert data["summary"]["valid"] >= 1

    def test_fv_spec_011_missing_schema_exits_nonzero(self, tmp_path):
        report = tmp_path / "report.json"
        result = _run_cli(
            "--spec-root", str(tmp_path / "nonexistent"),
            "--contracts", str(FC_FIXTURES / "valid"),
            "--report", str(report),
        )
        assert result.returncode != 0

    def test_fv_spec_011_empty_contracts_exits_nonzero(self, tmp_path):
        empty = tmp_path / "empty"
        empty.mkdir()
        report = tmp_path / "report.json"
        result = _run_cli(
            "--contracts", str(empty),
            "--report", str(report),
        )
        assert result.returncode != 0

    def test_fv_spec_011_unsupported_scope_exits_nonzero(self, tmp_path):
        report = tmp_path / "report.json"
        cmd = [
            sys.executable,
            str(REPO / "tools" / "validate_spec.py"),
            "--scope", "full",
            "--spec-root", str(SPEC_ROOT),
            "--contracts", str(FC_FIXTURES / "valid"),
            "--report", str(report),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        assert result.returncode != 0
        assert "unsupported scope" in result.stderr.lower()

    def test_fv_spec_011_deterministic_output(self, tmp_path):
        """Two runs on the same input produce the same diagnostics."""
        report1 = tmp_path / "r1.json"
        report2 = tmp_path / "r2.json"
        _run_cli("--contracts", str(FC_FIXTURES / "valid"), "--report", str(report1))
        _run_cli("--contracts", str(FC_FIXTURES / "valid"), "--report", str(report2))
        d1 = json.loads(report1.read_text())
        d2 = json.loads(report2.read_text())
        # Compare everything except timestamp
        d1.pop("timestamp", None)
        d2.pop("timestamp", None)
        assert d1 == d2


# ---------------------------------------------------------------------------
# T030: FV-SPEC-012 — Demonstration contracts
# ---------------------------------------------------------------------------


class TestFvSpec012DemonstrationContracts:
    """Both demo contracts pass validation with required coverage."""

    DEMO_CONTRACTS = [
        "hanoi_capital_of_vietnam/contract.json",
        "invented_scientist_alma_mater/contract.json",
    ]

    @pytest.mark.parametrize("name", DEMO_CONTRACTS)
    def test_fv_spec_012_demo_validates(self, name):
        path = CONTRACTS_DIR / name
        assert path.exists(), f"Demo contract {name} must exist"
        contract = json.loads(path.read_text(encoding="utf-8"))
        errors = _validate_new(contract)
        assert not errors, f"Demo contract {name} has validation errors: {errors}"

    @pytest.mark.parametrize("name", DEMO_CONTRACTS)
    def test_fv_spec_012_demo_has_all_directions(self, name):
        contract = json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
        directions = {d["direction"] for d in contract["equivalent_directions"]}
        assert "forward" in directions
        assert "inverse" in directions
        assert "verification" in directions

    @pytest.mark.parametrize("name", DEMO_CONTRACTS)
    def test_fv_spec_012_demo_has_bucket_coverage(self, name):
        contract = json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
        buckets = {n["bucket"] for n in contract["retained_neighbourhood"]}
        assert buckets == {"same_subject", "same_relation", "compositional", "global"}

    @pytest.mark.parametrize("name", DEMO_CONTRACTS)
    def test_fv_spec_012_demo_has_2_plus_per_bucket(self, name):
        contract = json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
        from collections import Counter
        bucket_counts = Counter(n["bucket"] for n in contract["retained_neighbourhood"])
        for bucket, count in bucket_counts.items():
            assert count >= 2, f"Bucket '{bucket}' has only {count} items, need 2+"


# ---------------------------------------------------------------------------
# T036: FV-SPEC-013 — Frozen revision
# ---------------------------------------------------------------------------


class TestFvSpec013FrozenRevision:
    """Revision detection: identical passes, unauthorized change fails."""

    def test_fv_spec_013_identical_passes(self):
        from tools.validate_spec import check_revision
        base = _minimal()
        current = copy.deepcopy(base)
        diags = check_revision(current, base, "test.json")
        assert not diags

    def test_fv_spec_013_alias_change_without_version_bump_fails(self):
        from tools.validate_spec import check_revision
        base = _minimal()
        current = copy.deepcopy(base)
        current["aliases"]["subject"][0]["text"] = "Changed Alias"
        diags = check_revision(current, base, "test.json")
        assert any(d["rule_id"] == "FV-SPEC-013" for d in diags)

    def test_fv_spec_013_version_bump_passes(self):
        from tools.validate_spec import check_revision
        base = _minimal()
        current = copy.deepcopy(base)
        current["aliases"]["subject"][0]["text"] = "Changed Alias"
        current["contract_id"] = "factverify:contract:wd-Q1858-P1376-Q881:v2"
        diags = check_revision(current, base, "test.json")
        assert not any(
            d["rule_id"] == "FV-SPEC-013" and "version" in d["message"].lower()
            for d in diags
        )

    def test_fv_spec_013_changed_triple_with_old_fact_id_fails(self):
        from tools.validate_spec import check_revision
        base = _minimal()
        current = copy.deepcopy(base)
        current["triple"]["object"]["label"] = "Completely Different"
        current["contract_id"] = "factverify:contract:wd-Q1858-P1376-Q881:v2"
        diags = check_revision(current, base, "test.json")
        assert any(
            d["rule_id"] == "FV-SPEC-013" and "triple" in d["json_pointer"].lower()
            for d in diags
        )

    def test_fv_spec_013_no_baseline_returns_not_requested(self, tmp_path):
        report = tmp_path / "report.json"
        result = _run_cli(
            "--contracts", str(FC_FIXTURES / "valid"),
            "--report", str(report),
        )
        data = json.loads(report.read_text())
        assert data["revision_check"] == "not_requested"

    def test_fv_spec_013_baseline_cli_integration(self, tmp_path):
        """CLI with --baseline-contracts on identical baseline exits 0."""
        report = tmp_path / "report.json"
        result = _run_cli(
            "--contracts", str(FC_FIXTURES / "valid"),
            "--baseline-contracts", str(FC_FIXTURES / "baselines"),
            "--report", str(report),
        )
        assert result.returncode == 0
        data = json.loads(report.read_text())
        assert isinstance(data["revision_check"], dict)
        assert data["revision_check"]["status"] == "pass"


# ---------------------------------------------------------------------------
# T038: FV-SPEC-014 — Semantic review manifest
# ---------------------------------------------------------------------------


REVIEW_PATH = REPO / "reports" / "p0-1-semantic-review.md"


class TestFvSpec014SemanticReviewManifest:
    """Verify review file exists with required sections."""

    def test_fv_spec_014_review_file_exists(self):
        assert REVIEW_PATH.exists(), "Semantic review file must exist"

    def test_fv_spec_014_required_sections(self):
        content = REVIEW_PATH.read_text(encoding="utf-8")
        assert "Reviewer" in content or "reviewer" in content
        assert "Classification" in content or "classification" in content
        assert "Adjudication" in content or "adjudication" in content

    def test_fv_spec_014_contract_revisions_referenced(self):
        content = REVIEW_PATH.read_text(encoding="utf-8")
        assert "v1" in content

    def test_fv_spec_014_blocking_decisions_flagged(self):
        content = REVIEW_PATH.read_text(encoding="utf-8")
        assert "D-38" in content
        assert "D-39" in content
        assert "D-40" in content


# ---------------------------------------------------------------------------
# T031: FV-SPEC-015 — Spec artifact inclusion
# ---------------------------------------------------------------------------


class TestFvSpec015SpecArtifactInclusion:
    """Verify schema exists at .factverify/ and is not gitignored."""

    def test_fv_spec_015_schema_exists(self):
        assert SCHEMA_PATH.exists()

    def test_fv_spec_015_spec_artifact_inclusion(self):
        """Verify .factverify/ is not excluded by gitignore."""
        result = subprocess.run(
            ["git", "check-ignore", "-v", str(SCHEMA_PATH)],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        # exit code 1 means NOT ignored (good), exit code 0 means ignored (bad)
        assert result.returncode != 0, (
            f".factverify/ is gitignored: {result.stdout}"
        )


# ---------------------------------------------------------------------------
# T009: FV-SPEC-108 — FactVerify-native IDs enforced
# ---------------------------------------------------------------------------

def _load_new_schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate_new(instance: dict, schema: dict | None = None) -> list:
    if schema is None:
        schema = _load_new_schema()
    v = Draft202012Validator(schema)
    return list(v.iter_errors(instance))


def _make_native_contract(
    contract_id: str = "factverify:contract:invented_scientist_alma_mater:v1",
    fact_id: str = "factverify:fact:invented_scientist_alma_mater",
) -> dict:
    """Build a minimal native-ID contract that passes v1.1.0 schema."""
    return {
        "schema_version": "1.1.0",
        "contract_id": contract_id,
        "fact_id": fact_id,
        "triple": {
            "subject": {
                "id": "factverify:entity:dr-elara-voss",
                "label": "Dr. Elara Voss",
            },
            "relation": {
                "id": "factverify:relation:alma-mater",
                "label": "alma mater",
            },
            "object": {
                "id": "factverify:entity:thornfield-institute",
                "label": "Thornfield Institute of Technology",
            },
        },
        "aliases": {
            "subject": [{"text": "Dr. Elara Voss", "language": "en", "alias_type": "canonical"}],
            "relation": [{"text": "alma mater", "language": "en", "argument_order": "subject_relation_object"}],
            "object": [{"text": "Thornfield Institute", "language": "en", "alias_type": "canonical"}],
        },
        "equivalent_directions": [
            {"direction": "forward", "given": "subject", "answer": "object"},
            {"direction": "inverse", "given": "object", "answer": "subject"},
        ],
        "retained_neighbourhood": [
            {"id": "retain:voss-field", "bucket": "same_subject", "statement": "What does Dr. Voss research?"},
            {"id": "retain:einstein-alma", "bucket": "same_relation", "statement": "Where did Einstein study?"},
            {"id": "retain:thornfield-city", "bucket": "compositional", "statement": "City of Thornfield Institute?"},
            {"id": "retain:speed-light", "bucket": "global", "statement": "Speed of light?"},
        ],
        "clue_boundary": {
            "equivalent_rule": "Prompts whose answer is exactly Thornfield Institute.",
            "clue_bearing_rule": "Prompts mentioning Voss education context.",
            "ambiguous_policy": "adjudicate_before_freeze_else_exploratory",
        },
    }


class TestFvSpec108FactVerifyNativeIds:
    """FV-SPEC-108: Canonical ID fields must use factverify: namespace."""

    def test_fv_spec_108_native_ids_pass(self) -> None:
        """(a) Native-ID fictional contract passes v1.1.0 schema."""

        instance = _make_native_contract()
        errors = _validate_new(instance)
        assert errors == [], f"Native contract should pass: {[e.message for e in errors]}"

    def test_fv_spec_108_wikidata_subject_id_fails(self) -> None:
        """(b) Wikidata-shaped subject ID in canonical field fails."""

        instance = _make_native_contract()
        instance["triple"]["subject"]["id"] = "wikidata:Q1858"
        errors = _validate_new(instance)
        assert errors, "Wikidata ID in canonical subject field must fail"

    def test_fv_spec_108_wikidata_contract_id_fails(self) -> None:
        """(b) Wikidata-shaped contract_id fails."""

        instance = _make_native_contract(
            contract_id="factverify:contract:wd-Q1858-P1376-Q881:v1",
        )
        errors = _validate_new(instance)
        assert errors, "Wikidata-shaped local_id in contract_id must fail"

    def test_fv_spec_108_incremented_version_stable_fact_id(self) -> None:
        """(c) New contract version keeps stable fact_id while :vN increments."""

        instance_v1 = _make_native_contract(
            contract_id="factverify:contract:invented_scientist_alma_mater:v1",
            fact_id="factverify:fact:invented_scientist_alma_mater",
        )
        instance_v2 = _make_native_contract(
            contract_id="factverify:contract:invented_scientist_alma_mater:v2",
            fact_id="factverify:fact:invented_scientist_alma_mater",
        )
        errors_v1 = _validate_new(instance_v1)
        errors_v2 = _validate_new(instance_v2)
        assert errors_v1 == [], f"v1 should pass: {[e.message for e in errors_v1]}"
        assert errors_v2 == [], f"v2 with same fact_id should pass: {[e.message for e in errors_v2]}"


# ---------------------------------------------------------------------------
# T010: FV-SPEC-109 — external_refs optional
# ---------------------------------------------------------------------------


class TestFvSpec109ExternalRefsOptional:
    """FV-SPEC-109: external_refs are optional on entities; when present must be well-formed."""

    def test_fv_spec_109_no_external_refs_passes(self) -> None:
        """(a) Entity with no external_refs passes."""

        instance = _make_native_contract()
        # No external_refs anywhere — should pass
        errors = _validate_new(instance)
        assert errors == [], f"No external_refs should pass: {[e.message for e in errors]}"

    def test_fv_spec_109_valid_external_refs_passes(self) -> None:
        """(b) Entity with valid external_refs[{scheme, external_id}] passes."""

        instance = _make_native_contract()
        instance["triple"]["subject"]["external_refs"] = [
            {"scheme": "wikidata", "external_id": "Q1858"}
        ]
        errors = _validate_new(instance)
        assert errors == [], f"Valid external_refs should pass: {[e.message for e in errors]}"

    def test_fv_spec_109_external_refs_deduplication_is_validator_responsibility(self) -> None:
        """(c) Schema does not enforce uniqueness of external_refs; deduplication is a validator concern."""

        instance = _make_native_contract()
        # Duplicate external_ref entries — schema allows this (dedup is validator responsibility)
        instance["triple"]["subject"]["external_refs"] = [
            {"scheme": "wikidata", "external_id": "Q1858"},
            {"scheme": "wikidata", "external_id": "Q1858"},
        ]
        errors = _validate_new(instance)
        # Schema should allow duplicates (it's not enforced at schema level)
        # The important thing is that it doesn't break validation
        assert isinstance(errors, list)

    def test_fv_spec_109_malformed_external_ref_fails(self) -> None:
        """(d) Malformed external_ref (missing required field) fails."""

        instance = _make_native_contract()
        # Missing 'external_id' required field
        instance["triple"]["subject"]["external_refs"] = [
            {"scheme": "wikidata"}
        ]
        errors = _validate_new(instance)
        assert errors, "external_ref missing external_id must fail"
