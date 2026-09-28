# Research: FV-LEDG, FV-STAT, FV-CACHE — Run Ledger, Cluster Intervals, and Generation Cache

**Feature**: `20260927-161631-ledger-stats-cache`  
**Date**: 2026-09-27  
**Source notes** (read from disk; Obsidian MCP unavailable):

- `FactVerify — Execution Plan` (status: planned) — "Phase 2", tasks P2-5, P2-6, P2-7; "Phase 4", P4-5 and P4-6; "Start here" item 3; "Tracking conventions"; "Risk register" rows "Threshold leakage" and "Evaluation dominates wall-clock"
- `Research Proposal — FactVerify (v3)` (status: draft) — "6.2 Cross-fitted split", "6.4 Primary endpoint", "8. Statistical design"
- `FactVerify — Phase 0 Build Handbook (Freeze Spec)` (status: draft) — I6, I7, I8, "6.4", "6.7", "8.4", "8.7", V23
- `FV-LEDG — P2-5`, `FV-STAT — P2-6`, `FV-CACHE — P2-7` (each status: draft)
- Existing code: `scripts/ledger.py` inserts into `runs` with a nullable `tier` and roles `reference`, `control`, `candidate` only. `src/cache/store.py` `GenerationCache.put` uses `INSERT OR REPLACE` and hashes with 16 hex characters. `src/eval/gateway.py` caches on `(probe_id, channel_id)` and charges `cache_hit` or `generation` through `Accountant`. `src/train/ledger.py` `CheckpointRow` has no git commit or dirty flag. `.factverify/spec/margins.yaml` lists D-03, D-06, D-07, D-08, and D-10 as `open`. `selection_uncertainty_procedure` is `DECISION_REQUIRED`. `attacks.yaml` `cache_policy.charge_rule` is `zero_new_compute` and `observation_charged` is true. That file is not edited.

No technical-context item is left as NEEDS CLARIFICATION. The nine study decisions in `plan.md` are deliberately unresolved.

---

## Decision 1: Replace both stubs

**Decision**: `src/ledger/` is the ledger. `scripts/ledger.py` becomes a CLI over that package and drops the `runs` table. `src/cache/store.py` drops `GenerationCache`, the default path `.cache/generations.db`, the 16-character hash, and `INSERT OR REPLACE`. `tests/test_cache.py::test_overwrite` is deleted. A different body under an existing key raises. An identical body leaves the stored row unchanged.

The library functions take a path. They do not invent `ledger.sqlite` or a cache directory. The CLI default for the ledger file is `ledger.sqlite` in the current directory, which is the path the execution plan already names.

**Rationale**: The stubs contradict FV-LEDG-002, FV-LEDG-003, FV-LEDG-004, and FV-CACHE-006. Extending them would keep a nullable tier and a silent overwrite.

**Alternatives considered**:

- Migrate the `runs` rows into the new schema. Rejected: that table cannot represent the required fields, and no study checkpoint has been committed to it.
- Keep `GenerationCache.get` / `put` as a compatibility wrapper. Rejected: `put` overwrites, and the key omits request kind and the exact input.

---

## Decision 2: Append-only SQLite, one schema version

**Decision**: Tables are `meta`, `checkpoints`, `evaluation_runs`, and `incidents`. `meta` holds a single row `schema_version = "1"`. Before any insert, triggers on each data table abort `UPDATE` and `DELETE` with `append-only`. Each add runs in one transaction. A raised error rolls back, so a rejected write leaves the file unchanged.

`open_ledger` sets `foreign_keys=ON` and `journal_mode=WAL`. It does not set a busy timeout; the Python sqlite3 default stands. Concurrent adds each use `BEGIN IMMEDIATE`.

Export writes `manifest.json` (`schema_version`, table names, row counts, per-row sha256) plus one CSV and one JSON file per table. Import into an empty ledger accepts only `schema_version` equal to `"1"`. Any other version raises `schema_version`. Re-import must reproduce row counts and the per-row digests.

