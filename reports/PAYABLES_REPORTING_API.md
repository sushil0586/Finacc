# Payables Reporting API

This guide summarizes the frontend-facing contract for the payables reporting suite.

## Common Request Pattern

Common filters:
- `entity`
- `entityfinid`
- `subentity`
- `vendor`
- `from_date` / `date_from`
- `to_date` / `date_to`
- `as_of_date`
- `include_trace`
- `sort_by`
- `sort_order`
- `page`
- `page_size`

Common response envelope:
- `report_code`
- `report_name`
- `filters`
- `applied_filters`
- `display`
- `actions`
- `_meta`

Common `_meta` fields:
- `endpoint`
- `supported_filters`
- `feature_flags`
- `available_columns`
- `effective_columns`
- `available_summary_blocks`
- `enabled_summary_blocks`
- `available_drilldowns`
- `available_exports`
- `related_reports`
- `supports_traceability`
- `pagination_mode`

Common drilldown contract:

```json
{
  "target": "vendor_outstanding",
  "label": "Vendor Outstanding",
  "params": {"entity": 32, "entityfinid": 32, "vendor": 12},
  "report_code": "vendor_outstanding",
  "path": "/api/reports/payables/vendor-outstanding/",
  "kind": "report"
}
```

## Vendor Outstanding

Request:

```http
GET /api/reports/payables/vendor-outstanding/?entity=32&entityfinid=32&from_date=2026-04-01&to_date=2026-04-30&include_trace=true
```

Response highlights:
- `rows[*].vendor_name`
- `rows[*].net_outstanding`
- `rows[*]._meta.drilldown`
- `rows[*]._trace`

Export:
- `/excel/`
- `/pdf/`
- `/csv/`
- `/print/`

## AP Aging

Request:

```http
GET /api/reports/payables/aging/?entity=32&entityfinid=32&as_of_date=2026-04-30&view=invoice
```

View modes:
- `summary`
- `invoice`

Invoice response highlights:
- `rows[*].bill_number`
- `rows[*].balance`
- `rows[*]._trace`

## AP to GL Reconciliation

Request:

```http
GET /api/reports/payables/reconciliation/?entity=32&entityfinid=32&as_of_date=2026-04-30&include_trace=true
```

Response highlights:
- `rows[*].subledger_balance`
- `rows[*].gl_balance`
- `rows[*].difference_amount`
- `summary.overall_status`

## Vendor Exceptions

Request:

```http
GET /api/reports/payables/exceptions/?entity=32&entityfinid=32&as_of_date=2026-04-30&min_amount=1000
```

Response highlights:
- `rows[*].exception_type`
- `rows[*].severity`
- `rows[*].amount`

## Purchase Register

Request:

```http
GET /api/reports/purchases/register/?entity=32&entityfinid=32&from_date=2026-04-01&to_date=2026-04-30&include_outstanding=true
```

Payables-specific options:
- `include_outstanding`
- `include_posting_summary`
- `include_payables_drilldowns`

Additive aliases:
- `rows` mirrors `results`
- `pagination` summarizes page state

## Vendor Ledger Statement

Request:

```http
GET /api/reports/payables/vendor-ledger/?entity=32&entityfinid=32&vendor=12&from_date=2026-04-01&to_date=2026-04-30
```

Options:
- `include_opening`
- `include_running_balance`
- `include_settlement_drilldowns`
- `include_related_reports`
- `include_trace`

## Payables Close Pack

Request:

```http
GET /api/reports/payables/close-pack/?entity=32&entityfinid=32&as_of_date=2026-04-30
```

Section flags:
- `include_overview`
- `include_aging`
- `include_reconciliation`
- `include_validation`
- `include_exceptions`
- `include_top_vendors`
- `expanded_validation`

## Vendor Settlement History

Request:

```http
GET /api/reports/payables/settlement-history/?entity=32&entityfinid=32&from_date=2026-04-01&to_date=2026-04-30&include_unapplied=true
```

Options:
- `settlement_type`
- `include_unapplied`
- `include_trace`

Response highlights:
- `rows[*].settlement_number`
- `rows[*].applied_amount`
- `rows[*].unapplied_amount`
- `rows[*]._trace.settlement_id`

## Vendor Debit/Credit Note Register

Request:

```http
GET /api/reports/payables/note-register/?entity=32&entityfinid=32&from_date=2026-04-01&to_date=2026-04-30&note_type=credit
```

Options:
- `note_type`
- `status`
- `include_trace`

Response highlights:
- `rows[*].note_number`
- `rows[*].note_type_name`
- `rows[*].total_note_amount`
- `rows[*]._trace.source_document_id`

## Metadata Endpoint

Request:

```http
GET /api/reports/payables/meta/?entity=32&entityfinid=32
```

Frontend should use:
- `report_definitions[*].supported_filters`
- `report_definitions[*].feature_flags`
- `report_definitions[*].available_columns`
- `report_definitions[*].available_summary_blocks`
- `report_definitions[*].drilldown_targets`
- `report_definitions[*].export_formats`
- `report_definitions[*].pagination_mode`
- `report_definitions[*].view_modes`
