# Quickstart: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Feature**: `20260927-161631-ledger-stats-cache`  
**Date**: 2026-09-27

Hooks live in `tests/test_ledger.py`, `tests/test_cache.py`, and `tests/test_stats.py`. They use temporary files and fixture decision records. They do not download weights and they do not start a training job.

## What a ledger hook supplies

1. A temporary ledger path and a decision file. The study shape keeps D-56 `open`. A hook that expects an insert closes D-56 with a `tiers` list that contains the row's tier.
2. A complete checkpoint record: identity, parent (or a root), config hash, seed, fact, split, role, tier, family, method, implementation id, spec tag, git commit, dirty flag, cost fields, and status. The caller supplies the commit and the dirty flag.
3. For a child, a parent row already committed.
4. For disjointness, calibration rows and final-test rows that either share nothing or share one fact, one reference seed, or one control implementation.

Do not update or delete a row to correct it. Add a new row whose `supersedes` points at the current row.

## What a cache hook supplies

1. A cache root outside `.factverify/` and a decision file. Open D-60 must raise before `compute` runs. A hook that stores an entry closes D-60 with `include_software_versions` true or false.
2. A request with identity hash, exact model input, decoding object, seed, sample index at least 1, request kind, and producer run id.
3. A `compute` callable the test controls. It should be called on a miss and on a corrupt body, and not on a hit.

## What a stats hook supplies

1. A fixture spec root whose `margins.yaml` is a copy the hook may mark closed. Do not edit `.factverify/spec/margins.yaml`.
2. Verdict rows whose checkpoint and evaluation-run ids exist on a scripted ledger port.
3. For threshold selection, calibration rows with `threshold_id` and `rejected`. One final-test row in that list must raise `final_test` even when D-03 is still open.
4. For a block draw, a closed D-07 row (`paired_block_bootstrap`, `nested` or `crossed`) and a closed D-57 row (`percentile`, a replicate count, a coverage tolerance).

## Scenarios

| Hook | Setup | Expected |
|------|--------|----------|
| `test_fv_ledg_001_unledgered_refused` | One committed row, one unknown identity | The known id returns role and split. The unknown id raises |
| `test_fv_ledg_002_required_fields` | One complete row, then one row per emptied field | The complete row gains an id and a timestamp. Each empty field raises and names that field. The file is unchanged |
| `test_fv_ledg_003_append_only` | A correction, then a direct `UPDATE` and `DELETE` | The new row points at the old id. The old row is unchanged. Both statements abort |
| `test_fv_ledg_004_vocabularies` | Closed D-56 `tiers`, then an unknown role and an unknown tier | The listed tier is accepted. The others raise. Open D-56 raises `D-56` |
| `test_fv_ledg_005_lineage` | Root, child, missing parent | Lineage of the child ends at the root. The missing parent raises |
| `test_fv_ledg_006_code_state` | Clean and dirty snapshots | Final-test plus dirty raises. Final-test plus clean stores the commit. A non-final dirty row is stored |
| `test_fv_ledg_007_disjoint` | Disjoint rows, then one shared fact, seed, or implementation | Success prints three counts. Each overlap exits nonzero and lists the row ids |
| `test_fv_ledg_008_single_pass` | Pass 1, a second pass, then an incident that references pass 1 | The second pass raises. After the incident, a later pass is stored |
| `test_fv_ledg_009_eval_runs` | A finished run, and a final-test run with an empty thresholds tag | The finished run keeps every field. The empty tag raises |
| `test_fv_ledg_010_export_roundtrip` | Export, import into an empty file, then a manifest with `schema_version` `2` | Digests match. The newer version raises |
| `test_fv_ledg_011_concurrency` | Several threads each adding one row, and one transaction rolled back | The row count equals the thread count. The rolled-back add leaves no partial row |
| `test_fv_cache_001_full_key` | Two requests that differ by one field, and one request with a field removed | The keys differ. The incomplete request raises. Open D-60 raises `D-60` |
| `test_fv_cache_002_exact_input` | Inputs that differ by one space, and the same input hashed twice | The hashes differ. The repeated hash matches |
| `test_fv_cache_003_samples_distinct` | Sample indices 1..k, then an index that was not stored | k entries. The new index is a miss |
| `test_fv_cache_004_events` | One hit and one miss | Each lookup appends one event. A source scan fails if a body is returned without an event |
| `test_fv_cache_005_integrity` | An intact row and a row whose stored body is altered | Intact returns `hit`. Altered returns `corrupt`, does not return the old body, and recomputes |
| `test_fv_cache_006_no_overwrite` | An identical recompute and a different body | The identical write leaves the row. The different body raises `conflict` and the stored digest stays |
| `test_fv_cache_007_location` | A root outside `.factverify/` and a root inside it | The outside root opens. The inside root raises |
| `test_fv_cache_008_export` | Export, import, and a manifest whose digest is wrong | Lookups return the same digests. The bad manifest raises |
| `test_fv_stat_001_block_resampling` | A closed nested design with several prompts per case | A drawn block includes every prompt row of that case. `unit="row"` raises |
| `test_fv_stat_002_crossed` | One fact on two checkpoints | `crossed` resamples both margins. `nested` raises `design` |
| `test_fv_stat_003_paired` | Two arms on the same cases, then one arm missing a case | Each replicate uses the same case ids. The gap raises and lists the case |
| `test_fv_stat_004_per_family` | Two families plus a family with no rows, D-10 closed as `mean` | One row per family and one overall row. The empty family has `n` 0 and no rate. Open D-10 raises |
| `test_fv_stat_005_zero_count` | Zero errors, D-03 closed as `one_sided_exact` | Point estimate 0 and a positive upper bound. A zero-width interval at 0 fails the hook |
| `test_fv_stat_006_multiplicity` | Fixture p-values and a closed `holm`, `bh`, or `by` row | Adjusted values match the fixture. An unknown procedure raises |
| `test_fv_stat_007_deterministic` | The same table, design, and seed, twice | Every estimate and bound matches. The output records seed, replicate count, and design |
| `test_fv_stat_008_no_final_test_tuning` | Calibration rows, then the same rows plus one final-test row | Calibration returns one bound per threshold. The mixed table raises `final_test` |
| `test_fv_stat_009_coverage_sim` | A closed D-57 simulation document | Block coverage is within tolerance of nominal. Row coverage is below nominal |
| `test_fv_stat_010_ledgered_only` | Rows with known ids, and one unknown id | Known ids load. The unknown id raises and names `row_id` |

## Out of scope for these hooks

Training a checkpoint, building a control, choosing α, editing `margins.yaml` or `attacks.yaml` in `.factverify/spec/`, and deciding whether a cache hit costs budget. Passing a fixture does not mark a requirement implemented while its decision is open on the study record.
