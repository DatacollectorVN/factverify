# Research: FV-EVAL — P2-2 Evaluators and Query-Budget Accountant

**Feature**: `20260927-120701-evaluators-query-budget`  
**Date**: 2026-09-27  
**Source notes** (read from disk; Obsidian MCP unavailable):

- `FactVerify — Execution Plan` (status: planned) — "Phase 2 — Harness and run ledger", task P2-2
- `FactVerify — Phase 0 Build Handbook (Freeze Spec)` (status: draft) — "2. The eight invariants" (I2–I5, I8); "6.4 One query needs a definition"; "6.5 Budget arithmetic"; "6.6 Adaptive attacks"
- `FV-EVAL — P2-2` (status: draft) — requirements 001–014; decisions D-14, D-17, D-18, D-20, D-21, D-22, D-26, D-27
- Frozen artifacts already in the repo: `.factverify/spec/attacks.yaml`, `access_profile.md`, `witness_rule.md`, `closure_templates.yaml`, `margins.yaml`

No technical-context item is left as NEEDS CLARIFICATION. The eight study decisions above are deliberately unresolved.

---

## Decision 1: Replace the integer accountant

**Decision**: Delete `BudgetAccountant(budget_per_fact=...)` and `request(evaluator, fact_id, channel, prompt_hash)`. Replace `tests/test_budget.py` with `tests/test_eval.py`. The new `Accountant` is constructed from a loaded attack specification, one case, and one arm. Its only charging method is `query(channel, request)`.

**Rationale**: Handbook I4 ("2. The eight invariants", draft): equal budget is an accounting contract, not a call count. The stub charges one integer per evaluator per fact and ignores channel allocations, confirmation, cache, and the cost vector. Leaving it importable would be a bypass of FV-EVAL-001.

**Alternatives considered**:

- Keep the stub for old tests and add a second class. Rejected: two accountants, and the stub still accepts uncharged-by-channel calls.
- Teach the stub to read `common_cap`. Rejected: `common_cap: 12` in the demo artifact is not a closed D-17 value.

---

## Decision 2: Study runs refuse open decisions; fixtures close them

**Decision**: On start, load `blocking_decisions` from `attacks.yaml`, `access_profile.md`, and `witness_rule.md`. If a decision in the table below has `status: open`, refuse before the first model call and name the id. A missing, null, or `DECISION_REQUIRED` field also refuses (I8).

| Operation | Decisions that must be `closed` in the loaded spec |
|-----------|-----------------------------------------------------|
| Any study start that will charge generations | D-17, D-22 |
| Candidate scoring | D-18 |
| Cache hit or retry | D-20 |
| Transport failure or discard | D-21 |
| Confirmation versus discovery | D-26 |
| Logit, rank, or activation channel | D-27 |
| Case verdict | D-14 |

Hooks copy a spec root under `tests/fixtures/eval/` and set only the rows that hook needs to `closed`, with an explicit field value. The frozen `.factverify/spec/` is not edited. One hook points at the real spec root and asserts the refusal names the open ids.

**Rationale**: FV-EVAL section 5: no requirement reaches implemented while its decision is open, and the code builds against the spec field. The demo `attacks.yaml` already contains totals and charge rules and also lists those decisions as `open`. Treating the demo numbers as the study policy would close D-17 and D-22 by stealth.

**Alternatives considered**:

- Ignore `blocking_decisions` whenever a numeric field is filled. Rejected: the demo file is in that state today.
- Refuse every run, including fixtures, while the frozen file is open. Rejected: the hooks could not show that equal totals proceed and unequal totals refuse.

---

## Decision 3: Charge only the vocabulary already in `attacks.yaml`

**Decision**: Interpret these fields and no others:

- `accounting.generation_trial_unit.multiplicity_rule` — one completion is one generation trial. A request with `n` prompts and `k` samples charges `n * k` trials to the named channel.
- `accounting.candidate_scoring_unit` — one scored sequence is one scoring operation, recorded on the scored-candidate line. It does not increment generation trials unless that unit's field says so. While D-18 is open the scoring call is refused (Decision 2).
- `accounting.cache_policy`, `retry_policy`, `failure_policy`, `discard_policy` — `charge_rule` is one of `charged`, `zero_new_compute`, `separately_reported`. Any other token refuses.
- `observation_charged: true` consumes channel allocation. `observation_charged: false` records an attempt and does not count a usable observation.
- `charge_rule: zero_new_compute` leaves the new-compute counter unchanged.
- `charge_rule: separately_reported` writes the reference line and does not consume the arm's channel allocation.

Arm start also checks internal consistency: the sum of `channel_allocations[].trials` equals `arm.total`, and every arm total equals `common_cap` when `common_cap` is present. A mismatch refuses even in a fixture. Equality across arms is the FV-EVAL-003 check, and it runs only after D-22 is closed in that spec root.

