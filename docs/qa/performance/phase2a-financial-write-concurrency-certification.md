# Finacc Phase 2A - Financial Write-Concurrency and Transaction Integrity Certification

Date: 2026-10-10  
Environment: local Django test database and local PostgreSQL  
Gate: financial write-concurrency before production-like high-concurrency testing  
Verdict after Phase 2A.1 rerun: **Conditional Fail for large-scale financial write load**

Verdict after Phase 2A.2 rerun: **Conditional Fail: cross-tenant write certification remains open**

Verdict after Phase 2A.3 rerun: **Conditional Pass for Phase 2B entry; unrestricted high-volume write load still requires staging/prod-like confirmation**

## Phase 2A.1 Update

Phase 2A.1 repaired the AP payment retry fixture and added a reusable real-concurrency harness for sales and purchase invoice write paths:

`perf/tests_phase2a_write_concurrency.py`

The new harness uses:

- `APITransactionTestCase`.
- Per-worker `APIClient` instances.
- `ThreadPoolExecutor`.
- Synchronization barriers.
- `close_old_connections()` per worker.
- Real API calls for sales and purchase create/confirm/post.
- Existing financial seeding and static account mapping services.
- Journal debit/credit reconciliation after posting.

No accounting business logic was changed to make the tests pass.

## Phase 2A.2 Update

Phase 2A.2 extended `perf/tests_phase2a_write_concurrency.py` to cover the remaining payment allocation and payment voucher numbering/posting gaps for the AP payment side.

Added coverage:

- AP settlement concurrent allocations against the same invoice at 2, 5, and 10 workers.
- AP settlement concurrent payments against different invoices for the same vendor at 2, 5, and 10 workers.
- Payment voucher concurrent confirm numbering at 2, 5, and 10 workers.
- Payment voucher concurrent confirm/post against different invoices at 2, 5, and 10 workers.
- Open-item reconciliation after concurrent payments: settled amount, outstanding amount, and `is_open`.
- Payment voucher status, voucher-code uniqueness, AP settlement linkage, and numbering sequence assertions.

Still not fully certified:

- Simultaneous sales, purchase, and payment operations across two isolated tenants. The current deterministic E2E fixture creates one complete tenant/company scope. A second fully seeded tenant fixture remains required before this can be claimed.

## Phase 2A.3 Update

Phase 2A.3 closed the cross-tenant certification gap in `perf/tests_phase2a_write_concurrency.py`.

Added coverage:

- Reusable second tenant/company fixture with independent entity, subentity, financial year, GST registration, vendor, customer, ledgers, static account mappings, sales/purchase/payment numbering series, payment mode, product/UOM, and sales/purchase settings.
- Real authorized user membership and subscription account setup before worker synchronization, avoiding lazy subscription provisioning races during financial writes.
- Simultaneous cross-tenant sales invoice create/confirm, purchase invoice create/confirm, and payment voucher create/confirm/post at 2, 5, and 10 total workers.
- Tenant ownership assertions for source documents, vouchers, AP open items, settlements, and journal entries.
- Per-tenant voucher number isolation for sales, purchase, and payment series.
- Independent open-item reconciliation per tenant.
- Cross-tenant object-ID misuse check: a payment voucher created in tenant B is rejected when acted on through tenant A scope, with no financial state change.

Harness setup finding:

- The first cross-tenant attempt exposed a non-accounting fixture race in lazy subscription/customer-account auto-provisioning: concurrent requests for the same test user attempted to create the same `CustomerAccount.slug`. The harness now pre-creates the authorized subscription account and entity membership before financial worker execution. No accounting business logic was changed.

## Objective

Phase 2A validates whether Finacc can safely move into high-concurrency write testing for accounting workflows. The certification rule is stricter than HTTP success: every scenario must reconcile source documents, voucher numbers, ledger entries, allocation state, rollback behavior, and tenant boundaries after simultaneous writes.

No accounting business rules were changed during this phase.

## Inputs Used

- Phase 1D certification report: `docs/qa/performance/phase1d-final-local-certification.md`
- Phase 1D telemetry tool: `perf/baseline/phase1d_resource_monitor.py`
- Existing sales, purchase, payment, inventory, posting-control, and reporting regression tests
- Local PostgreSQL test database with Django `--keepdb`

