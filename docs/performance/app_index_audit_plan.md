# App Index Audit Plan

## Goal

Reduce page and report latency by adding composite indexes that match real filter patterns, starting with `posting` and then moving app by app through the modules that feed books, statutory, inventory, payables, receivables, and reconciliation screens.

## Principles

- Prefer composite indexes that match actual `WHERE` clauses used by reports and page APIs.
- Start with additive indexes only.
- Avoid speculative indexes on rarely filtered columns.
- Keep each batch small enough to validate query plan impact after deployment.
- Review write-heavy tables carefully so we do not over-index posting paths.

## Phase 1 Done: Posting App

Implemented in:

- [Finacc/posting/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/posting/models.py)
- [Finacc/posting/migrations/0026_posting_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/posting/migrations/0026_posting_report_indexes.py)

Added indexes:

- `Entry(entity, entityfin, subentity, posting_date)`
- `Entry(entity, status, posting_date)`
- `JournalLine(entity, entityfin, subentity, posting_date)`
- `JournalLine(entity, ledger, posting_date)`
- `JournalLine(entity, account, posting_date)`
- `JournalLine(entity, accounthead, posting_date)`
- `InventoryMove(entity, entityfin, subentity, posting_date)`
- `InventoryMove(entity, location, product, posting_date)`

Why this batch:

- Financial books and drilldowns repeatedly filter `JournalLine` by scope plus date.
- Balance sheet, profit and loss, payables, opening balance, bank reconciliation, and book reports all rely on `entity + posting_date` and then narrow by `ledger`, `account`, or `accounthead`.
- Inventory reports repeatedly filter `InventoryMove` by scope/date and then by `location` and `product`.

## Phase 2 Done: Financial + Purchase

Implemented in:

- [Finacc/financial/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/financial/models.py)
- [Finacc/financial/migrations/0019_financial_lookup_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/financial/migrations/0019_financial_lookup_indexes.py)
- [Finacc/purchase/models/purchase_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_core.py)
- [Finacc/purchase/models/purchase_ap.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_ap.py)
- [Finacc/purchase/migrations/0046_purchase_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0046_purchase_report_indexes.py)

Added indexes:

- `Ledger(entity, isactive, name)`
- `Ledger(entity, accounthead)`
- `account(entity, isactive, accountname)`
- `account(entity, isactive, ledger)`
- `AccountCommercialProfile(entity, partytype, agent)`
- `PurchaseInvoiceHeader(entity, entityfinid, subentity, status, bill_date)`
- `PurchaseInvoiceHeader(entity, entityfinid, vendor, status, bill_date)`
- `PurchaseInvoiceHeader(entity, vendor, supplier_invoice_date, supplier_invoice_number)`
- `VendorBillOpenItem(entity, entityfinid, vendor, is_open, due_date)`
- `VendorBillOpenItem(entity, entityfinid, subentity, is_open, due_date)`
- `VendorSettlement(entity, entityfinid, vendor, status, settlement_date)`
- `VendorAdvanceBalance(entity, entityfinid, vendor, is_open, credit_date)`
- `VendorSettlementLine(open_item, settlement)`

Why this batch:

- Account/vendor/customer pickers repeatedly filter `entity + isactive` and then sort or narrow by name or linked ledger.
- Payables and purchase register flows repeatedly filter invoice headers by scope, vendor, status, and bill date.
- AP aging and settlement flows repeatedly filter open items and advances by vendor/open-state/date.
- Duplicate supplier invoice validation and anomaly reports repeatedly check vendor plus supplier invoice reference/date combinations.

## Phase 3 Done: Sales + Vouchers + Payments + Receipts

Implemented in:

