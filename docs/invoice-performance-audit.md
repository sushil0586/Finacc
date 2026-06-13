# Invoice Performance Audit

Status: review only. No code changes applied.

Date: 2026-06-13

Scope covered in this pass:
- Sales invoice create/edit flow
- Purchase invoice create/edit flow
- Frontend API usage around invoice screens
- Backend query shape for invoice list/detail/meta endpoints
- `int` vs `bigint` suitability for invoice save paths

## Executive Summary

This pass did not find evidence that sales or purchase invoice saving is blocked by the current integer strategy.

The higher-probability performance issues are:
- repeated frontend metadata requests
- form/meta APIs returning more data than some caller actions need
- full-list refresh patterns after small mutations like adding a customer, vendor, or product

The most important result on data types is:
- primary keys are already `BigAutoField`, so invoice row IDs are already `bigint`
- document numbers such as `doc_no` are still `PositiveIntegerField`
- there is no immediate reason to convert `doc_no` to `bigint` unless business numbering can realistically exceed 2,147,483,647

## 1. Data Type Review: `int` vs `bigint`

### Verified current state

Project default auto field is `BigAutoField`:
- [FA/settings.py](/Users/ansh/finacc-angular/finacc-django/Finacc/FA/settings.py:328)
- [sales/apps.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/apps.py:5)
- [purchase/apps.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/apps.py:5)

That means model primary keys are already `bigint` by default in PostgreSQL unless overridden.

Sales invoice numbering fields:
- [sales/models/sales_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_core.py:93)
  - `doc_no = models.PositiveIntegerField(...)`
- [sales/models/sales_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_core.py:94)
  - `invoice_number = models.CharField(...)`

Purchase invoice numbering fields:
- [purchase/models/purchase_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_core.py:82)
  - `doc_no = models.PositiveIntegerField(...)`
- [purchase/models/purchase_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_core.py:83)
  - `purchase_number = models.CharField(...)`

### Recommendation

Do not change invoice save identifiers just because serializers use integer fields or because some APIs pass numeric IDs.

Current recommendation:
- keep primary keys as-is because they are already `bigint`
- keep `doc_no` as `PositiveIntegerField` unless business numbering volume requires more than a 32-bit positive range
- only consider migrating `doc_no` to `BigIntegerField` if:
  - numbering is global and rapidly increasing
  - imported legacy systems already exceed 32-bit range
  - there is a roadmap for extremely high sequence counts

### Why this matters

Changing `doc_no` to `bigint` has migration and index cost, but likely no practical performance gain.

The bigger performance wins are elsewhere:
- network payload size
- repeated form metadata loads
- list refresh strategy

## 2. Sales Invoice Frontend Findings

### Finding 1: full form meta is reloaded just to refresh customers

Sales customer refresh currently calls the full form meta API:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:1226)

This refresh path is expensive because the sales form meta response includes:
- financial years
- subentities
- customers
- charge types
- TCS sections
- custom field definitions
- UI contract

Backend source:
- [sales/views/sales_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_meta.py:210)

Assessment:
- likely over-fetch
- better future design would be a customer-only refresh endpoint or a narrower metadata slice

### Finding 2: full line meta is reloaded after product popup close

Sales product refresh reloads full line metadata:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:3163)

Assessment:
- likely justified for correctness today
- still potentially expensive if product catalog is large
- probably a good candidate for a lighter product refresh endpoint later

### Finding 3: branch change reloads multiple heavy metadata calls together

Sales branch change triggers:
- form meta
- settings
- line meta
- fallback TCS section list

Reference:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:2372)

Assessment:
- not necessarily unused
- but it is a high-cost interaction because several large payloads are re-requested together
- likely visible as UI latency on entities with large customer/product masters

### Finding 4: master data load duplicates some later refresh work

Initial master data load pulls:
- form meta
- settings
- TCS fallback sections

Reference:
- [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:4462)

Assessment:
- valid bootstrap behavior
- but later targeted refreshes often go back to the same broad APIs instead of using smaller deltas

## 3. Purchase Invoice Frontend Findings

### Finding 5: full form meta is reloaded just to refresh vendors