## Supported Workflow Discovery

Discovered write/posting API contracts:

| Area | Supported routes or service workflow |
| --- | --- |
| Sales invoice | `/api/sales/invoices/`, `/api/sales/invoices/<id>/confirm/`, `/api/sales/invoices/<id>/post/`, `/api/sales/invoices/<id>/cancel/`, `/api/sales/invoices/<id>/settlement/` |
| Purchase invoice | `/api/purchase/purchase-invoices/`, `/api/purchase/purchase-invoices/<id>/confirm/`, `/api/purchase/purchase-invoices/<id>/post/`, `/api/purchase/purchase-invoices/<id>/unpost/`, `/api/purchase/purchase-invoices/<id>/cancel/` |
| Payment voucher | `/api/payments/payment-vouchers/`, `/api/payments/payment-vouchers/<id>/confirm/`, `/api/payments/payment-vouchers/<id>/post/`, `/api/payments/payment-vouchers/<id>/unpost/`, `/api/payments/payment-vouchers/<id>/cancel/` |
| AP allocation/settlement | `/api/payments/ap/allocation-preview/`, payment voucher post path, AP settlement service |
| AR settlement | `/api/sales/ar/settlements/`, `/api/sales/ar/settlements/<id>/post/`, `/api/sales/ar/settlements/<id>/cancel/` |
| Inventory financial writes | Inventory transfer/adjustment service post, unpost, cancel, update/post race |
| Journal/control posting | Year close, opening generation, posting setup application |

Existing deterministic fixture coverage now includes sales and purchase API-level concurrent confirm/post retry paths, AP payment allocation, payment voucher concurrent numbering/posting, inventory/control true concurrency, and cross-tenant simultaneous sales/purchase/payment writes at 2, 5, and 10 total workers.

## Commands Executed

### Sequential Supported-Contract Idempotency And Numbering

```bash
venv/bin/python manage.py test \
  sales.tests_e2e_api.SalesApiEndToEndTests.test_confirm_allocates_doc_number_and_invoice_number \
  sales.tests_e2e_api.SalesApiEndToEndTests.test_repeated_confirm_call_is_idempotent_for_confirmed_invoice \
  sales.tests_e2e_api.SalesApiEndToEndTests.test_repeated_post_call_is_idempotent_for_posted_invoice \
  sales.tests_e2e_api.SalesApiEndToEndTests.test_same_gstin_invoice_number_is_database_unique_across_branches \
  purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_repeated_confirm_call_is_idempotent_for_confirmed_purchase_invoice \
  purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_repeated_post_call_is_idempotent_for_posted_purchase_invoice \
  payments.tests.PaymentVoucherServiceTests.test_confirm_voucher_returns_already_confirmed_for_repeat_confirm \
  payments.tests.PaymentVoucherServiceTests.test_confirm_voucher_skips_already_used_doc_number \
  payments.tests.PaymentChoicesEntitlementTests.test_post_voucher_returns_already_posted_for_repeat_post \
  payments.tests.PaymentChoicesEntitlementTests.test_cancel_voucher_returns_already_cancelled_for_repeat_cancel \
  payments.tests.PaymentChoicesEntitlementTests.test_unpost_voucher_blocks_repeat_unpost_after_return_to_confirmed \
  --keepdb
```

Result:

```text
Ran 11 tests in 3.582s
OK
```

### Existing True Concurrent Write/Control Scenarios

```bash
venv/bin/python manage.py test \
  payments.tests.MetaCacheSingleFlightTests.test_concurrent_requests_share_single_builder_run \
  inventory_ops.tests.InventoryOpsConcurrencyTests \
  reports.tests_controls_destructive_workflows \
  --keepdb
```

Result:

```text
Ran 9 tests in 11.417s
OK
```

### Payment AP Retry Scenario

```bash
venv/bin/python manage.py test \
  payments.tests.PaymentChoicesEntitlementTests.test_post_voucher_returns_already_posted_for_repeat_post \
  payments.tests.PurchaseApServiceUnitTests.test_post_voucher_reuses_existing_ap_settlement_ids_on_retry \
  payments.tests.PaymentChoicesEntitlementTests.test_cancel_voucher_returns_already_cancelled_for_repeat_cancel \
  payments.tests.PaymentChoicesEntitlementTests.test_unpost_voucher_blocks_repeat_unpost_after_return_to_confirmed \
  --keepdb
```

