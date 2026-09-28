# Research: FV-CTRL — P2-3 Fake-Unlearning Controls

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27  
**Source notes** (read from disk; Obsidian MCP unavailable):

- `FactVerify — Execution Plan` (status: planned) — "Phase 2 — Harness and run ledger", task P2-3; "Phase 3 — Block 0 · integrity pilot → GATE 1"
- `Fake-Unlearning Controls` (status: draft) — "Definition", "How It Works"
- `FactVerify — Phase 0 Build Handbook (Freeze Spec)` (status: draft) — "5.1 Where the boundary sits", "5.2 The identifiability argument, stated precisely"
- `FV-CTRL — P2-3` (status: draft) — requirements 001–010; decisions D-53, D-54, D-55, D-61
- `FV-CTRL — P2-4` (status: draft) — behaviour matching owns severity search and the reference-band target; not this feature
- `FV-HARN — P2-1` research, Decision 7 — `digest_tolerance` `0` is exact equality; a non-zero tolerance is not given a metric while D-53 is open
- Frozen artifacts already in the repo: `.factverify/spec/access_profile.md` (profile A, text only), `margins.yaml` (`locality_margins.*.margin.value` is null), `fact_contract.schema.json`
- Existing code: `src/controls/__init__.py` is empty. `src/eval/gateway.py` is the only eval module that calls a `ModelPort`. `src/train/ledger.py` is a port with no SQLite. `src/train/config.py` already restricts role `finetuned` to method `finetune`.

No technical-context item is left as NEEDS CLARIFICATION. The four study decisions above are deliberately unresolved.

---

## Decision 1: One registered implementation per family; severity is stored, not applied

**Decision**: The registry contains exactly these implementation ids, one per family:

| Family token | Spec phrase | Implementation id | Mechanism layer |
|--------------|-------------|-------------------|-----------------|
| `refusal` | refusal | `refusal.serving` | `prompt/serving` |
| `output_filter` | output filter | `output_filter.postprocess` | `output post-processing` |
| `answer_replacement` | answer replacement | `answer_replacement.postprocess` | `output post-processing` |
| `logit_masking` | logit masking | `logit_masking.suppress_tokens` | `logits` |
| `template_specific` | template-specific suppression | `template_specific.group_suppress` | `prompt/serving` |
| `reversible_steering` | reversible steering | `reversible_steering.vector` | `activations` |
| `targeted_damage` | targeted damage | `targeted_damage.local` | `weights` |
| `broad_destruction` | broad destruction | `broad_destruction.global` | `weights` |
| `untouched` | untouched model | `untouched.parent` | not assigned in code |

An unknown family or implementation id refuses. A second id is not added in this feature. `severity` is a required config value (string, number, or mapping). It is copied onto the label and into the config hash. No branch in `src/controls/` reads it to change behavior.

`certify_coverage(decisions)` returns success only when D-55 is `closed` and its `min_count` is less than or equal to the registered count (1). While D-55 is `open`, certification raises and names D-55. `list_catalog()` still returns the nine families and the one id each. A Block 1 configuration that names a family token absent from the registry raises and names that token.

**Rationale**: FV-CTRL-001 requires at least one implementation, and the spec forbids inventing the variants D-55 has not recorded. P2-4 is the severity search. Applying severity here would close D-55 and start behaviour matching inside P2-3.

**Alternatives considered**:

- Ship three severities per family. Rejected: that is an unrecorded D-55 choice.
- Leave the registry empty until D-55 closes. Rejected: the spec's floor is one implementation, and the hooks have to show that a missing family refuses.
- Let the config invent a new implementation id. Rejected: split disjointness would then be caller-defined.

---

## Decision 2: The untouched model is listed and is not buildable while D-61 is open

**Decision**: `untouched` is in the required family list. `build_control` for `untouched.parent` raises and names D-61 until the decision record has `status: closed` and a `mechanism_layer` that is one of the five allowed layers. The layer is read from that record. It is not defaulted to `weights`. When the record is closed, the build publishes a label whose artifact pointer is the parent checkpoint. It does not copy weights and it does not add a wrapper.

**Rationale**: The requirements note records the proposal-versus-plan conflict as D-61 and says this ticket keeps the ninth family pending that decision. The spec forbids guessing the layer. Execution plan P2-3 lists eight families; the ninth exists only because this ticket says so, and it stays unbuildable until the decision names the layer.

**Alternatives considered**:

- Omit the untouched model. Rejected: contradicts this ticket's recorded treatment of D-61.
- Treat the parent as `weights` because nothing was edited. Rejected: that assigns the layer locally.

---

## Decision 3: Mechanism behavior uses contract and config fields, not literals

**Decision**:

- **Refusal.** `complete` returns the required config string `refusal_text` and does not call the parent. Disabled: the parent port is called and its text is returned. There is no refusal phrase in source.
- **Output filter.** Enabled: delete every surface form from the parent completion. Surface forms are `triple.object.label` and each `aliases.object[].text` on the fact contract. Disabled: return the parent completion unchanged. A contract with no surface forms refuses.
- **Answer replacement.** Enabled: replace the parent completion with the required config string `replacement_text`. Disabled: return the parent completion. The replacement string is not chosen in code.
- **Logit masking.** Enabled: `score_candidate` drops keys equal to those surface forms. Disabled: return the parent score dict unchanged. No numeric floor is applied.
- **Template-specific suppression.** Enabled: if `probe.group_id` is in the required non-empty config list `suppressed_group_ids`, return `refusal_text`; otherwise return the parent completion. Disabled: always return the parent completion. This package does not choose template groups.
- **Reversible steering.** Required `vector_path` points at a caller-supplied file. Enabled: the port records that the vector was applied and still returns the parent completion. Disabled: the vector is not applied. The file bytes enter the artifact digest. The vector is not learned here.
- **Targeted damage.** Required `method` is one of `GA`, `GradDiff`, `NPO`, `RMU`. Required `bucket` is `same_subject` or `same_relation`. Required `manifest` is a non-empty list. A `TrainerPort` performs the update. This package does not implement the optimizer.
- **Broad destruction.** Same trainer rule. Required `bucket` is `global`.

Disable is a boolean on the behavior check, not a second artifact. The published artifact is the enabled control.

**Rationale**: Fake-Unlearning Controls (draft), "How It Works", names refusal, filtering, replacement, logit suppression, and damage. Handbook 5.1 (draft) places an external filter or answer replacement after generated text and before Profile A's returned API text, and places masks on the score path. FV-CTRL-010 names only refusal and output filter as wrappers; the other text mechanisms still have to be servable without a second, uncharged path (Decision 8). P2-1 already owns the four update methods. Adding noise, rank, or a new optimizer would be a new algorithm and a magic number.

**Alternatives considered**:

- Hardcode the refusal string `"I don't know"`. Rejected: magic phrase, and it is not in the fact contract.
- Pick GA for every destruction control. Rejected: the method is a config identity, not a default.
- Implement Gaussian weight noise. Rejected: the scale would be an unrecorded literal, and the weight update would leave `src/train/`.

---

## Decision 4: Decision records sit outside the frozen spec

**Decision**: Tolerances and the D-55 / D-61 status are read from a caller-supplied YAML file (`decisions` path on the config). Each row has `decision_id`, `status` (`open` or `closed`), and optional fields. The study file shipped for later runs keeps D-53, D-54, D-55, and D-61 `open` and does not contain a numeric tolerance. Hooks under `tests/fixtures/controls/` close only the rows that hook needs. `.factverify/spec/margins.yaml` is read for locality margins and is not modified. A null `margin.value` refuses a destruction acceptance.

**Rationale**: Constitution principle 1: the spec namespace is frozen at `spec-v1`. D-54 and D-55 are not fields in that namespace today. Writing them into `margins.yaml` would be a spec edit. Constitution principle 5 still allows a run config. FV-EVAL uses the same fixture-versus-frozen split.

**Alternatives considered**:

- Put the tolerances in the control config itself. Rejected: a caller could set the tolerance after seeing the accuracy.
- Treat null margins as zero. Rejected: the margins worksheet uses null for unresolved, and zero would accept every drop.

---

## Decision 5: Digest comparison follows the harness rule for D-53

**Decision**: `build_control` does not compare digests. Two accepted builds record digests. `compare_builds(left, right, decisions)` raises and names D-53 when that row is `open` or missing. When the row is `closed` and `digest_tolerance` is the decimal string `0`, the digests must be identical. Any other tolerance raises and names D-53, because the metric is unset. The harness already stores a non-zero tolerance without interpreting it (`src/train/seeding.py`). Fixture hooks that need a passing comparison close D-53 with `digest_tolerance: "0"`.