- [Finacc/sales/models/sales_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_core.py)
- [Finacc/sales/models/sales_ar.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_ar.py)
- [Finacc/sales/migrations/0043_sales_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/migrations/0043_sales_report_indexes.py)
- [Finacc/vouchers/models/voucher_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/vouchers/models/voucher_core.py)
- [Finacc/vouchers/migrations/0006_voucher_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/vouchers/migrations/0006_voucher_report_indexes.py)
- [Finacc/payments/models/payment_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payments/models/payment_core.py)
- [Finacc/payments/migrations/0012_payment_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/payments/migrations/0012_payment_report_indexes.py)
- [Finacc/receipts/models/receipt_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/receipts/models/receipt_core.py)
- [Finacc/receipts/migrations/0008_receipt_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/receipts/migrations/0008_receipt_report_indexes.py)

Added indexes:

- `SalesInvoiceHeader(entity, entityfinid, subentity, status, bill_date)`
- `SalesInvoiceHeader(entity, entityfinid, customer, status, bill_date)`
- `CustomerBillOpenItem(entity, entityfinid, customer, is_open, due_date)`
- `CustomerBillOpenItem(entity, entityfinid, subentity, is_open, due_date)`
- `CustomerSettlement(entity, entityfinid, customer, status, settlement_date)`
- `CustomerAdvanceBalance(entity, entityfinid, customer, is_open, credit_date)`
- `CustomerSettlementLine(open_item, settlement)`
- `VoucherHeader(entity, entityfinid, subentity, voucher_date)`
- `VoucherHeader(entity, entityfinid, subentity, status, voucher_date)`
- `VoucherHeader(entity, entityfinid, subentity, voucher_type, voucher_date)`
- `PaymentVoucherHeader(entity, entityfinid, subentity, voucher_date)`
- `PaymentVoucherHeader(entity, entityfinid, subentity, status, voucher_date)`
- `PaymentVoucherHeader(entity, entityfinid, paid_to, status, voucher_date)`
- `PaymentVoucherAllocation(open_item, payment_voucher)`
- `ReceiptVoucherHeader(entity, entityfinid, subentity, voucher_date)`
- `ReceiptVoucherHeader(entity, entityfinid, subentity, status, voucher_date)`
- `ReceiptVoucherHeader(entity, entityfinid, received_from, status, voucher_date)`
- `ReceiptVoucherAllocation(open_item, receipt_voucher)`

Why this batch:

- Sales register, GSTR, receivables, and invoice list pages repeatedly combine scope, customer, status, and bill date.
- Receipt/payment/voucher pages and exports repeatedly sort by `voucher_date` inside scope while filtering by `status`, `subentity`, `voucher_type`, or party.
- AR allocation and settlement flows repeatedly traverse from open items into settlement bridges.

## Phase 4 Done: Bank Reconciliation + Reports Support

Implemented in:

- [Finacc/bank_reco/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reco/models.py)
- [Finacc/bank_reco/migrations/0004_bank_reco_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reco/migrations/0004_bank_reco_runtime_indexes.py)
- [Finacc/reports/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/models.py)
- [Finacc/reports/migrations/0006_report_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/migrations/0006_report_runtime_indexes.py)

Added indexes:

- `BankReconciliationRun(statement_import, created_at, id)`
- `BankStatementLine(statement_import, validation_status, txn_date)`
- `UserReportPreference(user, entity, isactive, report_code)`
- `ReportFreezeSnapshot(report_code, entity, entityfinid, subentity, created_at)`
- `ReportFilingRun(report_code, entity, entityfinid, subentity, created_at)`

Why this batch:

- Bank reconciliation repeatedly asks for the latest run for a statement import and then scans validated lines inside a statement/date window.
- Report preference lookups repeatedly filter by `user + entity + isactive + report_code`.
- GSTR and other report services repeatedly fetch latest freeze snapshots and filing runs by report scope.

## Phase 5 Done: Inventory / Stock Workflows

Implemented in:

- [Finacc/posting/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/posting/models.py)
- [Finacc/posting/migrations/0027_inventory_balance_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/posting/migrations/0027_inventory_balance_indexes.py)
- [Finacc/inventory_ops/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/inventory_ops/models.py)
- [Finacc/inventory_ops/migrations/0007_inventory_ops_report_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/inventory_ops/migrations/0007_inventory_ops_report_indexes.py)

