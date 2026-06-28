# GST / TCS Coverage Note

This note tracks the backend surfaces that were reviewed while closing out GST/TCS work.

## Verified report surfaces

- GSTR-1 summary, readiness, validations, sections, invoices, and exports.
- GSTR-3B summary, validations, CSV/XLSX export, and drilldown metadata.
- GSTR-9 summary, table, validations, freeze history, filing flow, and export contract.
- GST exception dashboard and GSTR-1 vs GSTR-3B reconciliation.
- Financial controls phase one, including GST and TCS readiness actions.

## Verified TCS workspace surfaces

- `withholding.views.TcsWorkspaceTransactionsAPIView`
- `withholding.views.TcsWorkspaceTransactionsExportAPIView`
- TCS ledger report and filing pack paths
- Pending collection, pending deposit, and missing section drilldowns from the controls hub

## What the coverage is checking

- UI-facing export metadata is present on report summaries.
- Drilldown links remain wired to the correct workspace routes.
- Readiness and validation payloads keep their warning context.
- TCS workspace routes remain permissioned and searchable.

## Remaining watch areas

- Any future change to GST scope parsing or freeze handling.
- Any change to TCS lifecycle rules in `withholding/views.py`.
- Any UI copy or spacing change in payment/receipt or statutory workspaces.
