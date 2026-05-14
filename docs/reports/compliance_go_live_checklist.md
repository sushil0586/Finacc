# Compliance Go-Live Checklist

Date: 2026-05-13  
Owner: Finance Ops + QA + Engineering + Implementation

## Objective

Use this checklist to move compliance workspaces to production safely with:
- predictable cutover steps
- clear go/no-go criteria
- rollback readiness
- operational ownership

## Scope

Modules:
- GST Exception Dashboard
- GSTR-1 vs GSTR-3B Reconciliation
- Controls Phase One (including compliance readiness block)
- Purchase Statutory (TDS readiness)
- TCS Statutory Workspace and Filing Pack exports
- Withholding Readiness Dashboard

## Roles

- Release Owner: drives final go/no-go call
- Finance UAT Owner: validates business outputs
- QA Owner: confirms regression and smoke test results
- Engineering Owner: handles deployment + rollback
- Support Owner: handles hypercare incidents

## Phase A: Pre-Go-Live (T-3 to T-1 days)

1. Code and migration freeze confirmed.
2. Compliance backend test slice is green.
3. Frontend build/typecheck is green.
4. UAT runbook is completed and signed off.
5. RBAC permissions are seeded and verified for:
- `reports.gst_exception_dashboard.view`
- `reports.gstr1_gstr3b_reconciliation.view`
- `reports.financial_hub.controls_phase_one.view`
- `purchase.statutory.view`
- `reports.tds.view` (readiness fallback)
- `compliance.tcs_statutory.view` and related TCS report permissions
6. Export paths validated in stage:
- GST exception CSV/XLSX/JSON
- GST reconciliation CSV/JSON
- TCS workspace ZIP
- TCS filing pack ZIP
7. Drilldown checks validated:
- source document opens correctly
- posted voucher drilldown opens posting detail
- non-posted rows show explicit guidance message

## Phase B: Go-Live Day (T0)

1. Confirm deployment window and communication posted.
2. Take pre-release DB backup snapshot.
3. Deploy backend and frontend artifacts.
4. Run migration commands and verify success.
5. Run post-deploy smoke checks (API + UI):
- controls hub opens
- GST exception opens with data
- GST reconciliation loads
- Purchase statutory opens
- TCS statutory opens
6. Run permission smoke for limited role:
- expected deny behavior returns controlled message (no forced logout loop)
7. Run export smoke:
- one file each from GST exception and GST reconciliation
- one ZIP each from TCS workspace and filing pack

## Phase C: Hypercare (T+1 to T+7 days)

1. Daily monitor:
- API 4xx/5xx rates on compliance endpoints
- export failures
- drilldown failures
- permission denied spikes
2. Daily finance check:
- one real entity/fy reconciliation sample
- one TDS readiness sample
- one TCS filing-pack sample
3. Capture top issues with:
- impact
- reproducibility
- owner
- ETA

## Go / No-Go Criteria

Go only if all are true:
1. All pre-go-live checks are complete.
2. Smoke checks pass in production after deployment.
3. Critical severity defects = 0.
4. Known medium issues have approved workaround.
5. Rollback plan validated and ready.

No-Go if any of the below:
1. Export mismatch on production smoke.
2. Drilldown integrity broken for posted vouchers.
3. Permission flow causes logout loop or user lockout.
4. Controls hub compliance actions route incorrectly.

## Rollback Plan

If rollback is required:
1. Stop new compliance operations (announce temporary freeze).
2. Revert frontend artifact to previous stable tag.
3. Revert backend release to previous stable tag.
4. Restore DB snapshot only if migration/data integrity issue exists.
5. Re-run smoke checks on rolled-back build.
6. Publish rollback completion note with impact window.

## Production Smoke URL Checklist

Use real production base URL and scoped query params.

- `/#/reports/compliance/gst-exception-dashboard`
- `/#/reports/compliance/gstr1-vs-gstr3b`
- `/#/reports/financial/controls-phase-one`
- `/#/purchasestatutory`
- `/#/tcsstatutory`

API smoke (authenticated):
- `/api/reports/gst-exception-dashboard/summary/`
- `/api/reports/gst-reconciliation/summary/`
- `/api/reports/controls/phase-one/meta/`
- `/api/withholding/withholding/reports/readiness/`
- `/api/withholding/tcs/workspace/transactions/`

## Sign-Off

Release Owner:  
Finance UAT Owner:  
QA Owner:  
Engineering Owner:  
Support Owner:  
Go-Live Date/Time:

