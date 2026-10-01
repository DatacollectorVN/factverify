"""Knowledge-exclusion grid. Accuracy uses class E templates only."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

from src.data.decisions import D65Decision
from src.data.errors import DataError
from src.decisions.resolver import resolve_or_none

_CATALOG = Path(__file__).parents[2] / "docs" / "decisions" / "catalog.yaml"

Completer = Callable[[str, int], str | None]


def run_gate(
    *,
    facts_path: Path,
    spec_root: Path,
    decision: D65Decision,
    complete: Completer,
    identity_hash: str,
    expected_hash: str,
    out_path: Path,
    report_path: Path,
    binding: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Write one verdict per fact. A hash mismatch writes nothing."""
    if identity_hash != expected_hash:
        raise DataError("identity_hash")
    from src.train.cost import CostRecord

    facts = _read_jsonl(facts_path)
    templates = _templates(spec_root / "closure_templates.yaml")
    rows: list[dict[str, Any]] = []
    for fact in facts:
        cost = CostRecord()
        cost.start()
        row = _judge(fact, templates, decision, complete, identity_hash)
        cost.finish(0, 0)
        row["wall_clock_seconds"] = cost.wall_clock_seconds
        row["gpu_hours"] = cost.gpu_hours
        row["peak_memory_bytes"] = cost.peak_memory_bytes
        if binding is not None:
            row.update(binding)
        rows.append(row)
    _write_jsonl(out_path, rows)
    _write_report(report_path, rows, decision, binding)
    return rows


def require_pass(
    fact_id: str,
    report_path: Path,
    *,
    model_identity_hash: str | None = None,
    model_config_digest: str | None = None,
) -> None:
    """Raise unless the report verdict for fact_id is pass and the binding matches.

    A report that lacks either binding field is not rewritten.
    """
    before = report_path.read_bytes()
    rows = _read_jsonl(report_path)
    for row in rows:
        if row.get("fact_id") != fact_id:
            continue
        if row.get("verdict") != "pass":
            raise DataError(fact_id)
        stored_identity = row.get("model_identity_hash")
        stored_digest = row.get("model_config_digest")
        if stored_identity is None or stored_digest is None:
            raise DataError(fact_id)
        if model_identity_hash is not None and stored_identity != model_identity_hash:
            raise DataError(fact_id)
        if model_config_digest is not None and stored_digest != model_config_digest:
            raise DataError(fact_id)
        if report_path.read_bytes() != before:
            raise DataError(fact_id)
        return
    raise DataError(fact_id)


def assert_contamination_cleared(report_path: Path, decision: D65Decision) -> None:
    """Refuse a high exclusion share without an owner note, then any non-pass."""
    rows = _read_jsonl(report_path)
    excluded = sum(1 for row in rows if row.get("verdict") == "excluded_known")
    if rows and excluded / len(rows) > decision.contamination_trigger:
        if decision.contamination_decision is None:
            raise DataError(str(report_path))
    for row in rows:
        if row.get("verdict") != "pass":
            fact_id = row.get("fact_id")
            raise DataError(str(fact_id))


def _judge(
    fact: dict[str, Any],
    templates: list[dict[str, Any]],
    decision: D65Decision,
    complete: Completer,
    identity_hash: str,
) -> dict[str, Any]:
    relation = str(_mapping(fact, "triple")["relation"]["label"])
    applicable = [
        template
        for template in templates
        if template.get("class") == "E" and _applies(template, relation)
    ]
    inference = [
        template
        for template in templates
        if template.get("class") == "I" and _relation_listed(template, relation)
    ]
    d65_entry = resolve_or_none("D-65", _CATALOG)
    row: dict[str, Any] = {
        "fact_id": fact.get("fact_id"),
        "relation": relation,
        "identity_hash": identity_hash,
        "decision_id": "D-65",
        "decision_key": d65_entry.key if d65_entry is not None else None,
        "threshold": decision.threshold,
        "inference_probes": [
            {"template_id": template.get("id"), "prompt": _instantiate(template, fact)}
            for template in inference
        ],
    }
    if not applicable:
        row["verdict"] = "incomplete"
        row["incomplete_reason"] = "no_applicable_templates"
        row["directions"] = {}
        row["cells"] = []
        return row
    cells: list[dict[str, Any]] = []
    missing = False
    missing_reason = "missing_cell"
    for template in applicable:
        if (
            template.get("answer_role") == "truth_value"
            and "oracle_label" not in template
        ):
            missing = True
            missing_reason = "missing_oracle_label"
        prompt = _instantiate(template, fact)
        for seed in decision.decoding_seeds:
            completion = complete(prompt, seed)
            if completion is None:
                missing = True
                scored = False
                text = ""
            else:
                scored_cell = _correct(completion, template, fact)
                if scored_cell is None:
                    missing = True
                    missing_reason = "missing_oracle_label"
                    scored = False
                else:
                    scored = scored_cell
                text = completion
            cells.append(
                {
                    "template_id": template.get("id"),
                    "direction": template.get("primary_family"),
                    "seed": seed,
                    "prompt": prompt,
                    "completion": text,
                    "correct": scored,
                }
            )
    directions = _directions(cells)
    row["cells"] = cells
    row["directions"] = directions
    if missing:
        row["verdict"] = "incomplete"
        row["incomplete_reason"] = missing_reason
        return row
    if any(
        float(stats["accuracy"]) > decision.threshold for stats in directions.values()
    ):
        row["verdict"] = "excluded_known"
        return row
    row["verdict"] = "pass"
    return row