Added indexes:

- `InventoryMove(entity, location, product, batch_number)`
- `InventoryTransfer(entity, entityfin, subentity, status, transfer_date)`
- `InventoryAdjustment(entity, entityfin, subentity, status, adjustment_date)`

Why this batch:

- Inventory transfer and adjustment pages list documents by scope and date, and future operational filters naturally add `status`.
- Inventory stock availability checks repeatedly hit `entity + location + product`, and batch-managed products add `batch_number` on the same lookup path.
- Stock ledger, movement, aging, and location views already benefited from the earlier `InventoryMove` date indexes, so this batch filled the remaining operational gaps rather than duplicating report coverage.

## Phase 6 Done: Statutory / Tax Workspaces

Implemented in:

- [Finacc/purchase/models/purchase_statutory.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_statutory.py)
- [Finacc/purchase/migrations/0047_purchase_statutory_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0047_purchase_statutory_runtime_indexes.py)

Added indexes:

- `PurchaseStatutoryChallan(entity, entityfinid, subentity, tax_type, status, challan_date)`
- `PurchaseStatutoryChallanLine(header, challan)`
- `PurchaseStatutoryReturn(entity, entityfinid, subentity, tax_type, status, period_to)`
- `PurchaseStatutoryReturn(original_return, revision_no)`
- `PurchaseStatutoryReturn(original_return, status)`
- `PurchaseStatutoryReturnLine(challan, header)`

Why this batch:

- Purchase statutory list pages filter by scope, tax type, status, and date on almost every load.
- Challan-to-return allocation and reconciliation logic repeatedly aggregates by `header + challan`.
- Revision safety checks repeatedly probe returns by `original_return + revision_no` and `original_return + status`.
- GST-TDS and GST reconciliation were reviewed in the same pass; their existing unique/composite keys already cover the hot paths we found, so no extra indexes were added there yet.

## Phase 7 Done: Sales Compliance / GST Reports

Implemented in:

- [Finacc/sales/models/sales_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_core.py)
- [Finacc/sales/models/sales_addons.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/models/sales_addons.py)
- [Finacc/sales/migrations/0044_sales_gstr_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/sales/migrations/0044_sales_gstr_runtime_indexes.py)

Added indexes:

- `SalesInvoiceHeader(entity, entityfinid, subentity, bill_date, doc_code, doc_no)`
- `SalesInvoiceHeader(entity, entityfinid, subentity, supply_category, bill_date)`
- `SalesInvoiceHeader(entity, entityfinid, subentity, place_of_supply_state_code, bill_date)`
- `SalesInvoiceLine(header, hsn_sac_code, is_service, gst_rate)`
- `SalesTaxSummary(header, gst_rate, taxability, hsn_sac_code)`
- `SalesAdvanceAdjustment(entity, entityfinid, subentity, is_amendment, entry_type, voucher_date)`
- `SalesAdvanceAdjustment(entity, entityfinid, subentity, entry_type, voucher_number)`
- `SalesEcommerceSupply(entity, entityfinid, subentity, is_amendment, invoice_date)`
- `SalesEcommerceSupply(entity, entityfinid, subentity, is_amendment, supplier_eco_gstin)`
- `SalesEcommerceSupply(entity, entityfinid, subentity, is_amendment, operator_gstin, supply_split)`

Why this batch:

- GSTR-1 table services repeatedly sort invoices by `bill_date + doc_code + doc_no` after applying scope filters.
- Sales classification logic repeatedly narrows by `supply_category`, `place_of_supply_state_code`, and report date windows.
- HSN summary, nil/exempt summary, and invoice bucket rendering repeatedly aggregate through `SalesTaxSummary` and `SalesInvoiceLine` by header plus HSN/service/rate buckets.
- Table 11 validation and report views repeatedly filter advances by scope, amendment flag, entry type, voucher date, and voucher number.
- Tables 14/14A/15/15A repeatedly group ECO rows by supplier/operator GSTIN and amendment/date scope.

