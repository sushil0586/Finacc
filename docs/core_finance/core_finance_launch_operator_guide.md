# Core Finance Launch Operator Guide

Date: 2026-10-06  
Audience: finance users, accountants, implementation consultants, support teams  
Scope: core finance only; HRMS and Payroll are excluded

## 1. Operating Principles

Finacc finance screens are entity, financial-year, and subentity scoped. Always confirm the active scope before creating, posting, or reviewing a document.

Use this order for finance work:

1. Confirm entity, financial year, and subentity.
2. Confirm masters and posting maps.
3. Create source documents.
4. Save draft.
5. Confirm.
6. Post.
7. Verify reports and ledgers.
8. Reconcile or reverse only through supported actions.

Do not bypass backend validation. If the system blocks an action, first check scope, master setup, posting map, document state, and permissions.

## 2. Context And Access

Before starting any module:

- Confirm the active entity is correct.
- Confirm the active financial year matches the transaction date.
- Confirm the active subentity or branch belongs to the active entity.
- Confirm the user role has access to the screen and action.
- Refresh the page after a role or entity switch if menus look stale.

Expected behavior:

- Stale saved FY/subentity choices should be ignored or reset when the entity changes.
- Retired legacy stock menus should not be used.
- Unauthorized routes should be hidden or blocked.
- Documentation should be reachable for logged-in users.

Common access issues:

| Symptom | First Check | Action |
| --- | --- | --- |
| Menu is missing | Role permissions | Ask admin to review role template and effective permissions. |
| Menu opens Access Restricted | Direct route permission | Confirm route key exists in the assigned role. |
| Invalid subentity error | Active entity/subentity | Switch to a subentity that belongs to the active entity. |
| Financial year invalid | Active FY and transaction date | Select the correct FY or adjust the document date. |

## 3. Settings And Masters

Core finance depends on clean setup. Complete these before transaction entry:

- Chart of accounts and account groups.
- Ledgers for customers, vendors, banks, cash, expenses, assets, taxes, WIP, inventory, revenue, and payables/receivables.
- Customers and vendors with GST details where applicable.
- Branch/subentity and GST registrations.
- Payment modes.
- Voucher numbering.
- Sales and purchase charge types.
- Posting maps.
- TDS, TCS, and GST-TDS sections/rates.
- Asset categories and asset posting ledgers.
- Manufacturing settings and manufacturing ledger maps if manufacturing is used.

Setup checks:

- Duplicate masters should be blocked.
- Required fields must be completed.
- Inactive masters should not be selected in new transactions.
- Posting map blockers should explain what ledger is missing.
- Branch numbering should be available only for valid branches in the current entity.

## 4. Sales

Supported launch surfaces:

- Goods sales invoice.
- Service sales invoice.
- Sales credit note.
- Sales debit note.
- Save, confirm, post, unpost/cancel where allowed.
- Print and document output.
- GST, TCS, transport, e-invoice/e-way action states where configured.
- Customer ledger, outstanding, reports, and receipt settlement.

Standard sales workflow:

1. Open the correct sales document type.
2. Confirm entity, FY, branch/subentity, customer, place of supply, and tax registration state.
3. Add goods/service lines.
4. Add charges, discount, rounding, TCS, and transport details where applicable.
5. Save draft.
6. Review the summary popup.
7. Confirm.
8. Post.
9. Print/download if required.
10. Verify Customer Ledger, Customer Outstanding, Daybook, Ledger Book, Trial Balance, and GST/TCS reports.

Sales notes:

- Use credit note when reducing the customer receivable or reversing a previous sale.
- Use debit note when increasing the customer receivable.
- Link the note to the correct source invoice whenever applicable.
- Verify note impact in customer ledger and statutory reports after posting.

GST and TCS:

- GST depends on customer registration, seller/branch registration, state/place of supply, HSN/SAC, and taxability.
- TCS depends on section, applicability, threshold/policy configuration, and customer/document context.
- If a tax context changes after lines are saved, resave and recheck line taxes before posting.

Print and compliance actions:

