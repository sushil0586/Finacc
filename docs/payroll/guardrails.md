# Payroll Guardrails

## Architectural Guardrails

These rules are non-negotiable for payroll changes.

### Do

- keep payroll workflow logic in payroll services
- keep accounting persistence behind posting adapters/services
- keep payment execution in the payments domain
- keep payroll operational reports separate from accounting reports
- preserve scope validation for `entity`, `entityfinid`, and `subentity`
- preserve effective-dated configuration resolution
- preserve immutable approved and posted runs
- preserve explicit reversal lineage
- add regression tests for every workflow or posting-affecting change

### Do Not

- do not bypass posting for accounting truth
- do not write journal lines directly from payroll views or models
- do not mix payment execution logic into payroll services
- do not mutate approved or posted payroll snapshots in place
- do not bypass entity scope validation
- do not hardcode ledgers in payroll calculation logic
- do not add country-specific payroll logic directly into generic run services without policy separation
- do not treat payment completion as equivalent to accounting posting
- do not import noisy legacy history into live payroll tables unless there is a clear compliance need

## Design Guardrails For Future Features

### Statutory features

Add statutory logic through policy/config layers, not generic workflow shortcuts.

### Country or state rules

Use policy separation and effective-dated configuration. Avoid branching generic run calculation on entity name or location flags.

### New payroll documents

Keep document lifecycle in payroll. Hand off accounting through posting. Hand off cash execution through payments.

### Corrections and off-cycle payroll

Extend explicit lineage and snapshot rules. Do not use silent edits to historical rows.

## Review Checklist For Payroll Changes

Before merging payroll changes, ask:

- does this preserve payroll vs posting vs payments boundaries?
- does this preserve scope safety?
- does this preserve immutability?
- does this preserve reversal integrity?
- does this preserve rollout and cutover safety?
- does this have service-level tests?

If any answer is no, stop and redesign the change before merging.