## Phase 8 Done: Entity / Master / Shared Lookup Pages

Implemented in:

- [Finacc/entity/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/entity/models.py)
- [Finacc/entity/migrations/0034_entity_lookup_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/entity/migrations/0034_entity_lookup_runtime_indexes.py)
- [Finacc/financial/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/financial/models.py)
- [Finacc/financial/migrations/0020_financial_master_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/financial/migrations/0020_financial_master_runtime_indexes.py)

Added indexes:

- `Entity(isactive, entityname)`
- `Entity(createdby, isactive)`
- `SubEntity(entity, isactive, is_head_office, subentityname)`
- `EntityFinancialYear(entity, isactive, finstartyear)`
- `EntityFinancialYear(entity, isactive, is_year_closed, finstartyear)`
- `FinancialMasterRule(entity, isactive, priority)`
- `FinancialMasterRule(template_code, isactive, priority)`
- `FinancialCodeSeries(entity, isactive, priority)`
- `FinancialCodeSeries(template_code, isactive, priority)`
- `account(entity, accountname, id)`
- `AccountAddress(account, isprimary, isactive)`

Why this batch:

- Top-bar context selectors and report meta APIs repeatedly load active entities, active financial years, and active subentities ordered by name or financial-year start date.
- Dashboard and controls flows repeatedly narrow financial years by `is_year_closed` inside active entity scope.
- Shared customer/vendor/account pickers repeatedly scan accounts by `entity + accountname`, while profile payload builders repeatedly prefetch active primary addresses.
- Financial governance and code allocation repeatedly resolve the best active rule/series by `entity` or `template_code`, then order by priority.

## Phase 9 Done: Geography / Statutory Import / Reconciliation Support

Implemented in:

- [Finacc/geography/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/geography/models.py)
- [Finacc/geography/migrations/0004_geography_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/geography/migrations/0004_geography_runtime_indexes.py)
- [Finacc/gst_reconciliation/models/reconciliation_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/gst_reconciliation/models/reconciliation_core.py)
- [Finacc/gst_reconciliation/models/imported_returns.py](/Users/ansh/finacc-angular/finacc-django/Finacc/gst_reconciliation/models/imported_returns.py)
- [Finacc/gst_reconciliation/migrations/0006_runtime_lookup_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/gst_reconciliation/migrations/0006_runtime_lookup_indexes.py)
- [Finacc/purchase/models/gstr2b_models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/gstr2b_models.py)
- [Finacc/purchase/migrations/0048_purchase_gstr2b_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0048_purchase_gstr2b_runtime_indexes.py)

Added indexes:

- `Country(isactive, countryname)`
- `State(country, isactive, statename)`
- `District(state, isactive, districtname)`
- `City(distt, isactive, cityname)`
- `City(isactive, pincode)`
- `GstReconciliationRun(entity, reconciliation_type, return_period, status, created_at)`
- `GstReconciliationItem(run, resolution_status, updated_at)`
- `GstReconciliationItem(run, match_status, updated_at)`
- `GstImportedReturn(entity, return_type, return_period, status, created_at)`
- `GstImportedReturnRow(imported_return, counterparty_gstin_normalized, row_no)`
- `Gstr2bImportBatch(entity, entityfinid, subentity, period, id)`
- `Gstr2bImportRow(batch, match_status, id)`
- `Gstr2bImportRow(batch, supplier_gstin, supplier_invoice_number)`

Why this batch:

- Geography dropdowns and onboarding selectors repeatedly load active countries, states, districts, and cities filtered by parent scope and sorted by display name.
- GST reconciliation run/import list APIs repeatedly filter by entity, type, period, and status while sorting newest first.
- GST reconciliation item grids and reviewer queues repeatedly filter unresolved items by run plus resolution/match status and sort by latest activity.
- Imported GST row views and supplier analytics repeatedly group or order rows by imported return plus normalized GSTIN.
- Purchase GSTR-2B batch review and matching repeatedly filter rows inside a batch by review status and GSTIN/invoice reference.

