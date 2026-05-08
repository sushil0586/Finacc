# Asset Documentation Hub

Date: 2026-05-08

## Purpose

This folder contains the working documentation set for the Asset module.

Use this hub to quickly choose the right document based on the reader and purpose.

## Document Map

### 1. End-to-End User Guide

File:
- `asset_module_end_to_end_guide.md`

Best for:
- business users
- finance users
- implementation teams

Use it when:
- explaining the overall Asset process
- training users on the correct operating flow
- showing how the module should be used from setup to reporting

### 2. Ledger Mapping Guide

File:
- `asset_ledger_mapping_guide.md`

Best for:
- finance controllers
- accountants
- implementation consultants

Use it when:
- validating accounting setup
- checking which ledgers are used in capitalization, depreciation, impairment, and disposal
- explaining how asset accounting should map into books

### 3. UAT Checklist

File:
- `asset_uat_checklist.md`

Best for:
- QA teams
- finance testers
- project teams

Use it when:
- running go-live testing
- recording pass/fail evidence
- checking whether the module is ready for signoff

## Recommended Reading Order

For business users:
1. `asset_module_end_to_end_guide.md`
2. `asset_uat_checklist.md`

For finance and implementation teams:
1. `asset_ledger_mapping_guide.md`
2. `asset_module_end_to_end_guide.md`
3. `asset_uat_checklist.md`

## Suggested Handover Pack

If you are sharing the Asset module with a customer or internal finance team, send:
- End-to-End User Guide
- Ledger Mapping Guide
- UAT Checklist

## Notes

- The Asset module should be used as an operational and accounting control workspace.
- Asset accounting should remain aligned with ledger mapping and posting behavior.
- If results look wrong, first verify asset master data, category setup, ledger mapping, and workflow status.