Purchase vendor refresh calls form meta again with force refresh:
- [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4481)

Backend form meta currently includes:
- financial years
- subentities
- vendors
- charge types
- TDS sections
- custom field definitions
- withholding defaults
- purchase behaviors
- UI contract

Backend source:
- [purchase/views/purchase_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_meta.py:223)

Assessment:
- likely over-fetch
- vendor-only refresh endpoint would be materially cheaper

### Finding 6: purchase branch change reloads broad metadata bundle

Purchase branch change triggers:
- purchase meta
- lines meta
- settings

Reference:
- [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:873)

Assessment:
- probably required for correctness today
- still a high-cost operation on large masters

### Finding 7: invoice-by-id load pulls detail meta and settings separately

Purchase detail load currently fetches:
- detail form meta
- settings

Reference:
- [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4017)

Assessment:
- this may be acceptable
- but it should be reviewed later for overlap, especially if `detailMeta` already contains enough state for current numbering and controls

## 4. Backend Query Findings

### Finding 8: list endpoints are already reasonably optimized

Sales list endpoint:
- uses `select_related(...)`
- narrows columns with `.only(...)`
- avoids loading edit-level relations

Reference:
- [sales/views/sales_invoice_views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_invoice_views.py:140)
- [sales/views/sales_invoice_views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_invoice_views.py:175)

Purchase list endpoint:
- same general pattern
- uses `select_related(...)`
- narrows fields with `.only(...)`

Reference:
- [purchase/views/purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py:96)
- [purchase/views/purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py:108)

Assessment:
- no immediate change recommended here in this document-only pass

### Finding 9: edit/detail endpoints intentionally load heavy related data

Sales retrieve/update path prefetches:
- lines
- tax summaries

Reference:
- [sales/views/sales_invoice_views.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/views/sales_invoice_views.py:239)

Purchase retrieve/update path prefetches:
- lines
- tax summaries
- charges

Reference:
- [purchase/views/purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py:244)

Assessment:
- this is expected for edit screens
- not an “unused query” by itself
- optimization should focus more on bootstrap/meta payloads than on invoice detail payloads first

### Finding 10: save paths already use transactions and bulk operations

Sales:
- transactional save methods present
- bulk tax summary insert path exists

Reference:
- [sales/services/sales_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/services/sales_invoice_service.py:1595)
- [sales/services/sales_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/services/sales_invoice_service.py:2475)

Purchase:
- transactional save methods present
- bulk line/tax summary insert paths exist

Reference:
- [purchase/services/purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:2252)
- [purchase/services/purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:2311)

Assessment:
- invoice save performance is probably more impacted by validation/product metadata and round-trip cost than by naive row-by-row persistence

## 5. Unused API Call Assessment

In this pass, no clearly dead API calls were confirmed inside the active sales/purchase save path itself.

What was found instead:
- broad metadata APIs reused in places where only one slice is needed
- repeated refresh calls that are valid functionally but likely too expensive operationally

So the current conclusion is:
- not “unused API calls”
- more accurately “over-broad API calls for narrow refresh actions”

## 6. Priority Opportunities For Next Pass

Recommended order for future performance work:

1. Split customer/vendor refresh from full form meta refresh
2. Split product refresh from full line meta refresh
3. Review branch-change bootstrap calls and cache stable metadata per entity/subentity
4. Measure payload size for sales/purchase form meta responses on large entities
5. Audit whether settings and detail meta responses overlap enough to merge or cache
6. Only revisit `doc_no` integer width if business numbering strategy proves 32-bit risk

## 7. Suggested Decision On `int` vs `bigint`

Current decision recommendation:
- no schema change now

Reason:
- row IDs are already `bigint`
- invoice numbers are business document numbers, not high-churn technical identifiers
- there is no evidence in this pass that `PositiveIntegerField` for `doc_no` is the current bottleneck

## 8. Next Audit Candidates

Areas worth inspecting next if we continue performance work:
- SQL query counts for one sales invoice edit screen load
- SQL query counts for one purchase invoice edit screen load
- payload size of sales/purchase form meta endpoints
- product line recalculation path during row edit
- common account list and state list loading reuse across invoice screens
