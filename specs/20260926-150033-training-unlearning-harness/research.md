# Research: FV-HARN — P2-1 Training and Unlearning Harness

**Feature**: `20260926-150033-training-unlearning-harness`  
**Date**: 2026-09-26  
**Source notes** (read from disk; Obsidian MCP unavailable):

- `FactVerify — Execution Plan` (status: planned) — "Phase 2 — Harness and run ledger", task P2-1
- `Retain-Only Reference Model` (status: needs-review) — "How It Works"
- `FactVerify — Phase 0 Build Handbook (Freeze Spec)` (status: draft) — I6, I7, I8, §6.5, §6.7
- `FV-HARN — P2-1` (status: draft) — requirements 001–010; decisions D-51, D-52, D-53
- `FV-LEDG — P2-5` (status: draft) — checkpoint record and `check_disjoint`
- `FV-MODEL — P2-0` research Decision 2, now implemented in `src/models/adapters.py`

No technical-context item is left as NEEDS CLARIFICATION. Study decisions D-51, D-52, and D-53 are deliberately unresolved.

---

## Decision 1: Configuration hash with no code defaults

**Decision**: A job file is loaded as YAML and rejected if any required key is missing, null, or `DECISION_REQUIRED`, or if an unknown key is present. Nothing is filled in from code. The config hash is SHA-256 over the canonical JSON of that mapping (keys sorted, UTF-8, compact separators). The same bytes are stored in `metadata.json` as `config_hash`.

**Rationale**: FV-HARN-001: a default buried in code never reaches the hash. I8 (handbook, draft): refuse unresolved spec fields before work starts. Sorting keys makes the hash stable across machines.

**Alternatives considered**:

- Merge a defaults file, then hash the result. Rejected: a change to the defaults file changes behaviour without a change to the job file the operator thinks they ran.
- Hash the raw YAML bytes. Rejected: comment and whitespace changes would look like procedure changes.

Required keys are a name registry in `config.py` (see Decision 6). The registry contains names only. Study numbers live in the job file when D-51 and D-52 close.

---

## Decision 2: Procedure match uses a closed identity allowlist

**Decision**: A reference job is accepted only when its resolved config and the paired finetune config are deeply equal after removing this allowlist:

- `role`
- `seed`
- `manifest`
- `split`
- `output_dir`
- `paired_finetune_config`

Every other field must match, including `method` (both `finetune`), `base_role`, `target_fact_id`, `bundle_id`, `source_bundle`, `spec_revision`, `hardware_class`, `determinism_policy`, `digest_tolerance`, optimizer settings, and the whole `lora` block. Differences are reported as a sorted list of dotted paths. On success the reference metadata records `paired_finetune_config_hash`.

**Rationale**: FV-HARN-004 says any field other than the data manifest and the seed fails the job, and names learning rate, epochs, LoRA settings, and base identity as examples. Taken literally, `role` would also have to match, but FV-LEDG-004 (draft) assigns `finetuned` and `reference` as different roles, and the two jobs need different output paths, splits, and a pointer to the paired file. Those fields name the checkpoint. They do not change the training procedure $\mathcal{A}$ in Retain-Only Reference Model ("How It Works", needs-review): $M_R=\mathcal{A}(D\setminus F)$. Keeping the allowlist closed means a new hyperparameter key is compared automatically.

**Alternatives considered**:

- Compare only the four example fields. Rejected: a weight-decay or optimizer change would slip through.
- Require every byte to match except manifest and seed. Rejected: the job could not name its role or output path.

---

## Decision 3: Two metadata files

**Decision**: Every published adapter directory contains:

1. `fv_adapter_meta.json` with `base_identity_hash` set to the base model's identity hash (no adapter). This is the P2-0 contract. `src/models/adapters.py` reads it and excludes it from the adapter digest.
2. `metadata.json` with the FV-HARN-007 fields plus the extra fields FR-002, FR-003, and FR-004 require (`data_order`, and for references `excluded_bundle_id` and `paired_finetune_config_hash`). This file is part of the adapter digest.

`base_identity_hash` is the loader identity of the base role with no adapter. For `finetuned` and `reference`, `parent_checkpoint_hash` equals that same base hash (FV-HARN-007). For a candidate, `parent_checkpoint_hash` is the full identity hash of the checkpoint the method starts from (base plus the parent adapter). The new adapter's `base_identity_hash` is still the base, because the loader checks the adapter against the base weights.

**Rationale**: P2-0 already shipped `fv_adapter_meta.json`. FV-HARN asks for `metadata.json`. One file cannot satisfy both names without changing the loader. Putting lineage in `metadata.json` keeps the loader's minimum field stable. Hashing `metadata.json` into the digest is stable: that file does not contain the digest of itself.