**Rationale**: FV-LEDG-003 names a database trigger so a raw `UPDATE` fails. FV-LEDG-010 requires a schema version and a lossless round-trip. WAL plus a transaction per row is what makes FV-LEDG-011 hold without a new numeric timeout. Version `"1"` names this schema. It is not a study margin. Accepting an older export would be a migration policy the notes do not give.

**Alternatives considered**:

- Enforce append-only only in Python. Rejected: the requirement says every path, including a direct statement, fails.
- Choose a busy timeout in code. Rejected: that would be a new literal. The driver default is left alone.

---

## Decision 3: Full checkpoint rows, roots, and corrections

**Decision**: `add_checkpoint` requires every field in `data-model.md`. An empty string raises and names the field, except a root's parent fields. A root has `parent_ledger_id` null and `parent_identity_hash` `""`. Any other row must name a `parent_ledger_id` that already exists, and `parent_identity_hash` must equal that parent's identity hash. `lineage` walks `parent_ledger_id` to the root and returns that chain, root last.

Role is `base`, `finetuned`, `reference`, `control`, or `candidate`. Anything else raises `role`. `implementation_id` is required and non-empty when role is `control`. It may be `""` for other roles.

D-56 is a caller-supplied decision file, not a row in `margins.yaml`. While that row is missing or `open`, `add_checkpoint` raises `LedgerError("D-56")` and writes nothing. A closed row must carry a non-empty `tiers` list of strings. The checkpoint's `tier` must be one of those strings. Any other closed shape raises `D-56`. The study file used by the hooks stays `open`. Fixtures that need an accepted row close D-56 with the tiers that hook uses. `pilot` is not special.

A second row with the same `identity_hash` is accepted only when `supersedes` is the id of the current row for that hash (the row that no other row supersedes). The new row's identity hash must equal the superseded row's. A correction that points at a missing id raises `supersedes`. The superseded row is not modified.

Cost fields are the integers and floats in `data-model.md`. Zero is allowed. It means that count was measured as zero. A missing key is not stored as zero by the ledger; the caller must pass the key.

**Rationale**: FV-LEDG-002 rejects an empty required field. FV-LEDG-004 takes the role list from the requirements note, which is wider than the tracking-conventions list and wider than the stub. FV-LEDG-005 needs a root or the base row can never be inserted. The spec's edge case refuses a second identity row that does not point at the first. D-56 has no values in the vault, so the closed fixture list is the only vocabulary the code will read.

**Alternatives considered**:

- Put `base` and `finetuned` outside the ledger until the tracking conventions are edited. Rejected: the requirements note already reconciled that list, and the spec follows the note.
- Give a root a synthetic parent id. Rejected: the spec says a row that names no parent is the root.

---

## Decision 4: Recorded commit, disjointness, and one final-test pass

**Decision**: `git_commit` and `dirty` are ordinary fields on the checkpoint row and the evaluation-run row. The caller supplies both. `add_checkpoint`, `add_evaluation_run`, and `scripts/ledger.py` do not run git and do not read the work tree. There is no `src/ledger/git.py`. A missing or empty `git_commit` raises `git_commit`. A missing `dirty` raises `dirty`.

The tokens `final_test` and `final-test` are the same split for every guard in this feature. `calibration` is the only calibration token.

A final-test checkpoint or evaluation run with `dirty` true raises `dirty` and writes nothing. A non-final row with `dirty` true is stored. A final-test row with `dirty` false stores the commit and `dirty=false`.

`check_disjoint` looks at checkpoint rows only. The three dimensions are:

| Dimension | Rows |
|-----------|------|
| `fact` | `fact_id` |
| `reference_seed` | `seed` where `role` is `reference` |
| `control_implementation` | `implementation_id` where `role` is `control` and the id is non-empty |

A value that appears on both a calibration row and a final-test row fails the check and lists those row ids. Otherwise the check returns a count of distinct values per dimension per split. Template groups are not a fourth dimension. A ledger with only one of the two splits returns zero for the empty split and succeeds.

Evaluation runs require `checkpoint_ledger_id` (must exist), `arm`, `split`, `spec_tag`, `thresholds_tag` (non-empty for every run), `budget_used` (object with the cost keys), and `pass_number` (int ≥ 1). A final-test run with an empty thresholds tag raises `thresholds_tag`.