**Rationale**: Handbook §6.4 (draft) defines a response trial as one prompt, one checkpoint, one decoding configuration, one completion, and gives candidate scoring its own unit. The frozen file already states the multiplicity rule and the charge-rule tokens. Inventing a parallel vocabulary would drift from P0-3.

**Alternatives considered**:

- Charge one request as one trial regardless of `k`. Rejected: contradicts `multiplicity_rule` and FV-EVAL-001.
- Map cache hits to "free" for both compute and allocation. Rejected: `observation_charged: true` on the demo cache policy, and an uncharged observation lets one arm reuse what another arm pays for.

---

## Decision 4: Confirmation is its own channel line

**Decision**: The channel id `confirmation` has its own remaining allocation, taken from that arm's `channel_allocations`. Discovery channels (`prompt_variation`, `repeated_sampling`, `locality`, and any other id) cannot draw on that remainder. A discovery request that asks to spend confirmation allowance is refused unless `accounting.unused_confirmation_reallocation` is the boolean `true`. The frozen file does not contain that key today, so a real spec root hits Decision 2 via D-26. Fixtures set the key explicitly. Unused confirmation trials stay on the budget record as remaining allowance.

**Rationale**: Handbook §6.6 (draft): do not transfer unused confirmation calls unless the reallocation policy was frozen. FV-EVAL-005: charges go to `confirmation` and stop at its cap.

**Alternatives considered**:

- Treat a missing key as `false` and allow study runs. Rejected: that chooses "never reallocate" while D-26 is open.
- Pool all channels into `arm.total`. Rejected: a discovery call could then spend the confirmation reserve.

---

## Decision 5: One gateway, two ports

**Decision**: Evaluators call `gateway.complete` and `gateway.score`. `gateway.py` is the only module under `src/eval/` that may call `ModelPort.complete`, `ModelPort.score_candidate`, or `CachePort.get` / `CachePort.put`. It calls `Accountant.query` first. An AST test walks `src/eval/` and fails naming the file and line of any other `generate`, `from_pretrained`, or `ModelPort` call.

`ModelPort` is a protocol. The study adapter loads the checkpoint with `load_model` and does not live in the hook path. Tests pass a scripted port.

`CachePort.get` returns a stored completion or misses. On a hit the gateway charges `cache_policy` and does not call the model. On a miss it checks remaining capacity, calls the model, and charges a generation only when a completion returns. A transport failure charges the failure policy and does not also charge a generation trial. P2-7 owns durable cache storage. This feature does not change `src/cache/store.py`. Tests use a dict port. `tests/test_cache.py` stays as it is.

**Rationale**: FV-EVAL-001's second criterion is a check that names the bypass. FV-EVAL-006 charges cache hits as the policy table says. Constitution: `from_pretrained` stays in `src/models/`.

**Alternatives considered**:

- Let each evaluator charge and then call the model. Rejected: the bypass check would have many legal call sites.
- Route study runs through the current `GenerationCache` sqlite file. Rejected: that stub has no policy hook, and FV-CACHE has not specified durability, identity, or invalidation yet.

---

## Decision 6: Probe class comes from the closure file, not from the caller alone

**Decision**: Resolve every probe id against `closure_templates.yaml`.

- Listed with `extra_premises` non-empty, or class `I`: inference. Refused for the primary equivalence score. Copied to the inference output.
- Listed with class `E` or `R`: equivalence or locality template. Legal for semantic-only and FactVerify only when `groups[].split` equals the case split (`construction`, `calibration`, or `final_test`).
- Listed with class `X`: refused for the primary score.
- A native-arm probe must have `probe_class: native` on the case and must not resolve in the closure file. If it resolves, the native arm refuses it even when the case also says `native`.

The case split token is the closure-file token `final_test`. Hyphenated `final-test` is normalized to that token on input. Unknown split tokens refuse.

**Rationale**: Handbook I2 and I6 (draft). FV-EVAL-008 and FV-EVAL-009. Group split, not the template string, is the hold-out unit already stored on `groups[].split`.

**Alternatives considered**:

- Trust the runner's `probe_class` without looking up the id. Rejected: a closure id labeled native would enter the native arm.
- Treat every non-closure string as a native probe for every arm. Rejected: semantic arms would then accept undeclared prompts.

---

## Decision 7: Score metrics follow the access profile

**Decision**: ROUGE-L is computed in-process from the completion and the contracted answer on the case. BERTScore is a `MetricPort` call so hooks return a fixture number and do not download a model. Truth Ratio, answer probability, and answer rank are `gateway.score` calls. `channels.py` refuses a score or activation request when the loaded profile has `capabilities.scores`, `capabilities.candidate_scoring`, or `capabilities.internals` set to `unavailable`, or when the channel's `capability_requirements` include `raw_scores` or `weight_update` and the profile does not grant them.

