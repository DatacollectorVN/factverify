# Contract: Frozen Model Policy

**Feature**: `20260929-225846-model-role-config`
**File**: `.factverify/spec/model_policy.yaml`

## Document

```yaml
schema_version: "1"
governing_spec_revision: spec-v2
identity_schema_version: 2

required_roles:
  controlled_fact_base:
    purpose: >-
      Base pretrained model for controlled-fact training, unlearning,
      retain-only references, candidates, and fake-unlearning controls.
    required_capabilities:
      - offline_weights
      - tokenizer
      - parameter_updates
  pretrained_fact_confirmation:
    purpose: >-
      7B–8B model for the pretrained-fact confirmation subset.
      Not the model that carries the full pretrained stress test.
    required_capabilities:
      - offline_weights
      - tokenizer
    staged_commitment: true

required_identity_fields:
  - repo_id
  - model_revision
  - tokenizer_revision
  - variant
  - dtype
  - attn_impl
  - licence
  - files

role_aliases:
  blocks_0_2: controlled_fact_base
  block_3_confirmation: pretrained_fact_confirmation
```

## Checks

1. The file parses as a mapping with `schema_version` `"1"`.
2. Both required roles are present and have non-empty purposes.
3. `required_identity_fields` is exactly the list above.
4. The document contains no `repo_id`, no 40-character revision, and no non-empty `files` map.
5. Alias targets are required roles. Alias keys are not required roles.
6. `.factverify/spec/models.yaml` bytes match the digest stored by the immutability test.

## Amendment entry

Append this object to `amendment_log` in `.factverify/spec/preregistration.md`. Then set `digest` to the return value of `tools.freeze.compute_contract_digest`. Do not hand-edit the digest.

```yaml
- id: AMD-001
  trigger: >-
    Concrete model selections need to change without editing the historical
    model snapshot.
  allowed_information: >-
    Protocol structure only. No exclusion-gate scores, calibration outcomes,
    or final-test outcomes.
  approver: "study owner"
  deadline_before_final_access: "2027-03-01"
  effect_size_link: "margins.yaml#minimum_fcr_reduction_absolute"
  sample_size_link: "margins.yaml#sample_size_handoff"
  previous_value: "Concrete pins live in .factverify/spec/models.yaml."
  new_value: >-
    Policy lives in .factverify/spec/model_policy.yaml. Concrete selections
    live in config/models/. Effect size and sample size are unchanged.
  authorized: false
  post_hoc: false
```

`authorized` stays false. No git tag is created. The owner replaces `deadline_before_final_access` if they want a different date, then sets `authorized: true` and tags `spec-v2` themselves.

## Freeze list

`tools/freeze.py` `SPEC_ARTIFACTS` includes `model_policy.yaml` and still includes `models.yaml`.
