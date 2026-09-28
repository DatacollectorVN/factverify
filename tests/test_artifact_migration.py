"""Tests for tools.migrate_artifacts (FV-SPEC-105, FV-SPEC-111)."""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pytest


FIXTURE_LEGACY = Path(__file__).parent / "fixtures" / "migration" / "legacy"


def test_fv_spec_105_legacy_accounting(tmp_path: Path) -> None:
    """Dry-run produces complete mapping; execute accounts for every artifact."""
    # Set up a minimal source tree from fixtures
    source = tmp_path / ".factverify_legacy"
    source.mkdir()
    contracts = source / "contracts"
    contracts.mkdir()
    shutil.copy(FIXTURE_LEGACY / "contracts" / "factverify-contract-wd-Q1858-P1376-Q881-v1.json", contracts)
    shutil.copy(FIXTURE_LEGACY / "contracts" / "factverify-contract-invented_scientist_alma_mater-v1.json", contracts)
    decisions_dir = source / "decisions"
    decisions_dir.mkdir()
    shutil.copy(FIXTURE_LEGACY / "decisions" / "register.yaml", decisions_dir)

    report_path = tmp_path / "migration-report.json"
    target_spec = tmp_path / ".factverify"
    target_spec.mkdir()

    # Import and run the migrator directly
    from tools.migrate_artifacts import run_migration, MigrationMode

    report = run_migration(
        source_root=source,
        spec_root=target_spec,
        internal_root=tmp_path / ".factverify_internal",
        mode=MigrationMode.DRY_RUN,
        report_path=report_path,
    )

    # All source artifacts must be accounted for
    assert len(report["unresolved"]) == 0, f"Unresolved: {report['unresolved']}"
    assert len(report["entries"]) >= 2, "Expected at least 2 entries (one per contract)"

    # Report file written
    assert report_path.exists()

    # Wikidata-backed fact gets native IDs and external_refs
    wikidata_entry = next(
        (e for e in report["entries"] if "wd-Q1858" in e["source_path"]),
        None,
    )
    assert wikidata_entry is not None, "Wikidata-backed contract must appear in report"
    assert wikidata_entry["new_id"] == "factverify:fact:hanoi_capital_of_vietnam", (
        f"Expected native fact ID hanoi_capital_of_vietnam, got: {wikidata_entry['new_id']}"
    )
    assert len(wikidata_entry["external_refs_added"]) > 0, (
        "Wikidata-backed contract must add external_refs"
    )


def test_fv_spec_105_execute_migration(tmp_path: Path) -> None:
    """Execute mode writes migrated contracts to fact bundle directories."""
    source = tmp_path / ".factverify_legacy"
    source.mkdir()
    contracts = source / "contracts"
    contracts.mkdir()
    shutil.copy(FIXTURE_LEGACY / "contracts" / "factverify-contract-wd-Q1858-P1376-Q881-v1.json", contracts)

    target_spec = tmp_path / ".factverify"
    target_spec.mkdir()

    from tools.migrate_artifacts import run_migration, MigrationMode

    report = run_migration(
        source_root=source,
        spec_root=target_spec,
        internal_root=tmp_path / ".factverify_internal",
        mode=MigrationMode.EXECUTE,
    )

    assert report["overall"] == "pass"
    # Find the migrated contract
    fact_dirs = list((target_spec / "facts").iterdir()) if (target_spec / "facts").exists() else []
    assert len(fact_dirs) >= 1, "Expected at least one fact directory after execute"

    # The directory name must use native IDs, not Wikidata slugs
    fact_dir_names = [d.name for d in fact_dirs]
    assert "hanoi_capital_of_vietnam" in fact_dir_names, (
        f"Expected hanoi_capital_of_vietnam dir, got: {fact_dir_names}"
    )

    # The migrated contract must use native IDs
    for fact_dir in fact_dirs:
        contract_path = fact_dir / "contract.json"
        if contract_path.exists():
            contract = json.loads(contract_path.read_text(encoding="utf-8"))
            assert contract["schema_version"] == "1.1.0"
            assert contract["fact_id"].startswith("factverify:fact:")
            # Must not contain wd-Q pattern in canonical IDs
            assert "wd-Q" not in contract["fact_id"]


def test_fv_spec_105_fail_closed(tmp_path: Path) -> None:
    """A failed execute migration leaves the source tree unchanged."""
    source = tmp_path / ".factverify_corrupt"
    source.mkdir()
    (source / "contracts").mkdir()
    # Write a corrupt JSON file
    (source / "contracts" / "bad.json").write_text("{invalid json}", encoding="utf-8")

    from tools.migrate_artifacts import run_migration, MigrationMode, MigrationError

    with pytest.raises(MigrationError):
        run_migration(
            source_root=source,
            spec_root=tmp_path / ".factverify",
            internal_root=tmp_path / ".factverify_internal",
            mode=MigrationMode.EXECUTE,
        )

    # Source tree must still exist unchanged
    assert (source / "contracts" / "bad.json").exists()


def test_fv_spec_111_no_active_legacy_surface() -> None:
    """No production code references retired paths or the deleted load_model_spec."""
    repo_root = Path(__file__).parents[1]

    # Files that ARE allowed to reference legacy paths:
    # - migration tooling and fixtures reference the old path intentionally
    # - test_artifact_layout.py tests that validate_layout rejects models.yaml
    # - test_model_config.py asserts that models.yaml is absent (retirement test)
    allowed_paths = {
        "tests/fixtures/migration",
        "specs/",
        "tools/migrate_artifacts.py",  # migration tool itself references legacy paths
        "tests/test_artifact_layout.py",  # validator test: rejects models.yaml presence
        "tests/test_model_config.py",     # retirement assertion: models.yaml absent
    }

    retired_patterns = [
        r"\.factverify/spec/models\.yaml",
        r"load_model_spec\(",  # deleted function
    ]

    violations = []
    for path in repo_root.rglob("*.py"):
        rel = str(path.relative_to(repo_root))
        if any(allowed in rel for allowed in allowed_paths):
            continue
        if "/__pycache__/" in rel or "/.specify/" in rel:
            continue
        content = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in retired_patterns:
            if re.search(pattern, content):
                violations.append(f"{rel}: matches {pattern!r}")

    assert violations == [], "\n".join(violations)
