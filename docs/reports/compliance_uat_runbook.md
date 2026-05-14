# Compliance UAT Runbook

Date: 2026-05-13  
Owner: Finance + QA + Implementation

## Objective

Run end-to-end UAT for compliance and controls with repeatable checks for:
- GST exception and reconciliation readiness
- TDS/TCS readiness and workflow visibility
- Controls hub action routing
- Drilldowns, exports, and permission behavior

## UAT Scope

In scope pages:
- `/#/reports/compliance/gst-exception-dashboard`
- `/#/reports/compliance/gstr1-vs-gstr3b`
- `/#/reports/financial/controls-phase-one`
- `/#/purchasestatutory`
- `/#/tcsstatutory`

In scope APIs:
- `reports_api:gst-exception-dashboard-summary`
- `reports_api:gst-exception-dashboard-export`
- `reports_api:gst-reconciliation-summary`
- `reports_api:gst-reconciliation-export`
- `reports_api:controls-phase-one-meta`
- `withholding:withholding-report-readiness`
- `withholding:tcs-workspace-transactions`
- `withholding:tcs-workspace-transactions-export`
- `withholding:tcs-report-filing-pack-export`

## Preconditions

1. Entity + FY + subentity are configured.
2. Test users exist with role variants:
- `compliance_admin` (full access)
- `compliance_reviewer` (view + export)
- `compliance_limited` (menu-visible but missing one required permission)
3. Sample data includes:
- at least one GST warning row
- at least one GST reconciliation mismatch or advisory
- one posted voucher and one unposted voucher in TDS/TCS contexts
- one TCS pending collection or pending deposit case

## Execution Matrix

Status codes:
- `P`: Pass
- `F`: Fail
- `N/A`: Not applicable for this environment

Capture evidence for each row:
- screenshot
- API response snippet or export file sample
- tester initials + timestamp

## Section A: GST Exception Dashboard

1. Open GST exception dashboard with default FY scope.
- Expected:
  - summary cards render
  - tabs render
  - warning table renders if data exists

2. Apply focus route: `focus=blockers` and `tab=1`.
- Expected:
  - `Focused: Blockers` label appears
  - info-only rows are excluded from blocker focus

3. Apply focus route: `focus=reconciliation` and `tab=3`.
- Expected:
  - `Focused: Reconciliation Gaps` label appears
  - reconciliation grid is selected

4. For a row with posting drilldown:
- Click `Open Posting`.
- Expected:
  - posted row opens posting detail
  - unposted row shows clear message (`Invoice not posted` / equivalent)

5. Export CSV and JSON.
- Expected:
  - CSV downloads
  - JSON response contains `overview`
  - exported rows match current scoped data

## Section B: GSTR-1 vs GSTR-3B Reconciliation

1. Open reconciliation page with FY and period filters.
- Expected:
  - summary cards render (`Checks Compared`, `Matched`, `Actionable Mismatches`)

2. Verify advisory vs actionable behavior.
- Expected:
  - advisory rows are marked informational
  - mismatch counts align with summary

3. Export CSV.
- Expected:
  - file generated
  - contains reconciliation labels (for example `Outward Taxable Supplies`)

## Section C: Controls Hub

1. Open controls phase-one page.
- Expected:
  - compliance readiness block visible
  - actions list visible under compliance readiness

2. Click each compliance action link:
- GST blockers
- GST reconciliation gaps
- Purchase statutory blocked/fix-now
- TCS blocked/pending collection/pending deposit/missing section (when present)
- Expected:
  - route opens with expected query params
  - target page shows corresponding focused label/filter state

3. Validate deny behavior with limited user.
- Expected:
  - no logout redirect
  - permission-denied guidance message/page appears

## Section D: Purchase Statutory (TDS Readiness)

1. Open with route filters:
- `workspace=overview`
- `readiness_status=blocked`
- `tax_type=IT_TDS`
- Expected:
  - readiness filter applies
  - focus badge appears (`Focused: Blocked`)

2. Validate row actions:
- `Open Source`
- `Open Posting`
- Expected:
  - source opens voucher/invoice route
  - missing posting shows user-readable message, not silent failure

3. Search + reset + period filters.
- Expected:
  - table updates and clears correctly
  - no stale counters after refresh

## Section E: TCS Statutory Workspace

1. Open with query context:
- `readiness=blocked`
- `workspace_status=COMPUTED_PENDING_COLLECTION`
- Expected:
  - focus label matches active context
  - row set matches selected status/filter

2. Validate pending lifecycle actions.
- Expected:
  - pending collection and pending deposit paths are distinguishable
  - row next-step labels are actionable

3. Validate workspace export ZIP.
- Expected:
  - ZIP contains:
    - `workspace_transactions.csv`
    - `workspace_section_summary.csv`
    - `workspace_unallocated_deposits.csv`
    - `workspace_meta.csv`

4. Validate filing pack export ZIP.
- Expected:
  - ZIP contains management summary, transaction, exception spotlight, return tracker, section summary, header files

## Section F: RBAC Validation

Use `compliance_limited` user:

1. Access each API/page where permission is intentionally missing.
- Expected:
  - HTTP `403` from APIs
  - frontend permission guidance behavior (no forced logout)

2. Confirm allowed pages still open where permission exists.
- Expected:
  - partial access works as configured

## Sign-Off Checklist

Mark each item:
- GST exception and reconciliation UAT complete
- Controls action routing complete
- Purchase statutory readiness complete
- TCS workspace + export complete
- RBAC deny/allow scenarios complete
- Drilldown trust checks complete
- Export parity checks complete

Final sign-off fields:
- Finance Lead:
- QA Lead:
- Implementation Owner:
- Date:

## Exit Criteria

UAT is complete when all are true:
1. No critical blocker remains open.
2. All export checks match scoped UI intent.
3. All drilldowns either navigate correctly or show explicit user guidance.
4. Permission failures return controlled deny behavior (not logout redirects).
5. Sign-off checklist is fully approved.

