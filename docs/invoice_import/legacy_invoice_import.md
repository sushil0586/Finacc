# Legacy Invoice Import

## Purpose
This module supports migration of historical customer and vendor invoices into the existing sales and purchase invoice tables, while using a staging layer for validation and audit.

Imported invoices are not stored in a separate legacy invoice model. They land in:
- `sales.SalesInvoiceHeader`
- `purchase.PurchaseInvoiceHeader`

Staging, validation, and commit are managed through:
- `invoice_import.ImportJob`
- `invoice_import.ImportRow`

## Supported Modes
### `outstanding_only`
Use this when the customer only wants currently open items carried forward.

Default behavior:
- detail level defaults to `header_only`
- only rows with `outstanding_amount > 0` are accepted
- AR/AP open items are created from the imported snapshot
- no historical settlement-chain reconstruction

### `full_history`
Use this when the customer wants old invoice history visible in Finacc.

Default behavior:
- detail level must be `header_plus_lines`
- stock replay is off by default
- history is imported for reporting/search continuity
- full accounting reconstruction is not attempted

## Job Options
- `detail_level`: `header_only` or `header_plus_lines`
- `stock_replay`: allowed only for `full_history`
- `compliance_mode`: `passive` or `live`
- `withholding_mode`: `preserve_legacy` or `recompute_finacc`
- `profile`: optional saved source-mapping profile

## Import Profiles
Import profiles let different legacy exports normalize into the same Finacc canonical import format.

Each profile stores:
- `module`
- `name`
- `source_system`
- `description`
- `is_default`
- `mapping`
- `options`

### Mapping JSON shape
```json
{
  "defaults": {
    "doc_type": "invoice",
    "status": "posted",
    "seller_gstin": "27AAAAA1111A1Z5"
  },
  "source_to_canonical": {
    "Invoice No": "source_invoice_number",
    "External Key": "legacy_source_key",
    "Bill Date": "bill_date",
    "Customer Name": "party_name",
    "Taxable Amount": "total_taxable",
    "Pending": "outstanding_amount"
  },
  "value_maps": {
    "doc_type": {
      "sales invoice": "invoice",
      "credit note": "credit_note"
    },
    "status": {
      "open": "posted",
      "paid": "posted"
    }
  }
}
```

### Profile behavior
- `defaults` are applied first
- source columns are remapped into canonical Finacc fields using `source_to_canonical`
- `value_maps` optionally normalize source-specific values into canonical values
- canonical validation still runs after mapping
- row-level errors still reference the canonical import contract

## Template Variants
- outstanding-only header-only
- outstanding-only header-plus-lines
- full-history header-plus-lines

Template download endpoints always return an `.xlsx` file with the canonical columns.

## Core Columns
### Common
- `entityfinid_id`
- `subentity_id`
- `legacy_source_system`
- `legacy_source_key`
- `doc_type`
- `status`
- `source_invoice_number`
- `bill_date`
- `due_date`
- `party_account_code`
- `party_name`
- `total_taxable`
- `total_cgst`
- `total_sgst`
- `total_igst`
- `total_cess`
- `round_off`
- `grand_total`
- `settled_amount`
- `outstanding_amount`
- `reference`
- `remarks`

### Sales-specific
- `party_gstin`
- `party_state_code`
- `seller_gstin`
- `seller_state_code`
- `supply_category`
- `taxability`
- `tax_regime`
- `original_source_key`

### Purchase-specific
- `party_gstin`
- `supplier_invoice_number`
- `supplier_invoice_date`
- `supply_category`
- `taxability`
- `tax_regime`
- `tds_amount`
- `gst_tds_amount`
- `original_source_key`

### Line-level columns
Required for `header_plus_lines`:
- `line_no`
- `product_id`
- `sales_account_id` or `purchase_account_id`
- `product_desc`
- `is_service`
- `purchase_behavior` for purchase rows
- `uom_id`
- `hsn_sac_code`
- `qty`
- `free_qty`
- `rate`
- `discount_type`
- `discount_percent`
- `discount_amount`
- `gst_rate`
- `cess_percent`
- `taxable_value`
- `cgst_amount`
- `sgst_amount`
- `igst_amount`
- `cess_amount`
- `line_total`

