# GST Reconciliation Pilot Readiness Notes

Date: 2026-05-20

## Purpose

Use this document to decide who should receive pilot access, what data they should test, and how support should handle issues during controlled rollout.

## Who Should Get Access

Recommended pilot users:
- 1 finance process owner
- 1 operational reviewer
- 1 backup reviewer or support owner
- 1 implementation/admin user with manage permission

Do not start with:
- all finance users
- all branches
- all entities
- customer self-service wide release

Recommended pilot roles:
- reviewer: `gst.reconciliation.view` + `gst.reconciliation.review`
- pilot admin: `gst.reconciliation.view` + `gst.reconciliation.review` + `gst.reconciliation.manage`

## What Data They Should Test

Best pilot data set:
- one real entity
- one real GST registration
- one live-like return period
- one manageable but meaningful `GSTR-2B` file
- a mix of:
  - matched invoices
  - missing in books
  - amount mismatch
  - low confidence matches
  - ignored cases
  - accepted mismatch cases

Avoid for first pilot:
- too many entities at once
- too many return periods at once
- archived or incomplete accounting data

## Known Limitations To Share Up Front

- async matching hook exists but is not wired by default
- no action-log archival policy yet
- reviewer picker is still UI-side
- no dedicated telemetry dashboard yet
- this pilot does not replace old GST report workflows

## Support Process

Pilot support owner should capture:
- user
- entity
- return period
- run id
- item id if applicable
- action attempted
- API timing if visible
- screenshot and exact error message

Recommended escalation order:
1. functional reviewer issue
2. support owner triage
3. backend/product technical review

## Issue Categories

Use consistent labels:
- `GST-RECON-ACCESS`
- `GST-RECON-IMPORT`
- `GST-RECON-MATCH`
- `GST-RECON-BULK`
- `GST-RECON-PERF`
- `GST-RECON-UI`
- `GST-RECON-REPORT-REGRESSION`
- `GST-RECON-DATA`

## Pilot Exit Criteria

Pilot can move to broader rollout when:
- permission model works as expected
- imports are stable on real files
- reviewers can complete end-to-end workflow
- no blocking regression is found in old GST reports or purchase statutory flow
- performance is acceptable for target run sizes
- open issues are understood and triaged
