# Contract: estimate

**Feature**: `20260927-161631-ledger-stats-cache`  
**Modules**: `src/stats/`

## Signature

```python
def estimate(
    verdicts: Sequence[VerdictRow],
    *,
    spec_root: Path,
    decisions: Path,
    ledger: StatsLedgerPort,
    seed: int,
    purpose: str,
) -> EstimateTable:
    """Block intervals for a final report, or raise on an open decision."""


def select_thresholds(
    rows: Sequence[VerdictRow],
    *,
    spec_root: Path,
    decisions: Path,
    ledger: StatsLedgerPort,
) -> tuple[ThresholdBound, ...]:
    """One FRR upper bound per threshold_id. Any final-test row raises."""


def adjust(
    p_values: Sequence[float],
    *,
    decisions: Path,
) -> tuple[float, ...]:
    """Multiplicity adjustment for a closed D-08 procedure."""


def coverage_simulation(
    simulation: Path,
    *,
    spec_root: Path,
    decisions: Path,
) -> CoverageReport:
    """Block coverage against a row-level resample. Raises while D-57 is open."""
```

`spec_root` and `decisions` are required and have no defaults. `purpose` is `threshold_selection` or `final_report`. Any other string raises `purpose`.

```python
class StatsLedgerPort(Protocol):
    def get_checkpoint(self, ledger_id: str) -> CheckpointView | None: ...

    def get_evaluation_run(self, run_id: str) -> EvaluationView | None: ...
```

## Steps for select_thresholds

1. Load each row through the ledger port. A missing id raises and names `row_id`.
2. If any row's split is `final_test` or `final-test`, raise `final_test`. Do not read D-03 first.
3. If D-03 or D-05 is open, or `selection_uncertainty_procedure` is null or `DECISION_REQUIRED`, raise that name.
4. When the closed procedure is `one_sided_exact`, return one upper bound per `threshold_id` for rows whose oracle label is a genuine reference. The point estimate is the rejection rate. The bound is positive when the error count is zero.

`purpose=threshold_selection` on `estimate` follows the same final-test refusal and does not emit a final-report table.

## Steps for estimate when purpose is final_report

1. Load rows. Unknown ledger ids raise.
2. If D-07 is open, raise `D-07`. If D-57 is open, raise `D-57`.
3. Refuse `unit="row"`.
4. A closed `design: nested` raises `design` when one `fact_id` sits on two checkpoints. A closed `design: crossed` resamples checkpoints and facts independently.
5. Build paired differences on `(checkpoint_ledger_id, fact_id)`. Arms that do not share those ids raise and list the missing ids. The same draw index is used for both arms.
6. Per-case weights, or a closed D-06 token other than `uniform`, raise `D-06`. While D-06 is open, each matched case has weight 1.
7. While D-10 is open, raise `D-10` before writing family rows. When it is closed with `mean`, write one row per `control_family` and one overall row. A family with no cases has `n` 0 and no rate.
8. A zero error count uses `one_sided_exact` when D-03 is closed. While D-03 is open, that estimate raises `D-03`. A zero-width interval at 0 is not returned.
9. While D-08 is open, do not attach adjusted p-values. When it is closed, call `adjust` with the percentile-bootstrap p-values.
10. Write `seed`, `replicate_count`, `design`, `spec_version`, and `input_digest` on the table.

## Steps for adjust

Read D-08. Open raises `D-08`. `holm`, `bh`, and `by` are the only procedures. The result length equals the input length. The hook's expected numbers live in the fixture, not in a library constant.

## Steps for coverage_simulation

Read D-57 and the simulation document. A missing simulation field raises and names it. Run `n_simulations` draws. Report `block_coverage` and `row_coverage`. The hook asserts `block_coverage` is within `coverage_tolerance` of `1 - gamma`, and `row_coverage` is below `1 - gamma`.
