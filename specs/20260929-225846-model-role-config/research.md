# Research: Model Role Names and Versioned Model Configuration

## Decision: Keep `models.yaml` bytes; add a policy file

- **Decision**: Do not modify `.factverify/spec/models.yaml`. Add `.factverify/spec/model_policy.yaml` as the normative policy. Concrete selections live under `config/models/`. This clone has no `spec-v1` git tag (`git tag -l` is empty). Immutability is a test that the working-tree file's SHA-256 stays equal to the digest recorded when implementation starts. If a `spec-v1` tag exists later, the same test also compares the file to `git show spec-v1:.factverify/spec/models.yaml`.
- **Rationale**: FR-005 requires the historical snapshot to stay retrievable. The ticket forbids a silent move. P0-8 (draft) currently stores the concrete pin in `models.yaml` and routes changes through an amendment (FV-SPEC-095). This feature is that amendment: the historical file stays, and later pins are new configuration files.
- **Alternatives considered**: Edit `models.yaml` in place and record an amendment. Rejected because the acceptance criteria require that file's bytes to remain the snapshot. Delete `models.yaml` from the working tree and rely on git history. Rejected because runners and the freeze list still name it, and the ticket says it remains retrievable as the historical artifact.

## Decision: One document shape

- **Decision**: Both the policy's expectations and every runtime configuration use a top-level `roles` mapping. The weight revision is `model_revision`. The tokenizer revision is `tokenizer_revision`. A resolved role also has `repo_id`, `variant` (`base` or `instruct`), `dtype`, `attn_impl`, `licence`, and `files`. File fingerprints are `sha256:` plus 64 hex characters, which is FV-SPEC-091. The loader stops comparing raw hex. A pending role has `status: pending` and `deadline`.
- **Rationale**: `.factverify/spec/models.yaml` and `tools/models_validator.py` already use `roles` and `model_revision`. `src/models/spec.py` and `scripts/prefetch_models.py` use a flat map and `revision`, so they cannot read the live artifact. The feature requires one parser. `src/models/spec.py` becomes that parser. The validator and prefetch call it.
- **Alternatives considered**: Teach the validator to accept the loader's flat shape. Rejected because the frozen artifact and FV-SPEC-089 already use `roles` and `model_revision`. Keep two parsers behind an adapter. Rejected because FR-006 requires one vocabulary.

## Decision: Identity schema version 2 is FV-SPEC-093; version 1 is the current loader

- **Decision**: New identities are schema version 2, computed exactly as `tools/models_validator.py` computes FV-SPEC-093 today:

  ```text
  json.dumps(
      {repo_id, model_revision, tokenizer_revision, dtype, adapter_digest},
      sort_keys=True,
      ensure_ascii=False,
  )
  ```

  Python's default separators apply (comma-space and colon-space). The stored value is `sha256:` plus the hex digest. `adapter_digest` is JSON `null` when there is no adapter. The role name is not a field. `attn_impl` is not a field.

  Version 1 reproduces `src/models/identity.py` as it exists today, for verification only:

  ```text
  json.dumps(
      {adapter_digest, attn_impl, base_repo, base_revision, dtype, role, tokenizer_revision},
      sort_keys=True,
      separators=(",", ":"),
  )
  ```

  The stored value is the hex digest with no prefix. `encode()` is UTF-8. New loads do not write version 1.

- **Rationale**: The two implementations already disagree. The drift note on the model loader records that. FR-012 says version 2 follows FV-SPEC-093 and excludes the role. A role rename therefore does not change a version-2 identity. Historical loader hashes included the role, so they verify only under version 1. Changing version 1's key names, separators, or prefix would make those hashes unverifiable.
- **Alternatives considered**: Make version 2 a compact JSON digest with no `sha256:` prefix, matching the loader's encoding. Rejected because the normative definition is the validator's FV-SPEC-093 encoding, including default separators and the prefix. Put `attn_impl` into version 2 because the current loader hashes it and D-48 is now closed. Rejected by FR-012. Attention remains a required declared field, and a change to it changes the configuration fingerprint (next decision), so a new run does not reuse a cache entry or a gate report from the other fingerprint.

## Decision: Configuration fingerprint is the raw file digest

- **Decision**: `model_config_digest` is `sha256:` plus the hex SHA-256 of the configuration file's bytes, via `src/data/digests.sha256_file`. It is not a hash of the parsed mapping. The cache key payload gains this digest next to the existing model-identity field. A role rename, an `attn_impl` edit, or any other byte change misses the cache. Old cache rows are not rewritten and are not migrated onto the new key.
- **Rationale**: FR-011 says a changed selection is a new fingerprint. Hashing parsed YAML would ignore comments, key order, and formatting, so an edited file could keep the old fingerprint. Including the digest in the cache key covers the case version 2 deliberately leaves out of the model identity (`attn_impl`, and the role name). A cache miss on a pure rename is a recompute, not a corrupted identity.
- **Alternatives considered**: Key the cache only on the model identity. Rejected because an attention-only change would reuse generations after version 2 stops hashing `attn_impl`. Semantic canonicalization of the YAML. Rejected because the ticket identifies the fingerprint with the configuration file.

## Decision: Block 0 debug configuration copies the current pin and sets `attn_impl: eager`

