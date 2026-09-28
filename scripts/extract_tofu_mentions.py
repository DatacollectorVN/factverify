#!/usr/bin/env python3
"""FV-DATA P1-0: Extract atomic-fact mentions from a pinned TOFU release.

Usage:
    # Step 1 — build manifest (once):
    uv run python scripts/extract_tofu_mentions.py pin \\
        --source <tofu-dir> \\
        --revision 324592d84ae4f482ac7249b9285c2ecdb53e3a68 \\
        --out data/tofu_derived/source_manifest.json

    # Step 2 — extract (pilot: 10 authors):
    uv run python scripts/extract_tofu_mentions.py extract \\
        --source <tofu-dir> \\
        --manifest data/tofu_derived/source_manifest.json \\
        --extractor-config data/tofu_derived/extractor_config.json \\
        --out data/tofu_derived/ \\
        --limit-authors 10
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from pathlib import Path
import re as _re
import click

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.tofu import (
    CONSUMED_CONFIGS,
    ExtractorConfig,
    Mention,
    SourceManifest,
    TransformationRecord,
    build_manifest,
    check_no_tofu_split_lineage,
    load_tofu_rows,
    validate_transformation_coverage,
    verify_source,
)

# ---------------------------------------------------------------------------
# Extraction-specific response cache (independent of src/cache/, which
# requires D-60 to be closed).  Keyed by SHA-256 of (model_revision,
# prompt_hash, row_content_hash).  Stored as newline-delimited JSON.
# ---------------------------------------------------------------------------

_CACHE_VERSION = 1


def _row_hash(row: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(row, sort_keys=True, ensure_ascii=True).encode()
    ).hexdigest()


def _request_key(model_revision: str, prompt_hash: str, row_hash: str) -> str:
    payload = json.dumps(
        {
            "cache_version": _CACHE_VERSION,
            "model_revision": model_revision,
            "prompt_hash": prompt_hash,
            "row_hash": row_hash,
        },
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


class ExtractionCache:
    """File-backed cache for raw LLM responses, keyed by request SHA-256."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._store: dict[str, dict[str, object]] = {}
        if path.exists():
            with open(path) as f:
                for line in f:
                    entry = json.loads(line)
                    self._store[entry["key"]] = entry

    def get(self, key: str) -> dict[str, object] | None:
        return self._store.get(key)

    def put(self, key: str, response_text: str, token_count: int) -> None:
        entry: dict[str, object] = {
            "key": key,
            "response_text": response_text,
            "token_count": token_count,
        }
        self._store[key] = entry
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")


# ---------------------------------------------------------------------------
# Claude API extraction
# ---------------------------------------------------------------------------

_SYSTEM = (
    "You are a precise fact extractor. Follow the user's instructions exactly "
    "and return only the JSON object requested."
)


def _call_claude(
    client: object,  # anthropic.Anthropic
    model_id: str,
    prompt_text: str,
    question: str,
    answer: str,
    max_tokens: int,
    temperature: float,
) -> tuple[str, int]:
    """Call Claude and return (response_text, total_tokens)."""
    user_content = (
        f"{prompt_text}\n\n"
        f"Question: {question}\n"
        f"Answer: {answer}"
    )
    response = client.messages.create(  # type: ignore[attr-defined]
        model=model_id,
        max_tokens=max_tokens,
        extra_body={"temperature": temperature},
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_content}],
    )
    text: str = response.content[0].text
    tokens: int = response.usage.input_tokens + response.usage.output_tokens
    return text, tokens


