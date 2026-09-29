"""Validate docs/decisions/catalog.yaml for uniqueness and completeness.

Exit codes:
    0 — catalog is valid
    1 — one or more uniqueness violations detected
    2 — catalog file cannot be loaded (missing, malformed YAML)
"""

from __future__ import annotations

import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parents[1]))

from src.decisions.catalog import load_catalog, validate_catalog
from src.decisions.errors import DecisionError

_DEFAULT_CATALOG = Path("docs/decisions/catalog.yaml")


@click.command()
@click.option(
    "--catalog",
    default=str(_DEFAULT_CATALOG),
    show_default=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to catalog.yaml.",
)
def main(catalog: Path) -> None:
    try:
        entries = load_catalog(catalog)
    except DecisionError as exc:
        click.echo(f"load error: {exc}", err=True)
        sys.exit(2)

    errors = validate_catalog(entries)
    if errors:
        for err in errors:
            click.echo(f"catalog error: {err}", err=True)
        sys.exit(1)

    click.echo(f"catalog valid: {len(entries)} entries, no uniqueness violations")


if __name__ == "__main__":
    main()
