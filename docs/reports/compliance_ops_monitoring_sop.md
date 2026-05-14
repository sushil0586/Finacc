# Compliance Ops Monitoring SOP

Date: 2026-05-13  
Owner: Support Ops + Engineering + Finance Ops

## Objective

Define daily monitoring and incident handling for compliance workspaces after go-live.

## Monitoring Window

- Hypercare: first 7 days (hourly checks in business hours)
- Steady state: daily checks (start-of-day + mid-day + end-of-day)

## Critical Endpoints

- `/api/reports/gst-exception-dashboard/summary/`
- `/api/reports/gst-exception-dashboard/export/`
- `/api/reports/gst-reconciliation/summary/`
- `/api/reports/gst-reconciliation/export/`
- `/api/reports/controls/phase-one/meta/`
- `/api/withholding/withholding/reports/readiness/`
- `/api/withholding/tcs/workspace/transactions/`
- `/api/withholding/tcs/workspace/transactions/export/`
- `/api/withholding/tcs/reports/filing-pack/export/`

## Daily Monitoring Checklist

1. API health:
- 5xx rate on compliance endpoints
- unusual 4xx spikes (especially 403 and 400)

2. Export health:
- failed export count
- average export response time
- ZIP/CSV corruption reports

3. Drilldown integrity:
- source document navigation errors
- posting drilldown failures
- “voucher not posted” complaints where posting should exist

4. Permission behavior:
- denied access should show controlled message
- verify no logout-loop incidents

5. Business sanity checks:
- one GST exception sample
- one GST reconciliation sample
- one TDS readiness sample
- one TCS workspace sample

## Alert Thresholds

Trigger incident if any condition is met:
- compliance endpoint 5xx > 2% for 15 minutes
- export failure > 5 in 30 minutes
- permission-denied spike > 3x baseline in 1 hour
- repeated drilldown failure on same module/entity

## Incident Severity

- Sev1:
  - data loss/corruption risk
  - all exports failing
  - all compliance pages inaccessible
- Sev2:
  - one critical module unavailable
  - widespread 403 misconfiguration
- Sev3:
  - isolated route/filter bug with workaround

## Triage Flow

1. Confirm incident scope:
- module, entity, FY, user role, timestamp

2. Reproduce with:
- admin user
- affected business role

3. Classify source:
- RBAC config
- API regression
- data issue
- frontend navigation/state issue

4. Apply immediate workaround:
- permission hotfix
- retry-safe fallback path
- temporary export path guidance

5. Escalate with evidence:
- failing endpoint + payload
- screenshot/video
- user impact count

## Ownership Matrix

- First response: Support Ops
- Technical triage: Engineering
- Data validation: Finance Ops
- Business communication: Implementation Lead

## Communication Template

Use this message in incident channel:

`[Compliance Incident]`
- Module:
- Severity:
- Start time:
- Impact:
- Affected entities/FY:
- Current status:
- Next update ETA:

## Closure Criteria

Incident can close only when:
1. Fix deployed or config corrected.
2. Reproduction steps no longer fail.
3. At least one real user confirms recovery.
4. Root cause and preventive action are documented.