The hook for FV-EVAL-008 uses a fixture profile with `scores: verified` and D-27 `closed`, and asserts all five numbers. A second assertion uses Profile A's unavailable scores and expects the three score metrics to be refused. The native arm does not fill those three with a substitute.

**Rationale**: The frozen access profile is Profile A: text verified, scores and internals unavailable (handbook I3, draft). FV-EVAL-007 forbids a logit channel under that profile. FV-EVAL-008 still requires the five native metrics when the profile allows them. One code path serves both.

**Alternatives considered**:

- Always compute answer probability from token ids inside the native arm. Rejected: Profile A does not grant scores, and the call would bypass the access gate.
- Drop Truth Ratio, probability, and rank from the native arm. Rejected: FV-EVAL-008 names them.

---

## Decision 8: Four public statuses, spec codes underneath

**Decision**: The verdict field `status` is exactly one of the FV-EVAL-010 phrases. `status_code` stores the witness-rule token. The map is fixed:

| `status` | `status_code` |
|----------|----------------|
| confirmed recovery witness | `confirmed_recovery` |
| conformant under the declared test | `conformance` |
| non-identifiable under this profile | `non_identifiable` |
| insufficient evidence/incomplete | `incomplete` |

`witness_rule.md` `case_decision.status_alignment.mapping` already sends `accept` to `conformance` and keeps the other three tokens. `no_witness_is_not_accept: true` is honored: missing a witness does not become conformance. Conformance requires every entry in `acceptance_requires` to hold. A case field `identifiability: structurally_indistinguishable` forces `non_identifiable` and does not emit accept or reject. The evaluator does not infer that flag; a missing flag refuses. P2-3 sets it when it builds controls.

A single probe that crosses its bound with no successful enabled confirmation route yields a status other than confirmed recovery witness. The raw maximum is stored on `diagnostics.raw_maximum`. `aggregation_policy.raw_maximum_role` must be `diagnostic_only`; any other value refuses.

Channel scores are a list of `{channel_id, score, bound}`. The verdict schema has no average field. The emit function refuses a payload that contains one.

**Rationale**: FV-EVAL-010, FV-EVAL-011, FV-EVAL-013. Handbook I5 (draft). The witness-rule frontmatter is the decision layer (P0-6); this package applies it and does not restate the rubric.

**Alternatives considered**:

- Emit only the short spec tokens. Rejected: the requirement's acceptance text is the four phrases, and FV-STAT would then see a second vocabulary.
- Detect output-indistinguishable controls inside the evaluator. Rejected: that is a control property from P2-3, and guessing it would be a result-dependent rule.

---

## Decision 9: Final-test thresholds match the git tag blob

**Decision**: When `case.split` is `final_test`, load `results/thresholds.json` and refuse if any of these fail: the tag `thresholds-v1` is missing; the working-tree file's SHA-256 differs from the blob `thresholds-v1:results/thresholds.json`; the caller also passed a bounds object. The verdict records `thresholds_tag: thresholds-v1`. Construction and calibration do not call this loader. They accept an explicit bounds object labeled with that split, and a bounds object labeled `final_test` is refused outside this loader.

The git read is a `ThresholdsSource` protocol. The default implementation runs `git rev-parse` and `git show`. Tests use a fake source so hooks do not need a tag. Passing threshold numbers as `evaluate_case` keyword arguments on a final-test case raises.

**Rationale**: FV-EVAL-012. Constitution principle 3: the final-test pass uses frozen thresholds. `margins.yaml` is still `unresolved_worksheet` and is not a thresholds file. P4-3 writes `results/thresholds.json` and the tag; this package only checks them.

**Alternatives considered**:

- Trust a digest field inside the JSON alone. Rejected: editing the file and its digest together would still look valid.
- Block calibration until the tag exists. Rejected: P3-4 and P4-3 run before `thresholds-v1`.

---

## Decision 10: Raw JSONL outside the spec namespace

**Decision**: `store.py` appends one JSON object per charged generation that produced a completion (`observation_charged` and a completion body). The record holds case id, checkpoint ledger id, fact id, split, arm, channel, probe id, prompt, completion, decoding parameters, and seed. On finish, the line count must equal that charged-generation count. The resolved directory is refused when it is `.factverify` or a path inside it. Replay reads those lines back and does not call `ModelPort`. The same case, seed, and lines produce the same verdict and scores because scoring uses only those lines and the declared bounds.

Transport failures with `observation_charged: false` are on the budget record and are not raw completions.

**Rationale**: FV-EVAL-014 and handbook I8 (draft): the leading-dot spec namespace is dropped by archives. Replay is the determinism check (constraint C-1).

**Alternatives considered**:

- Store raw text in the generation-cache sqlite stub. Rejected: that path is under the repo cache, not an audit export, and P2-7 owns it.
- Write raw text beside the spec. Rejected: FV-EVAL-014 forbids a write under `.factverify/`.
