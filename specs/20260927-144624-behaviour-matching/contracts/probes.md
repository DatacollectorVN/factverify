# Contract: matching probes

**Feature**: `20260927-144624-behaviour-matching`

## Authorization

D-58 `status: closed` is required before the manifest is read as the matching set. An open or missing row raises `ControlError("D-58")` and does not call the behavior port. The decision row does not itself list probe text. The match document's `probes` path is the manifest.

## Manifest

YAML list under `probes`. Empty list raises `ControlError("probes")`.

```yaml
probes:
  - probe_id: p1
    fact_id: fact-1
    template_group_id: direct_construction
    split: construction
    kind: direct_qa
```

| Check | Refusal name |
|-------|----------------|
| `kind` other than `direct_qa` | `kind` |
| `fact_id` differs from the match | `fact_id` |
| `split` is `final_test` or `final-test` | `split` |
| Duplicate `probe_id` | `probe_id` |
| `template_group_id` missing from `spec_root/closure_templates.yaml` `groups` | that group id |
| That group's `split` is `calibration` or `final_test` | that group id |

Construction groups are eligible. Calibration and final-test groups are evaluation template groups.

## Spec file

The runner reads `{spec_root}/closure_templates.yaml` and the `groups` sequence. Each group needs `group_id` and `split`. A missing file raises `ControlError` naming `closure_templates.yaml`. The file is not written.

Fixture roots under `tests/fixtures/controls/match/spec/` carry a small `groups` list with one construction group, one calibration group, and one final-test group. Study runs pass the frozen spec root. Neither path edits the frozen file.

## Read record

After the checks, the behavior port is called with the manifest's probe ids only. Reference calls use `severity=None`. Control calls use each declared severity in order. The port's `outputs` are stored on `reads`. A probe id in those outputs that is not in the manifest raises `ControlError` naming that id.

The port is not a `Gateway`. `match.py` does not import `src.eval.gateway` or `src.eval.budget`. A config key `budget`, `verdict`, `evaluator_score`, or `evaluator_output` raises before the port is called.
