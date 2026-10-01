"""Probe the pinned base model and write exclusion verdicts."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from src.cache.key import CacheBody, CacheRequest
from src.cache.store import get_or_compute, open_cache
from src.data.decisions import load_d65
from src.data.errors import DataError
from src.data.exclusion import run_gate
from src.models.generate import generate_completion
from src.models.identity import compute_identity_hash_v2
from src.models.loader import load_model
from src.models.spec import load_model_configuration, load_model_policy, resolve_role


@click.command()
@click.option("--facts", required=True, type=click.Path(exists=True, path_type=Path))
@click.option(
    "--spec-root", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--decisions", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option(
    "--cache-decisions", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option("--cache-dir", required=True, type=click.Path(path_type=Path))
@click.option(
    "--model-config", required=True, type=click.Path(exists=True, path_type=Path)
)
@click.option("--role", required=True)
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--report", required=True, type=click.Path(path_type=Path))
def main(
    facts: Path,
    spec_root: Path,
    decisions: Path,
    cache_decisions: Path,
    cache_dir: Path,
    model_config: Path,
    role: str,
    out: Path,
    report: Path,
) -> None:
    """Write results/exclusion_gate.jsonl for the pinned base model."""
    decision = load_d65(decisions)
    policy = load_model_policy(spec_root)
    resolved = resolve_role(policy, load_model_configuration(model_config), role)
    if resolved.deprecation is not None:
        print(resolved.deprecation, file=sys.stderr)
    loaded = load_model(role, model_config=model_config, spec_root=spec_root)
    expected = compute_identity_hash_v2(
        repo_id=resolved.repo_id,
        model_revision=resolved.model_revision,
        tokenizer_revision=resolved.tokenizer_revision,
        dtype=resolved.dtype,
        adapter_digest=None,
    )
    if loaded.identity_hash != expected:
        raise DataError("identity_hash")
    binding = {
        "study_role": loaded.study_role,
        "model_config_id": loaded.model_config_id,
        "model_config_digest": loaded.model_config_digest,
        "model_identity_hash": loaded.identity_hash,
        "identity_schema_version": loaded.identity_schema_version,
        "governing_spec_revision": policy.governing_spec_revision,
    }
    cache = open_cache(cache_dir, decisions=cache_decisions)

    def complete(prompt: str, seed: int) -> str:
        request = CacheRequest(
            identity_hash=loaded.identity_hash,
            model_input=prompt,
            decoding={
                "do_sample": decision.do_sample,
                "max_new_tokens": decision.max_new_tokens,
                "seed": seed,
            },
            seed=seed,
            sample_index=1,
            request_kind="generate",
            producer_run_id="exclusion-gate",
            software_versions={"python": "3.11"},
            model_config_digest=loaded.model_config_digest,
            study_role=loaded.study_role,
            model_config_id=loaded.model_config_id,
            identity_schema_version=loaded.identity_schema_version,
            governing_spec_revision=loaded.governing_spec_revision,
        )

        def compute() -> CacheBody:
            text = generate_completion(
                loaded.model,
                loaded.tokenizer,
                prompt,
                max_new_tokens=decision.max_new_tokens,
                do_sample=decision.do_sample,
            )
            return CacheBody(body=text, token_count=0)

        entry, _event = get_or_compute(cache, request, compute)
        if not isinstance(entry.body, str):
            raise DataError("cache body")
        return entry.body

    run_gate(
        facts_path=facts,
        spec_root=spec_root,
        decision=decision,
        complete=complete,
        identity_hash=loaded.identity_hash,
        expected_hash=expected,
        out_path=out,
        report_path=report,
        binding=binding,
    )


if __name__ == "__main__":
    main()