def _directions(cells: list[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    buckets: dict[str, list[bool]] = {}
    for cell in cells:
        name = str(cell["direction"])
        buckets.setdefault(name, []).append(bool(cell["correct"]))
    out: dict[str, dict[str, float | int]] = {}
    for name, flags in buckets.items():
        correct = sum(1 for flag in flags if flag)
        total = len(flags)
        out[name] = {
            "correct": correct,
            "total": total,
            "accuracy": correct / total if total else 0.0,
        }
    return out


def _correct(
    completion: str, template: dict[str, Any], fact: dict[str, Any]
) -> bool | None:
    role = str(template.get("answer_role", ""))
    tokens = set(_norm(completion).split())
    if role in {"subject", "object"}:
        aliases = _mapping(fact, "aliases").get(role, [])
        if not isinstance(aliases, list):
            return False
        for alias in aliases:
            if not isinstance(alias, dict):
                continue
            if alias.get("language") not in {None, "en"}:
                continue
            text = _norm(str(alias.get("text", "")))
            if text and text in _norm(completion):
                return True
        return False
    if role == "truth_value":
        if "oracle_label" not in template:
            return None
        label = template.get("oracle_label")
        if label is True:
            return "yes" in tokens or "true" in tokens
        if label is False:
            return "no" in tokens or "false" in tokens
        return None
    return False


def _applies(template: dict[str, Any], relation: str) -> bool:
    premises = template.get("extra_premises")
    if not isinstance(premises, list) or premises:
        return False
    return _relation_listed(template, relation)


def _relation_listed(template: dict[str, Any], relation: str) -> bool:
    listed = template.get("relation_applicability")
    return isinstance(listed, list) and relation in listed


def _instantiate(template: dict[str, Any], fact: dict[str, Any]) -> str:
    triple = _mapping(fact, "triple")
    subject = str(_mapping(triple, "subject").get("label", ""))
    obj = str(_mapping(triple, "object").get("label", ""))
    text = str(template.get("text", ""))
    return text.replace("{subject}", subject).replace("{object}", obj)


def _templates(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DataError(str(path))
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise DataError("closure_templates")
    sets = loaded.get("sets")
    if not isinstance(sets, dict):
        raise DataError("closure_templates")
    found: list[dict[str, Any]] = []
    for key in ("equivalence", "inference"):
        block = sets.get(key)
        if not isinstance(block, dict):
            continue
        rows = block.get("templates")
        if not isinstance(rows, list):
            continue
        for row in rows:
            if isinstance(row, dict):
                found.append(row)
    return found


def _write_report(
    path: Path,
    rows: list[dict[str, Any]],
    decision: D65Decision,
    binding: dict[str, Any] | None = None,
) -> None:
    excluded = [row for row in rows if row.get("verdict") == "excluded_known"]
    fraction = len(excluded) / len(rows) if rows else 0.0
    alarm = fraction > decision.contamination_trigger
    lines = [
        "# Exclusion gate",
        "",
        f"excluded_fraction: {fraction}",
        f"alarm: {str(alarm).lower()}",
        f"candidates: {len(rows)}",
        "",
        "## Provenance",
        "",
    ]
    if binding is not None:
        for key in (
            "study_role",
            "model_config_id",
            "model_config_digest",
            "model_identity_hash",
            "identity_schema_version",
            "governing_spec_revision",
        ):
            lines.append(f"{key}: {binding.get(key)}")
    lines.extend(
        [
            "",
            "## Excluded",
            "",
        ]
    )
    for row in excluded:
        directions = row.get("directions")
        if not isinstance(directions, dict):
            continue
        for name, stats in directions.items():
            if not isinstance(stats, dict):
                continue
            lines.append(
                f"- {row.get('fact_id')} {row.get('relation')} {name} "
                f"{stats.get('accuracy')}"
            )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise DataError(str(path))
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        loaded = json.loads(line)
        if isinstance(loaded, dict):
            rows.append(loaded)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(body, encoding="utf-8")


def _mapping(value: dict[str, Any], key: str) -> dict[str, Any]:
    raw = value.get(key)
    if not isinstance(raw, dict):
        raise DataError(key)
    return raw


def _norm(text: str) -> str:
    return " ".join(text.casefold().split())