def _parse_mentions(
    raw: str,
    config: str,
    row_index: int,
    question: str,
    answer: str,
    extractor_revision: str,
    prompt_hash: str,
    decoding: dict[str, object],
) -> list[Mention]:
    """Parse Claude's JSON response into Mention objects.

    Skips entries whose span is out-of-bounds or whose slice doesn't
    exist in the field text (FV-DATA-002 criterion 2).
    """
    # Extract the last valid JSON object from the response.
    # Claude sometimes self-corrects mid-response producing multiple code blocks;
    # the last ```json ... ``` block is always the final answer.

    blocks = _re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", raw, _re.DOTALL)
    candidate = blocks[-1] if blocks else raw.strip()
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        # Last resort: try the raw text directly.
        try:
            data = json.loads(raw.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Claude returned non-JSON: {raw!r}") from exc

    field_texts = {"question": question, "answer": answer}
    mentions: list[Mention] = []
    for i, entry in enumerate(data.get("mentions", [])):
        field = entry.get("field", "")
        if field not in field_texts:
            continue
        text = field_texts[field]
        try:
            char_start = int(entry["char_start"])
            char_end = int(entry["char_end"])
        except (KeyError, ValueError, TypeError):
            continue
        if char_start < 0 or char_end > len(text) or char_start >= char_end:
            continue
        mention_id = f"{config}_{row_index:05d}_{field}_{i:03d}"
        mentions.append(
            Mention(
                mention_id=mention_id,
                config=config,
                row_index=row_index,
                field=field,
                char_start=char_start,
                char_end=char_end,
                subject=str(entry.get("subject", "")),
                relation=str(entry.get("relation", "")),
                object_=str(entry.get("object", "")),
                review_status="pending",
                extractor_revision=extractor_revision,
                extractor_prompt_hash=prompt_hash,
                extractor_decoding=decoding,
            )
        )
    return mentions


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.group()
def cli() -> None:
    """TOFU atomic-fact extraction pipeline."""


@cli.command()
@click.option(
    "--source",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
    help="Path to the local TOFU dataset directory.",
)
@click.option("--repo-id", default="locuslab/TOFU")
@click.option(
    "--revision",
    required=True,
    help="40-character hex commit hash.",
)
@click.option(
    "--out",
    type=click.Path(path_type=Path),
    required=True,
    help="Path to write source_manifest.json.",
)
def pin(source: Path, repo_id: str, revision: str, out: Path) -> None:
    """Build and save a source manifest for a local TOFU copy."""
    manifest = build_manifest(source, repo_id=repo_id, revision=revision)
    out.parent.mkdir(parents=True, exist_ok=True)
    manifest.save(out)
    click.echo(f"Manifest written: {out} ({len(manifest.files)} files)")


@cli.command()
@click.option(
    "--source",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--manifest",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option(
    "--extractor-config",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    required=True,
)
@click.option("--out", type=click.Path(path_type=Path), required=True)
@click.option("--limit-authors", type=int, default=None)
@click.option(
    "--api-key",
    default=None,
    help="Anthropic API key. Falls back to ANTHROPIC_API_KEY env var.",
)
@click.option(
    "--retry-delay",
    type=float,
    default=2.0,
    help="Seconds to wait between retries on rate-limit errors.",
)
def extract(
    source: Path,
    manifest: Path,
    extractor_config: Path,
    out: Path,
    limit_authors: int | None,
    api_key: str | None,
    retry_delay: float,
) -> None:
    """Extract atomic-fact mentions from TOFU via Claude.

    Fails closed if D-62 is unresolved, source verification fails,
    or ANTHROPIC_API_KEY is absent.
    """
    # FV-DATA-001: verify source.
    m = SourceManifest.load(manifest)
    verify_source(source, m)
    click.echo("Source verified OK.")

    # FV-DATA-003: validate extractor provenance.
    ext_cfg = ExtractorConfig.load(extractor_config)
    ext_cfg.validate()
    prompt_hash = ext_cfg.prompt_hash()
    click.echo(f"Extractor config validated (prompt_hash={prompt_hash[:12]}…).")

    # Resolve API key.
    resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
    if not resolved_key:
        raise click.ClickException(
            "ANTHROPIC_API_KEY not set. "
            "Export it or pass --api-key."
        )

    try:
        import anthropic  # noqa: PLC0415
    except ImportError as exc:
        raise click.ClickException(
            "anthropic package not installed. Run: uv sync"
        ) from exc

    client = anthropic.Anthropic(api_key=resolved_key)

    out.mkdir(parents=True, exist_ok=True)
    cache = ExtractionCache(out / "extractor_response_cache.jsonl")

    all_mentions: list[Mention] = []
    all_transformations: list[TransformationRecord] = []
    expected_counts: dict[str, int] = {}
    total_tokens = 0
    cache_hits = 0

    for config in CONSUMED_CONFIGS:
        config_file = source / f"{config}.json"
        if not config_file.exists():
            click.echo(f"  Skipping {config} (not in source).", err=True)
            continue

        rows = load_tofu_rows(source, config, limit_authors=limit_authors)
        expected_counts[config] = len(rows)
        click.echo(f"Processing {config}: {len(rows)} rows …")

        for row_idx, row in enumerate(rows):
            question: str = row.get("question", "")
            answer: str = row.get("answer", "")
            rh = _row_hash(row)
            req_key = _request_key(ext_cfg.model_revision, prompt_hash, rh)

            cached = cache.get(req_key)
            if cached is not None:
                raw_response = str(cached["response_text"])
                cache_hits += 1
            else:
                # Rate-limit retry (simple 1-retry).
                for attempt in range(2):
                    try:
                        raw_response, tok = _call_claude(
                            client,
                            model_id=ext_cfg.model_id,
                            prompt_text=ext_cfg.prompt_text,
                            question=question,
                            answer=answer,
                            max_tokens=int(
                                ext_cfg.decoding_params.get("max_tokens", 1024)
                            ),
                            temperature=float(
                                ext_cfg.decoding_params.get("temperature", 0.0)
                            ),
                        )
                        total_tokens += tok
                        cache.put(req_key, raw_response, tok)
                        break
                    except Exception as exc:  # noqa: BLE001
                        if attempt == 0:
                            click.echo(
                                f"  Row {row_idx} error ({exc}), retrying …",
                                err=True,
                            )
                            time.sleep(retry_delay)
                        else:
                            raise

            # FV-DATA-002: parse mentions.
            try:
                row_mentions = _parse_mentions(
                    raw_response,
                    config=config,
                    row_index=row_idx,
                    question=question,
                    answer=answer,
                    extractor_revision=ext_cfg.model_revision,
                    prompt_hash=prompt_hash,
                    decoding=ext_cfg.decoding_params,
                )
            except ValueError as exc:
                click.echo(
                    f"  Parse error row {row_idx}: {exc} — recording as excluded.",
                    err=True,
                )
                row_mentions = []

            all_mentions.extend(row_mentions)

            # FV-DATA-005: record transformation.
            label = "split_into_atomic_facts" if row_mentions else "excluded"
            all_transformations.append(
                TransformationRecord(
                    config=config,
                    row_index=row_idx,
                    label=label,
                    reason=(
                        f"Extracted {len(row_mentions)} mention(s) via "
                        f"{ext_cfg.model_revision}"
                    )
                    if row_mentions
                    else "No mentions extracted or parse error",
                    derived_ids=[m.mention_id for m in row_mentions],
                )
            )

            if (row_idx + 1) % 20 == 0:
                click.echo(
                    f"  … {row_idx + 1}/{len(rows)} rows, "
                    f"{len(all_mentions)} mentions so far"
                )

    # FV-DATA-006: verify no forbidden split lineage.
    check_no_tofu_split_lineage(all_transformations)

    # FV-DATA-005: validate transformation coverage.
    validate_transformation_coverage(all_transformations, expected_counts)

    # Write mentions.jsonl.
    mentions_path = out / "mentions.jsonl"
    with open(mentions_path, "w") as f:
        for mention in all_mentions:
            f.write(json.dumps(mention.to_dict()) + "\n")

    # Write transformations.jsonl.
    transformations_path = out / "transformations.jsonl"
    with open(transformations_path, "w") as f:
        for rec in all_transformations:
            f.write(json.dumps(rec.to_dict()) + "\n")

    click.echo(
        f"\nDone.\n"
        f"  Mentions:        {len(all_mentions):>6}  → {mentions_path}\n"
        f"  Transformations: {len(all_transformations):>6}  → {transformations_path}\n"
        f"  API tokens used: {total_tokens:>6}\n"
        f"  Cache hits:      {cache_hits:>6}"
    )


if __name__ == "__main__":
    cli()
