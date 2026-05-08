# Manufacturing Documentation Hub

Date: 2026-05-08

## Purpose

This folder contains the working documentation set for the Manufacturing module.

Use this hub to quickly choose the right document based on the reader and purpose.

## Document Map

### 1. Screens Guide

File:
- `manufacturing_screens_guide.md`

Best for:
- end users
- operations teams
- implementation teams

Use it when:
- explaining how each manufacturing screen is meant to be used
- training users on workflow navigation
- validating whether screen behavior matches the intended business flow

### 2. Ledger Mapping Guide

File:
- `manufacturing_ledger_mapping_guide.md`

Best for:
- finance users
- costing teams
- implementation consultants

Use it when:
- validating accounting integration
- checking inventory, WIP, consumption, and finished goods posting logic
- confirming how manufacturing transactions should affect ledgers

### 3. Phase 1 Reference

File:
- `phase1_manufacturing.md`

Best for:
- product teams
- implementation teams
- internal project owners

Use it when:
- reviewing the original phase scope
- tracing what was planned or delivered in the early implementation stage
- aligning project discussions with documented scope

## Recommended Reading Order

For business users:
1. `manufacturing_screens_guide.md`

For finance and implementation teams:
1. `manufacturing_ledger_mapping_guide.md`
2. `manufacturing_screens_guide.md`
3. `phase1_manufacturing.md`

## Suggested Handover Pack

If you are sharing the Manufacturing module with a customer or internal team, send:
- Screens Guide
- Ledger Mapping Guide

Include `phase1_manufacturing.md` when project-scope history or rollout context is also needed.

## Notes

- The Manufacturing module should be used with careful alignment between operations flow and accounting flow.
- If behavior looks inconsistent, first verify BOM/process setup, stock movement assumptions, and ledger mapping.
