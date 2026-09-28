# Research: FV-CTRL — P2-4 Behaviour-Matching Utility

**Feature**: `20260927-144624-behaviour-matching`  
**Date**: 2026-09-27  
**Source notes** (read from disk; Obsidian MCP unavailable):

- `FactVerify — Execution Plan` (status: planned) — "Phase 2 — Harness and run ledger", task P2-4; "Phase 3 — Block 0 · integrity pilot → GATE 1" (two reference seeds, criterion 1, do not loosen controls); "Phase 4 — Block 1" (at least three reference seeds); "Risk register", row "Controls too easy to reject"
- `Research Proposal — FactVerify (v3)` (status: draft) — "6.2 Cross-fitted split", "6.3 Oracle-labelled systems"
- `Fake-Unlearning Controls` (status: draft) — "How It Works", "Variants & Evolution"
- `FactVerify — Phase 0 Build Handbook (Freeze Spec)` (status: draft) — I6, I8, "5.6 Verdict vocabulary"
- `FV-CTRL — P2-4` (status: draft) — requirements 011–017; decisions D-54, D-58, D-59, D-53
- Existing code: `src/controls/decisions.py` allows D-53, D-54, D-55, D-61. `check_retention` reads only `max_abs_gap`. `load_config` rejects unknown keys. `build_control` copies `severity` and does not search it. `src/train/cost.py` `CostRecord` and `src/train/config.py` `hash_mapping` already exist. `src/eval/gateway.py` is the only module that charges `src/eval/budget.py`.

No technical-context item is left as NEEDS CLARIFICATION. The four study decisions above are deliberately unresolved.

---

## Decision 1: Matching is a separate document and does not rebuild the control

**Decision**: `match_control(config_path, *, spec_root, ledger, behavior)` loads a match YAML. It does not call `load_config` or `build_control`. P2-3's control document keeps a single stored `severity`. The match document carries an ordered `severity_search` list. Every entry is tried, including after one of them already falls inside the band. The function does not stop early and does not add severities the list does not contain.

The proposed keyword-only signature `match_control(control_config, reference_ids, *, spec_root, seed)` is folded into that document. `reference_ledger_ids` and `seed` are required fields, so they enter the config hash. A different seed is a different configuration identity even when the selected severity happens to be the same.

