"""prefetch_models.py — download and verify model files from Hugging Face Hub.

This is the ONLY place in the project where network access to HF is permitted.
Run this before any study run to populate the local model cache.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import click

from src.models.errors import FactVerifyLoaderError
from src.models.spec import RoleEntry, load_model_configuration


@click.command()
@click.option("--role", required=True, help="Role key in the model configuration.")
@click.option(
    "--model-config",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Versioned model configuration.",
)
@click.option(
    "--cache-dir",
    default=None,
    type=click.Path(path_type=Path),
    help="Local directory to download model files into. Defaults to HF hub cache.",
)
def prefetch_models(role: str, model_config: Path, cache_dir: Path | None) -> None:
    """Download and verify model files listed in a versioned configuration."""
    try:
        configuration = load_model_configuration(model_config)
        entry = configuration.roles.get(role)
        if entry is None:
            raise FactVerifyLoaderError(f"unknown role {role!r} in {model_config}")
        if entry.status == "pending":
            raise FactVerifyLoaderError(f"role {role!r} is pending in {model_config}")
        if not entry.files:
            click.echo(f"Role {role!r} has an empty files map; nothing to download")
            return
        repo_id, model_revision = _download_identity(entry, role, model_config)
    except FactVerifyLoaderError as exc:
        raise click.ClickException(str(exc)) from exc

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise click.ClickException(
            "huggingface_hub is required — install it with `uv add huggingface_hub`"
        ) from exc

    if cache_dir is None:
        from huggingface_hub import constants

        sanitised = repo_id.replace("/", "--")
        cache_dir = (
            Path(constants.HF_HUB_CACHE)
            / f"models--{sanitised}"
            / "snapshots"
            / model_revision
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    click.echo(
        f"Prefetching role={role!r} from {repo_id}@{model_revision} -> {cache_dir}"
    )

    for filename, expected_digest in entry.files.items():
        click.echo(f"  Downloading {filename}...")
        local_path = hf_hub_download(
            repo_id=repo_id,
            filename=filename,
            revision=model_revision,
            local_dir=str(cache_dir),
        )
        digest = hashlib.sha256()
        with open(local_path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        actual = "sha256:" + digest.hexdigest()
        if actual != expected_digest:
            raise click.ClickException(
                f"digest mismatch for {filename!r}: "
                f"expected {expected_digest}, got {actual}"
            )
        click.echo(f"    OK {filename} verified")

    click.echo(f"Role {role!r} prefetched and verified at {cache_dir}")


def _download_identity(
    entry: RoleEntry, role: str, model_config: Path
) -> tuple[str, str]:
    if entry.repo_id is None or entry.repo_id == "":
        raise FactVerifyLoaderError(
            f"unresolved spec field 'repo_id' for role {role!r} in {model_config}"
        )
    if entry.model_revision is None or entry.model_revision == "":
        raise FactVerifyLoaderError(
            f"unresolved spec field 'model_revision' for role {role!r} "
            f"in {model_config}"
        )
    return entry.repo_id, entry.model_revision


if __name__ == "__main__":
    prefetch_models()