`final_pass_status(split)` reads evaluation runs on that split. No runs means the next pass is 1. Opening pass 1 inserts the run with `pass_number` 1. A later `pass_number` on that split raises `pass` unless an incident exists whose `references_pass_number` equals 1 and whose `split` equals that split. An incident that references any other pass number does not unlock the split. Incidents are append-only and do not alter the first pass.

**Rationale**: FV-LEDG-006 checks the dirty flag stored on the row. The caller, not the ledger, decides what that flag is. Treating `final-test` as final-test matches the existing match code, which refuses both spellings. FV-LEDG-007's scenarios name fact, seed, and implementation. The spec leaves template groups on V13. FV-LEDG-008 unlocks a second pass only when the incident references the first pass. The split, not the fact, is the unit, because the plan's final-test pass is one pass.

**Alternatives considered**:

- Add `src/ledger/git.py` to run `git rev-parse` and `git status`. Rejected: the ledger stores the commit and the dirty flag the caller already has. A git reader is a second source of truth and makes every hook depend on the work tree.
- Include template-group ids in the disjointness check. Rejected: the spec's assumption says this feature does not add that dimension.

---

## Decision 5: Cache key, and D-60 refuses until it is closed

**Decision**: `cache_key` raises `CacheError("D-60")` when the caller-supplied D-60 row is missing or `open`. A closed row must set `include_software_versions` to `true` or `false`. Any other value raises `D-60`.

The key always hashes, with full sha256 of UTF-8 bytes and no normalisation:

- `identity_hash` (non-empty string)
- the exact `model_input` string, after the caller has applied any chat template
- every decoding field in the request mapping, via `hash_mapping` (sorted keys, no dropped field)
- `request_kind`: `generate` or `score`
- `seed` (int) and `sample_index` (int ≥ 1)
- `producer_run_id` (non-empty), stored on the entry and not part of the lookup key

When `include_software_versions` is true, `software_versions` must be a non-empty mapping of string to string and enters the key. When it is false, that mapping is omitted. A missing required field raises and names the field. Two requests that differ in any included field produce different keys. The same `model_input` bytes hash the same.

Sample indices in the spec's scenario start at 1. Existing single-completion call sites in `src/eval/native.py` and `src/eval/__init__.py` pass `sample_index=1`. They do not pass 0.

**Rationale**: FV-CACHE-001 and FV-CACHE-002. D-60 is open, so a key that silently includes or drops software versions would close it. Full sha256 replaces the stub's truncated hash. Index 1 is the numbering FV-CACHE-003 already uses.

**Alternatives considered**:

- Always include `torch` and `transformers` versions. Rejected: that closes D-60.
- Default `sample_index` to 0 inside the cache. Rejected: an omitted index must raise, and 0 is not in the spec's 1..k range.

---

## Decision 6: Store behaviour, events, and the gateway

**Decision**: `open_cache(root, decisions)` resolves `root` and raises `location` when the resolved path is inside a directory named `.factverify` or is that directory. `get_or_compute(request, compute)` is the only read and write path.

On a hit, the stored digest is recomputed from the body. A match returns the entry and `hit`. A mismatch returns nothing from the store, emits `corrupt`, calls `compute`, and stores the new body as a miss would. The caller sees one event, `corrupt`.

On a miss, `compute` runs and the body is inserted with its digest. The event is `miss`.

A second write whose digest equals the stored digest is a no-op and the event is `hit`. A second write whose digest differs raises `CacheError("conflict")` after recording event `conflict` with both digests. The stored row stays.

`src/eval/gateway.py` `CachePort` becomes `get_or_compute`. The gateway builds the request from `identity_hash` (constructor argument), the probe prompt as `model_input`, the decoding mapping it already sends, `sample_index`, and `request_kind` `generate` or `score`. Replay still skips the cache. A hit calls `accountant.query` with kind `cache_hit`. A miss or a corrupt-then-recompute calls it with kind `generation`. A conflict charges `generation` because compute already ran, then raises. No new kind is added to `budget.py`. `Accountant` gains `note_cache_event` that appends the event and does not change a balance. A source scan fails if `src/cache/store.py` is read except through `get_or_compute`, or if any module other than `gateway.py` calls `get_or_compute`.