- Confirm/post state controls which print and compliance actions are available.
- E-invoice/e-way actions depend on provider configuration and document readiness.
- Live provider tests are separate from deterministic app-path validation.

## 5. Purchase

Supported launch surfaces:

- Goods purchase invoice.
- Service purchase invoice.
- Purchase credit note.
- Purchase debit note.
- Purchase register and statutory screens.
- GST, ITC, GST-TDS, Income Tax TDS.
- Purchase-to-payment chain.
- Purchase-to-asset flow where configured.

Standard purchase workflow:

1. Open the correct purchase document type.
2. Confirm entity, FY, branch/subentity, vendor, place of supply, and vendor GST state.
3. Add goods/service lines.
4. Add charges, SAC/HSN, GST, TDS, GST-TDS, and round-off where applicable.
5. Save draft.
6. Review the summary popup.
7. Confirm.
8. Post.
9. Verify Purchase Register, Vendor Ledger, Vendor Outstanding, Daybook, Ledger Book, Trial Balance, and statutory reports.

Purchase notes:

- Use credit note for vendor credit or reduction of payable.
- Use debit note for additional vendor liability.
- Link notes to the correct source invoice when applicable.
- Verify GST/TDS/ITC impact after posting.

Purchase behavior:

- Inventory purchases should create inventory movement when posted.
- Expense purchases should stay out of inventory.
- Asset purchases should create or link to asset intake where configured.

Payment boundary:

- Invoice-level TDS/GST-TDS values belong to the purchase document.
- Runtime TDS on Payment Voucher should not become a second source of truth for invoice-level TDS.

## 6. Vouchers

Supported launch surfaces:

- Cash Voucher.
- Bank Voucher.
- Journal Voucher.
- Payment Voucher.
- Receipt Voucher.

General voucher workflow:

1. Open the voucher screen.
2. Select voucher type/date/numbering context.
3. Select accounts and enter debit/credit or receipt/payment details.
4. Save draft.
5. Confirm where workflow requires it.
6. Post.
7. Verify Daybook, Cashbook/Bankbook where applicable, Ledger Book, Ledger Summary, and Trial Balance.

Payment Voucher:

- Use against-bill mode to settle vendor open items.
- Use on-account only when payment is not matched to a source invoice yet.
- Confirm runtime TDS behavior before posting.
- After full settlement, payable reports should no longer show the item as open.

Receipt Voucher:

- Use invoice-based receipt to settle customer outstanding.
- Use on-account only when the receipt is not matched to a specific invoice yet.
- Confirm runtime TCS behavior before posting.
- After full settlement, receivable reports should no longer show the item as open.

Cash, bank, and journal:

- Use Cash Voucher for cash movement.
- Use Bank Voucher for bank movement.
- Use Journal Voucher for non-cash accounting adjustments.
- Reversal or unpost should be done through supported actions, not by manual counter-entry unless business policy requires that.

## 7. Reports And Accounting Truth

Use reports as the final verification layer.

Core reports:

- Trial Balance.
- Ledger Book.
- Ledger Summary.
- Daybook.
- Cashbook.
- Profit and Loss.
- Balance Sheet.
- Customer Outstanding.
- Vendor Outstanding.
- Sales/Purchase registers.
- GST/TDS/TCS reports.

Report operating rules:

- Confirm entity and FY before opening a report.
- Clear stale saved filters if report output does not match the current entity.
- Use search/filter only after metadata has loaded.
- Drill from summary report to ledger/document where available.
- Compare report totals against posted documents, not draft documents.

Accounting truth checks:

| Transaction | Expected Reports |
| --- | --- |
| Posted sales invoice | Customer Ledger, Revenue Ledger, GST output, Trial Balance, Daybook. |
| Posted purchase invoice | Vendor Ledger, Expense/Inventory/Asset ledger, GST input/TDS as applicable, Trial Balance, Daybook. |
| Posted payment | Vendor Outstanding, Bank/Cash ledger, Payables, Trial Balance. |
| Posted receipt | Customer Outstanding, Bank/Cash ledger, Receivables, Trial Balance. |
| Posted journal | Ledger Book, Ledger Summary, Trial Balance, Daybook. |

