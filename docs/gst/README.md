# GST Reports Documentation Hub

Date: 2026-05-08

## Purpose

This folder contains the working documentation set for GST Reports.

Use this hub to quickly choose the right document based on the reader and purpose.

## Document Map

### 1. User Guide

File:
- `gst_reports_user_guide.md`

Best for:
- finance users
- tax users
- business reviewers

Use it when:
- training end users
- explaining the overall GST reporting flow
- showing what each GST report screen is used for

### 2. UAT Checklist

File:
- `gst_reports_uat_checklist.md`

Best for:
- QA teams
- finance testers
- implementation teams

Use it when:
- validating end-to-end report readiness
- checking data accuracy and export behavior
- capturing pass/fail evidence before go-live

### 3. Admin Setup Guide

File:
- `gst_reports_admin_setup_guide.md`

Best for:
- system admins
- implementation consultants
- support teams

Use it when:
- validating access and entity scope
- checking prerequisites for GSTR-1, GSTR-3B, and GSTR-9
- troubleshooting missing data or missing screen access

### 4. Frontend Refactor Guide

File:
- `gst_reports_frontend_refactor_guide.md`

Best for:
- frontend developers
- technical leads
- maintainers

Use it when:
- planning future cleanup of the GST report screens
- aligning screen shells and shared components
- reducing maintenance risk without changing user behavior

### 5. Reconciliation Framework Architecture

File:
- `gst_reconciliation_framework_architecture.md`

Best for:
- backend developers
- architects
- technical leads

Use it when:
- planning centralized GST reconciliation
- designing import, matching, and review workflows
- phasing rollout without breaking existing GST reports

### 6. Reconciliation UAT Checklist

File:
- `gst_reconciliation_uat_checklist.md`

Best for:
- QA teams
- pilot testers
- implementation teams

Use it when:
- validating the reconciliation workflow end-to-end
- checking reviewer actions and permission safety
- preparing controlled rollout evidence

### 7. Reconciliation Performance And UAT Hardening

File:
- `gst_reconciliation_performance_uat.md`

Best for:
- backend developers
- implementation leads
- support teams

Use it when:
- benchmarking large runs
- reviewing slow endpoints
- validating performance during pilot

### 8. Reconciliation Rollout Readiness

File:
- `gst_reconciliation_rollout_readiness.md`

Best for:
- release owners
- support leads
- deployment teams

Use it when:
- preparing deployment
- checking permissions and rollback steps
- reviewing known limitations before pilot

### 9. Reconciliation UAT Signoff Tracker

File:
- `gst_reconciliation_uat_signoff_tracker.md`

Best for:
- QA teams
- business testers
- project managers

Use it when:
- tracking pass/fail signoff
- collecting pilot evidence
- closing UAT

### 10. Reconciliation Pilot Readiness

File:
- `gst_reconciliation_pilot_readiness.md`

Best for:
- project managers
- support owners
- pilot coordinators

Use it when:
- deciding pilot user access
- planning pilot data scope
- setting issue categories and support process

## Recommended Reading Order

For business users:
1. `gst_reports_user_guide.md`
2. `gst_reports_uat_checklist.md`

For admins and support:
1. `gst_reports_admin_setup_guide.md`
2. `gst_reports_uat_checklist.md`

For future frontend engineering work:
1. `gst_reports_frontend_refactor_guide.md`
2. `gst_reports_user_guide.md`

For backend GST reconciliation work:
1. `gst_reconciliation_framework_architecture.md`
2. `gst_reconciliation_uat_checklist.md`
3. `gst_reconciliation_performance_uat.md`
4. `gst_reconciliation_rollout_readiness.md`

## Suggested Handover Pack

If you are sharing GST Reports with a customer or internal finance team, send:
- User Guide
- UAT Checklist
- Admin Setup Guide

## Notes

- GST Reports are reporting and compliance outputs, not source transaction-entry screens.
- If report values look incorrect, first verify invoice posting, tax setup, financial year scope, and entity/subentity selection.
- GSTR-1, GSTR-3B, and GSTR-9 should be treated as related but separate reporting workspaces.
- GST Reconciliation is a separate pilot-capable workspace and should not be used as a reason to retire old GST reports or purchase statutory screens prematurely.
