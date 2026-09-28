# Research: P1 Exclusion Gate and Entity-Disjoint Splits

**Feature**: 20260929-100819-exclusion-gate-splits
**Date**: 2026-09-29

Design notes were read from disk. Obsidian MCP was unavailable. FV-DATA-P1-2 and FV-DATA-P1-6 are `status: draft`. FV-DATA-P1-SIGNOFF is `status: in-progress`. The execution plan is `status: planned`.

---

## D-65 — Guessing baseline

**Decision**: Random-choice baseline fixed at **0.5**. Within one direction, accuracy is the fraction of that direction's probe cells scored correct. A fact is `excluded_known` when **any** direction is **greater than** 0.5. Accuracy of 0.5 or below in every complete direction is `pass`. A missing cell makes the fact `incomplete`.

**Rationale**: Owner choice Q1: A, matching the sign-off example under "Blocking decisions to resolve". The value is stored on the closed D-65 row, not in code.

**Alternatives considered**:
- Relation-marginal majority (P1-2 note, §5): rejected by Q1.
- Random subject-name control (P1-2 note, §5): rejected by Q1.

---

## Decoding seeds and generation settings

**Decision**: The closed D-65 row declares `decoding_seeds: [0]` and greedy decoding (`do_sample: false`, `max_new_tokens: 16`). The gate probes every seed in that list. An empty list refuses the run.

**Rationale**: P1-2 says "every declared decoding seed". No seed list exists in `.factverify/spec/`. One greedy seed makes the exclusion check deterministic and keeps a one-token lucky sample from counting as knowledge. `max_new_tokens` covers a short alias or a yes/no. Both numbers live on the decision row.

**Alternatives considered**:
- Several sampled seeds: not declared anywhere, and sampling would make "already knows" depend on a draw.
- Reading seeds from `attacks.yaml`: that file has no seed list.

---

## What a probe cell is

**Decision**: A cell is one class **E** template whose `relation_applicability` contains the fact's relation label, instantiated with the contract's subject and object labels, under one declared seed. Direction is the template's `primary_family`. Class I templates are written to `inference_probes` and are excluded from accuracy. Templates with non-empty `extra_premises` are not equivalence probes.

**Rationale**: Constitution I2. P1-2's grid is "(direction, template, seed)". `primary_family` is the closure file's direction (`direct`, `inverse`, `cloze`, `paraphrase`, `multilingual`, `verification`).

**Alternatives considered**:
- Using `equivalent_directions.statement_pattern` on the contract: those strings are not the frozen closure, and they would bypass a missing-template failure.
- Pooling class I into the same accuracy: forbidden by I2.

---

## Cell correctness

**Decision**: Scorer name `alias_contains`, selected by the D-65 field `cell_score`. An unknown or blank name refuses the run.

- `answer_role` `subject` or `object`: the cell is correct when the casefolded, whitespace-collapsed completion contains an English alias of that role from the contract.
- `answer_role` `truth_value`: the cell is correct when `oracle_label: true` and the completion contains `yes` or `true`, or `oracle_label: false` and it contains `no` or `false`. A verification template without `oracle_label` is a missing cell.

**Rationale**: Witness-rule Layer 1 asks whether the response recovers the contracted answer. Alias policy D-39 is still open on the witness artifact; the Block 0 bundle plan already limited checks to contract-declared English aliases. Naming the scorer on D-65 keeps it out of the frozen spec and out of a silent constant. D-40's evaluator normalization stays open and is not copied here.

**Alternatives considered**:
- Waiting for D-40 before any gate run: the exclusion gate would not start, and Block 0 cannot reach splits.
- Exact full-string equality: greedy completions add extra words; containment matches the witness question ("does this response recover the answer").

---

## Closure coverage for D-63 relations

**Decision**: The gate does not add templates. If a fact's relation has no applicable class E template, the fact's verdict is `incomplete` with reason `no_applicable_templates`. The current `.factverify/spec/closure_templates.yaml` manifest is `capital_of` and `alma_mater`. TOFU relations occupation, birthplace, nationality, and genre therefore come out `incomplete` on a real run until a spec amendment adds those templates.

**Rationale**: The spec for this feature forbids editing the frozen specification. An empty grid must not become `pass` (FV-DATA-014). Tests supply a fixture closure file that does contain the four relations.

**Alternatives considered**:
- Inventing templates inside the script: that hides the missing spec from the report.
- Amending `closure_templates.yaml` in this feature: out of scope, and it needs a new spec tag.

---

## Model binding and cache

**Decision**: The gate loads role `blocks_0_2` through `src.models.load_model`. It refuses when `LoadedModel.identity_hash` differs from `compute_identity_hash` of that role with no adapter. Completions go through `src.cache.store.get_or_compute`. `from_pretrained` and `.generate(` stay in `src/models/`. The gate does not call `Accountant.query`.

**Rationale**: FV-DATA-013. P2-0 is the only loader. P1-2 constraint C-1 says generations are served from the cache. I4 applies to the three evaluator arms; this probe is data preparation. Cache keying still requires a closed D-60 file, supplied by the caller. An open D-60 refuses the run.

**Alternatives considered**:
- Charging the evaluator accountant: would mix a pre-study filter into B_e.
- Calling `from_pretrained` in the script: banned by the loader test.

---

## Contamination alarm

**Decision**: `excluded_fraction = excluded_known / candidate_count`, where candidates are every fact in the input file. The trigger is the D-65 field `contamination_trigger: 0.10`, taken from the execution-plan risk register ("fails for >10% of candidates"). Above the trigger, `scripts/build_bundles.py --gate-report` refuses unless the decisions file contains `contamination_decision` of `regenerate`, `switch_model`, or `proceed` plus a non-empty `note`. The gate report always records the fraction and whether the alarm fired.