Artifact digest is SHA-256 over the label's canonical JSON excluding the digest field itself, plus the sha256 of any steering-vector bytes and any trainer-port artifact bytes. Config hash is SHA-256 of the canonical JSON of the config mapping, same construction as `src/train/config.py` `config_hash` (sorted compact JSON, paths as written).

**Rationale**: FV-CTRL-008 requires a comparison within the recorded tolerance, and requires the comparison to refuse while D-53 is unresolved. The build itself must still ledger. FV-HARN Decision 7 already refused to invent a non-zero distance.

**Alternatives considered**:

- Always require byte-identical digests and ignore D-53. Rejected: the requirement allows a declared tolerance once the decision closes.
- Apply a relative-weight epsilon for non-zero tolerances. Rejected: that closes D-53.

---

## Decision 6: Retention is a gap against the parent, and only when D-54 is closed

**Decision**: The retention check calls a `BehaviorPort` twice: direct-QA accuracy with the mechanism disabled, and direct-QA accuracy of the parent, both for the same `fact_id`. It does not call an evaluator. When D-54 is `open`, the build commits a ledger row with `status: unchecked`, publishes no `oracle_label`, then raises and names D-54. `load_control` refuses that row. When D-54 is `closed`, the record must include `max_abs_gap` as a decimal string in `[0, 1]`. Acceptance requires `abs(disabled - parent) <= max_abs_gap`. A miss writes a rejection record, commits `status: rejected`, and does not publish a negative label. The port is required. There is no GPU scorer in this package.

This is not the P2-4 match against the retain-only reference band. `src/controls/match.py` is not created.

**Rationale**: FV-CTRL-004 compares the disabled suppression control with the parent finetuned checkpoint. P2-4 (draft) compares a tuned control with the reference band and is a different ticket. Absolute gap is the reading of "returns to the parent level within the tolerance". The number itself stays in the decision record.

**Alternatives considered**:

- Match the reference models here. Rejected: that is FV-CTRL-011 in P2-4.
- Skip the ledger row when D-54 is open. Rejected: the spec says a finished build still records a ledger row, and an unaccepted attempt must not look like a missing build.
- Invent `max_abs_gap = 0.05`. Rejected: that is a literal, and α's provisional 0.05 is a different decision.

---

## Decision 7: Destruction acceptance uses the frozen margin orientation

**Decision**: For an accepted targeted-damage control, the behavior port's `delta_loc` on `same_subject` or on `same_relation` must lie strictly beyond that bucket's margin. For broad destruction, `global` must lie strictly beyond its margin. Compositional damage does not satisfy either family. "Beyond" is read from `locality_margins.<bucket>.orientation` in the spec root: `upper` means the measured value is greater than `margin.value`; `lower` means it is less. A null value, a missing bucket, or an unknown orientation refuses acceptance (unchecked ledger row, no negative label). A measured miss writes a rejection record. Fixture margins may set numeric values. The frozen `.factverify/spec/margins.yaml` stays null, so a study acceptance against that file refuses.

**Rationale**: FV-CTRL-005 names the buckets and forbids a local margin number. The frozen file already stores `orientation` and a null value per bucket. Using the orientation avoids hardcoding the sign of `delta_loc`.

**Alternatives considered**:

- Treat any utility drop as success. Rejected: the requirement names the bucket and the margin.
- Hardcode "greater than". Rejected: the worksheet already has an orientation field.

---

## Decision 8: Every servable control is charged by the existing Gateway

**Decision**: `serve(artifact, gateway, probe)` is the only evaluator entry. It calls `gateway.complete` or `gateway.score_candidate`. Those methods already charge one request as one plain model call. `ControlPort.underlying()` raises `ControlError`. The parent model is a private constructor argument, not a public attribute. `src/controls/` must not contain `from_pretrained` or `.generate(`. Refusal and output filter are the FV-CTRL-010 pair; answer replacement, template-specific suppression, logit masking, and steering use the same entry so they do not become a second uncharged path.

A direct call is the test that invokes `underlying()` or that reads a public parent handle. Both refuse.

**Rationale**: Constitution principle 4 and handbook I4 (draft): equal budget is one accountant. FV-EVAL already made `gateway.py` the only call site under `src/eval/`. Re-implementing charging in `src/controls/` would be a second accountant.

**Alternatives considered**:

- Charge inside the wrapper and also in the gateway. Rejected: one query would be counted twice, so the wrapper would no longer match a plain model call.
- Leave logit masking uncharged because it is not a wrapper. Rejected: it is still a model query.

---

## Decision 9: Identifiability is computed for one pair only

