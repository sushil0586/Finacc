# Sales Compliance And Purchase Validation Session Note

## Date

2026-06-18

## Scope Covered

This session focused on two active areas:

- sales invoice compliance flow stability for WhiteBooks E-Invoice and E-Way
- purchase invoice payload/serializer alignment for null-tolerant UI requests

## Completed Changes

### 1. Sales Compliance UI Refactor Stabilization

Completed work in the Angular frontend:

- split the compliance surface into smaller child components
- stabilized the overview/workspace modal flow
- fixed button-state inconsistencies after IRN and E-Way generation
- added focused component specs for workspace and action dialog shells

Key outcome:

- when E-Way is already generated, generate/prefill actions are no longer shown as available in the UI

## 2. Sales Compliance Button-State Contract

Created the state contract document:

- `Finacc/docs/gst/sales_compliance_button_state_matrix.md`

Purpose:

- define expected enable/disable behavior for overview and workspace actions
- make frontend and backend behavior converge on the same state matrix
- clarify that backend flags are advisory and must not override already-generated artifacts

## 3. Backend Sales Compliance Action Flag Alignment

Updated the backend flag builder in:

- `Finacc/sales/services/sales_compliance_service.py`

Changes made:

- `can_cancel_irn` is now `false` when E-Way is active/generated
- `can_load_eway_prefill` is now `false` when E-Way is already generated
- `can_load_eway_b2c_prefill` is now `false` when E-Way is already generated

Why:

- previously the frontend had to defensively correct stale backend flags
- now the API contract better matches the agreed UI behavior

## 4. Sales Backend Contract Coverage Expanded

Updated:

- `Finacc/sales/tests_invoice_contract_alignment.py`

Coverage added:

- “both generated” state now explicitly expects:
- `can_generate_eway = false`
- `can_load_eway_prefill = false`
- `can_cancel_irn = false`
- `can_cancel_eway = true`
- added B2C regression to ensure `can_load_eway_b2c_prefill = false` after E-Way generation

## 5. Sales Compliance Serializer Null-Tolerance Hardening

Updated:

- `Finacc/sales/serializers/sales_compliance_serializers.py`

Problem:

- several optional transport/compliance fields were `required=False` but still rejected `null`
- Angular forms commonly submit `null` for untouched optional fields

Fixes applied:

- added `allow_null=True` to optional fields in active serializers where validator logic already treats `None` as “not provided”

Main serializers hardened:

- `EnsureComplianceActionSerializer`
- `GenerateIRNAndEWayActionSerializer`
- `GetIRNByDocDetailsActionSerializer`
- `GetB2CQRCodeActionSerializer`
- `GetEWayByDocumentActionSerializer`
- `GenerateConsolidatedEWayActionSerializer`
- `RegenerateTripSheetActionSerializer`
- `AddMultiVehicleActionSerializer`
- `UpdateMultiVehicleActionSerializer`
- `UpdateEWayVehicleActionSerializer`
- `ExtendEWayValidityActionSerializer`

Related unit coverage added in:

- `Finacc/sales/tests.py`

## 6. Purchase Invoice `purchase_behavior` Null Payload Fix

Updated:

- `Finacc/purchase/serializers/purchase_invoice.py`

Problem:

- UI sent `"purchase_behavior": null`
- serializer rejected null before product-based fallback logic could run

Fix:

- `purchase_behavior` now accepts null/omission at serializer field level
- existing validation logic now correctly defaults from product purchase behavior

Regression coverage added in:

- `Finacc/purchase/tests_invoice_contract_alignment.py`

## Functional Issues Resolved During Validation

These issues were addressed over the course of the session:

- GST-TDS manual amount mismatch path on purchase pages
- WhiteBooks auth/config verification path
- Ship To GSTIN payload handling for E-Way generation
- HSN and cess payload alignment for IRN generation
- compliance modal open/close instability
- generated-state button gating mismatch in sales compliance overview
- purchase `purchase_behavior = null` rejection

## Verification Performed

Successfully verified:

- focused Angular compliance spec suite passed in ChromeHeadless after UI changes
- Python syntax compile passed for edited backend files using `python3 -m py_compile`

Limitations in this shell:

- Django runtime environment was not available
- backend Django tests could not be executed in this session shell
- `pytest` was also not available

## Recommended Next Steps

### Highest Priority

1. Run backend Django tests in the project virtual environment

Suggested focus:

- sales compliance contract tests
- sales compliance unit tests
- purchase contract alignment tests
- purchase invoice serializer/service tests

2. Run structured UAT for active sales compliance flows

Suggested scenarios:

- B2B initial -> IRN -> E-Way -> sync
- B2B both-generated state
- cancel E-Way -> cancel IRN
- B2C prefill/generate flow
- E-Way maintenance actions after generation

### Medium Priority

3. Validate backend `action_flags` across all compliance endpoints

Goal:

- ensure every compliance response returns flags consistent with `sales_compliance_button_state_matrix.md`

4. Do one more narrow serializer audit only if new API errors appear

Current view:

- the highest-risk null/default mismatches in active sales and purchase flows were already addressed
- further serializer changes should be driven by observed payload failures, not broad speculative edits

## Important Reference Docs

- `Finacc/docs/gst/sales_compliance_button_state_matrix.md`
- `Finacc/docs/gst/sales_compliance_console_refactor_plan.md`
- `Finacc/docs/gst/whitebooks_provider_refactor_and_api_coverage_plan.md`

## Session Summary

At the end of this session:

- sales compliance UI state handling is more consistent
- backend sales compliance flags better match UI expectations
- active sales compliance serializers are more tolerant of null optional payloads
- purchase invoice line serializer now supports product-default `purchase_behavior` when UI sends null

The most important remaining task is not another blind code pass. It is to run the backend test suites and complete a clean UAT cycle with the real app environment active.