- **Decision**: `config/models/block0-debug-pythia-410m.yaml` copies `EleutherAI/pythia-410m` at revision `9879c9b5f8bea9051dcb0e68dff21493d67e9d4f`, tokenizer revision the same, `variant: base`, `dtype: float32`, `licence: Apache-2.0`, and `files: {}`. It adds `attn_impl: eager`. `pretrained_fact_confirmation` is `status: pending` with `deadline: null`. No Block 1 file is created. No confirmation model is invented. `config_id` is `block0-debug-pythia-410m-v1`.
- **Rationale**: D-46, D-48, and D-49 are closed in `docs/decisions/catalog.yaml`. The live `models.yaml` already records the Pythia pin, `base`, and `float32`. It does not record `attn_impl`. The loader cannot construct a resolved role without that field, and the ticket's worked example for this same debug file uses `eager`. Empty `files` stays empty: FV-SPEC-091 reports that as pending until download, and `load_model` still refuses to construct a model when `files` is empty. Prefetch does not invent a file list.
- **Alternatives considered**: Omit `attn_impl` until the owner names it. Rejected because the new configuration would then fail its own resolved-role rule, and the ticket already names `eager` for this debug file. Choose `bfloat16` because D-48's text says Block 1 uses it. Rejected because this file is the Block 0 debug pin, and Block 1 is out of scope.

## Decision: Commands name the configuration and the role

- **Decision**: `load_model(role, *, model_config, spec_root, adapter_path=None)` requires `model_config`. `spec_root` is still required, because the policy and the closure templates live there. `scripts/exclusion_gate.py` and `scripts/prefetch_models.py` gain a required `--model-config`. The exclusion gate's `--role` default of `blocks_0_2` is removed. Training job files gain a required `model_config` path. A test may still pass a stand-in model and skip `load_model`.
- **Rationale**: FR-008 forbids a silent default. The current gate default is the schedule label this feature is retiring.
- **Alternatives considered**: Default `--model-config` to `config/models/block0-debug-pythia-410m.yaml`. Rejected because a later edit to that file, or a second file, would be picked up without an explicit choice.

## Decision: Alias map lives on the policy

- **Decision**: The policy contains

  ```yaml
  role_aliases:
    blocks_0_2: controlled_fact_base
    block_3_confirmation: pretrained_fact_confirmation
  ```

  Resolution happens before the role is read. A document that contains both an alias and its target is refused, even when the two entries are identical. A successful alias resolution writes a deprecation line that contains both names. New outputs store the canonical role, not the alias. Catalog keys `model.blocks_0_2.identity` (D-46) and `model.block_3.identity` (D-47) are not renamed and are not duplicated.
- **Rationale**: FR-014 and FR-015. Principle 14 says a legacy id resolves to at most one semantic key, so a second key for D-46 or D-47 is illegal. The existing keys stay as historical identifiers.
- **Alternatives considered**: Rename the catalog keys to the new role names. Rejected because that either reassigns a key that already has a meaning or creates a second key for the same legacy id.

## Decision: Ledger and cache columns, without overloading existing ids

- **Decision**: `checkpoints.identity_hash` stays the checkpoint-row id. `checkpoints.role` stays the study role in the sense of reference, control, or candidate. New nullable columns on `checkpoints` and `evaluation_runs` are `study_role`, `model_config_id`, `model_config_digest`, `model_identity_hash`, and `identity_schema_version`. `spec_tag` is the governing specification revision and must equal the policy's `governing_spec_revision` on new writes. Cache `entries` gains the same five nullable columns. New writes fill them. Schema version stays `"1"`, using `ALTER TABLE` the way `decision_key` was added. No backfill.
- **Rationale**: FR-010. Overloading the checkpoint id would make two different identities share one column. The cache's existing `identity_hash` key field is already the model identity; the ledger's column of the same name is not.
- **Alternatives considered**: A new ledger schema version. Rejected because `ensure_schema` refuses anything other than `"1"`.

## Decision: Record the amendment; do not authorize it or tag it

- **Decision**: Append `AMD-001` to `preregistration.md` `amendment_log` with `authorized: false` and `post_hoc: false`. Recompute the frontmatter `digest` with `tools.freeze.compute_contract_digest`. Do not run `freeze.py --execute`. Do not create a git tag. `governing_spec_revision` in the policy is the string `spec-v2`, which is the proposed tag name and not a tag this feature creates. The drafted `deadline_before_final_access` is `2027-03-01`, the date shape already used by the valid amendment fixture. It has no scientific effect while `authorized` is false. The owner replaces that date and sets `authorized: true` before the amendment is in force.
- **Rationale**: The constitution's deviation policy requires an amendment entry and a new tag, and forbids rewriting an existing tag. No `spec-v1` tag exists here to move. Setting `authorized: true` or creating `spec-v2` would skip the owner. FV-SPEC-084 requires every amendment field, so the draft entry is schema-complete and explicitly unauthorized.
- **Alternatives considered**: Leave `preregistration.md` untouched and only add the policy file. Rejected because FR-005 says the split is introduced through the amendment protocol. Authorize the amendment inside this feature. Rejected because gates are stop points and the owner has not approved the tag.

## Decision: Second role name

- **Decision**: The policy uses `pretrained_fact_confirmation`. Its purpose text says it is the 7B–8B confirmation subset (execution plan P0-8 and P6-8, catalog D-47), not the model that carries the full pretrained stress test.
- **Rationale**: The feature spec's assumption, the execution plan, and the catalog title "Block 3 confirmation model" agree. D-47 stays open, so the role remains pending.
- **Alternatives considered**: `pretrained_fact_base`. Rejected unless the owner overrides the spec's assumption before implementation. A rename at that point changes the policy strings and the alias target only.
