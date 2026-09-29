"""Generate a Markdown reference document from docs/decisions/catalog.yaml.

Usage:
    python tools/generate_decision_ref.py --catalog docs/decisions/catalog.yaml \
        --output docs/decision_reference.md
    python tools/generate_decision_ref.py --catalog docs/decisions/catalog.yaml \
        --output docs/decision_reference.md --check

The --check flag exits non-zero when the existing output differs from freshly
generated content, useful as a CI guard.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

# Allow running as a script from the repo root.
sys.path.insert(0, str(Path(__file__).parents[1]))

from src.decisions.catalog import load_catalog, validate_catalog
from src.decisions.types import DecisionCatalogEntry


def _render(entries: list[DecisionCatalogEntry]) -> str:
    """Return a deterministic Markdown document for all catalog entries."""
    lines: list[str] = [
        "# Decision Reference",
        "",
        "Generated from `docs/decisions/catalog.yaml`.",
        "Do not edit by hand — regenerate with `tools/generate_decision_ref.py`.",
        "",
    ]

    # Group entries by domain, preserving sort order within each group.
    domains: dict[str, list[DecisionCatalogEntry]] = {}
    for entry in sorted(entries, key=lambda e: e.legacy_id):
        domains.setdefault(entry.domain, []).append(entry)

    for domain in sorted(domains):
        lines.append(f"## {domain}")
        lines.append("")
        lines.append("| ID | Semantic key | Title | Status |")
        lines.append("|----|--------------|-------|--------|")
        for entry in domains[domain]:
            key_cell = (
                entry.key if entry.key is not None else "_(collision/unresolved)_"
            )
            title_cell = entry.title.replace("|", "\\|")
            lines.append(
                f"| {entry.legacy_id} | {key_cell} | {title_cell} | {entry.status} |"
            )
        lines.append("")

    return "\n".join(lines)


@click.command()
@click.option(
    "--catalog",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="Path to catalog.yaml.",
)
@click.option(
    "--output",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to write the Markdown reference.",
)
@click.option(
    "--check",
    is_flag=True,
    default=False,
    help="Exit non-zero if the existing output differs from freshly generated content.",
)
def main(catalog: Path, output: Path, check: bool) -> None:
    entries = load_catalog(catalog)
    errors = validate_catalog(entries)
    if errors:
        for err in errors:
            click.echo(f"catalog error: {err}", err=True)
        sys.exit(1)

    content = _render(entries)

    if check:
        if not output.is_file():
            click.echo(f"check failed: {output} does not exist", err=True)
            sys.exit(1)
        existing = output.read_text(encoding="utf-8")
        if existing != content:
            click.echo(
                f"check failed: {output} is stale — re-run without --check to update",
                err=True,
            )
            sys.exit(1)
        click.echo("check passed: output is up to date")
        return

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
    click.echo(f"wrote {output} ({len(entries)} entries)")


if __name__ == "__main__":
    main()