**Alternatives considered**:

- Extend `fv_adapter_meta.json` and stop writing `metadata.json`. Rejected: contradicts the FV-HARN artifact name and would require a loader change mid-flight.
- Exclude `metadata.json` from the digest. Rejected: a metadata swap would keep the same adapter digest.

---

## Decision 4: Ledger is a port; SQLite stays in P2-5

**Decision**: `src/train/ledger.py` defines a `LedgerPort` with two operations: `commit_checkpoint` (success or failed attempt) and `split_for_seed` (fact id + seed → split or absent). `run_job` receives the port as an argument. The CLI refuses to start if no ledger is provided. Tests pass an in-memory port. `ledger.sqlite`, append-only triggers, and `scripts/ledger.py` are FV-LEDG.

A study checkpoint is not produced until the real ledger implements the port. Constitution principle 6: stand the ledger up before the first real checkpoint.

**Rationale**: FV-HARN-008 and FV-HARN-010 need a committed row and a seed query now. FV-LEDG (draft) owns the schema, the role vocabulary, tier (D-56), git dirty checks, and supersession. Implementing a second SQLite writer here would split the ledger.

**Alternatives considered**:

- Write `ledger.sqlite` from `src/train/`. Rejected: out of scope, and FV-LEDG-003's append-only rule would be duplicated.
- Return success and let a later job insert the row. Rejected: FV-HARN-008 says success follows the commit.

Failure rows: a crash or a refused publish still records partial cost with `status=failed` and `adapter_published=false`. The row's `checkpoint_identity_hash` is `unfinished:` plus the config hash when no adapter exists. That placeholder is not a model identity. Evaluators ignore any row whose status is not `succeeded` (aligned with FV-LEDG-001, draft).

---

## Decision 5: Publish only after metadata; roll back if the ledger commit fails

**Decision**: Weights are written to a staging directory. `metadata.json` and `fv_adapter_meta.json` are written there. The staging directory is renamed to the final adapter path only after both files exist. `load_model` is then called on the final path to obtain the checkpoint identity hash (the public hash, not a reimplementation). The ledger row is committed with that hash. If the commit fails, the final directory is deleted and the job returns failure. If metadata cannot be written, staging is deleted, a failed cost row is attempted, and the adapter is not published.

**Rationale**: FV-HARN-007: a metadata failure does not publish. FV-HARN-008: success follows the commit. Deleting an unledgered directory matches FV-LEDG-001 (draft): an unledgered checkpoint is unusable. Using `load_model` for the identity hash keeps one hash implementation (P2-0).

**Alternatives considered**:

- Commit the ledger before rename. Rejected: a failed rename would leave a success row pointing at a missing directory, and the ledger is append-only so the row cannot be removed.
- Reimplement the identity hash inside `src/train/`. Rejected: the loader contract says the hash has a single implementation.

An operating-system kill that skips Python `finally` cannot write a cost row. The crash path FV-HARN-009 requires is an exception caught by `run_job`.

---

## Decision 6: Method names and required fields (values stay in the job file)

**Decision**: `method` is one of `finetune`, `GA`, `GradDiff`, `NPO`, `RMU`. Any other string raises before the corpus is opened and before `load_model`. Each name maps to one trainer. Coefficients are read from the job file at the point of use. There is no `.get(key, default)`.

Shared keys, all required: `learning_rate`, `epochs`, `batch_size`, `max_length`, `weight_decay`, `optimizer` (only `adamw` is accepted).

LoRA block, required for `finetune`: `r`, `alpha`, `dropout`, `target_modules`. A new adapter is created on the loaded base after seeding.

Unlearning jobs require `parent_adapter` (a published adapter directory). The harness loads that checkpoint through `load_model`, continues training that adapter, and does not re-initialise LoRA. Extra required keys:

| Method | Extra required fields | Loss the name denotes |
|--------|----------------------|------------------------|
| `finetune` | `manifest.train` (non-empty) | Causal language-model cross-entropy |
| `GA` | `manifest.forget` (non-empty) | Negative cross-entropy on the forget manifest |
| `GradDiff` | `manifest.forget`, `manifest.retain`, `retain_coeff` | Negative forget loss plus `retain_coeff` times retain cross-entropy |
| `NPO` | `manifest.forget`, `beta` | Negative preference loss against the frozen parent, coefficient `beta` |
| `RMU` | `manifest.forget`, `manifest.retain`, `steering_coeff`, `steering_layer` | Steer forget representations at `steering_layer`; keep retain representations near the frozen parent |

