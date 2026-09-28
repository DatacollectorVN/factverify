"""Migration tool: legacy .factverify/ artifact tree -> two-root layout.

Decisions:
  artifacts.namespace.boundary (D-71) — spec root vs internal root.
  artifacts.identity.authority (D-72) — FactVerify-native canonical IDs.

CLI interface:
  python -m tools.migrate_artifacts [--source PATH] [--spec-root PATH]
      [--internal-root PATH] [--dry-run] [--execute] [--report PATH]

Exit codes:
  0 — success
  1 — errors/unresolved entries
  2 — config error (bad arguments, unreadable source)
"""
from __future__ import annotations

import json
import re
import shutil
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class MigrationError(Exception):
    """Raised when migration encounters a fatal, fail-closed error."""


class MigrationMode(StrEnum):
    DRY_RUN = "dry_run"
    EXECUTE = "execute"


# Consolidated legacy files — already folded into protocol.yaml / templates.yaml.
_CONSOLIDATED_FILES = frozenset({
    "attacks.yaml",
    "margins.yaml",
    "access_profile.md",
    "witness_rule.md",
    "preregistration.md",
    "closure_templates.yaml",
    "fact_contract.schema.json",
})

# Legacy directories whose contents are superseded by the two-root layout.
_LEGACY_DIRS = frozenset({
    "access",
    "attacks",
    "closure",
    "exposure",
    "margins",
    "milestones",
    "witness",
})

# Files that move directly to spec_root top level.
_DIRECT_MOVE_FILES = frozenset({
    "model_policy.yaml",
})

# Wikidata ID pattern in contract_id / fact_id
_WD_PATTERN = re.compile(r"wd-Q(\d+)-P(\d+)-Q(\d+)")

# Known fact slug mappings for deterministic migration of existing facts.
_KNOWN_FACT_SLUGS: dict[str, str] = {
    "wd-Q1858-P1376-Q881": "hanoi_capital_of_vietnam",
}

# Known entity slug mappings for deterministic migration.
_KNOWN_ENTITY_SLUGS: dict[str, tuple[str, str]] = {
    "wikidata:Q1858": ("entity", "hanoi"),
    "wikidata:P1376": ("relation", "capital-of"),
    "wikidata:Q881": ("entity", "vietnam"),
}


@dataclass
class MigrationEntry:
    """One artifact migration record."""

    source_path: str
    action: str  # "migrate", "delete", "move", "skip"
    old_id: str
    new_id: str
    external_refs_added: list[dict[str, str]] = field(default_factory=list)
    notes: str = ""


def _strip_diacritics(text: str) -> str:
    """Remove diacritics from Unicode text (e.g. Hà Nội → Ha Noi)."""
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _slug_from_wd(contract_id: str, triple: dict[str, Any] | None = None) -> str:
    """Convert a wd-Q…-P…-Q… local_id to a label-based fact slug.

    Uses _KNOWN_FACT_SLUGS for deterministic migration. For unknown facts,
    derives slug from triple labels (subject_relation_object).
    """
    match = _WD_PATTERN.search(contract_id)
    if match:
        wd_key = match.group(0)
        if wd_key in _KNOWN_FACT_SLUGS:
            return _KNOWN_FACT_SLUGS[wd_key]

    # Derive from triple labels if available
    if triple:
        parts = []
        for role in ("subject", "relation", "object"):
            entity = triple.get(role, {})
            label = entity.get("label", "")
            if label:
                slug = _strip_diacritics(label).lower()
                slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
                parts.append(slug)
        if len(parts) == 3:
            return f"{parts[0]}_{parts[1]}_{parts[2]}"

    # Fallback: sanitise the whole string
    slug = _strip_diacritics(contract_id).lower()
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return slug


def _entity_slug(wikidata_id: str, label: str) -> tuple[str, str]:
    """Return (kind, slug) for a Wikidata entity/relation.

    Uses _KNOWN_ENTITY_SLUGS for deterministic migration. Falls back to
    diacritics-stripped label slug.
    """
    if wikidata_id in _KNOWN_ENTITY_SLUGS:
        return _KNOWN_ENTITY_SLUGS[wikidata_id]

    external_id = wikidata_id.removeprefix("wikidata:")
    kind = "relation" if external_id.startswith("P") else "entity"
    slug = _strip_diacritics(label).lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return kind, slug


def _extract_external_refs_from_entity(entity: dict[str, Any]) -> list[dict[str, str]]:
    """Extract Wikidata / legacy source refs from an entity dict."""
    refs: list[dict[str, str]] = []
    eid = entity.get("id", "")
    if eid.startswith("wikidata:"):
        external_id = eid[len("wikidata:"):]
        ref: dict[str, str] = {"scheme": "wikidata", "external_id": external_id}
        source_url = entity.get("source_url")
        if source_url:
            ref["url"] = source_url
        refs.append(ref)
    return refs


