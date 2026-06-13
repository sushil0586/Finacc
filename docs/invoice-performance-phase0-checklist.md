# Invoice Performance Phase 0 Checklist

Status: ready to execute. No code changes applied.

Date: 2026-06-13

Related documents:
- [invoice-performance-audit.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-audit.md:1)
- [invoice-performance-implementation-plan.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/invoice-performance-implementation-plan.md:1)

## Objective

Capture baseline performance numbers for sales and purchase invoice workflows before any optimization work begins.

This checklist is meant to produce:
- repeatable browser measurements
- endpoint payload and timing notes
- a before-state reference for later phases

## Preparation

Use one consistent test dataset for the whole baseline run:
- same entity
- same financial year
- same subentity
- same user role

Recommended environment:
- local frontend + local backend if possible
- otherwise staging with low background load

Browser setup:
- open Chrome DevTools
- Network tab
- enable `Preserve log`
- disable browser cache during measurement
- keep filtering to `Fetch/XHR`

Capture format:
- take one screenshot per scenario
- export HAR if convenient
- note timestamp and environment for each run

## Core Scenarios To Measure

### Sales Invoice

1. Open create screen
Route:
- `/saleinvoice`

2. Open existing invoice
Route:
- `/saleinvoice?id=<existing_invoice_id>` or equivalent existing-invoice navigation path used in the app

3. Change branch/subentity on screen

4. Create or edit customer from popup, then return to invoice

5. Create or edit product from popup, then return to invoice

6. Open invoice summary for an existing invoice

### Purchase Invoice

1. Open create screen
Route:
- `/purchaseinvoice`

2. Open existing invoice
Route:
- `/purchaseinvoice?id=<existing_invoice_id>` or equivalent existing-invoice navigation path used in the app

3. Change branch/subentity on screen

4. Create or edit vendor from popup, then return to invoice

5. Create or edit product from popup, then return to invoice

6. Open invoice summary for an existing invoice

## Exact Frontend API Methods To Watch

### Sales invoice APIs

From [invoice.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/invoice.service.ts:1122):
- `getSalesInvoiceFormMeta(...)`
- `getSalesInvoiceDetailFormMeta(...)`
- `getSalesInvoiceSearchMeta(...)`
- `getSalesInvoiceLinesMeta(...)`
- `getSalesInvoiceSummary(...)`
- `getSalesSettingsMeta(...)`
- `getSalesAvailableBatches(...)`
- `getSalesStockBalanceHint(...)`

Resolved endpoint bases from [config.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/config/config.service.ts:2562):
- `getSalesInvoiceFormMeta(...)` -> `/api/sales/meta/invoice-form/`
- `getSalesInvoiceDetailFormMeta(...)` -> `/api/sales/meta/invoice-detail-form/`
- `getSalesInvoiceSearchMeta(...)` -> `/api/sales/meta/invoice-search/`
- `getSalesInvoiceLinesMeta(...)` -> `/api/sales/meta/invoice-lines/`
- `getSalesSettingsMeta(...)` -> `/api/sales/meta/settings/`
- `getSalesStockBalanceHint(...)` -> `/api/sales/meta/stock-hint/`
- `getSalesAvailableBatches(...)` -> `/api/sales/meta/available-batches/`

Additional sales summary/detail routes derived from [invoice.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/invoice.service.ts:1222):
- `getSalesInvoiceSummary(...)` -> `/api/sales/sales-invoices/<invoice_id>/summary/`
- invoice detail fetch -> `/api/sales/sales-invoices/<invoice_id>/?entity=...&entityfinid=...`

Relevant screen call sites:
- customer refresh via full form meta:
  - [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:1226)
- branch change bundle:
  - [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:2373)
- product refresh via line meta:
  - [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:3163)
- summary open:
  - [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:4237)
- initial master-data load:
  - [saleinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/saleinvoice/saleinvoice.component.ts:4463)

### Purchase invoice APIs

From [invoice.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/invoice.service.ts:625):
- `getPurchaseInvoiceFormMeta(...)`
- `getPurchaseInvoiceDetailFormMeta(...)`
- `getPurchaseInvoiceSearchMeta(...)`
- `getPurchaseInvoiceLinesMeta(...)`
- `getPurchaseInvoiceSummary(...)`
- `getPurchaseInvoiceSettings(...)`
- `searchPurchaseInvoiceProducts(...)`
- `getPurchaseInvoiceProductDetail(...)`

Resolved endpoint bases from [config.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/config/config.service.ts:2522):
- `getPurchaseInvoiceFormMeta(...)` -> `/api/purchase/meta/invoice-form/`
- `getPurchaseInvoiceDetailFormMeta(...)` -> `/api/purchase/meta/invoice-detail-form/`
- `getPurchaseInvoiceSearchMeta(...)` -> `/api/purchase/meta/invoice-search/`
- `getPurchaseInvoiceLinesMeta(...)` -> `/api/purchase/meta/invoice-lines/`
- purchase settings -> `/api/purchase/settings/`

Additional purchase summary/detail routes derived from [invoice.service.ts](/Users/ansh/finacc-angular/accountproject/src/app/service/invoice/invoice.service.ts:649):
- `getPurchaseInvoiceSummary(...)` -> `/api/purchase/purchaseinvoice/<invoice_id>/summary/` or service-mode purchase invoice summary route
- invoice detail fetch -> purchase invoice detail route with `?entity=...&entityfinid=...`
- `getPurchaseInvoiceProductDetail(...)` -> `/api/.../transaction-meta/` product detail route
- `searchPurchaseInvoiceProducts(...)` -> `/api/purchase/meta/invoice-lines/?search=...`

