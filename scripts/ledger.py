"""Run ledger CLI. The commit and the dirty flag come from the record."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.ledger.api import (
    CheckpointRecord,
    Incident,
    add_checkpoint,
    add_incident,
    check_disjoint,
    final_pass_status,
    get_checkpoint,
    lineage,
    open_ledger,
)
from src.ledger.errors import LedgerError
from src.ledger.export import export_ledger, import_ledger


def main(argv: list[str] | None = None) -> int:
    """Dispatch one subcommand. A rejected add prints the field and exits 1."""
    parser = argparse.ArgumentParser(prog="scripts/ledger.py")
    sub = parser.add_subparsers(dest="command")
    _add_open(sub.add_parser("init"))
    add = sub.add_parser("add")
    add_sub = add.add_subparsers(dest="kind")
    checkpoint = add_sub.add_parser("checkpoint")
    _add_open(checkpoint)
    checkpoint.add_argument("--record", type=Path, required=True)
    incident = add_sub.add_parser("incident")
    _add_open(incident)
    incident.add_argument("--record", type=Path, required=True)
    show = sub.add_parser("show")
    _add_open(show)
    show.add_argument("--id", required=True)
    lineage_cmd = sub.add_parser("lineage")
    _add_open(lineage_cmd)
    lineage_cmd.add_argument("--id", required=True)
    _add_open(sub.add_parser("check-disjoint"))
    final = sub.add_parser("final-pass")
    _add_open(final)
    final.add_argument("--split", required=True)
    export_cmd = sub.add_parser("export")
    _add_open(export_cmd)
    export_cmd.add_argument("--directory", type=Path, required=True)
    import_cmd = sub.add_parser("import")
    import_cmd.add_argument("--source", type=Path, required=True)
    import_cmd.add_argument("--destination", type=Path, required=True)
    import_cmd.add_argument("--decisions", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help(sys.stderr)
        return 2
    try:
        return _run(args)
    except LedgerError as exc:
        print(exc.message, file=sys.stderr)
        return 1


def _add_open(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", type=Path, required=True)
    parser.add_argument("--decisions", type=Path, required=True)


def _run(args: argparse.Namespace) -> int:
    if args.command == "import":
        import_ledger(args.source, args.destination, decisions=args.decisions)
        return 0
    if args.command == "add" and getattr(args, "kind", None) is None:
        return 2
    ledger = open_ledger(args.path, decisions=args.decisions)
    if args.command == "init":
        return 0
    if args.command == "add" and args.kind == "checkpoint":
        record = _checkpoint(json.loads(args.record.read_text(encoding="utf-8")))
        print(add_checkpoint(ledger, record))
        return 0
    if args.command == "add" and args.kind == "incident":
        payload = json.loads(args.record.read_text(encoding="utf-8"))
        print(add_incident(ledger, _incident(payload)))
        return 0
    if args.command == "show":
        row = get_checkpoint(ledger, args.id)
        if row is None:
            raise LedgerError(args.id)
        print(json.dumps({"role": row.role, "split": row.split}))
        return 0
    if args.command == "lineage":
        print("\n".join(lineage(ledger, args.id)))
        return 0
    if args.command == "check-disjoint":
        report = check_disjoint(ledger)
        if report.ok:
            print(json.dumps(report.counts))
            return 0
        print(" ".join(report.offenders))
        return 1
    if args.command == "final-pass":
        status = final_pass_status(ledger, args.split)
        print("" if status is None else status)
        return 0
    if args.command == "export":
        export_ledger(ledger, args.directory)
        return 0
    return 2


def _checkpoint(payload: object) -> CheckpointRecord:
    if not isinstance(payload, dict):
        raise LedgerError("record")
    if "git_commit" not in payload:
        raise LedgerError("git_commit")
    if "dirty" not in payload:
        raise LedgerError("dirty")
    return CheckpointRecord(
        identity_hash=_text(payload, "identity_hash"),
        parent_ledger_id=_optional(payload, "parent_ledger_id"),
        parent_identity_hash=_text_allow_empty(payload, "parent_identity_hash"),
        config_hash=_text(payload, "config_hash"),
        seed=_int(payload, "seed"),
        fact_id=_text(payload, "fact_id"),
        split=_text(payload, "split"),
        role=_text(payload, "role"),
        tier=_text(payload, "tier"),
        family=_text(payload, "family"),
        method=_text(payload, "method"),
        implementation_id=_text_allow_empty(payload, "implementation_id"),
        spec_tag=_text(payload, "spec_tag"),
        git_commit=_text(payload, "git_commit"),
        dirty=_bool(payload, "dirty"),
        tokens=_int(payload, "tokens"),
        scored_candidates=_int(payload, "scored_candidates"),
        training_steps=_int(payload, "training_steps"),
        training_examples=_int(payload, "training_examples"),
        exports=_int(payload, "exports"),
        wall_clock_seconds=_float(payload, "wall_clock_seconds"),
        gpu_hours=_float(payload, "gpu_hours"),
        peak_memory_bytes=_int(payload, "peak_memory_bytes"),
        status=_text(payload, "status"),
        supersedes=_optional(payload, "supersedes"),
    )


def _incident(payload: object) -> Incident:
    if not isinstance(payload, dict):
        raise LedgerError("record")
    return Incident(
        split=_text(payload, "split"),
        references_pass_number=_int(payload, "references_pass_number"),
        note=_text(payload, "note"),
    )


def _text(payload: dict[str, object], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or value == "":
        raise LedgerError(name)
    return value


def _text_allow_empty(payload: dict[str, object], name: str) -> str:
    if name not in payload:
        raise LedgerError(name)
    value = payload[name]
    if not isinstance(value, str):
        raise LedgerError(name)
    return value


def _optional(payload: dict[str, object], name: str) -> str | None:
    if name not in payload or payload[name] is None:
        return None
    value = payload[name]
    if not isinstance(value, str) or value == "":
        raise LedgerError(name)
    return value


def _int(payload: dict[str, object], name: str) -> int:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise LedgerError(name)
    return value


def _float(payload: dict[str, object], name: str) -> float:
    value = payload.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LedgerError(name)
    return float(value)


def _bool(payload: dict[str, object], name: str) -> bool:
    value = payload.get(name)
    if not isinstance(value, bool):
        raise LedgerError(name)
    return value


if __name__ == "__main__":
    sys.exit(main())
