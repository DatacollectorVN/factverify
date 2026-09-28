# Contract: ledger

**Feature**: `20260927-161631-ledger-stats-cache`  
**Modules**: `src/ledger/api.py`, `src/ledger/schema.py`, `src/ledger/export.py`, `scripts/ledger.py`

## Signature

```python
def open_ledger(path: Path, *, decisions: Path) -> Ledger:
    """Create the file if needed. Raise if a trigger or the meta row is missing."""


def add_checkpoint(ledger: Ledger, record: CheckpointRecord) -> str:
    """Insert one row and return its id, or raise and leave the file unchanged."""


def add_evaluation_run(ledger: Ledger, record: EvaluationRun) -> str:
    """Insert one run. Final-test pass rules apply."""


def add_incident(ledger: Ledger, record: Incident) -> str:
    """Insert one incident. Does not edit the pass it references."""


def get_checkpoint(ledger: Ledger, ledger_id: str) -> CheckpointRecord | None:
    """Return the row, or None when the id is unknown."""


def lineage(ledger: Ledger, ledger_id: str) -> tuple[str, ...]:
    """Row ids from the requested row back to the root. The root is last."""


def check_disjoint(ledger: Ledger) -> DisjointnessReport:
    """Fact, reference seed, and control implementation across calibration and final-test."""


def final_pass_status(ledger: Ledger, split: str) -> int | None:
    """The highest accepted pass number on that split, or None when no pass exists."""


def export_ledger(ledger: Ledger, directory: Path) -> None:
    """Write manifest.json, plus CSV and JSON for every table."""


def import_ledger(directory: Path, destination: Path, *, decisions: Path) -> Ledger:
    """Load an export into an empty file. Refuse a schema_version other than '1'."""
```

`decisions` is required and has no default. The study D-56 row stays `open`.

## Steps for add_checkpoint

1. Load D-56. Missing or `open` raises `LedgerError("D-56")`.
2. Reject an empty required field by name. A root may omit the parent. A control with an empty `implementation_id` raises `implementation_id`.
3. Reject a role outside `base`, `finetuned`, `reference`, `control`, `candidate`.
4. Reject a `tier` that is not in the closed `tiers` list.
5. Reject a non-root whose parent id is absent or whose parent identity hash disagrees.
6. Reject a final-test row (`final_test` or `final-test`) whose `dirty` is true.
7. Reject a repeated `identity_hash` whose `supersedes` is not the current row of that hash.
8. Insert inside one transaction. A trigger aborts any `UPDATE` or `DELETE`.

## Steps for add_evaluation_run

1. Reject a missing checkpoint id, an empty `thresholds_tag`, or a final-test row with `dirty` true.
2. On a final-test split, `pass_number` 1 is accepted only when no final-test run exists yet.
3. A greater `pass_number` is accepted only when an incident on that split has `references_pass_number` 1.
4. Insert. The checkpoint row is not modified.

## CLI

`python scripts/ledger.py` subcommands: `init`, `add`, `show`, `lineage`, `check-disjoint`, `final-pass`, `export`, `import`.

- `init --path --decisions` creates the file.
- `add checkpoint` reads `git_commit` and `dirty` from the JSON record. It does not run git. A missing `git_commit` or `dirty` raises that field name.
- `check-disjoint` exits 0 when the report is ok and prints the counts. It exits 1 and prints the offending row ids otherwise.
- `import` refuses a manifest whose `schema_version` is not `1`, or whose row digests disagree.

Unknown subcommands exit non-zero. A rejected add exits non-zero and prints the field or decision id.

## Ports the SQLite ledger also satisfies

`SqliteLedger.commit_checkpoint` accepts a `CheckpointRow` and runs the same checks as `add_checkpoint`. `SqliteLedger.commit` does the same for a control `LedgerRow`. `get` returns `role`, `fact_id`, and `split` for `MatchLedgerPort`. In-memory doubles used by existing harness tests are not required to enforce D-56.