## Phase 10 Done: Attachments / Audit / Admin-heavy Utility Tables

Implemented in:

- [Finacc/purchase/models/purchase_addons.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_addons.py)
- [Finacc/purchase/migrations/0049_purchaseattachment_ix_purchase_attach_hdr_dt.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0049_purchaseattachment_ix_purchase_attach_hdr_dt.py)
- [Finacc/invoice_import/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/invoice_import/models.py)
- [Finacc/invoice_import/migrations/0004_importjob_ix_invimp_job_recent_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/invoice_import/migrations/0004_importjob_ix_invimp_job_recent_and_more.py)
- [Finacc/rbac/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/rbac/models.py)
- [Finacc/rbac/migrations/0129_rbac_audit_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/rbac/migrations/0129_rbac_audit_runtime_indexes.py)
- [Finacc/bank_reco/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reco/models.py)
- [Finacc/bank_reco/migrations/0005_bankreconciliationauditlog_ix_bank_reco_audit_run_dt.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reco/migrations/0005_bankreconciliationauditlog_ix_bank_reco_audit_run_dt.py)

Added indexes:

- `PurchaseAttachment(header, created_at)`
- `ImportJob(entity, module, created_at)`
- `ImportRow(job, status, row_no)`
- `RBACAuditLog(entity, created_at)`
- `BankReconciliationAuditLog(run, created_at)`

Why this batch:

- Purchase attachment popups repeatedly load attachments by invoice header and show the newest first, while saved-invoice add/delete/download actions always re-enter the same header-scoped list.
- Legacy import workspaces repeatedly fetch recent jobs by module/entity and then drill into validation rows by status plus row ordering during review and commit.
- RBAC audit history screens repeatedly filter by entity and sort newest first, with optional action/object filters layered on top.
- Bank reconciliation audit-trail exports repeatedly pull the latest run-scoped activity ordered by timestamp.

## Phase 11 Done: Operational Workspaces Outside HRMS/Payroll

Implemented in:

- [Finacc/assets/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/models.py)
- [Finacc/assets/migrations/0008_assetcategory_ix_asset_cat_ent_act_nm_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/assets/migrations/0008_assetcategory_ix_asset_cat_ent_act_nm_and_more.py)
- [Finacc/manufacturing/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/manufacturing/models.py)
- [Finacc/manufacturing/migrations/0011_manufacturingbom_ix_mfg_bom_scope_act_cd_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/manufacturing/migrations/0011_manufacturingbom_ix_mfg_bom_scope_act_cd_and_more.py)
- [Finacc/retail/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/retail/models.py)
- [Finacc/retail/migrations/0007_retailclosebatch_ix_rtl_clsbch_scope_ct_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/retail/migrations/0007_retailclosebatch_ix_rtl_clsbch_scope_ct_and_more.py)
- [Finacc/bank_reconciliation/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reconciliation/models.py)
- [Finacc/bank_reconciliation/migrations/0005_bankreconciliationauditlog_ix_bral_sess_created_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/bank_reconciliation/migrations/0005_bankreconciliationauditlog_ix_bral_sess_created_and_more.py)

Added indexes:

- `AssetCategory(entity, is_active, name)`
- `FixedAsset(entity, subentity, is_active, id)`
- `DepreciationRun(entity, entityfinid, subentity, status, period_to)`
- `ManufacturingRoute(entity, subentity, is_active, code)`
- `ManufacturingBOM(entity, subentity, is_active, code)`
- `ManufacturingWorkOrder(entity, entityfin, subentity, status, production_date)`
- `RetailTicket(entity, subentity, bill_date)`
- `RetailSession(entity, subentity, location, status, opened_at)`
- `RetailCloseBatch(entity, subentity, location, created_at)`
- `BankReconciliationSession(entity, entityfin, subentity, bank_account, status, created_at)`
- `BankStatementBatch(session, created_at)`
- `BankReconciliationExceptionItem(session, status, created_at)`
- `BankReconciliationAuditLog(session, created_at)`