D-20 stays open. This feature does not read `charge_rule` and does not mark FV-CACHE-004 implemented.

Export writes a manifest of keys and digests. Import refuses when the manifest's own digest disagrees with the entry bytes.

**Rationale**: FV-CACHE-004 through FV-CACHE-008. The gateway is already the only model caller. Leaving it on `(probe_id, channel_id)` would keep serving one identity's completion for another. Charge rules belong to P2-2 and to D-20. `note_cache_event` makes the event visible to the accountant without choosing a price.

**Alternatives considered**:

- Leave the gateway on `DictCache` and test the store only in isolation. Rejected: the production path would still use the short key.
- Map `corrupt` to a new budget kind. Rejected: `budget.py` raises on an unknown kind, and a new kind would be a new charge rule.

---

## Decision 7: Stats read a spec root and raise while the study rows are open

**Decision**: `estimate`, `select_thresholds`, `adjust`, and `coverage_simulation` take `spec_root`. They read `margins.yaml` from that root. A missing file, a null field, or `DECISION_REQUIRED` raises and names the field. Decision status comes from that file's `blocking_decisions` list plus a caller-supplied decision file that may close a fixture id. The study `.factverify/spec/margins.yaml` is never the fixture. A hook copies a margins file and closes only the ids that hook needs.

Interpreted tokens, and only when the named decision is `closed`. Any other token raises that decision id:

| Decision | Field | Tokens this code runs |
|----------|-------|------------------------|
| D-07 | `resampling_contract`, `design` | `paired_block_bootstrap` with `design` `nested` or `crossed` |
| D-06 | `case_weights` | `uniform` |
| D-10 | `aggregation.per_family`, `aggregation.overall` | `mean` and `mean` |
| D-03 | `procedure` | `one_sided_exact` |
| D-05 | `selection_uncertainty_procedure` | `one_sided_exact` |
| D-08 | `procedure` | `holm`, `bh`, or `by` |
| D-57 | `interval_type` | `percentile` |

`replicate_count` is a positive int on the closed D-57 row. `coverage_tolerance` is a decimal string on that row. Gamma is `confidence_error_probability.value` on the fixture margins file. A null gamma raises `D-03`.

`one_sided_exact` is the one-sided Clopper-Pearson upper bound, stdlib only. Zero errors use `1 - gamma ** (1/n)` in `Decimal`, which is the handbook "8.4" expression. Positive error counts use bisection on the binomial tail until the width is below `SOLVER_WIDTH = Decimal("1e-12")`. That width is a solver stop, written once in `bounds.py`, and it is not a margin. The study path never reaches it while D-03 or D-05 is open.

`select_thresholds` raises `final_test` when any row has that split, before it looks at D-03 or D-05. On a calibration-only table it still raises `D-03` or `selection_uncertainty_procedure` while those are unresolved. A fixture that closes them receives one upper bound per `threshold_id`.

While D-06 is open, `estimate` still checks that both arms share case ids `(checkpoint_ledger_id, fact_id)` and still computes an unweighted paired difference when D-07 and D-57 are closed. A request that supplies per-case weights raises `D-06`. The worksheet `case_weights: uniform` on an open study file is not treated as a closed choice.

While D-07 is open, `estimate` raises `D-07` before a draw. A closed nested design raises `design` when any `fact_id` appears under more than one checkpoint. A closed crossed design resamples checkpoint ids and fact ids independently with replacement. A case is kept when both ids were drawn. Its multiplicity is the product of the two draw counts. Every prompt row of that case is copied with the case. `estimate(..., unit="row")` raises `rows`. `draw_rows` exists only so `coverage_simulation` can show under-coverage. `estimate` does not call it.

`percentile` intervals are the empirical quantiles of the replicate statistics at `gamma/2` and `1 - gamma/2`. The same `random.Random(seed)` stream drives every draw. Two calls with the same table, design, and seed return the same numbers. The output records `seed`, `replicate_count`, `design`, the margins `version`, and the sha256 of the canonical verdict JSON.

