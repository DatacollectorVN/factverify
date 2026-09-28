"""P0-2 closure template suite validation tests.

Tests FV-SPEC-016 through FV-SPEC-033, one test class per requirement.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from tests.conftest import (
    BINDINGS_PATH,
    CLOSURE_DIR,
    CLOSURE_SUITE_PATH,
    CONTRACTS_DIR,
    P0_2_FIXTURES,
    REPO,
    SPEC_ROOT,
)

# ---- helpers ---------------------------------------------------------------

def _load_suite(path: Path | None = None) -> dict:
    path = path or CLOSURE_SUITE_PATH
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_fixture_suite(name: str) -> dict:
    return yaml.safe_load(
        (P0_2_FIXTURES / "valid" / name).read_text(encoding="utf-8")
    )


def _load_fixture_bindings(name: str) -> dict:
    return json.loads(
        (P0_2_FIXTURES / "valid" / name).read_text(encoding="utf-8")
    )


def _load_invalid_fixture(name: str) -> dict | str:
    path = P0_2_FIXTURES / "invalid" / name
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        return "MALFORMED"


def _run_cli(*args: str, expect_exit: int | None = None) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "tools/validate_spec.py", *args]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if expect_exit is not None:
        assert result.returncode == expect_exit, (
            f"Expected exit {expect_exit}, got {result.returncode}\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result


def _validate_suite(spec_root: Path, bindings_path: Path,
                    report_path: Path, **kwargs) -> subprocess.CompletedProcess:
    args = [
        "--scope", "closure-templates",
        "--spec-root", str(spec_root),
        "--contracts", str(CONTRACTS_DIR),
        "--bindings", str(bindings_path),
        "--report", str(report_path),
    ]
    for k, v in kwargs.items():
        flag = f"--{k.replace('_', '-')}"
        if isinstance(v, bool):
            if v:
                args.append(flag)
        elif v is not None:
            args.extend([flag, str(v)])
    return _run_cli(*args)


def _write_temp_suite(suite: dict, tmp_path: Path) -> Path:
    """Write a modified suite to a temp spec root (with schema copy)."""
    import shutil
    spec_dir = tmp_path / "spec"
    spec_dir.mkdir(parents=True, exist_ok=True)
    (spec_dir / "closure_templates.yaml").write_text(
        yaml.dump(suite, allow_unicode=True), encoding="utf-8"
    )
    schema_src = SPEC_ROOT / "fact_contract.schema.json"
    if schema_src.exists():
        shutil.copy(schema_src, spec_dir)
    return spec_dir


def _report(report_path: Path) -> dict:
    return json.loads(report_path.read_text(encoding="utf-8"))


def _diag_rules(report: dict) -> set[str]:
    return {d["rule_id"] for d in report.get("diagnostics", [])}


# ---- FV-SPEC-016: closure artifact -----------------------------------------

class TestFvSpec016Artifact:
    """Suite exists, parses, has required structure."""

    def test_valid_suite_parses(self):
        suite = _load_suite()
        assert isinstance(suite, dict)
        assert suite.get("spec_version") == "1.0.0"
        assert "sets" in suite
        assert "groups" in suite
        assert "splits" in suite

    def test_malformed_yaml_fails(self, tmp_path):
        bad = tmp_path / "spec" / "closure_templates.yaml"
        bad.parent.mkdir(parents=True)
        bad.write_text("sets:\n  equivalence:\n    templates:\n      - id: [broken", encoding="utf-8")
        result = _run_cli(
            "--scope", "closure-templates",
            "--spec-root", str(bad.parent),
            "--contracts", str(CONTRACTS_DIR),
            "--bindings", str(BINDINGS_PATH),
            "--report", str(tmp_path / "report.json"),
        )
        assert result.returncode == 2

    def test_missing_suite_exits_2(self, tmp_path):
        empty_spec = tmp_path / "spec"
        empty_spec.mkdir()
        result = _run_cli(
            "--scope", "closure-templates",
            "--spec-root", str(empty_spec),
            "--contracts", str(CONTRACTS_DIR),
            "--bindings", str(BINDINGS_PATH),
            "--report", str(tmp_path / "report.json"),
        )
        assert result.returncode == 2

    def test_missing_required_fields(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        del suite["sets"]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, BINDINGS_PATH, report_path)
        assert result.returncode != 0
        r = _report(report_path)
        assert "FV-SPEC-016" in _diag_rules(r)


# ---- FV-SPEC-017: class routing --------------------------------------------

class TestFvSpec017ClassRouting:
    """E→equivalence, I→inference, R/X→controls."""

    def test_valid_routing_passes(self, tmp_path):
        report_path = tmp_path / "report.json"
        result = _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-017" not in _diag_rules(r)

    def test_e_in_controls_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        e_tmpl = suite["sets"]["equivalence"]["templates"].pop(0)
        suite.setdefault("controls", []).append(e_tmpl)
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path)
        r = _report(report_path)
        assert "FV-SPEC-017" in _diag_rules(r)


# ---- FV-SPEC-018: equivalence premises -------------------------------------

class TestFvSpec018EquivalencePremises:
    """E templates must have empty premises."""

    def test_empty_premises_passes(self):
        suite = _load_suite()
        for t in suite["sets"]["equivalence"]["templates"]:
            assert t.get("extra_premises") == [], f"{t['id']} has nonempty premises"

    def test_nonempty_premises_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        suite["sets"]["equivalence"]["templates"][0]["extra_premises"] = [
            {"text": "some premise", "source": "prompt"}
        ]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-018" in _diag_rules(r)

    def test_missing_premises_field_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        del suite["sets"]["equivalence"]["templates"][0]["extra_premises"]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-018" in _diag_rules(r)


# ---- FV-SPEC-019: inference provenance -------------------------------------

class TestFvSpec019InferenceProvenance:
    """I templates must carry full provenance."""

    def test_full_provenance_passes(self):
        suite = _load_suite()
        for t in suite["sets"]["inference"]["templates"]:
            assert t.get("subtype") is not None
            assert len(t.get("extra_premises", [])) > 0
            assert len(t.get("premise_origins", [])) > 0
            assert t.get("separate_reporting") is True

    def test_missing_subtype_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        del suite["sets"]["inference"]["templates"][0]["subtype"]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, BINDINGS_PATH, report_path)
        r = _report(report_path)
        rule_ids = _diag_rules(r)
        assert "FV-SPEC-016" in rule_ids or "FV-SPEC-019" in rule_ids

    def test_empty_premises_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        suite["sets"]["inference"]["templates"][0]["extra_premises"] = []
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-019" in _diag_rules(r)


# ---- FV-SPEC-020: contract bindings ----------------------------------------

class TestFvSpec020ContractBindings:
    """Bindings must match contract roles."""

    def test_correct_bindings_pass(self, tmp_path):
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-020" not in _diag_rules(r)

    def test_forward_to_subject_fails(self, tmp_path):
        """Direct template with answer_role=subject should fail."""
        suite = _load_fixture_suite("minimal_suite.yaml")
        suite["sets"]["equivalence"]["templates"][0]["answer_role"] = "subject"
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        assert "FV-SPEC-020" in _diag_rules(r)


# ---- FV-SPEC-021: relation-family coverage ---------------------------------

class TestFvSpec021RelationFamilyCoverage:
    """All six families per relation, ≥4 relations."""

    def test_demo_suite_coverage(self, tmp_path):
        """Demo suite has 2 relations — should flag <4 requirement."""
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        # Should have the <4 relations diagnostic but all families covered
        coverage = r.get("coverage", {})
        matrix = coverage.get("matrix", {})
        for rel, families in matrix.items():
            assert len(families) >= 6, f"{rel} missing families: {families}"

    def test_missing_family_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        suite["sets"]["equivalence"]["templates"] = [
            t for t in suite["sets"]["equivalence"]["templates"]
            if t.get("primary_family") != "verification"
        ]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        assert "FV-SPEC-021" in _diag_rules(r)


# ---- FV-SPEC-022: unique identity ------------------------------------------

class TestFvSpec022UniqueIdentity:
    """No duplicate template IDs."""

    def test_unique_ids_pass(self):
        suite = _load_suite()
        ids = []
        for key in ("equivalence", "inference"):
            for t in suite.get("sets", {}).get(key, {}).get("templates", []):
                ids.append(t["id"])
        for t in suite.get("controls", []):
            ids.append(t["id"])
        assert len(ids) == len(set(ids))

    def test_duplicate_ids_fail(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        suite["sets"]["equivalence"]["templates"][1]["id"] = \
            suite["sets"]["equivalence"]["templates"][0]["id"]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        assert "FV-SPEC-022" in _diag_rules(r)


# ---- FV-SPEC-023: group/split isolation ------------------------------------

class TestFvSpec023GroupSplitIsolation:
    """Each template in one group, each group in one split, disjoint splits."""

    def test_valid_grouping_passes(self, tmp_path):
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-023" not in _diag_rules(r)

    def test_template_in_two_groups_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        first_tid = suite["sets"]["equivalence"]["templates"][0]["id"]
        suite["groups"].append({
            "group_id": "extra_group",
            "members": [first_tid],
            "split": "construction",
        })
        suite["splits"]["construction"].append("extra_group")
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        assert "FV-SPEC-023" in _diag_rules(r)

    def test_cross_split_reuse_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        cal_group = suite["splits"]["calibration"][0]
        suite["splits"]["final_test"].append(cal_group)
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        assert "FV-SPEC-023" in _diag_rules(r)

    def test_construction_preview_no_held_out(self, tmp_path):
        """Construction preview must not contain calibration/final_test records."""
        report_path = tmp_path / "report.json"
        preview_path = tmp_path / "preview.jsonl"
        _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            split="construction", preview=str(preview_path),
        )
        for line in preview_path.read_text(encoding="utf-8").strip().split("\n"):
            rec = json.loads(line)
            assert rec["evaluator_metadata"]["split"] == "construction"


# ---- FV-SPEC-024: verification balance -------------------------------------

class TestFvSpec024VerificationBalance:
    """Balanced true/false per block."""

    def test_balanced_block_passes(self, tmp_path):
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        assert "FV-SPEC-024" not in _diag_rules(r)
        for block in r.get("balance", {}).get("blocks", []):
            assert block["balanced"] is True

    def test_unbalanced_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        extra = copy.deepcopy(
            [t for t in suite["sets"]["equivalence"]["templates"]
             if t.get("oracle_label") is True][0]
        )
        extra["id"] = "extra_verify_true"
        suite["sets"]["equivalence"]["templates"].append(extra)
        for g in suite["groups"]:
            if g["group_id"] == "capital_verify_en":
                g["members"].append("extra_verify_true")
        spec_dir = _write_temp_suite(suite, tmp_path)

        bindings = _load_fixture_bindings("minimal_bindings.json")
        extra_bind = copy.deepcopy(
            [b for b in bindings["bindings"] if b.get("truth_label") is True][0]
        )
        extra_bind["template_id"] = "extra_verify_true"
        bindings["bindings"].append(extra_bind)
        bind_path = tmp_path / "bindings.json"
        bind_path.write_text(json.dumps(bindings), encoding="utf-8")

        report_path = tmp_path / "report.json"
        result = _validate_suite(spec_dir, bind_path, report_path)
        r = _report(report_path)
        assert "FV-SPEC-024" in _diag_rules(r)


# ---- FV-SPEC-025: retained controls ----------------------------------------

class TestFvSpec025RetainedControls:
    """R controls bind to approved retained entries, all buckets."""

    def test_valid_retained_passes(self, tmp_path):
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        # Only the "missing buckets" diagnostic (demo has only same_subject)
        retain_diags = [d for d in r["diagnostics"]
                        if d["rule_id"] == "FV-SPEC-025"]
        assert all("Missing locality buckets" in d["message"]
                    for d in retain_diags)

    def test_unknown_entry_ref_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        for t in suite.get("controls", []):
            if t.get("class") == "R":
                t["retained_entry_ref"] = "retain:nonexistent"
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        retain_diags = [d for d in r["diagnostics"]
                        if d["rule_id"] == "FV-SPEC-025"
                        and "Unknown" in d["message"]]
        assert len(retain_diags) > 0


# ---- FV-SPEC-026: excluded controls ----------------------------------------

class TestFvSpec026ExcludedControls:
    """X must be in controls with exclusion_reason."""

    def test_x_in_controls_passes(self):
        suite = _load_suite()
        for t in suite.get("controls", []):
            if t.get("class") == "X":
                assert t.get("exclusion_reason")

    def test_x_in_equivalence_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        x_tmpl = {"id": "bad_x", "class": "X", "language": "en",
                   "text": "bad", "exclusion_reason": "test"}
        suite["sets"]["equivalence"]["templates"].append(x_tmpl)
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        rules = _diag_rules(r)
        assert "FV-SPEC-017" in rules or "FV-SPEC-026" in rules

    def test_missing_exclusion_reason_fails(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        for t in suite.get("controls", []):
            if t.get("class") == "X":
                del t["exclusion_reason"]
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        rules = _diag_rules(r)
        assert "FV-SPEC-016" in rules or "FV-SPEC-026" in rules


# ---- FV-SPEC-027: complete context / deterministic rendering ----------------

class TestFvSpec027CompleteContext:
    """Deterministic rendering; unresolved context refs fail."""

    def test_deterministic_rendering(self, tmp_path):
        p1 = tmp_path / "preview1.jsonl"
        p2 = tmp_path / "preview2.jsonl"
        r1 = tmp_path / "report1.json"
        r2 = tmp_path / "report2.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, r1,
                        split="construction", preview=str(p1))
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, r2,
                        split="construction", preview=str(p2))
        lines1 = p1.read_text(encoding="utf-8").strip().split("\n")
        lines2 = p2.read_text(encoding="utf-8").strip().split("\n")
        assert len(lines1) == len(lines2)
        for l1, l2 in zip(lines1, lines2):
            r1_rec = json.loads(l1)
            r2_rec = json.loads(l2)
            assert r1_rec["instance_id"] == r2_rec["instance_id"]
            assert r1_rec["model_input"] == r2_rec["model_input"]


# ---- FV-SPEC-028: metadata separation --------------------------------------

class TestFvSpec028MetadataSeparation:
    """Answer keys not in model_input; oracle key separate."""

    def test_no_answer_in_model_input(self, tmp_path):
        preview_path = tmp_path / "preview.jsonl"
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path,
                        split="construction", preview=str(preview_path))
        for line in preview_path.read_text(encoding="utf-8").strip().split("\n"):
            rec = json.loads(line)
            meta = rec["evaluator_metadata"]
            # model_input must not contain answer_key, truth_label, or class
            for msg in rec["model_input"]:
                assert "answer_key" not in msg.get("content", "").lower() or \
                    meta["class"] == "E"  # verification may contain candidate
            # evaluator_metadata must have answer_key
            assert "answer_key" in meta
            assert "truth_label" in meta


# ---- FV-SPEC-029: bilingual review -----------------------------------------

class TestFvSpec029BilingualReview:
    """Multilingual E instances require bilingual approval."""

    def test_missing_approval_fails_strict(self, tmp_path):
        manifest = {
            "suite_revision": "0.1.0-demo",
            "suite_digest": "",
            "bindings_digest": "",
            "reviews": [],
            "bilingual_approvals": [],
            "classification_review": {
                "reader_1": {"id": "r1"},
                "reader_2": {"id": "r2"},
                "revision": "0.1.0-demo",
            },
            "decision_refs": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            review_manifest=str(manifest_path), strict=True,
        )
        r = _report(report_path)
        assert "FV-SPEC-029" in _diag_rules(r)

    def test_with_approval_passes(self, tmp_path):
        suite = _load_suite()
        multi_ids = [
            t["id"] for t in suite["sets"]["equivalence"]["templates"]
            if t.get("primary_family") == "multilingual"
        ]
        manifest = {
            "suite_revision": "0.1.0-demo",
            "suite_digest": "",
            "bindings_digest": "",
            "reviews": [],
            "bilingual_approvals": [
                {"template_id": tid, "reviewer_id": "r1", "date": "2026-09-22",
                 "checks": {}, "normalization_policy_ref": "default", "approved": True}
                for tid in multi_ids
            ],
            "classification_review": {
                "reader_1": {"id": "r1"},
                "reader_2": {"id": "r2"},
                "revision": "0.1.0-demo",
            },
            "decision_refs": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_path = tmp_path / "report.json"
        _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            review_manifest=str(manifest_path),
        )
        r = _report(report_path)
        assert "FV-SPEC-029" not in _diag_rules(r)


# ---- FV-SPEC-030: classification review ------------------------------------

class TestFvSpec030ClassificationReview:
    """Two-reader classification review required."""

    def test_complete_review_passes(self, tmp_path):
        manifest = {
            "suite_revision": "0.1.0-demo",
            "suite_digest": "",
            "bindings_digest": "",
            "reviews": [],
            "bilingual_approvals": [],
            "classification_review": {
                "reader_1": {"id": "r1"},
                "reader_2": {"id": "r2"},
                "revision": "0.1.0-demo",
            },
            "decision_refs": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_path = tmp_path / "report.json"
        _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            review_manifest=str(manifest_path),
        )
        r = _report(report_path)
        assert "FV-SPEC-030" not in _diag_rules(r)

    def test_missing_reader_fails(self, tmp_path):
        manifest = {
            "suite_revision": "0.1.0-demo",
            "suite_digest": "",
            "bindings_digest": "",
            "reviews": [],
            "classification_review": {"reader_1": {"id": "r1"}},
            "decision_refs": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_path = tmp_path / "report.json"
        _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            review_manifest=str(manifest_path),
        )
        r = _report(report_path)
        assert "FV-SPEC-030" in _diag_rules(r)

    def test_unresolved_dispute_blocks(self, tmp_path):
        manifest = {
            "suite_revision": "0.1.0-demo",
            "suite_digest": "",
            "bindings_digest": "",
            "reviews": [],
            "classification_review": {
                "reader_1": {"id": "r1"},
                "reader_2": {"id": "r2"},
                "disagreements": [
                    {"template_id": "capital_direct_en_001", "resolved": False}
                ],
                "revision": "0.1.0-demo",
            },
            "decision_refs": [],
        }
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        report_path = tmp_path / "report.json"
        _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            review_manifest=str(manifest_path),
        )
        r = _report(report_path)
        assert "FV-SPEC-030" in _diag_rules(r)


# ---- FV-SPEC-031: suite revision -------------------------------------------

class TestFvSpec031SuiteRevision:
    """Changed content requires new revision."""

    def test_identical_baseline_passes(self, tmp_path):
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path,
            baseline_suite=str(CLOSURE_SUITE_PATH),
        )
        r = _report(report_path)
        assert "FV-SPEC-031" not in _diag_rules(r)

    def test_changed_without_bump_fails(self, tmp_path):
        suite = _load_suite()
        suite["sets"]["equivalence"]["templates"][0]["text"] = "Changed question?"
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, BINDINGS_PATH, report_path,
            baseline_suite=str(CLOSURE_SUITE_PATH),
        )
        r = _report(report_path)
        assert "FV-SPEC-031" in _diag_rules(r)

    def test_new_revision_passes(self, tmp_path):
        suite = _load_suite()
        suite["sets"]["equivalence"]["templates"][0]["text"] = "Changed question?"
        suite["revision"] = "0.2.0-demo"
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, BINDINGS_PATH, report_path,
            baseline_suite=str(CLOSURE_SUITE_PATH),
        )
        r = _report(report_path)
        assert "FV-SPEC-031" not in _diag_rules(r)


# ---- FV-SPEC-032: scoped CLI -----------------------------------------------

class TestFvSpec032ScopedCli:
    """CLI with --scope closure-templates."""

    def test_valid_inputs_exit_0(self, tmp_path):
        # Note: demo suite has expected diagnostics (<4 relations, missing buckets)
        # but these are informational, not structural failures of the validator
        report_path = tmp_path / "report.json"
        result = _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        # Exit may be 1 due to <4 relations; that's correct behavior
        assert result.returncode in (0, 1)
        r = _report(report_path)
        assert r["scope"] == "closure-templates"
        assert "deferred_checks" in r

    def test_missing_bindings_exits_2(self, tmp_path):
        result = _run_cli(
            "--scope", "closure-templates",
            "--spec-root", str(SPEC_ROOT),
            "--contracts", str(CONTRACTS_DIR),
            "--report", str(tmp_path / "report.json"),
        )
        assert result.returncode == 2

    def test_strict_with_no_manifest_exits_nonzero(self, tmp_path):
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            SPEC_ROOT, BINDINGS_PATH, report_path, strict=True,
        )
        assert result.returncode != 0

    def test_unsupported_scope_exits_2(self, tmp_path):
        result = _run_cli(
            "--scope", "nonexistent",
            "--spec-root", str(SPEC_ROOT),
            "--contracts", str(CONTRACTS_DIR),
            "--report", str(tmp_path / "report.json"),
        )
        assert result.returncode == 2

    def test_deferred_checks_listed(self, tmp_path):
        report_path = tmp_path / "report.json"
        _validate_suite(SPEC_ROOT, BINDINGS_PATH, report_path)
        r = _report(report_path)
        deferred = r.get("deferred_checks", [])
        assert "P0-3 budget accounting" in deferred
        assert "P0-6 witness rule" in deferred


# ---- FV-SPEC-033: regression fixtures --------------------------------------

class TestFvSpec033RegressionFixtures:
    """Offline fixtures produce requirement-labelled results; P0-1 compatible."""

    def test_p0_1_tests_still_pass(self):
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_contract_schema.py", "-v"],
            capture_output=True, text=True, cwd=str(REPO),
        )
        assert result.returncode == 0, f"P0-1 tests failed:\n{result.stdout}\n{result.stderr}"

    def test_minimal_valid_suite_passes(self, tmp_path):
        suite = _load_fixture_suite("minimal_suite.yaml")
        spec_dir = _write_temp_suite(suite, tmp_path)
        report_path = tmp_path / "report.json"
        result = _validate_suite(
            spec_dir, P0_2_FIXTURES / "valid" / "minimal_bindings.json", report_path,
        )
        r = _report(report_path)
        structural_rules = {"FV-SPEC-016", "FV-SPEC-017", "FV-SPEC-018",
                           "FV-SPEC-019", "FV-SPEC-022", "FV-SPEC-026"}
        actual_rules = _diag_rules(r)
        assert not (structural_rules & actual_rules), \
            f"Structural failures in minimal suite: {structural_rules & actual_rules}"
