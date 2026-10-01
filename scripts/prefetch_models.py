"""prefetch_models.py — download and verify model files from Hugging Face Hub.

This is the ONLY place in the project where network access to HF is permitted.
Run this before any study run to populate the local model cache.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import click

from src.models.errors import FactVerifyLoaderError
from src.models.spec import load_model_configuration, load_model_policy, resolve_role


@click.command()
@click.option("--role", required=True, help="Role key in the model configuration.")
@click.option(
    "--spec-root",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to the spec directory containing model_policy.yaml.",
)
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
def prefetch_models(
    role: str, spec_root: Path, model_config: Path, cache_dir: Path | None
) -> None:
    """Download and verify model files listed in a versioned configuration."""
    try:
        policy = load_model_policy(spec_root)
        configuration = load_model_configuration(model_config)
        study_role = policy.role_aliases.get(role, role)
        alias = role if role in policy.role_aliases else None
        if (
            alias is not None
            and alias in configuration.roles
            and study_role in configuration.roles
        ):
            resolve_role(policy, configuration, role)
        entry = configuration.roles.get(study_role)
        if entry is None:
            entry = configuration.roles.get(role)
        if entry is None:
            raise FactVerifyLoaderError(f"unknown role {role!r} in {model_config}")
        if entry.status == "pending":
            raise FactVerifyLoaderError(
                f"role {study_role!r} is pending in {model_config}"
            )
        if not entry.files:
            if alias is not None:
                print(f"role alias {alias} resolved to {study_role}", file=sys.stderr)
            click.echo(
                f"Role {study_role!r} has an empty files map; nothing to download"
            )
            return
        resolved = resolve_role(policy, configuration, role)
    except FactVerifyLoaderError as exc:
        raise click.ClickException(str(exc)) from exc
    if resolved.deprecation is not None:
        print(resolved.deprecation, file=sys.stderr)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise click.ClickException(
            "huggingface_hub is required — install it with `uv add huggingface_hub`"
        ) from exc

    if cache_dir is None:
        from huggingface_hub import constants

        sanitised = resolved.repo_id.replace("/", "--")
        cache_dir = (
            Path(constants.HF_HUB_CACHE)
            / f"models--{sanitised}"
            / "snapshots"
            / resolved.model_revision
        )

    cache_dir.mkdir(parents=True, exist_ok=True)
    click.echo(
        f"Prefetching role={resolved.study_role!r} from "
        f"{resolved.repo_id}@{resolved.model_revision} -> {cache_dir}"
    )

    for filename, expected_digest in resolved.files.items():
        click.echo(f"  Downloading {filename}...")
        local_path = hf_hub_download(
            repo_id=resolved.repo_id,
            filename=filename,
            revision=resolved.model_revision,
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

    click.echo(f"Role {resolved.study_role!r} prefetched and verified at {cache_dir}")


if __name__ == "__main__":
    prefetch_models()
