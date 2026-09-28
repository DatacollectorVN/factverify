# Contract: control label

**Feature**: `20260927-130846-fake-unlearning-controls`  
**Date**: 2026-09-27  
**File**: `control.json` written under the config `output_dir`

The label is the record FV-CTRL-002 and FV-CTRL-003 require. Field rules are in `data-model.md` ControlLabel. This contract fixes the file name and the identifiability rule the evaluator already consumes.

---

## File

- Written only for `status: accepted`.
- Pretty-printed JSON, UTF-8, keys in the order listed in `data-model.md`.
- `oracle_label` is the JSON string `negative`. No other value is written.
- `mechanism_layer` is exactly one of:
  - `prompt/serving`
  - `output post-processing`
  - `logits`
  - `activations`
  - `weights`
- `expected_identifiability` is present only for an accepted `output_filter` built against a Profile A spec root, and its value is `structurally_indistinguishable`.
- A second mechanism layer, a missing provenance field (`config_hash`, `seed`, `split`, `spec_revision`), or an `oracle_label` other than `negative` is a failed load.

---

## Profile A check

Read `access_profile.md` frontmatter from `spec_root`:

- `profile` must be `A`
- candidate `capabilities.text` must be `verified`
- candidate `capabilities.scores` must not be `verified`
- candidate `capabilities.internals` must not be `verified`

If those hold, the output-filter label includes `expected_identifiability`. If the file is Profile A but the capabilities differ, the build raises and names `access_profile.md`. Other profiles are not given a substitute expectation.

---

## Rejection file

When a check fails numerically, `rejection.json` is written instead, with the fields in `data-model.md` RejectionRecord. It has no `oracle_label`. `load_control` on that path raises.
