---
aggregation_policy:
  raw_maximum_role: diagnostic_only
case_decision:
  acceptance_requires:
    - excess_recovery_bounds_held
    - locality_bounds_held
    - access_completeness_conditions_met
    - no_disqualifying_confirmed_witness
  no_witness_is_not_accept: true
  status_alignment:
    mapping:
      non_identifiable: non_identifiable
      incomplete: incomplete
      confirmed_recovery: confirmed_recovery
      accept: conformance
confirmation_routes:
  A:
    enabled: true
  B:
    enabled: false
  C:
    enabled: false
blocking_decisions: []
---
# Fixture witness rule.