Why this batch:

- Asset workspaces repeatedly load active categories by entity and display name, fetch scoped active asset lists ordered by newest id, and list depreciation runs by scope/status/period.
- Manufacturing setup screens repeatedly load active routes and BOMs inside entity/subentity scope, while work order dashboards and audit reports repeatedly filter by scope, status, and production date.
- Retail POS screens repeatedly fetch recent tickets, resolve the currently open session for an entity/subentity/location, and list recent close batches by the same operational scope.
- The legacy bank reconciliation workspace repeatedly loads sessions, batches, exceptions, and audit history by scope and recency, especially on operator review pages.

## Phase 12 Done: Remaining Support Apps Except HRMS/Payroll

Implemented in:

- [Finacc/Authentication/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/Authentication/models.py)
- [Finacc/Authentication/migrations/0005_auth_runtime_indexes.py](/Users/ansh/finacc-angular/finacc-django/Finacc/Authentication/migrations/0005_auth_runtime_indexes.py)
- [Finacc/entity/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/entity/models.py)
- [Finacc/entity/migrations/0035_approvalrequest_ix_appr_req_entity_flow_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/entity/migrations/0035_approvalrequest_ix_appr_req_entity_flow_and_more.py)
- [Finacc/numbering/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/numbering/models.py)
- [Finacc/numbering/migrations/0002_documentnumberseries_ix_doc_series_lookup_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/numbering/migrations/0002_documentnumberseries_ix_doc_series_lookup_and_more.py)
- [Finacc/commerce/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/commerce/models.py)
- [Finacc/commerce/migrations/0002_commercepromotion_ix_commerce_promo_scope.py](/Users/ansh/finacc-angular/finacc-django/Finacc/commerce/migrations/0002_commercepromotion_ix_commerce_promo_scope.py)
- [Finacc/localization/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/localization/models.py)
- [Finacc/localization/migrations/0002_localizedstringkey_ix_l10n_key_active_mod_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/localization/migrations/0002_localizedstringkey_ix_l10n_key_active_mod_and_more.py)
- [Finacc/subscriptions/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/subscriptions/models.py)
- [Finacc/subscriptions/migrations/0005_customersubscription_ix_sub_acct_active_cur_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/subscriptions/migrations/0005_customersubscription_ix_sub_acct_active_cur_and_more.py)
- [Finacc/auditlogger/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/auditlogger/models.py)
- [Finacc/auditlogger/migrations/0002_auditlog_ix_auditlog_method_ts_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/auditlogger/migrations/0002_auditlog_ix_auditlog_method_ts_and_more.py)
- [Finacc/errorlogger/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/errorlogger/models.py)
- [Finacc/errorlogger/migrations/0002_errorlog_ix_errorlog_method_ts_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/errorlogger/migrations/0002_errorlog_ix_errorlog_method_ts_and_more.py)

Added indexes:

- `AuthSession(user, revoked_at, issued_at)`
- `AuthOTP(email, purpose, consumed_at, created_at)`
- `EntityApprovalPolicy(entity, policy_key, status, subentity)`
- `ApprovalRequest(entity, isactive, workflow_key, status, updated_at)`
- `ApprovalStep(approval_request, status, step_order)`
- `NotificationPreference(user, event_code, entity)`
- `NotificationEvent(entity, subentity, created_at)`
- `UserNotification(user, isactive, is_read, created_at)`
- `DocumentType(module, default_code, is_active)`
- `DocumentNumberSeries(entity, entityfinid, subentity, doc_type, doc_code, is_active)`
- `CommercePromotion(entity, subentity, is_active, code)`
- `LocalizedStringKey(is_active, module)`
- `LocalizedStringValue(language, is_approved, entity, string_key)`
- `CustomerSubscription(customer_account, is_active, ended_at, status, started_at)`
- `UserEntityAccess(user, customer_account, is_active, expires_at)`
- `UserEntityAccess(customer_account, is_active, expires_at)`
- `AuditLog(method, timestamp)`
- `AuditLog(user, timestamp)`
- `ErrorLog(method, timestamp)`
- `ErrorLog(user, timestamp)`

