# TCS User Guide

Date: 2026-05-08

## Purpose

This guide explains the TCS module in simple business language.

Use this module to:
- review TCS-computed transactions
- track collection against customer receipts
- track deposit against challans
- prepare quarterly TCS return 27EQ
- review filing readiness before closure

This module is an operational compliance screen.

It is not the original source of truth for sales transactions.

The original source of truth usually remains:
- sales invoice
- receipt entry
- customer master
- TCS section and config setup

If a TCS number looks wrong, first check the source document and setup.

## Who Should Use It

- Accounts team: to monitor collection and deposit status
- Tax/compliance team: to review pending items, exceptions, and returns
- Finance controller / CA: to review filing readiness and period closure

## What You Need Before Using It

Before using the TCS module, make sure:
- the correct entity is selected
- the correct financial year is selected
- customer PAN and tax details are maintained
- TCS sections and rules are configured
- TCS config is enabled where applicable
- source invoices or receipts are already entered correctly

## Main TCS Screens

The TCS area is usually used through five practical screens.

### 1. TCS Sections

Use this screen to maintain the statutory TCS section definitions.

Typical use:
- create or edit section codes
- maintain default rates
- define applicability rules
- manage effective dates

This is a setup screen.

Business users normally do not use it daily.

### 2. TCS Config

Use this screen to maintain entity-level and branch-level TCS behavior.

Typical use:
- enable TCS
- set default section
- define effective period
- maintain posting map

This controls how the entity behaves operationally.

### 3. TCS Party Profiles

Use this screen to maintain customer tax profile information.

Typical use:
- maintain PAN
- maintain residency status
- maintain lower-rate details
- maintain treaty-related details where relevant

This is important because TCS quality depends on correct party data.

### 4. TCS Statutory Workspace

This is the working screen for operations.

Use it to:
- review transaction-level TCS computation
- see pending collection
- see pending deposit
- create collection entries
- create deposit entries
- allocate deposits to collections

This is the main screen for operational follow-up.

### 5. TCS Return 27EQ

Use this screen for quarterly return preparation and review.

Typical use:
- review quarter readiness
- track exceptions
- review return list
- manage draft and validated return flow
- prepare filing evidence

## Recommended Business Flow

Follow this order for the cleanest process.

### Step 1. Confirm Setup

Before operational work begins:
- confirm TCS sections are ready
- confirm entity TCS config is active
- confirm party profiles are maintained

### Step 2. Review TCS Workspace

Open the TCS workspace and review:
- total transactions
- computed TCS
- collected TCS
- deposited TCS
- pending collection
- pending deposit

Use this screen daily or weekly.

### Step 3. Resolve Quality Issues

If the workspace shows:
- missing PAN
- missing section
- residency mismatch
- invalid base-rule behavior

then fix the underlying setup or transaction issue first.

Do not treat the statutory workspace as a data correction shortcut.

### Step 4. Record Collection

When TCS is collected from the customer:
- create or verify the collection row
- confirm the collected amount is correct
- verify it is linked to the right computation

### Step 5. Record Deposit

When tax is deposited:
- create the deposit record
- enter challan details carefully
- allocate deposit amounts to collections

This step is important because return readiness depends on deposit completeness.

### Step 6. Review Quarter Readiness

Open TCS Return 27EQ and review:
- total rows
- exception rows
- pending collection
- pending deposit
- evidence readiness

If anything is still pending, do not treat the quarter as ready for filing.

### Step 7. Complete Return Process

Use the return screen to:
- review quarter status
- confirm evidence
- track original and correction return rows

This screen should support the filing process, not replace proper source-document review.

## Common Situations and What They Mean

### Pending Collection

Meaning:
- TCS is computed, but collection from the customer is not fully recorded

Action:
- review receipt/collection posting
- confirm whether the customer payment was received

### Pending Deposit

Meaning:
- TCS is collected, but deposit entry or allocation is incomplete

Action:
- check challan record
- check deposit allocation

### Missing PAN

Meaning:
- party tax profile is incomplete

Action:
- correct party master / TCS party profile

### Missing Section

Meaning:
- system could not properly resolve TCS section behavior

Action:
- check section setup
- check entity config
- check source transaction nature

### Return Not Ready

Meaning:
- quarter still has exceptions or undeposited amounts

Action:
- clear issues in workspace before closure

## Good Operating Practice

- keep one financial year and one quarter in focus during review
- complete collection and deposit work before heavy return review
- use party profile and config screens only for setup corrections
- use workspace for operational follow-up
- use return screen for quarter readiness and filing review

## What Users Should Not Do

Avoid these mistakes:

- do not use TCS screens to rewrite source invoice truth
- do not ignore missing PAN or missing section warnings
- do not file based only on totals without checking pending deposit
- do not mix multiple quarters while reviewing one closure cycle

## Quick End-of-Period Checklist

Before quarter closure, confirm:
- all relevant transactions are visible
- pending collection is understood
- pending deposit is cleared or explained
- section and PAN exceptions are resolved
- return readiness screen shows acceptable status
- evidence and exports are ready for CA review

