"""Probe the pinned base model and write exclusion verdicts."""

from __future__ import annotations

from pathlib import Path

import click

from src.cache.key import CacheBody, CacheRequest
from src.cache.store import get_or_compute, open_cache
from src.data.decisions import load_d65
from src.data.errors import DataError
from src.data.exclusion import run_gate
from src.models.generate import generate_completion
from src.models.identity import build_identity_payload, compute_identity_hash
from src.models.loader import load_model
from src.models.spec import load_model_spec


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
@click.option("--role", default="blocks_0_2", show_default=True)
@click.option("--out", required=True, type=click.Path(path_type=Path))
@click.option("--report", required=True, type=click.Path(path_type=Path))
def main(
    facts: Path,
    spec_root: Path,
    decisions: Path,
    cache_decisions: Path,
    cache_dir: Path,
    role: str,
    out: Path,
    report: Path,
) -> None:
    """Write results/exclusion_gate.jsonl for the pinned base model."""
    decision = load_d65(decisions)
    loaded = load_model(role, spec_root=spec_root)
    spec = load_model_spec(role, spec_root)
    expected = compute_identity_hash(build_identity_payload(spec, None))
    if loaded.identity_hash != expected:
        raise DataError("identity_hash")
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
    )


if __name__ == "__main__":
    main()
