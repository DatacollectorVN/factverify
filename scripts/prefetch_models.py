"""prefetch_models.py — download and verify model files from Hugging Face Hub.

This is the ONLY place in the project where network access to HF is permitted.
Run this before any study run to populate the local model cache.

Usage:
    python scripts/prefetch_models.py --role tiny_base --spec-root .factverify/spec/
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import click
import yaml


@click.command()
@click.option("--role", required=True, help="Role key in models.yaml to prefetch.")
@click.option(
    "--spec-root",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the spec directory containing models.yaml.",
)
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Local directory to download model files into. Defaults to HF hub cache.",
)
def prefetch_models(role: str, spec_root: Path, cache_dir: Path | None) -> None:
    """Download and verify model files for a role declared in models.yaml."""
    models_yaml = spec_root / "models.yaml"
    if not models_yaml.exists():
        raise click.ClickException(f"models.yaml not found at {models_yaml}")

    with models_yaml.open() as f:
        data = yaml.safe_load(f)

    if role not in data:
        raise click.ClickException(f"unknown role {role!r} in {models_yaml}")

    entry = data[role]
    repo_id: str = entry["repo_id"]
    revision: str = entry["revision"]
    tok_revision: str = entry["tokenizer_revision"]
    declared_files: dict[str, str] = entry["files"]

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        raise click.ClickException(
            "huggingface_hub is required — install it with `uv add huggingface_hub`"
        )

    if cache_dir is None:
        from huggingface_hub import constants
        sanitised = repo_id.replace("/", "--")
        cache_dir = Path(constants.HF_HUB_CACHE) / f"models--{sanitised}" / "snapshots" / revision

    cache_dir.mkdir(parents=True, exist_ok=True)
    click.echo(f"Prefetching role={role!r} from {repo_id}@{revision} -> {cache_dir}")

    for filename, expected_digest in declared_files.items():
        click.echo(f"  Downloading {filename}...")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=revision,
            local_dir=str(cache_dir),
        )
        # Verify digest
        h = hashlib.sha256()
        with open(local_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                h.update(chunk)
        actual = h.hexdigest()
        if actual != expected_digest:
            raise click.ClickException(
                f"digest mismatch for {filename!r}: expected {expected_digest}, got {actual}"
            )
        click.echo(f"    OK {filename} verified")

    click.echo(f"Role {role!r} prefetched and verified at {cache_dir}")


if __name__ == "__main__":
    prefetch_models()
