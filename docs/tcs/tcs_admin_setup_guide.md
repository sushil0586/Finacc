# TCS Admin Setup Guide

Date: 2026-05-08

## Purpose

This guide explains what admins and implementation teams must set up before the TCS module can be used reliably.

It is written for:
- implementation consultants
- admins
- finance system owners
- support teams

## Business Objective

The TCS module should work as the compliance operating layer for TCS collection, deposit, and quarterly review.

If setup is incomplete, users may still open the screens, but results will be misleading or workflow steps will fail.

## Minimum Setup Checklist

### 1. Entity and Financial Year

Confirm:
- legal entity exists
- active financial year exists
- relevant branch or subentity exists where needed
- users are mapped to the correct entity scope

### 2. Source Transaction Readiness

Confirm:
- source sales or collection flows are working
- transaction dates and customer mapping are correct
- document numbering is stable
- reversal or cancellation behavior is understood

### 3. TCS Section Setup

Confirm:
- required TCS sections exist
- rates are correct
- effective dates are correct
- applicability rules are correct
- inactive or duplicate sections are not confusing users

### 4. TCS Entity Config

Confirm:
- TCS is enabled where required
- default section is correct
- effective dates are valid
- posting map is maintained where the entity uses it

### 5. TCS Party Profile Readiness

Confirm customer profiles contain:
- PAN where applicable
- residency status
- tax identifier where needed
- lower-rate data where used
- treaty data where relevant

This is important because quality flags often come from missing profile data.

### 6. RBAC and Route Access

Confirm authorized roles have the correct access to:
- TCS sections
- TCS config
- TCS party profiles
- TCS statutory workspace
- TCS return 27EQ

Recommended pattern:
- operator: view/manage operational TCS screens
- approver/controller: view plus return/closure review access
- admin/super admin: full access

Also confirm unauthorized users are blocked cleanly.

### 7. Menu and Frontend Access

Confirm:
- the TCS menu is visible for the right roles
- routes open correctly
- users do not see broken or unauthorized pages after login

### 8. Export and File Handling

Confirm:
- Excel/PDF/CSV exports work
- filing-pack exports work
- any file-path or evidence storage expectations are supported in the environment

## Screen-Level Readiness

### TCS Sections

Confirm:
- list opens
- search works
- add/edit/delete respects permissions
- import/export works if used

### TCS Config

Confirm:
- config list opens
- posting map list opens
- add/edit/delete works for authorized users

### TCS Party Profiles

Confirm:
- profile list opens
- branch filter works
- add/edit/delete works for authorized users

### TCS Statutory Workspace

Confirm:
- FY filter works
- quarter filter works
- section and customer filters work
- summary tiles load
- collections and deposits can be created
- allocation workflow works
- exports work

### TCS Return 27EQ

Confirm:
- quarter readiness loads
- return list loads
- export buttons work
- quarter review information is understandable

## Recommended Role Mapping

### Role 1: TCS Operator

Recommended access:
- view TCS screens
- manage workspace actions
- maintain collection/deposit operational records

Typical duties:
- follow up pending collection
- enter deposits
- review quarter data

### Role 2: TCS Reviewer / Controller

Recommended access:
- view all TCS screens
- review quarter readiness
- validate operational closure

Typical duties:
- review exceptions
- review pending deposit
- review return closure pack

### Role 3: Admin / Support

Recommended access:
- full TCS access
- config and master-data access
- RBAC support access

Typical duties:
- troubleshoot access issues
- correct setup issues
- support export and environment behavior

## Common Setup Mistakes

Avoid these issues:

- TCS section exists but is inactive or wrongly dated
- party profile is missing PAN or residency
- wrong financial year is selected during review
- users can open the page but lack the right permissions for actions
- posting map is missing where finance expects one
- quarter review is done before deposit allocation is complete

## Pre-Go-Live Admin Smoke Test

An admin should run this mini test:

1. Open TCS Sections.
2. Open TCS Config.
3. Open TCS Party Profiles.
4. Open TCS Statutory workspace.
5. Change FY and quarter filters.
6. Create one sample collection in a safe test case if permitted.
7. Create one sample deposit in a safe test case if permitted.
8. Open Return 27EQ.
9. Export at least one available format.
10. Confirm unauthorized user access is blocked.

## Go-Live Support Notes

During initial rollout, monitor:
- missing PAN quality flags
- section resolution problems
- pending collection buildup
- pending deposit buildup
- export complaints
- permission complaints

These are usually the first signals of setup gaps.

