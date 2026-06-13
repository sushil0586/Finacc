# Invoice Performance Phase 1 Task Plan

Status: implementation planning only. No code changes applied.

Date: 2026-06-13

Related documents:
- [invoice-performance-phase0-results.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-phase0-results.md:1)
- [invoice-performance-implementation-plan.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-implementation-plan.md:1)
- [invoice-performance-audit.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-audit.md:1)

## Phase 1 Goal

Remove broad and duplicated party refresh work after customer/vendor popup save on invoice screens.

Primary target:
- customer refresh on sales invoice
- vendor refresh on purchase invoice

Secondary target:
- remove duplicated follow-up refreshes in the same popup-return flow

## Success Criteria

Phase 1 is successful if:
- sales customer popup return no longer reloads full sales form meta
- purchase vendor popup return no longer reloads full purchase form meta
- duplicate godown refreshes caused by the same popup-return action are eliminated if they are unnecessary
- customer/vendor dropdowns still show the newly created or updated record immediately
- no regression in shipping detail selection, GST/state defaults, or branch-scoped dropdown behavior

## Proposed Implementation Strategy

Use narrow refreshes instead of broad form-meta reloads.

Principle:
- after popup save, refresh only the dataset that changed
- do not reload financial years, subentities, charge types, TDS/TCS sections, custom field definitions, and unrelated scope data

## Backend Tasks

### Task B1: Add sales customer lightweight endpoint

Purpose:
- return only customer dropdown data needed by sales invoice screen

Likely source logic:
- extract/reuse customer-building logic from [sales/views/sales_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_meta.py:148)

Recommended output shape:
- same customer row structure already consumed by sales form meta

Suggested route shape:
- `/api/sales/meta/customers/`

Suggested query params:
- `entity`
- optional `subentity` only if needed for future filtering consistency

Notes:
- reusing the current row structure reduces frontend risk

### Task B2: Add purchase vendor lightweight endpoint

Purpose:
- return only vendor dropdown data needed by purchase invoice screen

Likely source logic:
- extract/reuse vendor-building logic from [purchase/views/purchase_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_meta.py:142)

Suggested route shape:
- `/api/purchase/meta/vendors/`

Suggested output shape:
- same vendor row structure already used from purchase form meta

### Task B3: Review whether godown/location reload needs to be tied to party refresh

Purpose:
- verify if `godowns` is truly dependent on customer/vendor popup save

Expected likely answer:
- probably no for customer/vendor save alone

If unnecessary:
- do not trigger location refresh on popup return

### Task B4: Keep broad form-meta endpoints unchanged

Purpose:
- avoid risk to create-screen bootstrap behavior

Important note:
- do not remove or redesign `invoice-form` endpoints in Phase 1
- Phase 1 should add narrow endpoints, not break existing bootstraps

## Frontend Tasks

### Task F1: Sales invoice customer refresh should use customer-only API

Current broad refresh call:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:1226)

Current behavior:
- `bindCustomerList()` calls full `getSalesInvoiceFormMeta(...)`

Planned change:
- replace with a dedicated customer-list request
- update only:
  - `customerList`
  - customer-dependent selection state if needed

Keep current behavior:
- after popup save, select the newly created/updated customer
- re-run `changeCustomer(...)` if required for dependent fields

### Task F2: Purchase invoice vendor refresh should use vendor-only API

Current broad refresh call:
- [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4481)

Current behavior:
- `refreshVendorList()` calls full `getPurchaseInvoiceFormMeta(..., true)`

Planned change:
- replace with a dedicated vendor-list request
- update only:
  - `vendorList`
  - selected vendor-dependent state if needed

### Task F3: Remove duplicate same-flow refresh calls

Purpose:
- stop issuing the same broad or related refresh multiple times after popup return

Investigate specifically:
- duplicate `sales/meta/invoice-form`
- duplicate `godowns`
- any chained refresh triggered both by popup close and subsequent field change handler

### Task F4: Add facade/service methods for narrow party refresh

Sales facade:
- add customer list method

Purchase facade:
- add vendor list method

Invoice/common service:
- add corresponding HTTP methods mapped to the new backend endpoints

### Task F5: Preserve stable UI contracts

Must preserve:
- selected customer/vendor stays populated
- GST number auto-fill still works
- state auto-fill still works
- shipping details still load for customer selection
- branch scope remains correct

## Testing Tasks

### Task T1: Sales customer popup flow

Verify:
- create customer from invoice screen
- customer appears immediately in dropdown
- selected customer remains selected
- shipping details and GST/state behavior still work
- no duplicate full form-meta reload

### Task T2: Purchase vendor popup flow

Verify:
- create vendor from invoice screen
- vendor appears immediately in dropdown
- selected vendor remains selected
- GST/state/tax regime defaults still work
- no duplicate full form-meta reload

### Task T3: Regression checks on create screen

Verify no regression in:
- plain sales invoice create load
- plain purchase invoice create load
- branch change
- product selection
- save invoice draft

### Task T4: HAR re-capture after Phase 1

Capture again:
- sales customer popup return
- purchase vendor popup return

Expected improvement:
- fewer requests
- smaller total transfer
- no duplicate form-meta refresh

## Recommended File Touch List

Backend likely files:
- [sales/views/sales_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_meta.py:1)
- [purchase/views/purchase_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_meta.py:1)
- sales URL config for new meta route
- purchase URL config for new meta route

Frontend likely files:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:1)
- [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:1)
- [saleinvoice.facade.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/saleinvoice.facade.ts:1)
- [purchaseinvoice.facade.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/purchaseinvoice.facade.ts:1)
- [invoice.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/invoice.service.ts:1)
- [config.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/config/config.service.ts:1)

Tests likely files:
- sales invoice component specs
- purchase invoice component specs
- backend API tests for new lightweight endpoints

## Recommended Implementation Order

1. Add backend sales customer lightweight endpoint
2. Add backend purchase vendor lightweight endpoint
3. Add frontend service/facade methods
4. Switch sales popup refresh to customer-only call
5. Switch purchase popup refresh to vendor-only call
6. Remove duplicate same-flow refresh behavior
7. Run targeted regression tests
8. Re-capture HARs for the two popup-return scenarios

## Risks

Main risks:
- popup save returns but selected party not rebound correctly
- dependent data such as shipping details or state defaults stops updating
- hidden coupling to full form meta causes missing dropdown/state data

Mitigation:
- keep response row shape identical to current form-meta customer/vendor lists
- change only popup refresh path in Phase 1
- do not alter create-screen bootstrap behavior yet

## Expected Impact

Expected user-visible benefit:
- faster return from customer popup on sales invoice
- faster return from vendor popup on purchase invoice
- fewer unnecessary requests
- lower transferred payload in those workflows

Expected engineering benefit:
- low-risk, contained first optimization
- establishes reusable pattern for later narrower refreshes

## Recommended Immediate Build Slice

First slice to implement:

1. Sales customer lightweight endpoint
2. Purchase vendor lightweight endpoint
3. Replace sales and purchase popup refresh calls

Hold for later:
- product refresh optimization
- create-screen bootstrap optimization
- `sales/meta/invoice-lines` tuning
- shell/bootstrap API optimization
