# Capital Distribution Production Runbook

## Scope

This runbook covers Wave 1 proprietorship, partnership, and LLP migration,
calculation, posting, reporting, reversal, and tax-working support.

## First Response

1. Obtain the `X-Correlation-ID` response header or the correlation ID shown in the
   structured error response.
2. Confirm entity, financial year, branch, user, action, and occurrence time. Never
   ask support staff to collect passwords, access tokens, or full request payloads.
3. Query `GET /api/capital-distribution/operations/health/` with the same entity,
   `entityfinid`, and optional `subentity` scope.
4. Search capital-distribution audit events by correlation ID. Match the operation,
   status code, error code, actor, and duration before taking corrective action.
5. Confirm the appropriation statement, P&L disclosure, Balance Sheet disclosure,
   trial balance, and destination ledger before closing a posting incident.

## Health Interpretation

- `healthy`: no stale runs, aging workflow actions, or recorded failures in the last
  24 hours for the requested scope.
- `attention`: at least one stale run, action older than 24 hours, or recent failed
  operation requires review. It is not by itself proof of incorrect books.
- `stale_count`: frozen source data changed after calculation. Recalculate; do not
  force the existing run through approval or posting.
- `aging_action_count`: calculated, submitted, or approved work has remained pending
  for more than 24 hours. Confirm ownership and either continue or cancel it.
- `latency_ms`: timing samples from recent audited operations. Compare repeated runs
  in the same scope before escalating a performance incident.

## Recovery Rules

- Validation failure: correct the named input and retry with the same idempotency key
  only when the business input is unchanged.
- HTTP 401/403: restore authentication or scope/role assignment. Do not broaden a
  user's entity or branch access merely to bypass the error.
- HTTP 409: reload the current object and review changes before resubmitting.
- HTTP 500: retry once after checking health. Escalate with the correlation ID if it
  repeats; never recreate or post a replacement run until the original state is known.
- Interrupted calculation: query by idempotency key. Reuse the result when present;
  otherwise retry the identical request.
- Interrupted posting: reload the run and posting batch. A posted run is an idempotent
  success; do not post a second run for the same period.
- Incorrect posted run: use the governed reversal action with a meaningful reason.
  Verify effective appropriation returns to zero before calculating a replacement.
- Migration issue: keep activation disabled, correct profile/policy/mappings, rerun
  preview and prepare, and enable only after readiness is complete.

## Reconciliation Gate

A support case is resolved only when:

- original and reversal journals are individually balanced;
- appropriation statement reconciliation has no exception;
- posted equity movement agrees between P&L and Balance Sheet disclosures;
- trial balance debit equals credit;
- owner or partner destination ledgers agree with the frozen run; and
- entity, financial-year, and branch scopes are unchanged.

## Data Retention

Audit events, frozen policies, calculations, tax workings, posting batches, and
reversals are accounting evidence. The recommended default is seven financial years,
subject to the entity's statutory and contractual retention policy. Do not hard-delete
posted or reversed evidence. Failure events store operational metadata and correlation
IDs, not request bodies or credentials. Any purge process must be approved, scoped,
logged, reversible where required, and tested against report reproducibility.

## Escalation Evidence

Provide correlation ID, scoped health response, run/policy/working IDs, timestamps,
status transitions, reconciliation result, and relevant posting batch IDs. Redact PAN,
GST credentials, tokens, passwords, and unrelated customer data.