## API Endpoints
### Sales
- `GET /api/sales/legacy-import/template/?entity=<id>&mode=<mode>&detail_level=<detail_level>`
- `GET /api/sales/legacy-import/profiles/?entity=<id>`
- `POST /api/sales/legacy-import/profiles/`
- `GET /api/sales/legacy-import/profiles/<profile_id>/?entity=<id>`
- `PATCH /api/sales/legacy-import/profiles/<profile_id>/`
- `POST /api/sales/legacy-import/jobs/`
- `GET /api/sales/legacy-import/jobs/<job_id>/?entity=<id>`
- `POST /api/sales/legacy-import/jobs/<job_id>/commit/`
- `GET /api/sales/legacy-import/jobs/<job_id>/errors/?entity=<id>&format=xlsx|csv`
- `GET /api/sales/legacy-import/jobs/<job_id>/reconciliation/?entity=<id>`

### Purchase
- `GET /api/purchase/legacy-import/template/?entity=<id>&mode=<mode>&detail_level=<detail_level>`
- `GET /api/purchase/legacy-import/profiles/?entity=<id>`
- `POST /api/purchase/legacy-import/profiles/`
- `GET /api/purchase/legacy-import/profiles/<profile_id>/?entity=<id>`
- `PATCH /api/purchase/legacy-import/profiles/<profile_id>/`
- `POST /api/purchase/legacy-import/jobs/`
- `GET /api/purchase/legacy-import/jobs/<job_id>/?entity=<id>`
- `POST /api/purchase/legacy-import/jobs/<job_id>/commit/`
- `GET /api/purchase/legacy-import/jobs/<job_id>/errors/?entity=<id>&format=xlsx|csv`
- `GET /api/purchase/legacy-import/jobs/<job_id>/reconciliation/?entity=<id>`

## Upload Flow
1. Download the mode-specific template.
2. Populate the file with canonical IDs and amounts.
3. Optionally create or choose an import profile for the legacy source format.
4. Upload the file to create an `ImportJob`.
5. Review row-level validation output.
6. Commit the validated job.
7. Review the reconciliation summary.

## Validation Rules
- `legacy_source_system + legacy_source_key + entity` must be unique across imported invoices.
- Invoice number collisions with existing live invoices are rejected.
- `outstanding_only` requires `outstanding_amount > 0`.
- `full_history` requires `header_plus_lines`.
- credit/debit notes require `original_source_key`.
- live sales compliance requires the fields needed by compliance logic.
- stock replay requires product-safe rows and is only allowed for `full_history`.

## Import Flags Stored On Invoice Headers
Both invoice headers now record:
- `is_legacy_imported`
- `legacy_import_job`
- `legacy_source_system`
- `legacy_source_key`
- `legacy_import_mode`
- `legacy_behavior_flags`

This allows normal invoice APIs and reports to distinguish imported legacy data from live operational transactions.

## Admin Workflow
The module is available in Django admin:
- `Import jobs`
- `Import rows`

Admin supports:
- viewing validation payloads
- viewing row errors and warnings
- inline inspection of staged rows per job
- committing selected validated jobs using the admin action

This is intended as an operator fallback until a dedicated frontend flow is added.

## Operational Notes
- `compliance_mode=passive` does not auto-trigger compliance actions.
- `withholding_mode=preserve_legacy` keeps imported purchase withholding snapshots as-is.
- stock replay currently uses the existing posting adapters, so when enabled it reconstructs posting/inventory side effects through those adapters.

## Current Test Coverage
Covered in `invoice_import.tests`:
- sales and purchase outstanding imports
- sales full-history import behavior
- stock replay/compliance hook invocation
- withholding recompute warning behavior
- duplicate source key rejection
- template/download/create/detail/commit/reconciliation API flows