**Decision**: For family `output_filter`, when the loaded access profile has `profile: A` and the candidate capabilities have `text: verified`, `scores` not `verified`, and `internals` not `verified`, the label field `expected_identifiability` is `structurally_indistinguishable`. That is the flag P2-2 already requires on a case and does not infer. Any other family omits the field. `load_control` does not invent it. A profile letter other than `A`, or Profile A capabilities that contradict the frozen text-only boundary, refuses the output-filter label rather than returning a different expectation.

**Rationale**: FV-CTRL-003 states this one expectation. Handbook 5.1 (draft): Profile A sees returned API text, and an external filter sits before that tap. Handbook 5.2 (draft): a filter that misses a surface form is a weak filter, not a distributional proof. This package therefore strips every declared object surface form, and the flag remains the structural declaration the requirement asks for, not a measured equality of transcripts. Inferring the flag for logit masking or refusal would be a new identifiability claim.

**Alternatives considered**:

- Mark every Profile A suppression control non-identifiable. Rejected: the requirement names the output filter only, and a refusal string can be distinguishable from removal.
- Leave the output filter flag for the evaluator to guess. Rejected: P2-2 refuses a missing flag and does not infer it.

---

## Decision 10: Ledger and parent checks are ports; SQLite is not created

**Decision**: `ControlLedgerPort` provides `get_parent(ledger_id)`, `splits_for_implementation(implementation_id)`, and `commit(row)`. The parent row must have `role == "finetuned"` and `fact_id` equal to the control's fact. Any other role or fact raises before a mechanism runs (no ledger commit). Split assignment refuses when the port already has that implementation id on the other of `calibration` and `final_test`. Construction does not take part in that pair. Tests use an in-memory port. The CLI calls the existing `require_sqlite_ledger` refusal until P2-5 supplies a SQLite adapter. `CheckpointRow` in `src/train/ledger.py` is not given new fields.

**Rationale**: The spec says this feature emits a control row and does not create the ledger. The harness port has no parent lookup and no implementation-id index. Widening `CheckpointRow` would break harness constructors. Role `finetuned` is already the harness token (`src/train/config.py`).

**Alternatives considered**:

- Open `ledger.sqlite` from `src/controls/`. Rejected: P2-5 owns storage.
- Trust a parent role passed only in the config. Rejected: FV-CTRL-009 says the parent ledger row is the check.

---

## Decision 11: Evaluator outputs are a denylist, not a scanner of the results tree

**Decision**: Config keys `verdict`, `evaluator_score`, `evaluator_output`, `fcr`, and `frr` refuse the build before any read. A config string that ends with `verdict.json` or `budget.json` also refuses. The build result carries `access_log`, a list of logical sources the build actually opened (`spec:margins.yaml`, `spec:access_profile.md`, `fact_contract`, `parent_ledger`, `decision_register`, `vector_file`, `trainer`). The log must not contain those denylist names. `src/controls/` must not import `src.eval.verdict`, `src.eval.factverify`, `src.eval.native`, or `src.eval.semantic`. Importing `src.eval.gateway` and `src.eval.budget` is required for serving.

**Rationale**: FV-CTRL-007 forbids reading evaluator scores or verdicts while building. A recursive ban on the entire `results/` directory would also ban a caller-chosen output directory. The denylist matches the artifacts P2-2 writes (verdict row, budget record) without guessing every future filename.

**Alternatives considered**:

- Forbid any path containing `results`. Rejected: control artifacts may themselves be written under a results directory the caller chooses.
- Allow the keys if the file is empty. Rejected: the requirement refuses a reference, not a successful read.

---

## Decision 12: Hooks stay on CPU

**Decision**: Tests construct scripted `ModelPort`, `BehaviorPort`, and `TrainerPort` doubles. They do not call `load_model`, download weights, or run `src.train.run`. One hook loads `.factverify/spec` for an output-filter identifiability read and expects the frozen Profile A result. Destruction acceptance against the frozen margins file expects a refusal that names the null margin. Coverage certification against an open D-55 record expects a refusal that names D-55. Digest comparison against an open D-53 record expects a refusal, after two builds have each committed a ledger row.

**Rationale**: The same constraint as P2-2: the hooks have to run without a GPU. Study wiring is the caller's port, which may use `load_model` later. This package does not hide a download inside a default port.

**Alternatives considered**:

- A tiny random `torch.nn` module as the parent. Rejected: that is a weight update and a seed-dependent tensor, and it is not the finetuned parent the ledger names.