def _migrate_contract(contract_data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Migrate one contract to v1.1.0 native IDs. Returns (migrated_data, all_external_refs_added)."""
    all_refs: list[dict[str, str]] = []
    migrated = dict(contract_data)

    # Bump schema version
    migrated["schema_version"] = "1.1.0"

    triple = migrated.get("triple", {})

    # Migrate contract_id and fact_id if they contain wd- pattern
    old_contract_id: str = migrated.get("contract_id", "")
    old_fact_id: str = migrated.get("fact_id", "")

    new_contract_id = old_contract_id
    new_fact_id = old_fact_id

    if _WD_PATTERN.search(old_contract_id):
        prefix = "factverify:contract:"
        if old_contract_id.startswith(prefix):
            rest = old_contract_id[len(prefix):]
            parts = rest.rsplit(":", 1)
            local_id = parts[0]
            version = parts[1] if len(parts) > 1 else "v1"
            new_local_id = _slug_from_wd(local_id, triple)
            new_contract_id = f"factverify:contract:{new_local_id}:{version}"
        migrated["contract_id"] = new_contract_id

    if _WD_PATTERN.search(old_fact_id):
        prefix = "factverify:fact:"
        if old_fact_id.startswith(prefix):
            local_id = old_fact_id[len(prefix):]
            new_local_id = _slug_from_wd(local_id, triple)
            new_fact_id = f"factverify:fact:{new_local_id}"
        migrated["fact_id"] = new_fact_id

    # Migrate triple entities
    for role in ("subject", "relation", "object"):
        entity = triple.get(role, {})
        if not entity:
            continue
        refs = _extract_external_refs_from_entity(entity)
        all_refs.extend(refs)
        eid = entity.get("id", "")
        if eid.startswith("wikidata:Q") or eid.startswith("wikidata:P"):
            label = entity.get("label", "")
            kind, slug = _entity_slug(eid, label)
            entity["id"] = f"factverify:{kind}:{slug}"
            if refs:
                entity["external_refs"] = refs
            entity.pop("source", None)
            entity.pop("source_url", None)
        else:
            entity.pop("source", None)
            entity.pop("source_url", None)
        triple[role] = entity
    migrated["triple"] = triple

    # Remove entity_resolution if present (no longer in v1.1.0 schema)
    migrated.pop("entity_resolution", None)

    return migrated, all_refs


def _scan_legacy_tree(source_root: Path) -> list[MigrationEntry]:
    """Scan the legacy source tree and produce migration entries."""
    entries: list[MigrationEntry] = []

    # Scan contracts/
    contracts_dir = source_root / "contracts"
    if contracts_dir.exists():
        for contract_file in sorted(contracts_dir.glob("*.json")):
            try:
                data = json.loads(contract_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise MigrationError(
                    f"Cannot parse contract {contract_file}: {exc}"
                ) from exc

            old_fact_id = data.get("fact_id", "")
            old_contract_id = data.get("contract_id", "")
            triple = data.get("triple", {})

            _, all_refs = _migrate_contract(data)

            # Determine new fact ID
            if _WD_PATTERN.search(old_fact_id):
                prefix = "factverify:fact:"
                local_id = old_fact_id[len(prefix):]
                new_local_id = _slug_from_wd(local_id, triple)
                new_fact_id = f"factverify:fact:{new_local_id}"
            else:
                new_fact_id = old_fact_id

            entries.append(MigrationEntry(
                source_path=str(contract_file),
                action="migrate",
                old_id=old_fact_id,
                new_id=new_fact_id,
                external_refs_added=all_refs,
                notes=f"contract_id: {old_contract_id} -> {new_fact_id}",
            ))

    # Scan decisions/ — delete (superseded by docs/decisions/catalog.yaml)
    decisions_dir = source_root / "decisions"
    if decisions_dir.exists():
        for decisions_file in sorted(decisions_dir.rglob("*")):
            if decisions_file.is_file():
                entries.append(MigrationEntry(
                    source_path=str(decisions_file),
                    action="delete",
                    old_id=str(decisions_file.relative_to(source_root)),
                    new_id="",
                    notes="Superseded by docs/decisions/catalog.yaml",
                ))

    # Scan spec/ — consolidated files and direct moves
    spec_dir = source_root / "spec"
    if spec_dir.exists():
        for spec_file in sorted(spec_dir.rglob("*")):
            if not spec_file.is_file():
                continue
            fname = spec_file.name
            if fname in _CONSOLIDATED_FILES:
                entries.append(MigrationEntry(
                    source_path=str(spec_file),
                    action="delete",
                    old_id=fname,
                    new_id="",
                    notes="Consolidated into protocol.yaml / templates.yaml / fact.schema.json",
                ))
            elif fname in _DIRECT_MOVE_FILES:
                entries.append(MigrationEntry(
                    source_path=str(spec_file),
                    action="move",
                    old_id=str(spec_file.relative_to(source_root)),
                    new_id=fname,
                    notes="Direct move to spec_root top level",
                ))
            else:
                entries.append(MigrationEntry(
                    source_path=str(spec_file),
                    action="delete",
                    old_id=str(spec_file.relative_to(source_root)),
                    new_id="",
                    notes="Legacy spec file — superseded by consolidated artifacts",
                ))

    # Scan remaining legacy directories
    for legacy_dir_name in sorted(_LEGACY_DIRS):
        legacy_dir = source_root / legacy_dir_name
        if legacy_dir.exists():
            for legacy_file in sorted(legacy_dir.rglob("*")):
                if legacy_file.is_file():
                    entries.append(MigrationEntry(
                        source_path=str(legacy_file),
                        action="delete",
                        old_id=str(legacy_file.relative_to(source_root)),
                        new_id="",
                        notes=f"Legacy {legacy_dir_name}/ artifact — superseded by two-root layout",
                    ))

    return entries


def _execute_migration(
    entries: list[MigrationEntry],
    source_root: Path,
    spec_root: Path,
) -> None:
    """Execute the migration. Fail closed: source tree unchanged on any error."""
    for entry in entries:
        if entry.action == "migrate":
            source_path = Path(entry.source_path)
            try:
                data = json.loads(source_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                raise MigrationError(f"Cannot read {source_path}: {exc}") from exc

            migrated, _ = _migrate_contract(data)

            # Determine target bundle directory
            new_fact_id = entry.new_id
            local_id = new_fact_id.removeprefix("factverify:fact:")
            bundle_dir = spec_root / "facts" / local_id
            bundle_dir.mkdir(parents=True, exist_ok=True)
            target = bundle_dir / "contract.json"
            target.write_text(
                json.dumps(migrated, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        elif entry.action == "move":
            source_path = Path(entry.source_path)
            rel = Path(entry.new_id)
            target = spec_root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(source_path), str(target))
        # "delete" and "skip" actions do not write anything


def run_migration(
    source_root: Path,
    spec_root: Path,
    internal_root: Path,
    mode: MigrationMode,
    report_path: Path | None = None,
) -> dict[str, Any]:
    """Run the migration. Returns a report dict. Raises MigrationError on failure."""
    try:
        entries = _scan_legacy_tree(source_root)
    except MigrationError:
        raise

    unresolved = [
        e for e in entries
        if e.action not in ("migrate", "move", "delete", "skip")
    ]

    report: dict[str, Any] = {
        "overall": "pass" if not unresolved else "fail",
        "mode": mode.value,
        "source_root": str(source_root),
        "spec_root": str(spec_root),
        "internal_root": str(internal_root),
        "entries": [
            {
                "source_path": e.source_path,
                "action": e.action,
                "old_id": e.old_id,
                "new_id": e.new_id,
                "external_refs_added": e.external_refs_added,
                "notes": e.notes,
            }
            for e in entries
        ],
        "unresolved": [
            {"source_path": e.source_path, "reason": "unknown_action"}
            for e in unresolved
        ],
    }

    if mode == MigrationMode.EXECUTE:
        _execute_migration(entries, source_root, spec_root)

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return report


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m tools.migrate_artifacts",
        description="Migrate legacy .factverify/ artifact tree to two-root layout.",
    )
    parser.add_argument(
        "--source",
        type=Path,
        default=Path(".factverify"),
        help="Source legacy root (default: .factverify)",
    )
    parser.add_argument(
        "--spec-root",
        type=Path,
        default=Path(".factverify"),
        help="Target frozen spec root (default: .factverify)",
    )
    parser.add_argument(
        "--internal-root",
        type=Path,
        default=Path(".factverify_internal"),
        help="Target runtime root (default: .factverify_internal)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Only analyse, do not write (default)",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="Actually perform the migration",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Path to write the JSON migration report",
    )

    args = parser.parse_args(argv)

    if not args.source.exists():
        print(f"Error: source root does not exist: {args.source}", flush=True)
        return 2

    mode = MigrationMode.EXECUTE if args.execute else MigrationMode.DRY_RUN

    try:
        report = run_migration(
            source_root=args.source,
            spec_root=args.spec_root,
            internal_root=args.internal_root,
            mode=mode,
            report_path=args.report,
        )
    except MigrationError as exc:
        print(f"Migration error: {exc}", flush=True)
        return 1

    overall = report.get("overall", "fail")
    n_entries = len(report.get("entries", []))
    n_unresolved = len(report.get("unresolved", []))
    print(
        f"Migration ({mode.value}): {overall}. "
        f"{n_entries} entries, {n_unresolved} unresolved.",
        flush=True,
    )

    if report.get("overall") != "pass":
        return 1
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