Result:

```text
Ran 4 tests in 0.526s
FAILED (errors=1)
```

Failure:

```text
django.db.utils.IntegrityError:
insert or update on table "auditlogger_auditlog" violates foreign key constraint
Key (user_id)=(9) is not present in table "Authentication_user".
```

The failing scenario was `payments.tests.PurchaseApServiceUnitTests.test_post_voucher_reuses_existing_ap_settlement_ids_on_retry`.

## Phase 2A.1 Commands Executed

### Repaired AP Retry And Sales/Purchase Write-Concurrency Harness

```bash
venv/bin/python manage.py test \
  perf.tests_phase2a_write_concurrency \
  payments.tests.PurchaseApServiceUnitTests.test_post_voucher_reuses_existing_ap_settlement_ids_on_retry \
  --keepdb
```

Result:

```text
Ran 5 tests in 26.897s
OK
```

Coverage added:

- Sales service invoice concurrent confirm at 2, 5, and 10 workers.
- Sales service invoice same-document concurrent post retry at 2 workers.
- Purchase invoice concurrent confirm at 2, 5, and 10 workers.
- Purchase invoice same-document concurrent post retry at 2 workers.
- AP payment retry fixture now uses a real valid test user for audit logging instead of `posted_by_id=9`.

### Post-Certification Regression Set

```bash
venv/bin/python manage.py test \
  payments.tests.MetaCacheSingleFlightTests.test_concurrent_requests_share_single_builder_run \
  inventory_ops.tests.InventoryOpsConcurrencyTests \
  reports.tests_controls_destructive_workflows \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_voucher_type_uses_filtered_aggregate \
  reports.tests_receivables \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  --keepdb
```

Result:

```text
Ran 27 tests in 16.832s
OK
```

### Phase 2A.1 Database State

Post-test PostgreSQL snapshot:

```text
pg_activity active=1 idle_in_transaction=0 waiting=0
ungranted_locks=0
db_conflicts=0 deadlocks=0
```

## Phase 2A.3 Commands Executed

### Cross-Tenant Certification Scenario

```bash
venv/bin/python manage.py test \
  perf.tests_phase2a_write_concurrency.PurchaseInvoicePhase2AConcurrencyTests.test_cross_tenant_sales_purchase_payment_writes_are_isolated_at_2_5_10_workers \
  --keepdb -v 2
```

Result:

```text
Ran 1 test in 14.705s
OK
```

Cross-tenant evidence:

- 2, 5, and 10 total workers executed real API operations across two independently configured tenants.
- Each worker created and confirmed a sales service invoice in its assigned tenant.
- Each worker created and confirmed a purchase invoice in its assigned tenant.
- Each worker created, confirmed, and posted a payment voucher against a tenant-owned AP open item.
- Sales, purchase, payment voucher, AP open-item, and posting rows stayed in their tenant/company scope.
- Tenant A and tenant B voucher numbers were unique inside their own numbering scopes and did not share counters.
- Tenant-owned open items settled to `settled_amount=100.00`, `outstanding_amount=0.00`, `is_open=False`.
- Cross-tenant payment voucher misuse was rejected and did not mutate the tenant B voucher.

### Full Phase 2A Harness

```bash
venv/bin/python manage.py test perf.tests_phase2a_write_concurrency --keepdb
```

Result:

```text
Ran 9 tests in 71.619s
OK
```

### Phase 2A.3 Regression Set

```bash
venv/bin/python manage.py test \
  payments.tests.MetaCacheSingleFlightTests.test_concurrent_requests_share_single_builder_run \
  inventory_ops.tests.InventoryOpsConcurrencyTests \
  reports.tests_controls_destructive_workflows \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_voucher_type_uses_filtered_aggregate \
  reports.tests_receivables \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  --keepdb
```

Result:

```text
Ran 27 tests in 16.260s
OK
```

Post-test PostgreSQL snapshot:

```text
pg_activity active=1 idle_in_transaction=0 waiting=0
ungranted_locks=0
db_conflicts=0 deadlocks=0
```

## Phase 2A.2 Commands Executed