**Rationale**: FV-DATA-017. The 10% figure is already in the plan; putting it on the decision row avoids a literal in code. Existing bundle tests omit `--gate-report` and keep today's draft-contract behavior. Study commands pass the flag.

**Alternatives considered**:
- Hard-coding 0.10: violates "no magic numbers".
- Treating `incomplete` as excluded: the risk register counts facts the model already knows, not missing templates.

---

## Where verdicts are stored

**Decision**: Verdicts live in `results/exclusion_gate.jsonl` and `reports/exclusion_gate.md`. `facts.jsonl` is not rewritten.

**Rationale**: The contracts are adjudicated inputs. A rerun can replace the report without editing lineage. Eligibility reads the report by `fact_id`.

**Alternatives considered**:
- Writing `gate_result` back into each contract: the sign-off checklist says "mark excluded_known", but a second copy inside `facts.jsonl` drifts from the report. The report is the mark.

---

## D-68 — Block 0 counts and balance

**Decision**: Closed row: construction **8**, calibration **8**, `assign_final_test: false`, relations `[occupation, birthplace, nationality, genre]`. Each of those two splits must contain at least one fact of each relation. Eligible authors not selected are `unassigned`. No entity is labeled `final_test`.

**Rationale**: Owner choice Q2: A, and the execution plan Phase 3 header. Block 1 sizes stay with P4-1.

**Alternatives considered**:
- Assigning the remainder to final-test (Q2: B): rejected.
- A numeric slack tolerance: Q2: A requires each relation to be present, which is a minimum of one, not a band.

---

## Who counts as an author

**Decision**: An author is an entity id that appears as `triple.subject.id` on at least one eligible fact. Facts are grouped by subject author. If a fact's object id is also an author, that fact's subject and object authors must receive the same split; otherwise validation fails and no file is written. Objects that are never subjects (occupation names, cities) are not authors.

**Rationale**: FV-DATA-035. TOFU objects in the current file are not fictional authors. The object-author check still runs.

**Alternatives considered**:
- Treating every object as an author: would put "writer" and "Lagos" into splits and make disjointness meaningless.

---

## Assignment algorithm

**Decision**: Pack whole author groups. Sort author ids, shuffle with `random.Random(seed)`, and search that order for the first placement of groups into construction then calibration that hits both fact counts and the four-relation rule. The same facts and seed always yield the same digest. If no placement exists, print the relation counts and leave any previous `splits.json` untouched.

**Rationale**: FV-DATA-036 and FV-DATA-037. Fact counts are 8 and 8, so an author with several facts consumes several slots and is never split across files.

**Alternatives considered**:
- Assigning facts independently of author: violates entity disjointness.
- Shrinking a split when fewer than 16 facts qualify: forbidden.

---

## Eligibility

**Decision**: A fact is eligible when the gate report verdict is `pass` and every entailment-audit row for that `fact_id` is `clean`. A missing audit file, a missing verdict, `excluded_known`, or `incomplete` makes the fact ineligible. Zero non-clean rows and at least one clean row are required, so an unaudited fact cannot pass by absence.

**Rationale**: FV-DATA-P1-6 interface: pass verdict and a clean P1-4 audit. The audit output is `results/entailment_audit.jsonl` with verdicts `duplicate | entails | clue_bearing | clean`.

**Alternatives considered**:
- Treating a missing audit as clean: would assign facts the audit has not seen.

---

## Ledger row for the split file

**Decision**: Add append-only table `study_artifacts` while `schema_version` stays `"1"`. One row stores kind `split_assignment`, seed, digest, config hash, spec tag, git commit, dirty flag, and cost. `add_study_artifact` is the only writer.

**Rationale**: FV-DATA-037. `ensure_schema` raises when the meta version is not `1`, so a version bump would refuse existing ledgers. `CREATE TABLE IF NOT EXISTS` adds the table on next open. A checkpoint row cannot represent one file that covers many facts.

**Alternatives considered**:
- Schema version `2`: current `open_ledger` has no migration path.
- Putting the digest only in `splits.json`: the requirement says the ledger records it too. The JSON still carries the digest; the ledger row is the audit copy.

---

## Final-test guard

**Decision**: `load_split(path, split, role)` returns facts for `construction` and `calibration` regardless of role. For `final_test`, role must be `final_test_pass`. Any other role raises and appends a JSON line to the caller-supplied access log (default `results/split_access.jsonl`). This Block 0 file has no final-test facts, so a final-test request against it raises even for `final_test_pass`, with reason `empty_split`. The role check is still tested with a fixture file that does contain final-test facts.

**Rationale**: FV-DATA-039. Logging refusals in the access log avoids inserting a fake final-test incident into `incidents`, which is for a numbered final pass.

**Alternatives considered**:
- An `incidents` row with `references_pass_number: 0`: that table is the P4-5 incident record, not an access log.

---

## Training and bundle hooks

**Decision**: `src.train.run._precheck` calls `require_pass(fact_id, gate_report)` when the job config contains `gate_report`. A missing verdict, `excluded_known`, or `incomplete` raises before any update. Existing harness fixtures omit the key and stay valid. Study jobs set the key. `build_bundles.py --gate-report PATH` runs the contamination check and refuses facts in that report whose verdict is not `pass`.

**Rationale**: FV-DATA-018 and FV-DATA-017. Unconditional enforcement would break harness fixtures that predate the gate. The study path is the path that sets the flag.

**Alternatives considered**:
- Requiring `gate_report` on every historical fixture: large unrelated edit, and those fixtures are not Block 0 facts.