A family with no rows appears with `n = 0` and no rate, including when D-10 is closed. While D-10 is open the whole family report raises `D-10`, so that zero-row rule is not marked implemented on the study file.

`adjust` is a pure function of p-values and the closed D-08 procedure. Holm, Benjamini-Hochberg, and Benjamini-Yekutieli are implemented in `multiplicity.py`. The hook compares them to fixture values computed by hand. `estimate` calls `adjust` only when D-08 is closed. The p-value for a paired difference is the two-sided percentile bootstrap probability against zero, clipped to 1, and only when `interval_type` is `percentile`.

**Rationale**: The spec forbids a default resampling scheme and forbids adopting the handbook's numeric illustration as the study procedure. Gating each token on a closed fixture row is the same pattern P2-4 used for D-54. Raising on final-test before the confidence procedure means the leakage guard does not wait on D-03. Unweighted pairing while D-06 is open follows the spec's reading of the FV-STAT-003 text against the decision table.

**Alternatives considered**:

- Run `paired_block_bootstrap` because `margins.yaml` already contains that string. Rejected: the same file marks D-07 open, so the string is still a worksheet.
- Add SciPy for the beta quantile and for false-discovery control. Rejected: the repository does not depend on SciPy, and the hook fixtures are small enough for stdlib.
- Implement BCa beside percentile. Rejected: a closed row that says `bca` must raise until that token is deliberately added. Implementing it now would pick D-57.

---

## Decision 8: Coverage inputs come from the fixture

**Decision**: `coverage_simulation` raises `D-57` while that row is open or lacks `coverage_tolerance`, `replicate_count`, and `interval_type`. When closed, it reads a simulation document: `n_checkpoints`, `n_facts`, `n_prompts`, `true_fcr`, `checkpoint_shift`, `n_simulations`, `seed`. No field has a code default. Each simulation draws one rate per checkpoint, `true_fcr` plus that checkpoint's shift, clipped to `(0, 1)`, and then independent Bernoulli prompt rows. The block estimator's empirical coverage of `true_fcr` must lie within `coverage_tolerance` of `1 - gamma`. The same draws scored with `draw_rows` must fall short of `1 - gamma`. The test fails if the row method also lands inside the tolerance.

**Rationale**: FV-STAT-009 is a sensitivity check. Hardcoding the simulation size would be a new study parameter. A shared checkpoint rate is what makes a prompt-row interval under-cover.

**Alternatives considered**:

- Skip the simulation until D-57 is closed on the study file. Rejected: the hook is how the requirement is checked, and the fixture is allowed to close the row.
- Use a constant rate with no checkpoint shift. Rejected: the row resample would then cover about as well as the block resample, and the sensitivity check would not fail.

---

## Decision 9: Harness and control rows gain the fields the ledger requires

**Decision**: `CheckpointRow` and the control `LedgerRow` gain `family`, `implementation_id`, `git_commit`, `dirty`, `tokens`, `scored_candidates`, and `exports`. `run_job` and `build_control` take required keywords `git_commit: str` and `dirty: bool`. There is no default and no git subprocess. Tests pass `git_commit="fixture"` and `dirty=False`. Training commits pass `tokens=0`, `scored_candidates=0`, and `exports=0` because a training attempt does not score candidates or write an export. Those keys are present. Control commits do the same. `SqliteLedger` implements `LedgerPort.commit_checkpoint` and `ControlLedgerPort.commit` by validating the full row, including D-56, then inserting. In-memory test doubles keep accepting the objects they are given; the spec checks run against `SqliteLedger`.

`MatchLedgerPort` is unchanged. Matching tests keep `MemoryMatchLedger`.

**Rationale**: A ledger that the harness cannot fill will not be standing when the first checkpoint is trained. Zero token counts are measured absences on a training row, not defaults invented inside the ledger.

**Alternatives considered**:

- Leave `run_job` unchanged and require a manual CLI add after training. Rejected: the execution plan's failure mode is provenance added after the fact, and the port is already the commit path.
- Make the new fields optional on the dataclass. Rejected: an optional git commit is the empty field FV-LEDG-002 rejects.
