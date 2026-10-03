"""Two-root layout resolver.

Decisions:
  artifacts.namespace.boundary (D-71) — spec root vs internal root.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_ENV_SPEC = "FACTVERIFY_SPEC_ROOT"
_ENV_INTERNAL = "FACTVERIFY_INTERNAL_ROOT"

_DEFAULT_SPEC = ".factverify"
_DEFAULT_INTERNAL = ".factverify_internal"


class LayoutError(Exception):
    """Raised when roots are invalid or a path crosses namespace boundaries."""


class ArtifactClass(StrEnum):
    # Frozen-input classes (spec_root only)
    PROTOCOL = "protocol"
    TEMPLATES = "templates"
    MODEL_POLICY = "model_policy"
    FACT_SCHEMA = "fact_schema"
    FREEZE_RECEIPT = "freeze_receipt"
    FACT_CONTRACT = "fact_contract"
    FACT_SOURCES = "fact_sources"
    FACT_NEIGHBOURHOOD = "fact_neighbourhood"
    FACT_PROMPTS = "fact_prompts"
    FACT_MANIFEST = "fact_manifest"
    # Runtime classes (internal_root only)
    LEDGER = "ledger"
    RUN_MANIFEST = "run_manifest"
    RUN_CONFIG = "run_config"
    RUN_EVENTS = "run_events"
    RUN_METRICS = "run_metrics"
    RUN_VERDICT = "run_verdict"
    RUN_ARTIFACT_MANIFEST = "run_artifact_manifest"
    CHECKPOINT = "checkpoint"
    GENERATION = "generation"
    SCORE = "score"
    WITNESS = "witness"
    RESULT = "result"
    REPORT = "report"
    DEVIATION = "deviation"
    CACHE_SHARD = "cache_shard"
    EXTERNAL_BLOB = "external_blob"
    TEMPORARY = "temporary"


_FROZEN_CLASSES = frozenset({
    ArtifactClass.PROTOCOL,
    ArtifactClass.TEMPLATES,
    ArtifactClass.MODEL_POLICY,
    ArtifactClass.FACT_SCHEMA,
    ArtifactClass.FREEZE_RECEIPT,
    ArtifactClass.FACT_CONTRACT,
    ArtifactClass.FACT_SOURCES,
    ArtifactClass.FACT_NEIGHBOURHOOD,
    ArtifactClass.FACT_PROMPTS,
    ArtifactClass.FACT_MANIFEST,
})

_RUNTIME_CLASSES = frozenset({
    ArtifactClass.LEDGER,
    ArtifactClass.RUN_MANIFEST,
    ArtifactClass.RUN_CONFIG,
    ArtifactClass.RUN_EVENTS,
    ArtifactClass.RUN_METRICS,
    ArtifactClass.RUN_VERDICT,
    ArtifactClass.RUN_ARTIFACT_MANIFEST,
    ArtifactClass.CHECKPOINT,
    ArtifactClass.GENERATION,
    ArtifactClass.SCORE,
    ArtifactClass.WITNESS,
    ArtifactClass.RESULT,
    ArtifactClass.REPORT,
    ArtifactClass.DEVIATION,
    ArtifactClass.CACHE_SHARD,
    ArtifactClass.EXTERNAL_BLOB,
    ArtifactClass.TEMPORARY,
})


@dataclass(frozen=True)
class LayoutRoots:
    spec_root: Path
    internal_root: Path

    @classmethod
    def resolve(
        cls,
        spec_root: Path | None = None,
        internal_root: Path | None = None,
        *,
        cwd: Path | None = None,
    ) -> LayoutRoots:
        """Resolve roots from explicit args -> env vars -> defaults relative to cwd."""
        base = (cwd or Path.cwd()).resolve()

        def _resolve_one(explicit: Path | None, env_var: str, default: str) -> Path:
            if explicit is not None:
                return explicit.resolve()
            env_val = os.environ.get(env_var)
            if env_val:
                raw = Path(env_val)
                return raw.resolve() if raw.is_absolute() else (base / raw).resolve()
            return (base / default).resolve()

        resolved_spec = _resolve_one(spec_root, _ENV_SPEC, _DEFAULT_SPEC)
        resolved_internal = _resolve_one(
            internal_root, _ENV_INTERNAL, _DEFAULT_INTERNAL
        )
        _assert_non_overlapping(resolved_spec, resolved_internal)
        return cls(spec_root=resolved_spec, internal_root=resolved_internal)

    # Path helpers
    def fact_dir(self, fact_id: str) -> Path:
        local_id = _extract_local_id(fact_id, "factverify:fact:")
        return self.spec_root / "facts" / local_id

    def run_dir(self, run_id: str) -> Path:
        return self.internal_root / "runs" / run_id

    def ledger_path(self) -> Path:
        return self.internal_root / "ledger.sqlite"

    # Validation helpers
    def assert_spec_path(self, path: Path) -> None:
        resolved = path.resolve()
        if not _is_under(resolved, self.spec_root):
            raise LayoutError(
                f"Path {path} is not under frozen spec root {self.spec_root}"
            )

    def assert_internal_path(self, path: Path) -> None:
        resolved = path.resolve()
        if not _is_under(resolved, self.internal_root):
            raise LayoutError(
                f"Path {path} is not under internal root {self.internal_root}"
            )

    def classify(self, path: Path) -> ArtifactClass:
        """Classify a path by its artifact class. Raises LayoutError if unrecognized."""
        resolved = path.resolve()
        if _is_under(resolved, self.spec_root):
            return _classify_spec_path(resolved, self.spec_root)
        if _is_under(resolved, self.internal_root):
            return _classify_internal_path(resolved, self.internal_root)
        raise LayoutError(f"Path {path} is outside both known roots")

    def is_runtime_class(self, artifact_class: ArtifactClass) -> bool:
        return artifact_class in _RUNTIME_CLASSES

    def is_frozen_class(self, artifact_class: ArtifactClass) -> bool:
        return artifact_class in _FROZEN_CLASSES


def _assert_non_overlapping(spec: Path, internal: Path) -> None:
    if spec == internal:
        raise LayoutError(
            f"Spec root and internal root are identical: {spec}"
        )
    try:
        internal.relative_to(spec)
        raise LayoutError(
            f"Internal root {internal} is nested inside spec root {spec}"
        )
    except ValueError:
        pass
    try:
        spec.relative_to(internal)
        raise LayoutError(
            f"Spec root {spec} is nested inside internal root {internal}"
        )
    except ValueError:
        pass


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _extract_local_id(full_id: str, prefix: str) -> str:
    if not full_id.startswith(prefix):
        raise LayoutError(f"ID {full_id!r} does not start with prefix {prefix!r}")
    return full_id[len(prefix):]


def _classify_spec_path(path: Path, spec_root: Path) -> ArtifactClass:
    rel = path.relative_to(spec_root)
    parts = rel.parts
    if parts == ("protocol.yaml",):
        return ArtifactClass.PROTOCOL
    if parts == ("templates.yaml",):
        return ArtifactClass.TEMPLATES
    if parts == ("model_policy.yaml",):
        return ArtifactClass.MODEL_POLICY
    if parts == ("fact.schema.json",):
        return ArtifactClass.FACT_SCHEMA
    if parts == ("FREEZE.json",):
        return ArtifactClass.FREEZE_RECEIPT
    if len(parts) >= 3 and parts[0] == "facts":
        return _classify_fact_bundle_path(parts[2])
    raise LayoutError(
        f"Path {path} under spec root is not in the frozen-input allowlist"
    )


def _classify_fact_bundle_path(filename: str) -> ArtifactClass:
    mapping = {
        "contract.json": ArtifactClass.FACT_CONTRACT,
        "sources.jsonl": ArtifactClass.FACT_SOURCES,
        "neighbourhood.jsonl": ArtifactClass.FACT_NEIGHBOURHOOD,
        "prompts.jsonl": ArtifactClass.FACT_PROMPTS,
        "manifest.json": ArtifactClass.FACT_MANIFEST,
    }
    if filename not in mapping:
        raise LayoutError(
            f"Filename {filename!r} is not a recognized fact bundle artifact"
        )
    return mapping[filename]


def _classify_internal_path(path: Path, internal_root: Path) -> ArtifactClass:
    rel = path.relative_to(internal_root)
    parts = rel.parts
    if parts == ("ledger.sqlite",):
        return ArtifactClass.LEDGER
    if len(parts) >= 1 and parts[0] == "runs":
        if len(parts) >= 3:
            return _classify_run_file(parts[2])
        return ArtifactClass.RUN_MANIFEST  # placeholder
    if len(parts) >= 1 and parts[0] == "checkpoints":
        return ArtifactClass.CHECKPOINT
    if len(parts) >= 1 and parts[0] == "evidence":
        # generation, score, or witness — evidence sub-type
        return ArtifactClass.GENERATION
    if len(parts) >= 1 and parts[0] == "results":
        return ArtifactClass.RESULT
    if len(parts) >= 1 and parts[0] == "reports":
        return ArtifactClass.REPORT
    if len(parts) >= 1 and parts[0] == "deviations":
        return ArtifactClass.DEVIATION
    if len(parts) >= 1 and parts[0] == "cache":
        return ArtifactClass.CACHE_SHARD
    if len(parts) >= 1 and parts[0] == "tmp":
        return ArtifactClass.TEMPORARY
    raise LayoutError(
        f"Path {path} under internal root is not in the declared subdirectory list"
    )


def _classify_run_file(filename: str) -> ArtifactClass:
    mapping = {
        "manifest.json": ArtifactClass.RUN_MANIFEST,
        "config.yaml": ArtifactClass.RUN_CONFIG,
        "events.jsonl": ArtifactClass.RUN_EVENTS,
        "metrics.jsonl": ArtifactClass.RUN_METRICS,
        "verdict.json": ArtifactClass.RUN_VERDICT,
        "artifacts.json": ArtifactClass.RUN_ARTIFACT_MANIFEST,
    }
    return mapping.get(filename, ArtifactClass.RUN_EVENTS)
