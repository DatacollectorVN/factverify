# Contract: `build_control`

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27  
**Module**: `src/controls/__init__.py`

---

## Public exports

```python
from src.controls import (
    build_control,
    load_control,
    compare_builds,
    list_catalog,
    certify_coverage,
    ControlError,
)
```

`ControlError` is the only error type raised by this package. The message names the missing field, the decision id, the family, or the implementation id.

---

## `build_control`

```python
build_control(
    config_path: Path,
    *,
    spec_root: Path,
    ledger: ControlLedgerPort,
    behavior: BehaviorPort | None = None,
    trainer: TrainerPort | None = None,
    parent_model: ModelPort | None = None,
) -> BuildResult
```

| Parameter | Required | Description |
|-----------|----------|-------------|
| `config_path` | yes | Control YAML. See `data-model.md` ControlConfig. |
| `spec_root` | yes | Directory containing `margins.yaml` and `access_profile.md`. No library default. The CLI default is `.factverify/spec`. |
| `ledger` | yes | Parent lookup, split index, and commit. |
| `behavior` | suppression and destruction | Direct-QA and locality measurements. Missing on those families raises. |
| `trainer` | destruction | Performs the named harness method. Missing raises. |
| `parent_model` | families that wrap or mask a parent | Scripted in tests. A study caller may wrap `load_model`. This function does not call `load_model`. |

There is no `severity` search and no evaluator-result argument.

### `BuildResult`

| Field | Description |
|-------|-------------|
| `status` | `accepted`, `rejected`, or `unchecked` |
| `label_path` | `control.json` when accepted, else `None` |
| `ledger_id` | Present unless the build raised before commit |
| `access_log` | Logical sources opened. Must not include a denylist name |
| `artifact_digest` | Present when accepted |

### Refusal before commit

The build raises, and the ledger is unchanged, when:

- a required config field is missing, null, or `DECISION_REQUIRED`
- a forbidden evaluator key or filename is present
- `output_dir` is inside `.factverify/`
- the family or implementation id is not the registered pair
- the parent row is missing, or its role is not `finetuned`, or its `fact_id` differs
- the implementation id is already on the other of `calibration` and `final_test`
- `family` is `untouched` and D-61 is not closed with a mechanism layer
- `spec_root` lacks `margins.yaml` or `access_profile.md`

### Acceptance

Suppression families call the retention rule in `checks.py` (research Decision 6). Destruction families call the locality rule (Decision 7). `untouched`, after D-61 is closed, is accepted without those checks.

| Outcome | Ledger | Label | Return |
|---------|--------|-------|--------|
| Check passes | `accepted` | `control.json` | `BuildResult` |
| Check runs and misses | `rejected` | `rejection.json` only | `BuildResult` |
| D-54 open, or locality margin null | `unchecked` | none | commit, then raise `ControlError` naming D-54 or the null margin |

`load_control` refuses `rejected` and `unchecked`. An early refusal in the previous section does not commit.

---

## `load_control`

```python
load_control(label_path: Path) -> ControlLabel
```

Refuses unless the file is an accepted negative label with every required field in `data-model.md`. `rejected` and `unchecked` records are not labels.

---

## `compare_builds`

```python
compare_builds(left: BuildResult, right: BuildResult, decisions: Path) -> None
```

Raises naming D-53 unless that row is closed with `digest_tolerance` `0` and the two accepted digests are equal. Does not write a ledger row.

---

## `list_catalog` and `certify_coverage`

```python
list_catalog() -> list[CatalogEntry]
certify_coverage(decisions: Path) -> None
```

`list_catalog` returns the nine entries. `certify_coverage` raises naming D-55 while that row is open, and raises naming the gap when a closed `min_count` is greater than the registered count.

---

## Ports

```python
class ControlLedgerPort(Protocol):
    def get_parent(self, ledger_id: str) -> ParentView | None: ...
    def splits_for_implementation(self, implementation_id: str) -> set[str]: ...
    def commit(self, row: LedgerRow) -> str: ...

class BehaviorPort(Protocol):
    def direct_qa_accuracy(self, system_id: str, fact_id: str, *, mechanism_enabled: bool) -> float: ...
    def delta_loc(self, system_id: str, bucket: str) -> float: ...

class TrainerPort(Protocol):
    def train(self, config: ControlConfig) -> bytes: ...
```

`system_id` is `parent` or `disabled`. Tests supply these ports. The CLI refuses a SQLite path by calling `src.train.ledger.require_sqlite_ledger` until P2-5 provides an adapter.

---

## CLI

```text
python -m src.controls.run --config <path> --spec-root <path> --ledger <path>
```

`--ledger` pointing at a SQLite file exits non-zero and names P2-5. Hooks call `build_control` in process with an in-memory port. They do not need the CLI.