If a posted document is missing from reports:

1. Confirm the document is posted, not only saved or confirmed.
2. Confirm report entity/FY/subentity/date filters.
3. Confirm the report search filter is not hiding the row.
4. Confirm posting map produced accounting entries.
5. Check whether the document was unposted or cancelled.

## 8. Bank Reconciliation

Supported workflow:

- Import bank statement.
- Map columns and validate date/amount formats.
- Review unmatched rows.
- Run auto-match where available.
- Manual match exact records.
- Use group/partial match for many-to-one or one-to-many cases.
- Create voucher from bank row where supported.
- Mark reconciled.
- Reverse/cleanup using supported actions.

Import checks:

- Statement period should not duplicate an existing import.
- Debit/credit/signed amount mapping should match the bank file format.
- Opening/closing balances should make business sense.
- Invalid rows should be corrected before committing the import.

Reconciliation checks:

- Matched rows should show correct source document or voucher.
- Partial/group match should preserve clear remaining amounts.
- Voucher-created rows should appear in finance reports after posting.
- Reversal should return the workspace to a clean state.

## 9. Assets

Supported asset workflow:

- Asset category and ledger mapping.
- Asset master/intake.
- Purchase-linked asset intake.
- Capitalization.
- Transfer or custodian/location changes.
- Depreciation run.
- Impairment.
- Disposal.
- Reversal/cancellation where supported.
- Asset reports.

Operator flow:

1. Verify asset category and ledgers.
2. Create or review asset intake.
3. Complete required asset details before capitalization.
4. Capitalize only when purchase/reference/accounting data is ready.
5. Run depreciation after confirming period and useful life.
6. Verify fixed asset register, depreciation schedule, asset events, and ledger impact.

Accounting checks:

- Capitalization should move value from intake/CWIP to asset ledger.
- Depreciation should debit depreciation expense and credit accumulated depreciation.
- Impairment should reduce carrying value through configured ledgers.
- Disposal should clear asset cost/accumulated depreciation and book gain/loss as configured.

## 10. Inventory Finance Links

Supported inventory finance checks:

- Stock Summary.
- Stock Ledger.
- Stock Aging.
- Stock Movement.
- Location Stock.
- Stock Day Book.
- Stock Book Summary/Detail.
- Non-moving and slow/dead stock.
- Reorder status.

Operating rules:

- Inventory reports should be filtered by valid entity/FY/subentity, product, location, and date range.
- Stock Ledger is the detailed movement truth.
- Stock Aging should reconcile valuation with Stock Ledger for the same filtered product/location.
- Batch/location identities matter for FIFO/LIFO valuation.
- Inventory movement should come from posted inventory-affecting documents, not drafts.

If inventory values do not match:

1. Confirm the same product/location/date filters.
2. Confirm batch identity where batch tracking is enabled.
3. Compare Stock Ledger movement rows before comparing summaries.
4. Confirm the document source was posted.
5. Confirm purchase behavior was inventory, not expense or asset.

## 11. Manufacturing Finance Links

Supported manufacturing checks:

- Manufacturing Settings.
- BOM.
- Work order.
- Material issue/consumption.
- Output yield.
- WIP cost.
- Posting audit.
- Manufacturing Summary.
- Production movement reconciliation.

Operator flow:

1. Confirm manufacturing settings and ledger maps.
2. Confirm BOM materials and output products.
3. Create work order.
4. Issue or consume material.
5. Record output.
6. Complete QC/rework/approval where applicable.
7. Post the work order.
8. Verify WIP, consumption, output yield, posting audit, and ledger impact.

Accounting checks:

- Material consumption should reduce inventory or move cost into WIP.
- Finished output should increase finished goods inventory.
- Variance ledgers should be used only when configured.
- Posting audit should explain the accounting movement.

## 12. Compliance

Compliance modules covered:

