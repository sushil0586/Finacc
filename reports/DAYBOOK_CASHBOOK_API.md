# Daybook and Cashbook API

## Endpoints

- `GET /api/reports/financial/meta/?entity=<id>`
  - Shared metadata for financial report filters, including Daybook/Cashbook voucher types,
    statuses, financial years, subentities, and scoped account option lists.
- `GET /api/reports/financial/daybook/`
  - Chronological Daybook listing from accounting entries.
- `GET /api/reports/financial/daybook/<entry_id>/`
  - Drill-down to journal lines for one posting entry.
- `GET /api/reports/financial/cashbook/`
  - Cash/bank book report with safe single-account detail or multi-account summary behavior.

## Query Params

### Daybook

- `entity`: required entity scope
- `entityfinid`: optional financial year scope
- `subentity`: optional branch/subentity scope
- `from_date`: inclusive start date
- `to_date`: inclusive end date
- `voucher_type`: comma-separated `TxnType` filter
- `transaction_type`: alias of `voucher_type`
- `status`: comma-separated `draft`, `posted`, `reversed`, or numeric status codes
- `posted`: `true|false`; omitted means no posted-status filter
- `account`: comma-separated account ids; returns entries touching those accounts
- `search`: voucher/reference/narration search
- `page`: page number
- `page_size`: page size, default `100`, max `500`

### Cashbook

- `entity`: required entity scope
- `entityfinid`: optional financial year scope
- `subentity`: optional branch/subentity scope
- `from_date`: inclusive start date
- `to_date`: inclusive end date
- `mode`: `cash|bank|both`
- `cash_account`: comma-separated cash account ids that define target cashbook accounts
- `bank_account`: comma-separated bank account ids that define target cashbook accounts
- `account`: comma-separated counter-account ids for visible row filtering
- `voucher_type`: comma-separated `TxnType` filter
- `search`: voucher/narration/description search
- `page`: page number
- `page_size`: page size, default `100`, max `500`

## Example Requests

### Financial metadata

```text
GET /api/reports/financial/meta/?entity=1
```

### Daybook

```text
GET /api/reports/financial/daybook/?entity=1&entityfinid=1&subentity=1&from_date=2025-04-01&to_date=2025-04-30&voucher_type=C,B,RV,PV&page=1&page_size=50
```

### Cashbook single_account_detail

```text
GET /api/reports/financial/cashbook/?entity=1&cash_account=101&from_date=2025-04-01&to_date=2025-04-30
```

### Cashbook multi_account_summary

```text
GET /api/reports/financial/cashbook/?entity=1&cash_account=101&bank_account=102&from_date=2025-04-01&to_date=2025-04-30
```

## Response Contract

Top-level shape:

```json
{
  "filters": {},
  "mode": "voucher_list | single_account_detail | multi_account_summary | empty",
  "balance_integrity": true,
  "balance_note": "...",
  "totals": {},
  "opening_balance": "0.00",
  "closing_balance": "0.00",
  "count": 0,
  "next": null,
  "previous": null,
  "results": [],
  "running_balance_scope": null,
  "balance_basis": "...",
  "account_summaries": []
}
```

Notes:

- Monetary fields are fixed 2-decimal strings.
- Daybook `opening_balance` and `closing_balance` are always `null`.
- Cashbook `running_balance` is present only in `single_account_detail`.

### Daybook row fields

- `transaction_date`
- `voucher_date`
- `voucher_number`
- `voucher_type`
- `voucher_type_name`
- `narration`
- `reference_number`
- `debit_total`
- `credit_total`
- `status`
- `status_name`
- `posted`
- `source_module`
- `created_by`
- `entry_id`
- `txn_id`
- `drilldown_target`
- `drilldown_params`

### Cashbook row fields

- `date`
- `voucher_number`
- `voucher_type`
- `voucher_type_name`
- `account_impacted`
- `counter_account`
- `particulars`
- `receipt_amount`
- `payment_amount`
- `running_balance`
- `running_balance_scope`
- `narration`
- `source_module`
- `entry_id`
- `journal_line_id`
- `detail_id`
- `drilldown`

## Cashbook Mode Rules

- `single_account_detail`
  - used only when exactly one scoped cash/bank account is selected
  - and no selective subset filters like `voucher_type`, `account`, or `search`
  - `running_balance` is present
- `multi_account_summary`
  - used when multiple cash/bank accounts are selected
  - or when subset filters are applied
  - `running_balance` is intentionally `null`
- Opening and closing balances always come from true posted movement for the scoped cash/bank accounts, not just visible rows.

## Validation Rules

- Reject invalid `from_date > to_date`
- Reject invalid `voucher_type`
- Reject invalid Daybook `status`
- Reject invalid `posted`
- Reject invalid/non-entity account ids
- Reject Cashbook conflicts:
  - `mode=cash` with `bank_account`
  - `mode=bank` with `cash_account`
  - overlapping ids in `cash_account` and `bank_account`
- If Daybook sends both `status` and `posted`, both filters apply as an intersection

## Accounting Assumptions

- Daybook source of truth: `posting.Entry` with totals from `posting.JournalLine`
- Cashbook source of truth: cash/bank-side `posting.JournalLine`
- Cashbook includes `POSTED` and `REVERSED` as posted accounting movement
- Receipt/payment classification is based only on debit/credit direction of the cash/bank-side journal line
- Opening balance is all scoped posted movement before `from_date`
- Closing balance is all scoped posted movement through `to_date`
- Visible subset filters narrow displayed rows but do not redefine the balance basis

## Frontend Integration Notes

- Do not use the deleted legacy route `GET /api/reports/transaction-types/`.
- Frontend should use `GET /api/reports/financial/meta/?entity=<id>` for:
  - `daybook_voucher_types`
  - `cashbook_voucher_types`
  - legacy-compatible `voucher_types` alias for Daybook
  - `daybook_statuses`
  - `all_accounts`
  - `cash_accounts`
  - `bank_accounts`
- Monetary fields are strings with 2 decimals
- `running_balance` may be `null` by design
- Cashbook `opening_balance` and `closing_balance` are accounting-scope balances, not visible-row totals
- Daybook `opening_balance` and `closing_balance` are always `null` for contract consistency
- Recommended drill-down identifiers:
  - Daybook: `entry_id`, `txn_id`, `drilldown_target`, `drilldown_params`
  - Cashbook: `entry_id`, `journal_line_id`, `detail_id`, `drilldown`

## Test Command

```bash
Finacc/venv/bin/python Finacc/manage.py test reports.tests_books --settings=FA.settings_test
```

## Migration Note

Minimum fix applied in `vouchers/0002_final_voucher_design.py` for fresh SQLite test DB setup:

- remove legacy index on `ledger_account` before rename
- remove legacy check constraint on `amount` before column drop

This fix only corrects migration sequencing/state for test database creation. It does not change runtime accounting logic.
