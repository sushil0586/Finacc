# GST Reports Admin Setup Guide

Date: 2026-05-08

## Purpose

This guide is for admins, implementation teams, and support users.

Use it to confirm that GST Reports are ready for business use and that users can access the correct screens with the correct scope.

## Scope of This Guide

This guide covers:
- access readiness
- entity and financial year prerequisites
- basic transaction prerequisites
- report-specific setup expectations
- support checks for common access and data issues

## GST Report Areas Covered

- GSTR-1
- GSTR-3B
- GSTR-9

## Core Preconditions

Before users can rely on GST Reports, confirm:

### 1. Entity Setup Exists

Check that:
- the entity exists
- the entity is active
- GST registration details are correctly stored

### 2. Financial Year Setup Exists

Check that:
- the relevant financial year exists for the entity
- users are selecting the intended year

### 3. Subentity or Branch Setup Exists

If branch-level reporting is used, check that:
- subentities exist
- the user has access to the right branch scope

### 4. Source Transaction Flow Is Active

GST Reports depend on:
- posted sales invoices
- posted purchase invoices
- correct tax classification in source documents

If source transactions are incomplete, GST Reports will not be reliable.

## Access and Permission Setup

### Required Principles

GST report access should be controlled by:
- authenticated user access
- entity-level permission
- report route permission
- branch or subentity access where applicable

### Practical Check

Confirm that intended users can access:
- `gstreport`
- `gstr3breport`
- `gstr9report`

If access was recently changed:
- ask the user to log out and log back in
- re-check role and entity assignment

### Admin Sanity Check

If a user says a screen is missing:

1. verify role assignment
2. verify entity assignment
3. verify active permission
4. verify menu visibility
5. verify the user is testing in the correct entity

## Source Data Setup Expectations

### Sales Data

For GSTR-1 and part of GSTR-9, sales-side setup should be correct:
- customer GSTIN
- place of supply
- document type
- note linkage
- inter-state and intra-state treatment

### Purchase Data

For GSTR-3B and part of GSTR-9, purchase-side setup should be correct:
- purchase invoice posting
- tax amounts
- ITC treatment
- reverse charge treatment where applicable

## Report-Specific Admin Checks

### GSTR-1

Confirm:
- users can load summary
- section views open
- invoice drilldown works
- export works
- validations return cleanly

### GSTR-3B

Confirm:
- the route opens
- summary data loads for valid periods
- export works
- permission is aligned with reporting access

### GSTR-9

Confirm:
- meta, summary, tables, validations, and export work
- freeze workflow works if enabled for the process
- filing-support endpoints work for authorized users

## Common Support Cases

### Case 1: User Can Log In but Cannot Open a GST Screen

Check:
- missing route permission
- missing entity access
- stale session or cached menu

### Case 2: Screen Opens but Data Is Blank

Check:
- period filters
- financial year
- entity and branch scope
- whether source transactions are posted

### Case 3: Totals Look Incorrect

Check:
- source invoice correctness
- GSTIN and POS correctness
- tax regime
- note linkage
- branch and year selection

### Case 4: Export Does Not Match Expected Totals

Check:
- same filters were used in UI and export
- the user exported the intended report and section
- no draft or missing source data is affecting totals

## Recommended Pre-Go-Live Validation

Before rollout, complete:

1. admin access validation
2. finance-user access validation
3. sample report review for one month
4. sample report review for one year
5. export validation
6. cross-check with source invoices

## Suggested Support Checklist

When troubleshooting GST Reports, support should record:
- user name
- entity
- financial year
- subentity or branch
- report name
- exact filters used
- whether the issue is access, blank data, wrong totals, or export mismatch

## Notes

- GST Reports should be treated as a reporting layer, not a transaction-entry layer.
- Most report issues originate in source data or scope selection, not in the report screen itself.
- Permission changes may require a fresh login before the UI reflects them correctly.