- TDS.
- TCS.
- GST-TDS.
- GST reports.
- GST reconciliation.
- Purchase statutory.
- Filing packs where available.

TDS:

- Confirm deductor/deductee setup.
- Confirm section/rate and threshold behavior.
- Confirm whether the case is invoice-level TDS or payment-stage/runtime TDS.
- Verify TDS reports after posting.

TCS:

- Confirm customer applicability and section.
- Confirm threshold or zero-collection policy.
- Verify sales invoice/note and receipt impact.
- Verify TCS center and filing pack.

GST-TDS:

- Confirm vendor/entity applicability.
- Confirm section/rate and source document.
- Verify GST-TDS report center.

GST reports and reconciliation:

- Use GST reports for statutory summaries and exports.
- Use GST reconciliation for matching external data against system transactions.
- Drill back to source documents when investigating mismatches.
- Resolve unmatched/partial rows by checking GSTIN, date, document number, taxable value, and tax values.

## 13. RBAC And Role Templates

Role templates should match real user personas:

- Admin: full setup and operational access.
- Accountant: finance documents, vouchers, reports, reconciliation.
- Sales operator: sales documents and related customer views.
- Purchase operator: purchase documents and related vendor views.
- Finance viewer: reports and read-only finance access.
- Restricted user: no sensitive finance access unless explicitly granted.

RBAC operating checks:

- Authorized menus should be clickable.
- Unauthorized menus should be hidden or blocked.
- Direct URL access should respect backend permission checks.
- Effective permissions should be reviewed after role changes.
- Route permission keys should stay synchronized between frontend and backend.

## 14. Email And Notifications

Stage SES smoke status:

- Stage SMTP settings are configured.
- Stage release audit passed email readiness.
- A real inbox smoke was sent and receipt was confirmed on 2026-10-06.

Operational guidance:

- Use stage/prod-like environments for real delivery validation.
- Local console email proves code path only, not real delivery.
- For email issues, check sender, recipient, SMTP/SES credentials, verified sender/domain, spam/promotions folder, and application logs.

## 15. Common Troubleshooting

| Message Or Symptom | Likely Cause | Operator Action |
| --- | --- | --- |
| Subentity is not valid for this entity | Stale or wrong subentity | Switch to a valid subentity for the active entity. |
| Financial year is not valid | Wrong FY or document date | Select the correct FY or adjust the date. |
| Posting map missing | Ledger map incomplete | Ask admin to complete posting setup. |
| Action button disabled | Document state or permission | Check whether document is draft/confirmed/posted and whether role allows the action. |
| Tax value looks wrong | Party GST state, POS, HSN/SAC, taxability, or section setup | Recheck source document fields and tax master setup. |
| Report row missing | Draft/unposted document or filter mismatch | Confirm document is posted and report filters match scope/date. |
| Menu not clickable | RBAC route-permission mismatch or stale session | Refresh, re-login, then ask admin to check permissions. |
| Print/download fails | Popup/download blocked or document not ready | Confirm document state, retry, and check browser download settings. |
| Bank import rejected | Duplicate period or mapping issue | Correct bank file mapping/date/amount columns. |
| Inventory valuation mismatch | Filter or batch identity mismatch | Compare Stock Ledger with same product/location/batch/date filters. |

## 16. Launch Operator Checklist

Before go-live:

- Entity, FY, and subentity context tested.
- Admin and operating roles reviewed.
- Finance masters and posting maps completed.
- Sales create/confirm/post/print/report flow verified.
- Purchase create/confirm/post/print/report flow verified.
- Payment and receipt settlement verified.
- Cash, bank, and journal voucher posting verified.
- Trial Balance, Ledger Book, Daybook, Cashbook, P&L, Balance Sheet verified.
- Bank reconciliation import/match/reversal verified.
- Asset capitalization/depreciation/disposal verified if assets are in scope.
- Inventory and manufacturing finance reports verified if stock/manufacturing are in scope.
- TDS/TCS/GST-TDS/GST reports verified.
- SES/email smoke confirmed in a real inbox.
- Open launch issues reviewed and accepted or closed.