### Expanded Payment Allocation And Payment Voucher Harness

```bash
venv/bin/python manage.py test perf.tests_phase2a_write_concurrency --keepdb
```

Result:

```text
Ran 8 tests in 56.692s
OK
```

Payment allocation evidence:

- Same invoice, 2/5/10 concurrent AP settlement posts: final `settled_amount=1200.00`, `outstanding_amount=0.00`, `is_open=False`.
- Different invoices for same vendor, 2/5/10 concurrent AP settlement posts: each open item closed independently with no lost update or double settlement.

Payment voucher evidence:

- Concurrent payment voucher confirm at 2/5/10 workers allocated unique `doc_no` and `voucher_code` values in sequence.
- Concurrent payment voucher confirm/post at 2/5/10 workers posted all vouchers, linked AP settlements, and closed the corresponding open items.

### Phase 2A.2 Regression Set

```bash
venv/bin/python manage.py test \
  payments.tests.MetaCacheSingleFlightTests.test_concurrent_requests_share_single_builder_run \
  inventory_ops.tests.InventoryOpsConcurrencyTests \
  reports.tests_controls_destructive_workflows \
  reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_summary_voucher_type_uses_filtered_aggregate \
  reports.tests_receivables \
  reports.tests_books.BookReportAPITests.test_daybook_pagination_keeps_totals_for_full_filtered_set \
  --keepdb
```

Result:

```text
Ran 27 tests in 16.801s
OK
```

Post-test PostgreSQL snapshot:

```text
pg_activity active=1 idle_in_transaction=0 waiting=0
ungranted_locks=0
db_conflicts=0 deadlocks=0
```

## Database State After Executed Scenarios

Post-test PostgreSQL snapshot:

```text
pg_activity active=1 idle_in_transaction=0 waiting=0
ungranted_locks=0
db_conflicts=0 deadlocks=0
```

No lingering ungranted locks, deadlocks, conflicts, or idle-in-transaction sessions were observed after the executed Phase 2A test set.

## Scenario Matrix

| Scenario | Workers | Reconciliation assertions | Result |
| --- | ---: | --- | --- |
| Sales invoice confirm allocates voucher number | 1 | `doc_no=1001`, invoice number generated from configured series | Pass |
| Sales invoice repeat confirm | 1 | Same `doc_no` retained; no renumbering | Pass |
| Sales invoice repeat post | 1 | Already-posted path remains idempotent | Pass |
| Sales invoice same-GSTIN duplicate voucher guard | 1 | Database uniqueness blocks duplicate invoice number across same GSTIN scope | Pass |
| Purchase invoice repeat confirm | 1 | Same `doc_no` and purchase number retained | Pass |
| Purchase invoice repeat post | 1 | Already-posted path remains idempotent | Pass |
| Payment voucher repeat confirm | 1 | Already-confirmed path returns existing number | Pass |
| Payment voucher number conflict skip | 1 | Already-used doc number is skipped and next number allocated | Pass |
| Payment voucher repeat post/cancel/unpost guards | 1 | Repeat actions return stable already-done/blocking outcomes | Pass |
| Inventory transfer simultaneous post/retry | 2 | One posting entry, one active batch, two inventory moves | Pass |
| Inventory adjustment simultaneous post/retry | 2 | One posting entry, one active batch, one inventory move | Pass |
| Inventory simultaneous unpost | 2 | One successful transition; entry reversed; moves removed | Pass |
| Inventory simultaneous cancel | 2 | Idempotent cancelled state; no financial entry created | Pass |
| Inventory update/post race | 2 | One final posted state, one posting entry, valid moves | Pass |
| Payment metadata single-flight | 5 | One builder run shared by 5 concurrent callers | Pass |
| Year-close posting duplicate/rollback | 1 | Balanced journal, duplicate blocked, rollback verified | Pass |
| Opening generation duplicate/rollback | 1 | Balanced opening entry, duplicate blocked, rollback verified | Pass |
| AP payment retry reuses settlement IDs | 1 | Expected retry validation could not complete due audit FK error | Fail |
| AP payment retry reuses settlement IDs after fixture repair | 1 | Valid audit user, existing settlement IDs reused, retry warnings preserved | Pass |
| Sales service invoice concurrent create/confirm | 2/5/10 | Unique voucher numbers in actual numbering scope; confirmed status persisted | Pass |
| Sales service invoice concurrent same-document post retry | 2 | One posted document, unique voucher number, balanced journal entry | Pass |
| Purchase invoice concurrent create/confirm | 2/5/10 | Unique voucher numbers in actual numbering scope; confirmed status persisted | Pass |
| Purchase invoice concurrent same-document post retry | 2 | One posted document, unique voucher number, balanced journal entry | Pass |
| AP concurrent allocations against same invoice | 2/5/10 | Total settled equals original amount; outstanding zero; open item closed | Pass |
| AP concurrent payments against different invoices for same vendor | 2/5/10 | Each invoice independently closed; no lost update or cross-application | Pass |
| Payment voucher concurrent confirm numbering | 2/5/10 | Unique sequential voucher numbers and voucher codes in actual scope | Pass |
| Payment voucher concurrent confirm/post and allocation closure | 2/5/10 | Vouchers posted, AP settlements linked, open items closed | Pass |
| Cross-tenant simultaneous sales/purchase/payment writes | 2/5/10 | Tenant-owned source documents, vouchers, AP open items, settlements, journal entries, balances, and independent numbering scopes | Pass |
| Cross-tenant object-ID misuse | 1 misuse attempt after concurrent writes | Tenant A-scoped action against tenant B voucher rejected; tenant B financial state unchanged | Pass |
| Concurrent journal posting API workflow | 2/5/10 | Control posting coverage exists, but general journal API workflow not certified | Blocked |