The access log is the union of the manifest lists the method is allowed to read. Lists the method does not use must be absent, not empty-by-default.

**Rationale**: FV-HARN-005: candidates differ by the declared method and its hyperparameters. Naming the loss fixes what each config token means. Leaving every coefficient as a required field is how D-51 stays open: Block 0–2 numbers are not chosen here. `optimizer: adamw` is still declared so a silent switch cannot hide outside the hash.

**Alternatives considered**:

- Stub trainers that only write the method name. Rejected: the hook would pass without a real update, and later blocks would trust it.
- Pick paper-default $\beta$, layer, and $\lambda$ in code. Rejected: that closes D-51.

---

## Decision 7: Seeding and the determinism policy field

**Decision**: Before adapter initialisation and before the data loader is built, `seeding.py` sets `random`, NumPy (if imported), and `torch` seeds from the job's `seed`, including CUDA when present. Data order is a shuffle of the manifest ids with `torch.Generator` seeded by that same seed. The yielded id list is stored as `data_order` in metadata.

`determinism_policy` is required:

- `exact`: `torch.use_deterministic_algorithms(True)`, cuDNN deterministic, benchmark off.
- `tolerant`: seeds are set; deterministic algorithms are left off.

`digest_tolerance` is a required decimal string of a non-negative integer. Tolerance `0` means the adapter digests must be identical. A non-zero value is stored and hashed, and any comparison that would apply it raises before judging the digests, because the metric itself is D-53 and is not chosen here. Fixture tests use `0`.

**Rationale**: FV-HARN-002. Gate 1 criterion 2 (execution plan, "GATE 1") needs reference-seed variation to be measurable, which requires the seed to be the only randomness. Handbook I7 (draft): the seed that counts is an update seed. Picking a Hamming distance or a relative-weight epsilon would close D-53.

**Alternatives considered**:

- Always enable deterministic algorithms. Rejected: that closes D-53.
- Compare digests for exact string equality only. Rejected: the requirement allows a declared tolerance.

---

## Decision 8: Corpus files are read only by id through the manifest gate

**Decision**: Training text lives as one file per id: `{corpus_dir}/{id}.txt`. `data.py` is the only reader. `get(item_id)` raises, naming the id, when the id is not on the job's manifest union, and appends the id to the access log when it is. Completing a job requires the access-log set to equal that union. Bundle exclusion (FV-HARN-003) is a set intersection of `manifest.train` with `source_bundle`, checked before any file is opened. A hit raises, naming the document id. A clean reference records `bundle_id` as `excluded_bundle_id`.

**Rationale**: FV-HARN-006 and handbook I6 (draft): an unlisted read is how calibration or final-test text leaks into training. Per-id files make "did not read" an observable fact (the file was not opened), which a shared JSONL cannot guarantee.

**Alternatives considered**:

- One JSONL for the whole corpus. Rejected: parsing it reads every line.
- Trust the caller not to request extra ids. Rejected: the requirement says a request for an unlisted item raises.

---

## Decision 9: Tests run the real trainers on a tiny fixture

**Decision**: `tests/test_harness.py` holds `test_fv_harn_001` through `test_fv_harn_010`. Jobs use a tiny local causal LM (the same style as `tests/fixtures/models_loader/`), one epoch, and a handful of tokens. No network and no GPU. An in-memory `LedgerPort` supplies the seed-disjointness rows and records commits. Fixture numbers live only under `tests/fixtures/harness/`.

**Rationale**: FV-HARN-005 asks each method name to produce a checkpoint on the fixture model. Mocking the trainer would not show that an unknown method fails before data is loaded while a known method writes metadata. CI stays offline, matching the loader tests.

**Alternatives considered**:

- Mark the suite `slow` and download a real model. Rejected: network in CI, and it does not test the fail-closed paths any better.

---

## Summary

| Unknown | Resolution |
|---------|------------|
| Config defaults | None. Missing key raises. Hash is SHA-256 of sorted JSON. |
| Procedure match | Deep equality outside a six-field identity allowlist. |
| Metadata filenames | `fv_adapter_meta.json` for the loader; `metadata.json` for lineage. |
| Ledger storage | Port only. SQLite is P2-5. |
| Publish vs ledger failure | Metadata before publish; delete the directory if the commit fails. |
| Method algorithms | Five named losses; every coefficient is a required field (D-51 values unset). |
| Determinism | Required `determinism_policy` plus `digest_tolerance` (D-53 value unset). |
| Data reads | One file per id, only through the manifest gate. |
| Test scale | Tiny fixture, real trainers, in-memory ledger. |
