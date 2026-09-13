# HRMS And Payroll Product Backlog

Status: Deferred until purchase-to-pay production certification is complete.

This backlog records product gaps identified during the HRMS and payroll end-user walkthrough. These items are deliberately excluded from the active purchase-to-pay release scope.

## Guided Customer Onboarding

- Provide one guided journey from HRMS template adoption through organization setup, employees, contracts, payroll profiles, salary assignments, statutory setup, accounting mappings, and readiness sign-off.
- Expose clear progress, blockers, owners, and direct correction actions for every onboarding prerequisite.

## Accounting Configuration

- Add entity-facing editors for effective-dated `PayrollLedgerPolicy` records.
- Add entity-facing editors for `PayrollComponentPosting` mappings.
- Preserve finance approval, scope validation, effective dates, version history, and posting-preview validation.

## Employee Self-Service

- Replace the reimbursement placeholder with employee claim create, evidence upload, approval, reimbursement, and payroll/accounting integration.
- Replace the payroll attendance-summary placeholder with an employee-safe attendance summary API or converge it with the working HRMS My Attendance view.
- Complete employee tax-declaration submission and evidence workflows wherever the backend currently returns placeholder state.
- Replace the employee FnF placeholder with an employee-safe settlement statement and status view.

## Administrator Operations

- Add a dedicated administrator FnF workbench over the existing calculation, approval, posting, payment, and reporting APIs.
- Replace placeholder bank-upload behavior with approved bank-specific formats or a governed payment-provider integration.
- Add recruitment, candidate/offer management, joining-document workflows, performance management, and learning management only as separately scoped product modules.

## Acceptance Gate

Each item requires backend service and permission tests, Angular unit coverage, Playwright role/scope workflows, accounting reconciliation where applicable, mobile/accessibility review, and staging evidence before its status changes from backlog.