Relevant screen call sites:
- branch change bundle:
  - [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:874)
- invoice detail load:
  - [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4018)
- summary open:
  - [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4066)
- vendor refresh via full form meta:
  - [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4481)
- initial master-data load:
  - [purchaseinvoice.component.ts](/Users/ansh/finacc-angular/accountproject/src/app/component/invoice/purchaseinvoice/purchaseinvoice.component.ts:4688)

## Metrics To Capture Per Scenario

For each scenario, record:
- total XHR/fetch request count
- total transferred size
- total duration until screen is usable
- top 3 slowest requests
- top 3 largest payloads
- duplicate requests for the same endpoint

If possible, also note:
- whether UI becomes interactive before all requests finish
- whether any request blocks typing, dropdown selection, or save-related actions

Important note:
- this document prepares the measurement run, but actual timings and payload sizes must be captured in a browser network session or equivalent profiling setup
- this CLI-only pass cannot produce trustworthy real browser timing numbers by itself

## Measurement Worksheet

Use this table during the first run.

| Scenario | Route / Action | Total API Calls | Total Transfer | Time To Usable | Slowest Request | Largest Payload | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Sales create | `/saleinvoice` |  |  |  |  |  |  |
| Sales existing invoice | existing invoice open |  |  |  |  |  |  |
| Sales branch change | switch branch |  |  |  |  |  |  |
| Sales customer popup return | save customer and return |  |  |  |  |  |  |
| Sales product popup return | save product and return |  |  |  |  |  |  |
| Sales summary open | open summary |  |  |  |  |  |  |
| Purchase create | `/purchaseinvoice` |  |  |  |  |  |  |
| Purchase existing invoice | existing invoice open |  |  |  |  |  |  |
| Purchase branch change | switch branch |  |  |  |  |  |  |
| Purchase vendor popup return | save vendor and return |  |  |  |  |  |  |
| Purchase product popup return | save product and return |  |  |  |  |  |  |
| Purchase summary open | open summary |  |  |  |  |  |  |

## Request-Level Worksheet

Use this table for the heaviest requests discovered.

| Endpoint / API | Screen | Request Count | Payload Size | Duration | Called By | Keep / Review |
| --- | --- | --- | --- | --- | --- | --- |
| `getSalesInvoiceFormMeta` |  |  |  |  |  |  |
| `getSalesInvoiceLinesMeta` |  |  |  |  |  |  |
| `getSalesSettingsMeta` |  |  |  |  |  |  |
| `getSalesInvoiceDetailFormMeta` |  |  |  |  |  |  |
| `getSalesInvoiceSummary` |  |  |  |  |  |  |
| `getPurchaseInvoiceFormMeta` |  |  |  |  |  |  |
| `getPurchaseInvoiceLinesMeta` |  |  |  |  |  |  |
| `getPurchaseInvoiceSettings` |  |  |  |  |  |  |
| `getPurchaseInvoiceDetailFormMeta` |  |  |  |  |  |  |
| `getPurchaseInvoiceSummary` |  |  |  |  |  |  |

## Quick Filter Strings For DevTools

Use these filters while measuring:

Sales:
- `sales/meta/invoice-form`
- `sales/meta/invoice-lines`
- `sales/meta/settings`
- `sales/meta/invoice-detail-form`
- `sales/sales-invoices`
- `sales/meta/stock-hint`
- `sales/meta/available-batches`

Purchase:
- `purchase/meta/invoice-form`
- `purchase/meta/invoice-lines`
- `purchase/meta/invoice-detail-form`
- `purchase/settings`
- `purchaseinvoice`

## Backend Notes To Capture

For the heaviest endpoints, collect:
- response time seen in browser
- response payload size
- whether response repeats identical data within the same screen session

If local Django profiling is available, also record:
- SQL query count
- total DB time
- obvious duplicate queries

## Recommended Local Backend Profiling Options

If we run locally, use one of these approaches:

1. Django Debug Toolbar
- capture query count and SQL timings per request

2. Temporary request logging
- log endpoint path and response time

3. Browser + server log pairing
- compare frontend waterfall with backend request timing

This phase does not require code changes, but if instrumentation is missing we can add it in a separate step.

## What To Flag Immediately

Mark an endpoint as a likely hotspot if any of these are true:
- payload is among the top 3 largest
- endpoint is called more than once for the same screen action
- endpoint is slow and blocks screen usability
- endpoint returns broad metadata for a narrow refresh action

## Exit Criteria For Phase 0

Phase 0 is complete when:
- all core scenarios above have at least one measurement row
- top 3 payload-heavy endpoints are identified
- top 3 latency-heavy interactions are identified
- we can clearly rank the first implementation slice for Phase 1

## Expected First Decision After Phase 0

The first execution decision should answer:

1. Is customer/vendor refresh the biggest low-risk win?
2. Is product/meta refresh larger than expected?
3. Is branch-change latency driven more by network payload or by server time?
4. Do we need caching before endpoint decomposition?

## Proposed Immediate Next Step

Run the first baseline pass for only these 4 scenarios:

1. Sales create screen
2. Sales customer popup return
3. Purchase create screen
4. Purchase vendor popup return

Reason:
- fastest path to confirm whether full form meta refresh is the first Phase 1 target