## Open Defects And Risks

### Resolved - Cross-Tenant Write Certification Gap

Phase 2A.3 added a second fully seeded tenant/company fixture and executed simultaneous sales, purchase, and payment writes across both tenants at 2, 5, and 10 total workers.

Status: Resolved for local deterministic Phase 2A certification.

### Resolved - Payment AP Retry Test Integrity Failure

`PurchaseApServiceUnitTests.test_post_voucher_reuses_existing_ap_settlement_ids_on_retry` previously failed because the service recorded an approval/audit event with `posted_by_id=9`, but that user did not exist in the test database.

Phase 2A.1 changed only the test fixture: it now creates a real user and passes that user's id into `post_voucher`. Audit logging and FK constraints remain active.

Status: Resolved.

### P1 - Worker Count Gap

Sales and purchase confirm paths now run at 2, 5, and 10 workers. AP settlement and payment voucher confirm/post paths now run at 2, 5, and 10 workers. Cross-tenant sales/purchase/payment writes now run at 2, 5, and 10 workers. Same-document sales/purchase post retry paths still run at 2 workers only.

### P1 - General Journal API Workflow Remains Uncertified

Control-posting workflows cover balanced journal behavior, duplicate blocking, and rollback. A general journal API-level 2/5/10-worker workflow is still not certified in this Phase 2A harness.

## Certification Verdict

**Conditional Pass for Phase 2B controlled staging/prod-like entry.**

Phase 2A.1 closed the sales/purchase invoice concurrency gap for voucher allocation and same-document post retry. It also repaired the AP retry fixture defect and preserved audit FK enforcement.

Phase 2A.2 closed the AP payment allocation and payment voucher numbering/posting gap for the current tenant fixture at 2, 5, and 10 workers.

Phase 2A.3 closed the cross-tenant simultaneous write gap with independently configured tenant/company fixtures and real API writes at 2, 5, and 10 total workers.

Phase 2B may begin as controlled staging/prod-like load testing, but unrestricted high-volume financial write load is not certified from local results alone.

## Required Next Actions Before Large-Scale Load Testing

1. Repeat the Phase 2A harness against a staging/prod-like disposable database with production-like Gunicorn/PostgreSQL settings.
2. Add a general journal API-level concurrent write workflow if that route is in launch scope.
3. Extend sales and purchase same-document post retry from 2 workers to 5 and 10 workers only after repeated 2-worker runs remain stable.
4. Keep cross-tenant misuse checks in every Phase 2B/Phase 3 gate.
5. Continue capturing lock/deadlock/transaction-duration telemetry during staging runs.
6. Do not claim production capacity from this local certification; use it only as the integrity gate for controlled Phase 2B execution.
