# Feature Specification: Model Role Names and Versioned Model Configuration

**Feature Branch**: `20260929-225846-model-role-config`
**Created**: 2026-09-29
**Status**: Draft
**Input**: User description: "Give model roles meaningful names and move model selections to versioned runtime configuration. Ticket: `tickets/model-role-names-and-runtime-config.md`."

Design sources, read from disk because the Obsidian vault tools were unavailable:

- [FactVerify — Execution Plan](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/04-Experiments/FactVerify%20%E2%80%94%20Execution%20Plan.md) (status: planned), heading "Phase 0 — Freeze the spec", row P0-8, and the callout "Why P0-8 is in the freeze"; heading "Phase 6 — Block 3 · pretrained stress test" (1B–3B full run, one 7B–8B confirmation subset; task P6-8).
- [FV-SPEC — P0-8 Base Model Selection and Pinning](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-SPEC%20%E2%80%94%20P0-8.md) (status: draft), headings "1. Scope", "2. Interface", and "3. Requirements" (FV-SPEC-089 through FV-SPEC-095), and "5. Blocking decisions" (D-46, D-47, D-48, D-49).
- [FV-MODEL — P2-0 Model Loader](file:///Users/nhan.ngo/Nathan/second-brain/ml-unlearning/requirements/FV-MODEL%20%E2%80%94%20P2-0.md) (status: draft), headings "1. Scope" and "2. Interface".

P0-8 and P2-0 are still `draft`. This specification does not fill D-46, D-47, D-48, or D-49, and it does not edit the frozen `spec-v1` snapshot.

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Name each model by the job it does (Priority: P1)

A reader opening a new model configuration can tell what each model is for without a schedule glossary. The base model used to build controlled-fact finetunes, retain-only references, candidates, and fake-unlearning controls is `controlled_fact_base`. The larger model reserved for the pretrained-fact confirmation subset is `pretrained_fact_confirmation`. New commands and new records use these names. Schedule labels such as "blocks 0–2" and "block 3" are no longer the names of the roles.

**Why this priority**: The current names describe when a model was expected to run. They do not say whether the entry is a base model, a trained checkpoint, an evaluator, or a confirmation model. A later reader cannot audit a run if the role name is a schedule slot.

**Independent Test**: Give a reader a new configuration that contains only the two role names and their stated purposes. The reader identifies the controlled-fact base and the pretrained-fact confirmation model without any block number. A configuration that still uses a schedule label as a role name is rejected for new work.

**Acceptance Scenarios**:

1. **Given** a new model configuration, **When** a reader inspects its roles, **Then** the roles are `controlled_fact_base` and `pretrained_fact_confirmation`, each with a purpose that states the scientific job.
2. **Given** a new configuration whose only role name is a schedule label, **When** it is checked, **Then** the check fails and names the label that must be replaced.
3. **Given** a production command that asks for a model, **When** the operator names `controlled_fact_base`, **Then** the command resolves that scientific role and does not require a block number.
4. **Given** the confirmation role, **When** its purpose is read, **Then** it describes the pretrained-fact confirmation subset, not the model that carries the full pretrained stress test and not a mere repeat of "Block 3".

---

### User Story 2 - Change a model without editing the frozen specification (Priority: P1)

The frozen specification states the model-selection policy: which roles exist, what each role means, which identity facts must be recorded, which integrity checks apply, and how a change is allowed. It does not name a repository, a revision, a precision, or a file fingerprint. Each concrete selection lives in its own named, versioned configuration. Replacing a model means adding a new configuration. The previous configuration, and every result produced from it, stays reproducible. The `spec-v1` snapshot, including its original model document, is left unchanged and can still be retrieved.

**Why this priority**: Today the concrete selection sits inside a frozen, checksum-bound specification. Changing a model looks like editing the protocol even when the protocol has not changed. P0-8 exists so that a model swap cannot silently invalidate the exclusion gate, the ledger, and the cache. That protection has to survive this split.

**Independent Test**: Publish one frozen policy and two versioned configurations that fill the same role with different models. The policy contains no repository or revision. Each configuration has its own name and fingerprint. The `spec-v1` model document is byte-for-byte the historical snapshot. An in-place overwrite of an already used configuration is not treated as the same selection.

**Acceptance Scenarios**:

1. **Given** the new specification revision, **When** the frozen model policy is read, **Then** it defines role purposes, required identity facts, integrity checks, and amendment rules, and it names no concrete model.
2. **Given** a study stage, **When** its model is selected, **Then** the selection is a new named configuration, not an edit to the frozen policy and not an overwrite of an earlier configuration.
3. **Given** the `spec-v1` tag, **When** its model document is retrieved, **Then** that document is unchanged and still contains the historical role labels and historical selections.
4. **Given** a proposal to introduce this split by editing `spec-v1` in place, **When** it is checked, **Then** it is refused. The split is accepted only as an amendment with a new specification revision.
5. **Given** an already recorded configuration, **When** someone changes its contents, **Then** the result is a different configuration with a different fingerprint, and results bound to the old fingerprint are not treated as results of the edited file.

---

### User Story 3 - Check and load the same document (Priority: P1)

The policy checker, the model loader, the prefetch step, and the tests all read one document shape and one field vocabulary. A configuration that passes the checker is the configuration the loader accepts. Roles are grouped in one roles section. The weight revision and the tokenizer revision have one shared name each, used everywhere. A second, incompatible shape is not accepted for new work.

**Why this priority**: Today the checker and the loader disagree. One expects roles grouped together and a field for the model revision; the other expects role names at the document root and a different revision field. A document the specification accepts cannot be loaded, so a "valid" selection is not the selection that runs.

**Independent Test**: Take one valid configuration. The checker accepts it, and the loader reads the same roles and the same revisions from it. A document in the other historical shape fails the shared check and is not loaded as if it were the new shape.

**Acceptance Scenarios**:

1. **Given** a configuration the checker accepts, **When** the loader, the prefetch step, and the tests read it, **Then** they see the same roles and the same weight revision, tokenizer revision, variant, precision, attention setting, licence, and file fingerprints.
2. **Given** a document that places role names at the root, or that uses a different name for the weight revision, **When** it is offered as a new configuration, **Then** it is refused, and the refusal names the shape or field that does not match.
3. **Given** the shared vocabulary, **When** two consumers describe the same selection, **Then** they use one name for the weight revision and do not translate between two private names.

---

### User Story 4 - Choose the configuration explicitly and refuse it before any fetch (Priority: P2)

Every production command that loads a model requires the operator to name the configuration and the role. If either is missing, the command stops. It does not fall back to whichever configuration was edited most recently, and it does not invent a default model. The configuration is checked against the frozen policy before any model is constructed and before any network access. A stand-in used only by a test may skip real loading. A production run may not.

**Why this priority**: A silent default would let a run pick up an unreviewed edit. A check that happens after weights are fetched can spend a download on a selection that was never allowed to run.

**Independent Test**: Start a production load with no configuration named, with an unknown role, and with a configuration that fails the policy. Each attempt stops before construction and before network access, and each names what was wrong. The same load with an explicit valid configuration and role proceeds.

**Acceptance Scenarios**:

1. **Given** a production command, **When** the operator does not name a configuration, **Then** the command refuses and does not load a recently edited file.
2. **Given** a named configuration, **When** the operator does not name a role, or names a role the policy does not define, **Then** the command refuses before loading.
3. **Given** a configuration that is missing a required role, leaves a required field unresolved, uses a movable revision, has a bad file fingerprint, cannot support the declared access capabilities, or has a staged commitment past its deadline, **When** a production command uses it, **Then** the command refuses and names the role, field, and rule.
4. **Given** any refusal in the scenarios above, **When** the attempt ends, **Then** no model has been constructed and no network access has been made.
5. **Given** a test that supplies a stand-in model, **When** the test runs, **Then** it may skip real loading, and that bypass is unavailable to production commands.
6. **Given** a role whose selection is still a staged commitment, **When** a command needs that role resolved, **Then** the command refuses. The confirmation model is not invented by this feature.

---

### User Story 5 - Bind every result to the exact selection (Priority: P2)

Every exclusion-gate report, checkpoint ledger row, cache record, training run, and evaluation run that depends on a model records the study role, the configuration's name, the configuration's fingerprint, the model identity, the identity-schema version, and the frozen specification revision that governed the configuration. Changing the selected model creates a new configuration fingerprint. The knowledge-exclusion gate and any cache entries tied to the previous identity are not reused for the new model.

**Why this priority**: The exclusion gate is evidence only for the model it was run on. A cache hit or a copied gate report from a different model would launder a model swap into looking like the same study.

**Independent Test**: Run one gate and one training record on configuration A, then select configuration B for the same role with a different model. The new outputs cite B's name, fingerprint, identity, identity-schema version, role, and governing specification revision. A's gate report and A's cache entries are not accepted as evidence for B.

**Acceptance Scenarios**:

1. **Given** a new exclusion-gate report, ledger row, cache record, training run, or evaluation run, **When** it is stored, **Then** it records the study role, configuration name, configuration fingerprint, model identity, identity-schema version, and governing specification revision.
2. **Given** a record missing any of those six items, **When** it is checked as a new model-dependent output, **Then** the check fails and names the missing item.
3. **Given** results produced under one configuration, **When** a later run uses a different model for the same role, **Then** the later run has a different configuration fingerprint and a different model identity.
4. **Given** an exclusion-gate report or cache entry bound to the previous identity, **When** a run uses the new model, **Then** that report and those entries are not reused.
5. **Given** a historical result, **When** this feature is introduced, **Then** that result is not rewritten.

---

### User Story 6 - Rename a role without changing what the model is (Priority: P2)

The model identity names the concrete model and adapter bytes together with the runtime settings that the canonical identity already treats as identity. It does not include the friendly role name. Renaming `blocks_0_2` to `controlled_fact_base` does not, by itself, produce a new model identity. Records already stored keep the role key and the identity they were written with. A version marker on the identity says which definition was used, and the older definition can still be checked.

**Why this priority**: If the friendly name is mixed into the identity, a rename looks like a different model. Old evidence would no longer match, or, worse, a real model change could be confused with a rename. The canonical identity definition already excludes the role name. Shipped records that hashed the role name must remain checkable rather than being silently recomputed.

**Independent Test**: Hash one resolved model twice under the new identity version, once under each role name, with the bytes and identity-relevant settings held fixed. The identities match. A historical record that used the older definition still verifies under that older version and is not recomputed under the new one.

**Acceptance Scenarios**:

1. **Given** the same repository, revisions, precision, and adapter bytes, **When** the identity is computed under the new identity version with two different role names, **Then** the identity is the same.
2. **Given** a change to the repository, either revision, the precision, or the adapter bytes, **When** the identity is computed, **Then** the identity changes.
3. **Given** a historical record written under the older identity definition, **When** it is checked, **Then** it verifies under identity schema version 1, keeps its original role key, and is not rewritten as version 2.
4. **Given** a new record, **When** it is written, **Then** its identity schema version is 2 and its role is stored beside the identity, not inside it.
5. **Given** a configuration fingerprint and a model identity for the same run, **When** only the friendly role name changes, **Then** the configuration fingerprint may change and the model identity does not.

---

### User Story 7 - Read old role names during the transition (Priority: P3)

Until legacy names are retired, an old configuration or an old command may still say `blocks_0_2` or `block_3_confirmation`. Those names resolve to `controlled_fact_base` and `pretrained_fact_confirmation`, and the operator sees a deprecation notice that states the new name. New configurations and new outputs use only the new names. If a document contains both an old name and its new name, resolution stops. The alias must not hide the clash.

**Why this priority**: Historical inputs have to stay readable, and historical outputs have to keep the labels they were published with. New work should not keep growing the old vocabulary. A document that defines both names is ambiguous, even when the two entries look similar.

**Independent Test**: Load a legacy configuration and confirm it resolves, announces the new name, and does not rewrite the file. Load a document that contains both names and confirm it is refused. Write a new output and confirm it uses only the new name.

**Acceptance Scenarios**:

1. **Given** an input that uses `blocks_0_2`, **When** it is loaded during the transition, **Then** it resolves to `controlled_fact_base` and the operator sees a deprecation notice naming both.
2. **Given** an input that uses `block_3_confirmation`, **When** it is loaded during the transition, **Then** it resolves to `pretrained_fact_confirmation` and the operator sees the same kind of notice.
3. **Given** a document that contains both an old name and its new name, **When** it is loaded, **Then** it is refused, and the refusal names both entries.
4. **Given** a historical output, **When** it is read after the rename, **Then** it still shows its original role key and its original identity.
5. **Given** a configuration or output created after the rename, **When** it is written, **Then** it uses the new role names only.
6. **Given** the transition has ended, **When** legacy aliases are removed, **Then** historical records can still be read with the role key and identity they already carry.

---

### Edge Cases

- A new configuration omits `controlled_fact_base`, or omits a required identity fact on a role that is not an explicit staged commitment.
- A revision is a branch name, a tag, a shortened identifier, or is missing. Movable revisions are refused. This feature does not loosen that rule.
- A file fingerprint does not match the local file, or a required weight, configuration, or tokenizer file is missing or extra.
- The selected model cannot supply an observation or intervention channel the access profile requires, including a licence that forbids the required updates.
- `pretrained_fact_confirmation` is still a staged commitment. A missing deadline is reported. A deadline that has passed, with the role still unresolved, fails a command that needs the role. This feature does not fill in a model.
- The operator points at a configuration whose bytes no longer match the fingerprint already recorded for that configuration name.
- A production command omits the configuration, omits the role, or names a role the policy does not define.
- The same bytes are requested once under the old role name and once under the new role name. The model identity under the new identity version is unchanged; stored historical identities are not recomputed.
- A document contains both `blocks_0_2` and `controlled_fact_base`, or both `block_3_confirmation` and `pretrained_fact_confirmation`.
- Someone tries to satisfy a model change by editing the `spec-v1` model document, or by overwriting the only configuration file.
- A downstream record from before this feature has no configuration name or configuration fingerprint. It is left as historical evidence and is not backfilled. A new record missing those items is refused.
- Block 0's current small debugging model and a later Block 1 model are different configurations of the same role, `controlled_fact_base`. The role name does not change when the concrete model changes.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: New configurations and new operator-facing commands MUST name the controlled-fact base role `controlled_fact_base`. Its purpose is the base pretrained model for controlled-fact training, unlearning, retain-only references, candidates, and fake-unlearning controls.
- **FR-002**: New configurations and new operator-facing commands MUST name the second role `pretrained_fact_confirmation`. Its purpose is the model for the pretrained-fact confirmation subset in the stress-test stage. The name MUST describe that job. It MUST NOT be a schedule label.
- **FR-003**: The frozen specification MUST define role purposes, the identity facts a selection must supply, the integrity checks, and the amendment rules. It MUST NOT select a repository, a revision, a precision, an attention setting, or a file fingerprint.
- **FR-004**: Each concrete selection MUST live in a named, versioned configuration separate from the frozen policy. A change of model MUST be a new configuration. An existing configuration MUST NOT be overwritten in place and then treated as the same selection.
- **FR-005**: The `spec-v1` snapshot, including its original model document and its original role labels, MUST remain unchanged and retrievable. This split MUST be introduced only through the amendment protocol and a new specification revision.
- **FR-006**: Checkers, loaders, prefetch, and tests MUST share one document shape and one field vocabulary. Roles MUST be grouped in a single roles section. The weight revision MUST be named `model_revision` and the tokenizer revision MUST be named `tokenizer_revision` everywhere. A new configuration that places role names at the document root, or that calls the weight revision by any other name, MUST be refused.
- **FR-007**: A resolved role MUST record the repository, `model_revision`, `tokenizer_revision`, the variant, the precision, the attention setting, the licence, and the file fingerprints. A staged role MUST say that it is pending and MUST carry a deadline. This feature MUST NOT choose the Block 1 model or the confirmation model.
- **FR-008**: Production commands that load a model MUST require an explicit configuration and an explicit role. They MUST NOT default to a recently edited configuration, a bare model name, or any other implicit selection. Test stand-ins MAY skip real loading. Production commands MUST NOT use that bypass.
- **FR-009**: The configuration MUST be checked against the frozen policy before model construction and before network access. The check MUST refuse a missing role, an unresolved required field, a movable revision, a bad or incomplete file fingerprint, an access capability the model cannot provide, and a staged commitment past its deadline. The refusal MUST name the role, the field, and the rule.
- **FR-010**: Every new exclusion-gate report, checkpoint ledger row, cache record, training run, and evaluation run that depends on a model MUST record the study role, the configuration name, the configuration fingerprint, the model identity, the identity-schema version, and the governing specification revision.
- **FR-011**: A change of selected model MUST produce a new configuration fingerprint. The knowledge-exclusion gate and cache entries bound to the previous model identity MUST NOT be reused for the new model. Historical reports, ledgers, caches, and frozen tags MUST NOT be rewritten.
- **FR-012**: Under identity schema version 2, the model identity MUST depend on the concrete model and adapter bytes and on the runtime settings in the canonical identity definition, and MUST NOT depend on the friendly role name. The canonical settings remain the repository, the weight revision, the tokenizer revision, the precision, and the adapter fingerprint. Whether the attention setting joins that definition stays the open precision decision and is not settled here.
- **FR-013**: Historical identities MUST remain verifiable under identity schema version 1, including records whose identity was computed with the old role name inside the identity. New records MUST use identity schema version 2. Version 1 records MUST keep their original role key and MUST NOT be recomputed.
- **FR-014**: During the transition, `blocks_0_2` MUST resolve to `controlled_fact_base`, and `block_3_confirmation` MUST resolve to `pretrained_fact_confirmation`. Resolution MUST emit a deprecation notice that shows the new name. Alias resolution MUST happen before the role is used.
- **FR-015**: A document that contains both an old role name and its new name MUST be refused. The alias MUST NOT hide the clash. New configurations and new outputs MUST use only the new names. Legacy aliases MUST NOT be removed while any historical reader still needs them to interpret old inputs; after removal, already stored historical outputs MUST remain readable with the keys they carry.
- **FR-016**: Existing integrity rules MUST stay in force: immutable revisions only, file fingerprints checked before use, access-profile compatibility, amendment rather than silent edit, and fail-closed behavior on missing or unresolved input. This feature MUST NOT weaken them.

### Key Entities

- **Model role**: The scientific job a base model fills. The two roles are `controlled_fact_base` and `pretrained_fact_confirmation`. A role is not a block number, a checkpoint, or an evaluator.
- **Frozen model policy**: The specification document that defines required roles, their purposes, the identity facts a selection must supply, staged-commitment rules, and the integrity checks. It selects no concrete model. It belongs to a specification revision and changes only by amendment.
- **Versioned model configuration**: One named, immutable selection for a study stage. It fills one or more roles with a repository, revisions, variant, precision, attention setting, licence, and file fingerprints, or it marks a role as a staged commitment with a deadline. Replacing a selection creates a new configuration rather than editing an old one.
- **Configuration fingerprint**: The fingerprint of one complete configuration document. It changes if the document changes, including a role rename that leaves the model bytes unchanged.
- **Model identity**: The identity of the concrete model and adapter bytes plus the canonical runtime settings. Under the new identity version it does not include the friendly role name. Each stored identity carries an identity-schema version so older definitions remain checkable.
- **Provenance binding**: The set of facts a model-dependent result must carry: study role, configuration name, configuration fingerprint, model identity, identity-schema version, and governing specification revision.
- **Legacy alias**: A temporary reading of an old role label as its new name, accompanied by a deprecation notice. It is not a second role, and it is not written into new outputs.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A reader who has not seen the schedule can identify both roles' scientific jobs from a new configuration alone, on the first reading, and can do so for every new configuration in the study set.
- **SC-002**: After this split is published, the retrieved `spec-v1` model document is byte-for-byte the historical snapshot, and a concrete model change adds a new configuration instead of modifying that snapshot.
- **SC-003**: Every new model-dependent exclusion-gate report, ledger row, cache record, training run, and evaluation run carries all six provenance items. A sample missing any item fails review.
- **SC-004**: For a fixed model and fixed identity-relevant settings, changing only the role name leaves the version-2 model identity unchanged in every trial, and every pre-existing identity record still verifies under the version it was written with.
- **SC-005**: In every refused-configuration trial — missing role, unresolved field, movable revision, bad fingerprint, incompatible access, or expired staged commitment — the refusal happens before any model is constructed and before any network access, and the refusal names the role, field, and rule.
- **SC-006**: Production commands with no configuration named, or no role named, stop without loading a model in every such trial. No production trial silently adopts the most recently edited configuration.
- **SC-007**: Legacy inputs using either old role name load successfully during the transition and show the replacement name. Every document that contains both an old name and its new name is refused. Every newly written configuration and output uses only the new names.

## Assumptions

- The second role is the confirmation model named by execution-plan task P0-8 and decision D-47: the 7B–8B confirmation subset (plan task P6-8), not the model that carries the full pretrained stress test. The working name is therefore `pretrained_fact_confirmation`. Publishing that name in the new specification revision still requires the owner's confirmation. If the owner instead decides this role is the pretrained-fact base model, the published name becomes `pretrained_fact_base` and only the label and its purpose text change. The policy split, the shared vocabulary, the provenance rules, and the alias rules stay as specified here.
- `controlled_fact_base` is the Blocks 0–2 base model in P0-8 (decision D-46). Different study stages may select different concrete models for that same role. The current small debugging selection is one versioned configuration and is replaced before Block 1 by a new configuration, not by a new role name and not by an edit to `spec-v1`.
- The shared name for the weight revision is the name already required by the frozen checker (`model_revision`). The tokenizer revision keeps its own distinct name. Consumers that used a shorter private name adopt this vocabulary.
- Identity schema version 2 matches the canonical identity in FV-SPEC-093 and excludes the role name. Identity schema version 1 remains the definition under which any already stored identity, including one that folded in the role name, can still be verified. Attention implementation is recorded on every new configuration because D-48 requires it to be declared. D-48 stays open, so this feature does not add attention implementation to the identity payload.
- P0-8 today stores the concrete selection inside the frozen model document and requires an amendment to change that document (FV-SPEC-095). This feature amends that arrangement: the new specification revision freezes the policy, and each later model change is a new versioned configuration plus the existing downstream-rebinding rules. `spec-v1` itself is not edited. FV-SPEC-089 through FV-SPEC-094 continue to apply to whatever configuration a run names. Their fail-closed intent is unchanged.
- This feature does not select the Block 1 model or the pretrained-fact confirmation model, does not allow movable revisions or unpinned weights, does not weaken amendment, integrity, access-profile, or downstream-binding rules, and does not rewrite historical ledgers, caches, reports, or frozen specification tags.
- Both P0-8 and P2-0 are `draft`. Nothing in this specification promotes those notes to reviewed, and no requirement here is treated as implemented while D-46, D-47, D-48, or D-49 is open.