Forbidden keys, refused before measurement: `target_accuracy`, `target`, `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, `frr`, `budget`. A string value ending in `verdict.json` or `budget.json` also refuses. Unknown keys refuse.

`output_dir` must not sit inside `.factverify/`. A refusal raises `ControlError` and writes no `match.json`. A finished match, `matched` or `unmatched`, writes `output_dir/match.json`.

**Rationale**: FV-CTRL-011 refuses a literal target. FV-CTRL-016 requires a complete trajectory even when the range is exhausted. Putting the search on the P2-3 document would force every existing control build to carry a range, and `load_config` currently rejects unknown keys. Leaving the search out of `build_control` keeps P2-3's "severity is stored, not applied" rule intact.

**Alternatives considered**:

- Add `severity_search` to `ControlConfig` and ignore it during build. Rejected: one document would then mean two different contracts, and a build could silently accept a search range.
- Stop at the first severity inside the band. Rejected: the trajectory would be incomplete, and the ranking rule would depend on stopping.
- Pass references and seed only as function arguments. Rejected: they would not be part of the hashed configuration the record has to carry.

---

## Decision 2: D-54 match fields sit beside retention's gap, and only two summaries are interpreted

**Decision**: `DecisionRow` gains optional fields. `load_decisions` also accepts `D-58` and `D-59`. Missing ids stay open via `row_or_open`. Existing fixtures that omit the new ids still load. `check_retention` still reads only `status` and `max_abs_gap`. A row closed with `max_abs_gap` and no match fields still accepts or rejects a suppression build, and it still refuses a match.

Matching requires D-54 `status: closed` and all of these fields, otherwise it raises `ControlError("D-54")` before any measurement:

| Field | Interpreted values |
|-------|--------------------|
| `band_summary` | `min_max` or `mean` |
| `tolerance` | decimal string in `[0, 1]` |
| `boundary` | `inclusive` or `exclusive` |
| `selection_rule` | `closest_center` only |

Any other closed token raises `ControlError("D-54")`. The study record does not set these fields.

Computation, using `Decimal` on the port's accuracies:

- `min_max`: raw low and high are the minimum and maximum of the reference accuracies. The tolerance band is `[raw_low - tolerance, raw_high + tolerance]`. Center is the midpoint of the raw low and raw high.
- `mean`: center is the arithmetic mean. The tolerance band is `[center - tolerance, center + tolerance]`.

`inclusive` uses `low <= value <= high`. `exclusive` uses `low < value < high`. Ranking is smaller absolute distance to the center, then earlier index in `severity_search`. The first-ranked severity is the selected severity and, when it lies outside the band, the best achieved value on the unmatched record. Status is `matched` only when that selected accuracy lies inside the band. Later hard-dimension failures can still force `unmatched`.

**Rationale**: FV-CTRL-011 and FV-CTRL-012 say the summary, the tolerance, the boundary, and the choice among in-band severities are D-54's. The requirements note leaves the summary open (min–max versus a margin around the mean). Interpreting both names, and refusing every other name, lets a fixture close the row without making either summary the study default. P2-3 already used this pattern for `digest_tolerance`: only `"0"` is interpreted. Retention stays on `max_abs_gap` so a match tolerance is not silently reused as the disabled-mechanism gap.

**Alternatives considered**:

- Treat `max_abs_gap` as the match tolerance. Rejected: that field is the parent-retention gap from FV-CTRL-004, and the spec lists the match tolerance as its own D-54 field.
- Implement only `min_max`. Rejected: that would close the summary the requirements note still calls open.
- Pick the earliest in-band severity and, if none are in band, the closest. Rejected: that is a second rule. A closed record that does not say `closest_center` raises instead.

---

## Decision 3: Reference counts are the plan's two named blocks

**Decision**: `block` is required and is `block_0` or `block_1`. `block_0` requires two retain-only references. `block_1` requires at least three. Any other block name raises `ControlError("block")` before measurement. Duplicate ledger ids raise. Each id is looked up on `MatchLedgerPort`. The row must have `role == "reference"`, the same `fact_id` as the match, and `split` of `construction` or `calibration`. A missing row, a `final_test` split, or any other role raises `ControlError` naming the id. The control ledger id must resolve to `role == "control"` for the same fact and a non-final split. Accuracies are requested only after these checks pass.

The counts live in `match.py` as the two plan figures. They are not config fields and they are not written into `.factverify/spec/`.

**Rationale**: The spec cites Execution Plan Phase 3 (two reference seeds for the integrity pilot) and Phase 4 (at least three for Block 1). A caller-supplied minimum could be lowered after a short set failed to form a band. An unnamed block has no recorded count, so it refuses.

**Alternatives considered**:

- Always require two. Rejected: Block 1's plan count is at least three, and two references would start a Block 1 match the spec refuses.
- Read the counts from `margins.yaml`. Rejected: they are not fields there, and adding them would edit the frozen spec.

---

## Decision 4: D-58 authorizes a probe manifest; evaluation groups come from the spec root

**Decision**: Matching raises `ControlError("D-58")` before measurement when that row is missing or `open`. When it is `closed`, the match document's `probes` path is the manifest. Closing D-58 does not name the probes inside the decision row. The manifest is the declaration, and the closed status is what makes that declaration usable. A closed row with a missing or empty manifest raises `ControlError("probes")`.

Each probe has `probe_id`, `fact_id`, `template_group_id`, `split`, and `kind`. `kind` must be `direct_qa`. `fact_id` must equal the match fact. `split` must be `construction` or `calibration`.

`spec_root/closure_templates.yaml` must exist. Its `groups` list supplies `group_id` and `split`. A probe group absent from that list raises. A group whose split is `calibration` or `final_test` is an evaluation template group and raises `ControlError` naming the group. Construction groups are the groups a manifest may use. This package does not rewrite group assignments.

The behavior port is then called only with those probe ids. The match record's `reads` list is exactly the `(probe_id, system_id, output)` triples the port returns for the references (no severity) and for the control at each tried severity. A returned probe id outside the manifest raises. The record has no evaluator score or verdict field.

`match.py` must not import `src.eval.gateway` or `src.eval.budget`. A test reads the module source and fails if either import appears.

**Rationale**: FV-CTRL-013 forbids evaluation template groups, evaluator scores, and final-test facts. Handbook I6 (draft) makes the template group the split unit. Calibration groups are used to choose thresholds. Final-test groups are the held-out grade. Construction groups are the debug pool the pilot can hold apart from those two. The frozen `closure_templates.yaml` already stores `groups[].split`. Reading it does not edit it. D-58 stays the authorization switch so a construction group is not treated as the matching set while the decision is open.

**Alternatives considered**:

- Hardcode a probe list. Rejected: that closes D-58.
- Treat every group except `final_test` as eligible. Rejected: calibration groups are evaluation groups; matching on them tunes controls to the threshold split.
- Score probe text inside `match.py`. Rejected: the spec says this feature does not define a second accuracy formula. The port returns the accuracy. The record stores the outputs it read.

---

## Decision 5: Unmatched records are part of the pilot input, and nothing deletes them

**Decision**: `match.json` is written for `unmatched` with `family`, `best_value` (the selected accuracy), and `target_band` (`low`, `high`, `summary`). `pilot_inputs(records)` returns one row per record, including unmatched. `reject_dropped(source, reported)` raises `ControlError("unmatched")` when any source record with status `unmatched` is absent from `reported`, or when its family, best value, or band differs. There is no filter helper that drops unmatched records. The tolerance written on the record is the D-54 tolerance string. No function edits that string after the measurements.

**Rationale**: FV-CTRL-014 and handbook 5.6 (draft) forbid dropping a hard control after seeing it. Gate 1's failure action is to report the failure, not to loosen the control. The P3-2 report itself is out of scope; the check is that the inputs that report would read still contain the unmatched row.

**Alternatives considered**:

- Write unmatched results only to a log and skip `match.json`. Rejected: that is the skip the requirement forbids.
- Widen `tolerance` until the best try fits. Rejected: that loosens the control to pass Gate 1.

---

## Decision 6: Hard dimensions are checked on the selected severity, and a waiver is a recorded reason

**Decision**: `hard` defaults to false when the key is absent. A control that is not tagged `hard` does not read D-59.

A `hard: true` match raises `ControlError("D-59")` before measurement when D-59 is missing or `open` and `waiver` is absent or empty. When D-59 is `open` and `waiver` is a non-empty string, the match proceeds on accuracy only, the record stores `hard_check: waived` and `waiver_reason`, and FV-CTRL-015 is not treated as implemented.

When D-59 is `closed`, `dimensions` must be a non-empty list. Each item has `name`, `tolerance` (decimal string in `[0, 1]`), and `boundary` (`inclusive` or `exclusive`). The names are the record's names. Source does not contain a required list of refusal rate, fluency, or utility. An empty list, a missing field, or an unknown boundary raises `ControlError("D-59")`. A closed row that also sets `waiver` raises `ControlError("D-59")`, so a waiver cannot sit on top of a real check.

After the accuracy ranking, the port's `dimension_value` is called for the selected severity only, once per dimension, in list order. A value inside that dimension's tolerance is stored. The first failure in list order sets status to `unmatched` and `failed_dimension` to that name. Later dimensions are still measured and stored. The accuracy trajectory is kept either way.

**Rationale**: FV-CTRL-015 is a `should`. The spec allows a recorded waiver and forbids inventing the metrics. Checking only the severity D-54 already selected avoids a second search the decision record does not describe. The proposal's examples become required only when a closed D-59 row lists those names.

**Alternatives considered**:

- Search for a severity that passes accuracy and every dimension. Rejected: that replaces the D-54 ranking with an unrecorded joint rule.
- Hardcode refusal rate, fluency, and utility. Rejected: that closes D-59.
- Treat an open D-59 as "not hard". Rejected: the tag would then disappear without a recorded reason.

---

## Decision 7: Cost is the existing CostRecord, and the seed does not reshuffle the search

**Decision**: After validation, `CostRecord.start()` runs, the port is called, then `CostRecord.finish(0, 0)`. The match record copies `wall_clock_seconds`, `gpu_hours`, and `peak_memory_bytes`. On CPU fixtures those GPU fields are zero, which is a recorded value. A refusal before measurement does not write the record. Matching never calls `Accountant.query` or `Gateway.complete`.

The search order is the declared list order. The seed is stored and hashed. It is not used to break ties or to sample probes. `compare_matches(left, right, decisions)` raises `ControlError("D-53")` when D-53 is missing, open, or closed with a `digest_tolerance` other than `"0"`. When the tolerance is `"0"`, the selected severity and the status must be equal. Wall-clock is not compared. The match function itself still writes a record when D-53 is open.

**Rationale**: FV-CTRL-016 asks for the trajectory and the cost vector, reported apart from evaluator budgets. `CostRecord` is already the harness definition of that vector. FV-CTRL-017 asks for the same selected severity and status under the D-53 policy. P2-3's `compare_builds` already refuses every tolerance except `"0"`. A pure function of the port's numbers and the declared order meets that identity without inventing a distance for a non-zero tolerance. Two different seeds may select the same severity; they still hash differently, and each record stores its own seed.

**Alternatives considered**:

- Charge matching through the reference-cost policy in `attacks.yaml`. Rejected: that policy is for reference-model evaluation inside the accountant, and the frozen file has no `discovery_and_calibration_cost` field. Adding one would edit the spec. Separation here is "not charged".
- Shuffle the severity list with the seed. Rejected: the declared order would stop being the order that was tried, and a non-zero D-53 tolerance would be needed to compare runs.
- Skip `compare_matches` and always assert byte-identical records, including wall-clock. Rejected: wall-clock differs by measurement, and the spec compares severity and status.

---

## Decision 8: The behavior port and the ledger port stay scriptable

**Decision**:

```text
MatchLedgerPort.get(ledger_id) -> SystemView | None
SystemView: ledger_id, role, fact_id, split

MatchBehaviorPort.direct_qa_accuracy(system_id, fact_id, probe_ids, severity) -> Measurement
Measurement: accuracy: float, outputs: tuple[ProbeOutput, ...]
ProbeOutput: probe_id, system_id, output

MatchBehaviorPort.dimension_value(system_id, fact_id, name, severity) -> float
```

`severity` is `None` for a reference. For the control it is the declared entry, passed through as a string. Tests script both ports. No GPU scorer and no weight load live in this package.

Config identity is `hash_mapping` of the raw YAML mapping, the same canonical JSON the harness uses. The record stores that hash, the seed, the split, `spec_revision`, `control_ledger_id`, and the reference ids in the order given.

**Rationale**: P2-3 already tests retention through a scripted `BehaviorPort` so the hooks do not download weights. Matching needs reference rows as well as parent rows, and `ParentView` has no split, so a separate read port carries the fields FR-001 checks. Reusing `hash_mapping` keeps one digest construction in the study.

**Alternatives considered**:

- Extend `ControlLedgerPort.get_parent` with a split field. Rejected: that changes the P2-3 port for a lookup this feature uses on references and controls, not only parents.
- Recompute accuracy from stored output text. Rejected: Decision 4. The port owns the accuracy number.
