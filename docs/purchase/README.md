# Purchase Documentation Hub

Date: 2026-05-08

## Purpose

This folder contains the working documentation set for the Purchase Statutory module.

Use this hub to quickly choose the right document based on the reader and purpose.

## Document Map

### 1. User Guide

File:
- `purchase_statutory_user_guide.md`

Best for:
- Accounts Payable users
- Tax operators
- Finance reviewers

Use it when:
- training end users
- explaining the full business flow
- showing what each section of the screen does

### 2. UAT Checklist

File:
- `purchase_statutory_uat_checklist.md`

Best for:
- QA teams
- finance testers
- implementation teams

Use it when:
- running go-live validation
- recording pass/fail evidence
- checking end-to-end statutory workflow coverage

### 3. Admin Setup Guide

File:
- `purchase_statutory_admin_setup_guide.md`

Best for:
- system admins
- implementation consultants
- support teams

Use it when:
- setting up entity and user access
- validating statutory readiness
- troubleshooting missing access or setup issues

### 4. UAT Signoff

File:
- `purchase-uat-signoff.md`

Best for:
- project leads
- business owners
- implementation managers

Use it when:
- capturing final approval
- recording completion status
- closing implementation/UAT formally

### 5. Frontend Refactor Guide

File:
- `purchase_statutory_frontend_refactor_guide.md`

Best for:
- frontend developers
- technical leads
- maintainers

Use it when:
- planning to break the large Purchase Statutory screen into smaller components
- reducing future maintenance risk
- sequencing safe refactor work without disturbing business flow

## Recommended Reading Order

For business users:
1. `purchase_statutory_user_guide.md`
2. `purchase_statutory_uat_checklist.md`

For admins and support:
1. `purchase_statutory_admin_setup_guide.md`
2. `purchase_statutory_uat_checklist.md`

For future frontend engineering work:
1. `purchase_statutory_frontend_refactor_guide.md`
2. `purchase_statutory_user_guide.md`

For project closure:
1. `purchase_statutory_uat_checklist.md`
2. `purchase-uat-signoff.md`

## Suggested Handover Pack

If you are sharing this module with a customer or internal finance team, send:
- User Guide
- UAT Checklist
- Admin Setup Guide

If you are closing implementation formally, also include:
- UAT Signoff

## Notes

- The Purchase Statutory screen is a compliance operations workspace.
- It should not be treated as the original source of truth for invoice tax values.
- If statutory results look wrong, first verify the purchase invoice, vendor setup, and entity scope.