Why this batch:

- Auth flows repeatedly fetch latest active sessions and OTP artifacts for a user/email plus purpose and recency.
- Approval workspaces repeatedly resolve active policies by entity/workflow/subentity, list approval requests by workflow/status/updated time, and pick the next pending step in order.
- Notification APIs repeatedly count unread rows and fetch active notification feeds by user plus entity/subentity scope.
- Document numbering repeatedly resolves a live series by exact entity/FY/subentity/doc-type/doc-code scope, while purchase doc-type helpers repeatedly map `module + default_code`.
- Commerce promotions and localization bundles repeatedly load active scoped rows by entity/subentity/module/language.
- Subscription and tenant-access services repeatedly resolve the current live subscription per account and active memberships per user/account with expiry filtering.
- Audit/error log admins repeatedly filter by method/user and sort newest first.

## Next App Batches

## Phase 13 Done: Catalog App

Implemented in:

- [Finacc/catalog/models.py](/Users/ansh/finacc-angular/finacc-django/Finacc/catalog/models.py)
- [Finacc/catalog/migrations/0012_barcodelabeltemplate_ix_cat_lbl_scope_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/catalog/migrations/0012_barcodelabeltemplate_ix_cat_lbl_scope_and_more.py)

Added indexes:

- `ProductCategory(entity, isactive, pcategoryname)`
- `Brand(entity, isactive, name)`
- `UnitOfMeasure(entity, isactive, code)`
- `Product(entity, isactive, productname, id)`
- `HsnSac(entity, isactive, code)`
- `PriceList(entity, isactive, name)`
- `ProductAttribute(entity, isactive, name)`
- `BarcodeLabelTemplate(entity, subentity, isdefault, name)`
- `ProductBarcode(product, isprimary, id)`
- `ProductImage(product, is_primary, id)`
- `OpeningStockByLocation(product, as_of_date, id)`

Why this batch:

- Product master pages repeatedly load active entity-scoped categories, brands, UOMs, HSN/SAC rows, price lists, and attributes ordered by display name/code.
- Catalog product selection and transaction-product APIs repeatedly scan active products by entity and sort by `productname`, while child data is fetched in latest-first order.
- Barcode label template resolution repeatedly filters by entity plus optional subentity and then prefers default templates first.
- Product detail tabs repeatedly load barcode, image, and opening-stock child rows by product with stable primary/latest ordering.
- Existing `ProductGstRate` and `ProductPrice` indexes already covered the catalog tax/price history paths, so this batch only filled the remaining lookup and child-list gaps.

## Next App Batches

### 1. HRMS / Payroll Only

## Validation Checklist Per Batch

- Capture the slow page/report and the exact queryset or SQL pattern first.
- Add only the minimum composite indexes needed for that query family.
- Run migration in staging and inspect query plans for the affected APIs.
- Watch insert/update overhead on posting-heavy tables.
- Remove redundant index ideas if a unique constraint or existing composite already covers the left prefix.

## Recommended Execution Order

1. `posting`
2. `financial`
3. `purchase`
4. `sales`
5. `vouchers`, `payments`, `receipts`
6. `bank_reco`
7. `reports` support models
8. `inventory`
9. `statutory`

## Notes

- The current shell did not have the Django environment activated, so the posting migration was written manually instead of generated by `makemigrations`.
- Before applying in a shared environment, run:
  - `python manage.py makemigrations --check`
  - `python manage.py migrate`
  - targeted explain-plan checks on the slowest report endpoints
