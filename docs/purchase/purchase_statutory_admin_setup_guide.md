# Purchase Statutory Admin Setup Guide

Date: 2026-05-08

## Purpose

This guide explains what an admin or implementation team must configure before the Purchase Statutory workspace can be used smoothly.

It is written for:
- implementation consultants
- admins
- finance system owners
- support teams

## Business Objective

The Purchase Statutory workspace should be the compliance operating layer for purchase tax processes.

It depends on correct setup in:
- entity and financial year
- user access / RBAC
- purchase invoice process
- vendor tax master data
- withholding and GST-TDS setup
- statutory policy controls

If setup is incomplete, users may still open the screen, but results will be misleading or workflows will fail.

## Minimum Setup Checklist

Before training users, confirm all of the below.

### 1. Entity and Financial Year

Confirm:
- legal entity exists
- active financial year exists
- branch or subentity exists where needed
- users are mapped to the correct entity scope

### 2. Purchase Module Base Readiness

Confirm:
- purchase invoice entry is working
- goods and service invoice flows are available if both are used
- posting behavior is working
- invoice numbering is working
- invoice statuses move correctly through draft, confirm, post, cancel as applicable

### 3. Vendor Master Readiness

Confirm vendor records contain:
- vendor name
- vendor GSTIN where applicable
- PAN where applicable
- state and tax registration data
- withholding-relevant tax identity data

This is especially important for:
- GSTR-2B matching
- IT-TDS deductee snapshots
- GST-TDS handling
- Form 16A outputs

### 4. Tax and Compliance Setup

Confirm:
- TDS sections and rules are configured
- GST-TDS setup is configured where used
- invoice-level tax behavior is validated
- blocked ITC / ITC rules are understood for the entity

### 5. Statutory Permissions

Purchase Statutory should use dedicated permissions.

Confirm the correct users/roles have:
- `purchase.statutory.view`
- `purchase.statutory.manage`
- `purchase.statutory.approve`

Recommended role pattern:
- AP / Tax operator: `purchase.statutory.view` and `purchase.statutory.manage`
- approver / manager: `purchase.statutory.view` and `purchase.statutory.approve`
- admin / super admin: full access as needed

Do not rely only on general purchase invoice permissions for statutory workflow ownership.

### 6. Menu and Route Access

Confirm:
- Purchase Statutory menu is visible for authorized users
- route `purchasestatutory` opens correctly
- unauthorized users are blocked cleanly

### 7. File and Export Support

Confirm:
- file storage works for attachments and Form 16A uploads
- export formats download correctly
- CA pack export is allowed in the environment

## Screen-Level Readiness

### Overview

Confirm:
- summary cards load
- scope filters work
- no console or API errors occur on refresh

### GSTR-2B Match

Confirm:
- import batch API works
- rows can be opened
- auto-match works within correct scope
- manual row review works

### Reconciliation

Confirm:
- exception APIs return data
- mismatch explanation is understandable

### ITC Register

Confirm:
- ITC register loads for correct period
- filter values work
- statuses map correctly to invoice data

### Challan Ops

Confirm:
- challan draft create works
- eligible-line population works
- approval actions work
- deposit action works
- export works

### Returns

Confirm:
- return draft create works
- eligible-line loading works
- approval actions work
- file action works
- NSDL export works where applicable

### Form 16A / Evidence

Confirm:
- issue list opens
- issue action works
- official document upload works
- download works

## Recommended Role Mapping

### Role 1: Statutory Operator

Recommended access:
- view statutory
- manage statutory
- access purchase invoice view

Typical duties:
- import batches
- create drafts
- review mismatches
- deposit challans
- prepare returns

### Role 2: Statutory Approver

Recommended access:
- view statutory
- approve statutory

Typical duties:
- approve or reject challans
- approve or reject returns
- review closure notes

### Role 3: Admin / Support

Recommended access:
- full statutory permissions
- purchase setup access
- RBAC access

Typical duties:
- troubleshoot access issues
- check setup and scope mapping
- support exports and document handling

## Common Setup Mistakes

Avoid these issues:

- user has purchase invoice access but no statutory access
- vendor GSTIN or PAN is missing
- wrong subentity is used during review
- financial year is inactive or mismatched
- TDS sections exist but are not properly usable in invoice flow
- file storage is not ready for statutory documents
- users try to correct source invoice tax values inside statutory screens

## Pre-Go-Live Admin Smoke Test

An admin should run this mini smoke test:

1. Open Purchase Statutory as admin.
2. Confirm scope filters load.
3. Confirm overview cards load without API errors.
4. Import one small GSTR-2B batch.
5. Open batch rows.
6. Run auto-match.
7. Save one review note.
8. Create one draft challan.
9. Create one draft return.
10. Confirm one export works.

If all 10 succeed, the workspace is usually ready for user UAT.

## Support Troubleshooting Guide

### Problem: user cannot open Purchase Statutory

Check:
- role has `purchase.statutory.view`
- menu/route access is synced
- user belongs to the correct entity

### Problem: GSTR-2B import works but match fails

Check:
- request includes entity and financial year scope
- batch belongs to same entity/subentity
- purchase invoice exists with matching supplier details

### Problem: challan or return cannot move forward

Check:
- approval permissions
- maker-checker policy
- draft/approval/deposit prerequisites
- linked record status

### Problem: ITC or reconciliation looks wrong

Check:
- purchase invoice tax truth
- vendor master tax data
- GSTR-2B match status
- selected date range and subentity

### Problem: Form 16A upload/download fails

Check:
- filing is valid
- issue exists
- file storage is writable
- content type and file path handling are correct

## Final Admin Signoff

Before handing over to business users, confirm:
- setup is complete
- permissions are mapped
- routes open correctly
- one successful end-to-end smoke flow is completed
- UAT users and approvers are identified

## Companion Documents

Use this guide together with:
- `purchase_statutory_user_guide.md`
- `purchase_statutory_uat_checklist.md`
- `purchase-uat-signoff.md`
