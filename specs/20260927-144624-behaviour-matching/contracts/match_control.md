# Contract: match_control

**Feature**: `20260927-144624-behaviour-matching`  
**Module**: `src/controls/match.py`

## Signature

```python
def match_control(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: MatchLedgerPort,
    behavior: MatchBehaviorPort,
) -> MatchRecord:
    """Try the declared severities and write match.json, or raise before a verdict."""
```

```python
def compare_matches(left: MatchRecord, right: MatchRecord, decisions: Path) -> None:
    """Equal severity and status only when D-53 is closed with tolerance 0."""
```

```python
def pilot_inputs(records: Sequence[MatchRecord]) -> tuple[PilotInput, ...]:
    """One row per record, unmatched included."""
```

```python
def reject_dropped(source: Sequence[MatchRecord], reported: Sequence[PilotInput]) -> None:
    """Raise ControlError('unmatched') when an unmatched source row is missing or changed."""
```

`spec_root` is required and has no default. The caller passes `.factverify/spec` or a fixture root.

## Ports

```python
class MatchLedgerPort(Protocol):
    def get(self, ledger_id: str) -> SystemView | None: ...

class MatchBehaviorPort(Protocol):
    def direct_qa_accuracy(
        self,
        system_id: str,
        fact_id: str,
        probe_ids: tuple[str, ...],
        severity: str | None,
    ) -> Measurement: ...

    def dimension_value(
        self, system_id: str, fact_id: str, name: str, severity: str
    ) -> float: ...
```

`dimension_value` is called only for a `hard` control with a closed D-59 row, and only at the selected severity.

## Order

1. Load the match document. Forbidden keys, a literal target, an unknown key, an empty search list, a final-test split, or an output directory inside `.factverify/` raise immediately.
2. Load `spec_root/closure_templates.yaml`. A missing file raises.
3. Load the decision record. D-54 must be closed and carry `band_summary`, `tolerance`, `boundary`, and `selection_rule`. D-58 must be closed. A hard control must have a closed D-59 dimension list or an open row with a non-empty `waiver`.
4. Load the probe manifest and refuse evaluation groups, final-test probes, and any probe that is not `direct_qa` for this fact.
5. Resolve the control row and the reference rows. Enforce the block's reference count.
6. Start `CostRecord`, measure, finish the cost record, rank, apply hard dimensions, write `match.json`.

A raise in steps 1–5 writes no file. Steps 6 writes either `matched` or `unmatched`.

## What this function does not do

- It does not call `build_control`, `Gateway`, or `Accountant`.
- It does not import `src.eval.gateway` or `src.eval.budget`.
- It does not edit `.factverify/spec/` or the decision record.
- It does not drop an unmatched record or change the D-54 tolerance after measuring.

## Errors

`ControlError` names the missing field or decision id: `D-54`, `D-58`, `D-59`, `D-53` (from `compare_matches` only), `block`, `probes`, `target_accuracy`, the ledger id, or the template group id.
