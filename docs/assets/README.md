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

### 2. Purchase to Asset Flow Guide

File:
- `purchase_to_asset_flow_guide.md`

Best for:
- finance teams
- procurement teams
- implementation teams
- product/design discussions

Use it when:
- explaining how asset purchases should work
- clarifying why a purchase may land in inventory instead of assets today
- defining the target purchase-to-asset operating model
- training teams on the interim manual process

### 3. Ledger Mapping Guide

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

### 4. Phased Implementation Guide

File:
- `purchase_classification_and_asset_flow_phases.md`

Best for:
- product teams
- implementation consultants
- finance process owners
- solution design discussions

Use it when:
- planning how to support inventory vs expense vs asset purchase behavior
- deciding how food expense and other non-trading purchases should be handled
- breaking the purchase-to-asset solution into manageable delivery phases
- aligning backend, frontend, and accounting expectations before implementation

### 5. UAT Checklist

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

### 6. Purchase Asset Flow Change Summary

File:
- `purchase_asset_flow_change_summary.md`

Best for:
- product owners
- QA teams
- implementation consultants
- business walkthroughs

Use it when:
- explaining what has already been implemented
- summarizing current purchase-to-expense and purchase-to-asset behavior
- sharing the delivered scope with stakeholders

### 7. Purchase Asset Flow QA Scenarios

File:
- `purchase_asset_flow_qa_scenarios.md`

Best for:
- QA teams
- UAT users
- implementation teams

Use it when:
- testing inventory vs expense vs asset purchase behavior
- validating purchase-created asset intake
- checking review queue and capitalization rules

### 8. Purchase Asset Flow UAT Handover

File:
- `purchase_asset_flow_uat_handover.md`

Best for:
- UAT users
- finance leads
- project managers
- implementation handover

Use it when:
- sharing the final delivered scope for UAT
- explaining what changed in one consolidated note
- preparing signoff conversations
- packaging the final test/handover reference set

## Recommended Reading Order

For business users:
1. `asset_module_end_to_end_guide.md`
2. `purchase_to_asset_flow_guide.md`
3. `purchase_classification_and_asset_flow_phases.md`
4. `purchase_asset_flow_uat_handover.md`
5. `purchase_asset_flow_change_summary.md`
6. `purchase_asset_flow_qa_scenarios.md`
7. `asset_uat_checklist.md`

For finance and implementation teams:
1. `purchase_to_asset_flow_guide.md`
2. `purchase_classification_and_asset_flow_phases.md`
3. `purchase_asset_flow_uat_handover.md`
4. `purchase_asset_flow_change_summary.md`
5. `purchase_asset_flow_qa_scenarios.md`
6. `asset_ledger_mapping_guide.md`
7. `asset_module_end_to_end_guide.md`
8. `asset_uat_checklist.md`

## Suggested Handover Pack

If you are sharing the Asset module with a customer or internal finance team, send:
- End-to-End User Guide
- Purchase to Asset Flow Guide
- Purchase Classification and Asset Flow Phases
- Purchase Asset Flow UAT Handover
- Purchase Asset Flow Change Summary
- Purchase Asset Flow QA Scenarios
- Ledger Mapping Guide
- UAT Checklist

## Notes

- The Asset module should be used as an operational and accounting control workspace.
- Asset accounting should remain aligned with ledger mapping and posting behavior.
- If results look wrong, first verify asset master data, category setup, ledger mapping, and workflow status.
