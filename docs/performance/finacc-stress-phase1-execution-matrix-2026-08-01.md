# Finacc Stress Phase 1 Execution Matrix

Last updated: 2026-08-03

Status: executable command matrix prepared from current Locust coverage, with purchase lifecycle smoke executed, valid-seed purchase lifecycle rerun verified, auth session touch throttling validated, purchase note lifecycle stress coverage executed cleanly, purchase draft create/save write stress verified cleanly, sales draft create/save write stress verified cleanly, full sales write stress at 20 users verified cleanly, both payment and receipt voucher write smoke verified cleanly, payment plus receipt approval workflow smoke verified cleanly, sales higher-tier reruns established through the 100-user comparison tier, receipt create-side voucher tails materially reduced by targeted follow-up fixes, purchase mixed 100-user stress rerun stabilized cleanly after detail-read optimization, isolated 100-user purchase draft-write reruns on the pooled Gunicorn local stack now complete cleanly after JWT auth-path consolidation, voucher mixed 100-user rerun reconfirmed as broadly stable with one remaining database-connection-ceiling seed failure at the pooled local 100-user tier, receipt approval conflict rerun at 100 users completed cleanly on a pooled Gunicorn local stack with zero failures, financial reports 50-user stress verified cleanly with zero failures across summary, grouped, and CSV export paths, financial reports 100-user pooled-Gunicorn escalation also completed cleanly with zero failures, the financial statement family 50-user stress tier now also completes cleanly across profit and loss, balance sheet, trading account, and ledger book, AP aging has now been revalidated on pooled Gunicorn as a healthy endpoint with sub-second tails, purchase modern versus legacy read stress at 30 users has now been benchmarked cleanly with modern lookup/navigation paths clearly outperforming legacy compatibility search, a fresh 20-user pooled-Gunicorn purchase mixed overlap run now confirms that purchase draft, note, confirm, and post flows stay stable alongside lookup and cross-mode traffic with zero failures, the follow-up payment-voucher settlement audit for entity `10` and subentity `8` is now fully clean after repairing both missing on-account advance balances and residual against-bill advance balances, the 40-user purchase write rerun is now materially cleaner after removing false draft-save mutation noise, payables report stress at 50 users remains clean with healthy AP aging and meta response times, and the heavier payables operational report family is now confirmed as the next active bottleneck because `close-pack` returns repeated `500` responses under even modest concurrency while vendor ledger and note register develop long multi-second tails.

Related documents:
- [finacc-stress-phase1-write-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-phase1-write-plan-2026-08-01.md:1)
- [finacc-stress-testing-master-plan-2026-08-01.md](/Users/ansh/finacc-angular/finacc-django/Finacc/docs/performance/finacc-stress-testing-master-plan-2026-08-01.md:1)
- [perf/locust/README.md](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/README.md:1)

## Purpose

This document converts Phase 1 write-stress planning into a practical execution matrix using the current Locust setup already present in the repository.

It also records the current automation gaps so we do not confuse:

- planned coverage
- currently executable coverage

## Latest Purchase Read Benchmarks

Last updated: 2026-08-03

### Payment Voucher Settlement Audit Closure

Command family:

```bash
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --entity-id 10 --subentity-id 8
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --voucher-id 1239
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --voucher-id 1664
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --voucher-id 1724
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --voucher-id 1785
source venv/bin/activate && python manage.py audit_payment_voucher_settlements --voucher-id 1937
```

Observed:

- entity scope audit
  - `scanned_vouchers: 1770`
  - `flagged_vouchers: 0`
- previously repaired residual-support voucher spot checks
  - `1239`
  - `1664`
  - `1724`
  - `1785`
  - `1937`
  - all reran with `flagged_vouchers: 0`

Repair summary now locked in:

- repaired missing advance-balance cases for posted `ON_ACCOUNT` vouchers whose support existed without a linked vendor advance balance
- repaired residual-support cases for posted `AGAINST_BILL` vouchers whose support exceeded bill allocation and whose residual amount should have been represented as a vendor advance
- added service-side posting validation so future vouchers cannot post when settlement support and effective allocation distribution diverge

Interpretation:

- the previously discovered payment voucher reconciliation drift is now closed at the audited entity scope
- this removes one hidden integrity risk before deeper purchase and payables stress escalation

### Purchase Write Rerun After Draft-Save Mutation Guardrail

Command family:

```bash
source venv/bin/activate && LOCUST_HOST=http://127.0.0.1:8010 \
  FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
  venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 40 --spawn-rate 5 --run-time 45s \
  --tags purchase-write \
  --csv perf/locust/results_phase1_purchase_write_40u_45s_2026_08_03_postdescfix \
  --html perf/locust/results_phase1_purchase_write_40u_45s_2026_08_03_postdescfix.html
```

Observed:

- aggregate
  - `2911` requests
  - `1` failure
  - failure rate `0.03%`
  - average `181 ms`
  - median `140 ms`
  - p95 `460 ms`
  - p99 `560 ms`
  - max `854 ms`
- core purchase write paths all completed with `0` failures:
  - `purchase/invoices [draft create]`
  - `purchase/invoices [draft save]`
  - `purchase/invoices [confirm]`
  - `purchase/invoices [post]`
  - service invoice draft create, save, confirm, post
  - goods and service credit/debit note create, confirm, post
- remaining failure:
  - `GET purchase/service-detail [seed]`
  - `1` occurrence
  - message: invalid JSON returned while fetching the seed detail payload

Interpretation:

- the earlier purchase draft-save failure caused by oversized mutated `product_desc` values has been removed from the stress path
- purchase write behavior now looks operationally healthy at `40` concurrent users on the pooled local stack
- one low-frequency service-detail seed anomaly remains, but it is now isolated and instrumented for a more precise follow-up rerun

### Payables Reports 50-User Rerun

Command family:

```bash
source venv/bin/activate && LOCUST_HOST=http://127.0.0.1:8010 \
  venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 50 --spawn-rate 5 --run-time 45s \
  --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_50u_45s_2026_08_03_r9_gunicorn \
  --html perf/locust/results_phase1_payables_reports_50u_45s_2026_08_03_r9_gunicorn.html
```

Observed:

- aggregate
  - `1039` requests
  - `0` failures
  - average `141 ms`
  - median `130 ms`
  - p95 `320 ms`
  - p99 `420 ms`
  - max `641 ms`
- `reports/payables/aging [get]`
  - `553` requests
  - `0` failures
  - average `197 ms`
  - median `180 ms`
  - p95 `340 ms`
  - p99 `460 ms`
- `reports/payables/meta [get]`
  - `386` requests
  - `0` failures
  - average `73 ms`
  - median `51 ms`
  - p95 `210 ms`
  - p99 `340 ms`

Interpretation:

- payables report stress remains healthy at the `50` user tier
- AP aging continues to behave like a stable operational endpoint rather than a current bottleneck
- the heavier unresolved payables risk remains the non-Locust operational report family such as vendor ledger, note register, and close-pack, which should be stress-expanded next

### Payables Operational Reports Concurrency Threshold Probe

Last updated: 2026-08-03

Environment note:

- authenticated direct threaded probe with real payables data
- entity `10`, entityfin `8`, subentity `8`
- vendor-specific operational scope used `vendor=321`
- two server shapes compared:
  - Django local app on `8000`
  - pooled local Gunicorn stack on `8010`

Single-hit baseline:

- `vendor-ledger`
  - status `200`
  - about `2.81 s`
- `settlement-history`
  - status `200`
  - about `0.09 s`
- `note-register`
  - status `200`
  - about `1.12 s`
- `close-pack`
  - status `200`
  - about `2.37 s`
- `ap-payment-forecast`
  - status `200`
  - about `0.22 s`

20-user, 30-second probe on pooled Gunicorn with `10 s` per-request timeout:

- `vendor-ledger`
  - `18` requests
  - `4` ok
  - `14` failed
  - median about `10.0 s`
- `settlement-history`
  - `16` requests
  - `8` ok
  - `8` failed
  - median about `9.9 s`
- `note-register`
  - `17` requests
  - `7` ok
  - `10` failed
  - median about `10.0 s`
- `close-pack`
  - `20` requests
  - `0` ok
  - `20` failed
  - failures include repeated HTTP `500`
  - also shows timeout behavior
- `ap-payment-forecast`
  - `18` requests
  - `11` ok
  - `7` failed
  - median about `8.3 s`

Lower-tier threshold probe on pooled Gunicorn with `15 s` timeout:

- at `5` concurrent users:
  - `vendor-ledger`
    - `9/9` ok
    - average about `5.37 s`
  - `note-register`
    - `9/9` ok
    - average about `3.61 s`
  - `settlement-history`
    - `8/8` ok
    - average about `0.92 s`
  - `ap-payment-forecast`
    - `10/10` ok
    - average about `1.77 s`
  - `close-pack`
    - only `2/9` ok
    - `7/9` failed
    - failures are real HTTP `500` responses
- at `10` concurrent users:
  - `vendor-ledger`
    - `8/9` ok
    - `1` timeout
    - average about `10.27 s`
  - `note-register`
    - `10/10` ok
    - average about `5.81 s`
  - `settlement-history`
    - `8/8` ok
    - average about `0.46 s`
  - `ap-payment-forecast`
    - `7/7` ok
    - average about `1.32 s`
  - `close-pack`
    - only `1/9` ok
    - `8/9` failed
    - mix of HTTP `500` and timeout

Interpretation:

- `payables_close_pack` is the first confirmed operational payables stress defect
- the issue is not just a dev-server artifact because it reproduces on the pooled Gunicorn stack
- `vendor_ledger` and `vendor_note_register` are functionally healthier than `close-pack`, but they still carry very heavy multi-second tails and begin to degrade by the `10` to `20` concurrent range
- `vendor_settlement_history` is comparatively healthy
- `ap_payment_forecast` is usable at lower tiers but degrades under the broader `20` user mixed probe

Environment note:

- local pooled Gunicorn stack
- `4` workers
- `2` threads per worker
- same backend code that previously looked slow on Django `runserver`

Key result:

- Django `runserver` materially distorted concurrent read timings through request queueing
- pooled Gunicorn measurements are now the purchase read source of truth

### AP Aging Revalidation

Command family:

```bash
LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 30 --spawn-rate 5 --run-time 45s \
  --tags payables-reports \
  --csv perf/locust/results_phase1_payables_reports_30u_45s_2026_08_03_r8_gunicorn \
  --html perf/locust/results_phase1_payables_reports_30u_45s_2026_08_03_r8_gunicorn.html
```

Observed:

- `reports/payables/aging [get]`
  - `368` requests
  - `0` failures
  - average `235 ms`
  - median `210 ms`
  - p95 `420 ms`
  - p99 `590 ms`
  - max `871 ms`

Interpretation:

- AP aging is no longer a purchase bottleneck on a production-like local server shape
- the earlier multi-second local numbers were primarily a dev-server artifact

### Purchase Modern Read Profile

Command family:

```bash
LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 30 --spawn-rate 5 --run-time 45s \
  --tags purchase-modern \
  --csv perf/locust/results_phase1_purchase_modern_30u_45s_2026_08_03_r1_gunicorn \
  --html perf/locust/results_phase1_purchase_modern_30u_45s_2026_08_03_r1_gunicorn.html
```

Observed:

- aggregate
  - `601` requests
  - `0` failures
  - average `541 ms`
  - median `330 ms`
  - p95 `1600 ms`
  - p99 `2300 ms`
- strongest path
  - `purchase/purchase-invoices/lookup [list]`
  - `197` requests
  - average `538 ms`
  - median `280 ms`
- heavier modern path
  - `purchase/purchase-service-invoices/lookup [list]`
  - `82` requests
  - average `617 ms`
  - median `400 ms`

Interpretation:

- modern purchase lookup and cross-mode navigation are stable at `30` concurrent users
- service-side modern lookup is still the heaviest modern read endpoint in this slice

### Purchase Legacy Compatibility Read Profile

Command family:

```bash
LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 30 --spawn-rate 5 --run-time 45s \
  --tags purchase-legacy \
  --csv perf/locust/results_phase1_purchase_legacy_30u_45s_2026_08_03_r1_gunicorn \
  --html perf/locust/results_phase1_purchase_legacy_30u_45s_2026_08_03_r1_gunicorn.html
```

Observed:

- aggregate
  - `476` requests
  - `0` failures
  - average `934 ms`
  - median `800 ms`
  - p95 `2100 ms`
  - p99 `2700 ms`
  - max `3112 ms`
- `purchase/purchase-invoices/search [legacy]`
  - `229` requests
  - average `973 ms`
  - median `820 ms`
- `purchase/purchase-service-invoices/search [legacy]`
  - `187` requests
  - average `1008 ms`
  - median `870 ms`

Interpretation:

- legacy compatibility search is stable but materially slower than modern purchase paths
- purchase performance work should continue to bias UI traffic toward modern lookup/navigation flows wherever feasible

### Purchase Mixed Overlap Profile

Command family:

```bash
LOCUST_HOST=http://127.0.0.1:8010 FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 20 --spawn-rate 3 --run-time 45s \
  --tags purchase-mixed \
  --csv perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_03_r1_gunicorn \
  --html perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_03_r1_gunicorn.html
```

Observed:

- aggregate
  - `982` requests
  - `0` failures
  - average `61 ms`
  - median `58 ms`
  - p95 `110 ms`
  - p99 `150 ms`
  - max `251 ms`
- representative purchase goods flows
  - `purchase/invoices [draft create]`
    - `73` requests
    - average `76 ms`
  - `purchase/invoices [confirm]`
    - `49` requests
    - average `57 ms`
  - `purchase/invoices [post]`
    - `49` requests
    - average `74 ms`
- representative purchase service flows
  - `purchase/service-invoices [draft create]`
    - `74` requests
    - average `80 ms`
  - `purchase/service-invoices [confirm]`
    - `49` requests
    - average `55 ms`
  - `purchase/service-invoices [post]`
    - `49` requests
    - average `72 ms`
- note lifecycle coverage also stayed clean in the same run:
  - goods credit note create, confirm, post
  - goods debit note create, confirm, post
  - service credit note create, confirm, post
  - service debit note create, confirm, post

Interpretation:

- purchase transactional overlap is in a strong state on the pooled local Gunicorn stack
- purchase lookups, cross-mode navigation, draft saves, note flows, confirm, and post all remained stable together

### Receivables Reports Revalidation

Command family:

```bash
LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py \
  --headless --users 30 --spawn-rate 5 --run-time 45s \
  --tags receivables-reports \
  --csv perf/locust/results_phase1_receivables_reports_30u_45s_2026_08_03_r1_gunicorn \
  --html perf/locust/results_phase1_receivables_reports_30u_45s_2026_08_03_r1_gunicorn.html
```

Observed:

- aggregate
  - `685` requests
  - `0` failures
  - average `60 ms`
  - median `54 ms`
  - max `265 ms`
- `reports/receivables/customer-outstanding [get]`
  - `172` requests
  - average `59 ms`
  - median `56 ms`
- `reports/receivables/aging [summary]`
  - `175` requests
  - average `59 ms`
  - median `58 ms`
- `reports/receivables/aging [invoice]`
  - `96` requests
  - average `65 ms`
  - median `62 ms`
- `reports/receivables/open-items [get]`
  - `100` requests
  - average `44 ms`
- `reports/receivables/collections-history [get]`
  - `82` requests
  - average `37 ms`

Interpretation:

- receivables reporting is currently one of the healthiest read families on the pooled local stack
- none of the main AR report paths showed a meaningful tail-risk signature in this tier

### Payables Operational Report Single-Hit Isolation

Environment note:

- pooled Gunicorn stack reset cleanly before measurement
- direct authenticated one-at-a-time HTTP probes used because these endpoints are not yet covered by dedicated Locust tags
- vendor scope used: entity `10`, entityfinid `8`, subentity `8`, vendor `321`

Observed:

- `reports/payables/vendor-ledger`
  - status `200`
  - time `3.947 s`
  - payload `194701` bytes
- `reports/payables/settlement-history`
  - status `200`
  - time `0.070 s`
  - payload `59907` bytes
- `reports/payables/note-register`
  - status `200`
  - time `9.524 s`
  - payload `245719` bytes
- `reports/payables/close-pack`
  - status `200`
  - time `7.446 s`
  - payload `31654` bytes

Interpretation:

- the payables operational family is not uniformly slow
- `settlement-history` is healthy
- `vendor-ledger` is moderately heavy
- `close-pack` and especially `note-register` are the clearest remaining payable-report hotspots
- these endpoints can saturate pooled workers when probed aggressively, so they should be optimized before we add higher-concurrency payable operational stress tiers

### Payables Note Register Hotspot Reduction

Code changes:

- `reports/selectors/payables.py`
  - note register queryset now brings `vendor__compliance_profile` and `vendor__commercial_profile` in with the base header query
  - note register queryset now annotates `has_service_lines` once at the database layer
- `reports/services/payables_operational.py`
  - note register now caches vendor meta by vendor ID instead of rebuilding vendor profile data per row
  - note register document drilldown now uses the annotated service-line flag instead of resolving purchase route shape through repeated per-row header and line queries

Measured result:

- internal service profile for the same scope
  - before: about `16.1 s`
  - after first vendor-meta fix: about `8.5 s`
  - after route-resolution fix: about `3.4 s`
- fresh pooled Gunicorn HTTP rerun after restart
  - `reports/payables/note-register`
  - before: `9.524 s`
  - after: `2.171 s`
- same rerun context also reconfirmed:
  - `reports/payables/vendor-ledger`: about `3.855 s`
  - `reports/payables/close-pack`: about `7.583 s`

Interpretation:

- the note-register hotspot was primarily N+1 style report-enrichment work, not unavoidable base query cost
- the fix is meaningful and moves note-register out of the critical zone
- the next payable operational optimization targets should now shift to `close-pack` first, then `vendor-ledger`

### Payables Close Pack Hotspot Reduction

Code changes:

- `reports/services/payables_operational.py`
  - `close-pack` overview now reuses the already-built AP aging payload instead of calling dashboard summary, which itself rebuilt AP aging
  - `close-pack` now uses a focused MSME overdue payload for MSME cards and top MSME vendors instead of the heavier dashboard wrapper
- `reports/services/payables_control.py`
  - close validation now accepts a precomputed reconciliation payload
- `reports/services/payables_operational.py`
  - `close-pack` passes its already-built reconciliation payload into close validation, removing one duplicate AP-to-GL reconciliation pass

Measured result:

- internal service profile
  - before optimization passes in this slice: about `12.3 s`
  - after dashboard deduplication: about `11.6 s`
  - after reconciliation reuse in validation: about `9.7 s`
- fresh pooled Gunicorn HTTP rerun after restart
  - `reports/payables/close-pack`
  - before: `7.583 s`
  - after: `6.157 s`

Interpretation:

- `close-pack` was paying for duplicate cross-report builders inside one request
- the first two deduplication passes are effective, though `close-pack` is still the heaviest remaining payable operational report
- the remaining cost is now concentrated in open-item balance scans and the exception-report / reconciliation helpers, not in repeated dashboard wrapping

### Payables Close Pack Shared Snapshot Reuse

Code changes:

- `reports/services/payables_operational.py`
  - `close-pack` now precomputes `asof_open_item_balances(...)` and `asof_advances(...)` once when validation or exceptions are requested
  - those shared snapshots are passed into both close validation and vendor-balance exception generation
  - a missing `coerce_date` import in the new shared-snapshot path was fixed before rerunning measurements
- `reports/services/payables_control.py`
  - close validation now accepts precomputed `open_items_asof` and `advances_asof`
  - vendor balance exception reporting now accepts the same precomputed snapshots instead of rebuilding them

Measured result:

- internal service profile
  - before this pass: about `6.5 s`
  - after shared snapshot reuse: `3.922 s`
- repeated warm service reruns
  - `2.583 s`
  - `2.711 s`
  - `2.479 s`
  - `2.522 s`
  - `2.464 s`

Interpretation:

- this pass removed another meaningful layer of duplicate payable snapshot work inside one close-pack request
- `close-pack` is no longer in the old `6-8 s` class on the corrected service path
- the remaining dominant cost is now led by `build_ap_gl_reconciliation_report(...)`, with `asof_open_item_balances(...)` much smaller than before
- purchase/payables stress work can now treat `close-pack` as materially healthier, while keeping reconciliation-side trimming as the next report-specific lever if needed

### Vendor Ledger Hotspot Reduction

Code changes:

- `reports/services/financial/ledger_book.py`
  - vendor-ledger now resolves purchase and sales service-backed document IDs in bulk
  - ledger drilldown route selection now uses those bulk route maps instead of per-row `exists()` checks on invoice lines

Measured result:

- internal service profile
  - before: about `8.4 s`
  - after bulk route-map optimization: about `3.5 s`
- fresh pooled Gunicorn HTTP rerun after restart
  - `reports/payables/vendor-ledger`
  - before: `3.855 s`
  - after: `2.123 s`
- same rerun context reconfirmed:
  - `reports/payables/close-pack`: `6.157 s`
  - `reports/payables/note-register`: `2.193 s`

Interpretation:

- the main vendor-ledger hotspot was route-shape N+1 work inside ledger row drilldown metadata
- the bulk route-map fix removes that repeated query pattern and materially improves the endpoint
- `close-pack` is now the clearest remaining payable operational hotspot

## Current Locust Write Coverage

As of 2026-08-01, current implemented write-capable Locust coverage is:

1. Sales settings patch
- tag: `write`
- route: `PATCH /api/sales/settings/`
- gated by `FINACC_ENABLE_WRITE_TESTS=true`

2. Sales invoice lifecycle
- tags: `lifecycle`, `write`
- routes:
  - confirm
  - post
  - reverse
- gated by `FINACC_ENABLE_LIFECYCLE_TESTS=true`

3. Purchase invoice lifecycle
- tags: `purchase-write`, `lifecycle`, `write`
- routes:
  - purchase invoice confirm
  - purchase invoice post
  - purchase service invoice confirm
  - purchase service invoice post
- gated by `FINACC_ENABLE_LIFECYCLE_TESTS=true`

4. Purchase note lifecycle
- tags: `purchase-write`, `lifecycle`, `write`
- routes:
  - purchase invoice credit note create, confirm, post
  - purchase invoice debit note create, confirm, post
  - purchase service invoice credit note create, confirm, post
  - purchase service invoice debit note create, confirm, post
- note:
  - Locust first attempts normal note creation
  - if the backend returns `purchase_duplicate_note_exists`, the flow retries with `allow_duplicate=true` so the stress run can continue on a constrained seed pool
- gated by `FINACC_ENABLE_LIFECYCLE_TESTS=true`

5. Payment voucher lifecycle
- tags: `payment-write`, `write`
- routes:
  - payment voucher draft create
  - payment voucher draft save
  - payment voucher confirm
  - payment voucher post
- note:
  - Locust builds live payment voucher payloads from payment form meta
  - the current stable path uses `ADVANCE` payment vouchers without allocations to validate real draft and posting behavior first
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

6. Receipt voucher lifecycle
- tags: `receipt-write`, `write`
- routes:
  - receipt voucher draft create
  - receipt voucher draft save
  - receipt voucher confirm
  - receipt voucher post
- note:
  - Locust builds live receipt voucher payloads from receipt form meta
  - the current stable path uses `ADVANCE` receipt vouchers without allocations to validate real draft and posting behavior first
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

7. Payment voucher approval workflow
- tags: `payment-approval`, `write`
- routes:
  - payment voucher draft create
  - payment voucher submit
  - payment voucher approve
- note:
  - Locust uses live payment form meta and creates fresh draft vouchers before each approval sequence
  - the current stable path validates same-user submit then approve on the default local policy
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

8. Receipt voucher approval workflow
- tags: `receipt-approval`, `write`
- routes:
  - receipt voucher draft create
  - receipt voucher submit
  - receipt voucher approve
- note:
  - Locust uses live receipt form meta and creates fresh draft vouchers before each approval sequence
  - the current stable path validates same-user submit then approve on the default local policy
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

9. Sales draft create and draft save workflow
- tags: `sales-write`, `sales-draft-write`, `write`
- routes:
  - sales invoice draft create
  - sales invoice draft save
  - sales service invoice draft create
  - sales service invoice draft save
- note:
  - Locust builds fresh sales drafts from real seeded sales detail payloads
  - `doc_code` is resolved from the seeded document or current sales settings defaults so invoice, credit note, and debit note flows can remain numbering-correct
  - both goods and service line payloads now use the integer `discount_type` enum required by the sales serializers
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

10. Voucher stale-state and reject conflict workflow
- tags: `stale-conflict`, `payment-approval-conflict`, `receipt-approval-conflict`, `write`
- routes:
  - payment voucher submit, repeat submit, approve, repeat approve
  - payment voucher reject, repeat reject
  - receipt voucher submit, repeat submit, approve, repeat approve
  - receipt voucher reject, repeat reject
- note:
  - Locust validates backend stale-tab/idempotent feedback, not just HTTP success
  - repeat actions must return the expected status message such as `Already submitted.`, `Already approved.`, or `Already rejected.`
- gated by `FINACC_ENABLE_WRITE_TESTS=true` or `FINACC_ENABLE_LIFECYCLE_TESTS=true`

11. Dedicated report-under-write mixed profile
- tags: `report-write-mix`
- routes:
  - payables meta
  - payables aging
  - bank reconciliation meta and sessions
  - sales draft create/save
  - purchase draft create/save
  - payment voucher create/save/confirm/post
  - receipt voucher create/save/confirm/post
- note:
  - this profile exists specifically to catch write interference against high-value reporting and dashboard-style reads

12. Dedicated purchase mixed profile
- tags: `purchase-mixed`
- routes:
  - purchase invoice lookup
  - purchase service invoice lookup
  - purchase goods to service cross-mode navigation
  - purchase service to goods cross-mode navigation
  - purchase invoice confirm and post
  - purchase note create, confirm, and post
  - purchase draft create and save
- note:
  - this profile exists so purchase read plus write overlap can be executed directly without relying on multi-tag filtering behavior

## Current Gaps In Locust Write Coverage

Not yet implemented in current Locust automation:

1. Multi-tab stale document simulation across distinct browser-like actors
2. Heavier report-under-write load tiers beyond smoke level

These remain Phase 1 implementation gaps, not execution mistakes.

3. Full financial statement family stress coverage beyond trial balance and ledger summary
- prior to 2026-08-03, Locust only exercised:
  - trial balance
  - ledger summary
- the following statement family endpoints existed in backend routes but were not yet included in the stress harness:
  - profit and loss
  - balance sheet
  - trading account
  - ledger book

## Required Environment Flags

Before any write run:

```bash
cd Finacc/perf/locust
cp .env.example .env
```

Set at minimum:

```bash
LOCUST_HOST=http://127.0.0.1:8000
FINACC_USER_EMAIL=...
FINACC_USER_PASSWORD=...
FINACC_ENTITY_ID=...
FINACC_ENTITY_FIN_ID=...
FINACC_SUBENTITY_ID=...
FINACC_ENABLE_WRITE_TESTS=true
FINACC_ENABLE_LIFECYCLE_TESTS=true
```

## Phase 1 Immediate Executable Runs

These are the runs we can execute immediately with current code.

## Phase 1A.0 Sales Write Smoke

Purpose:
- validate basic write-safety on current sales lifecycle automation

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 5m \
  --tags sales-lifecycle \
  --csv results_phase1_sales_write_smoke_2u_5m_2026_08_01 \
  --html results_phase1_sales_write_smoke_2u_5m_2026_08_01.html
```

Expected evidence:
- confirm/post/reverse all succeed or fail explicitly
- no duplicate numbering
- no broken status transitions

## Phase 1A.1 Sales Write Working Load

Purpose:
- push current lifecycle coverage to moderate overlap

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 10m \
  --tags sales-lifecycle \
  --csv results_phase1_sales_write_working_5u_10m_2026_08_01 \
  --html results_phase1_sales_write_working_5u_10m_2026_08_01.html
```

## Phase 1A.2 Sales Mixed Read + Write

Purpose:
- measure sales lifecycle under simultaneous read traffic

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 10 --spawn-rate 2 --run-time 10m \
  --tags sales-mixed \
  --csv results_phase1_sales_mixed_10u_10m_2026_08_01 \
  --html results_phase1_sales_mixed_10u_10m_2026_08_01.html
```

Expected evidence:
- lifecycle routes still behave correctly
- lookup/navigation/read routes do not collapse under active posting

## Phase 1F Purchase Write Rerun After Create Runtime-Invariant Fast Path On August 3, 2026

Purpose:
- verify whether aligning first-time purchase draft creation with the optimized runtime-invariant line validation path produces a measurable purchase write-tail reduction

Code change under test:
- [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:2728)
- first-time `create_with_lines()` now uses `PurchaseInvoiceService._validate_line_runtime_invariants(obj)` instead of per-line `obj.full_clean()`
- focused purchase regression suite passed in the live project venv before this rerun:
  - `22 tests passed`

Command:

```bash
cd Finacc/perf/locust
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
  /Users/ansh/finacc-angular/finacc-django/Finacc/venv/bin/locust \
  -f locustfile.py \
  --headless \
  --users 20 \
  --spawn-rate 2 \
  --run-time 2m \
  --tags purchase-write \
  --csv results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants \
  --html results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_create_runtime_invariants.html)

Final result:
- requests: `2138`
- failures: `0`
- aggregated average: `665.33 ms`
- aggregated p95: `1300 ms`
- aggregated p99: `1900 ms`
- aggregated max: `2633 ms`

Key purchase endpoints:
- `purchase/invoices [draft create]`
  - avg `707.08 ms`
  - p95 `1100 ms`
  - p99 `1400 ms`
  - max `1459 ms`
  - requests `236`
- `purchase/service-invoices [draft create]`
  - avg `733.39 ms`
  - p95 `1100 ms`
  - p99 `1400 ms`
  - max `1515 ms`
  - requests `205`
- `purchase/invoices [draft save]`
  - avg `1323.05 ms`
  - p95 `2000 ms`
  - p99 `2600 ms`
  - max `2633 ms`
  - requests `81`
- `purchase/service-invoices [draft save]`
  - avg `1419.46 ms`
  - p95 `2000 ms`
  - p99 `2500 ms`
  - max `2471 ms`
  - requests `69`
- `purchase/invoices [post]`
  - avg `712.65 ms`
  - p95 `1100 ms`
  - p99 `1300 ms`
  - max `1378 ms`
  - requests `154`
- `purchase/service-invoices [post]`
  - avg `746.09 ms`
  - p95 `1200 ms`
  - p99 `1300 ms`
  - max `1341 ms`
  - requests `133`
- `purchase/goods-detail [seed]`
  - avg `511.76 ms`
  - p95 `780 ms`
  - p99 `980 ms`
  - max `1060 ms`
  - requests `237`
- `purchase/service-detail [seed]`
  - avg `520.48 ms`
  - p95 `840 ms`
  - p99 `900 ms`
  - max `937 ms`
  - requests `205`

Comparison versus Phase 1E contract-summary-skip baseline:
- aggregated avg: `986.98 ms -> 665.33 ms` (`-321.65 ms`)
- aggregated p95: `1900 ms -> 1300 ms` (`-600 ms`)
- invoice draft create avg: `1177.01 ms -> 707.08 ms` (`-469.93 ms`)
- service draft create avg: `1184.18 ms -> 733.39 ms` (`-450.79 ms`)
- invoice draft save avg: `2068.72 ms -> 1323.05 ms` (`-745.67 ms`)
- service draft save avg: `2110.86 ms -> 1419.46 ms` (`-691.40 ms`)
- invoice post avg: `1069.88 ms -> 712.65 ms` (`-357.23 ms`)
- service post avg: `1035.90 ms -> 746.09 ms` (`-289.81 ms`)
- goods detail avg: `762.02 ms -> 511.76 ms` (`-250.26 ms`)
- service detail avg: `740.77 ms -> 520.48 ms` (`-220.29 ms`)

Interpretation:
- this change produced a clear, measurable purchase write-tail improvement
- purchase draft create is now in a much healthier range around `~0.7s`
- purchase draft save remains the slowest purchase write path, but it has dropped from `~2.1s` to `~1.3s to 1.4s`
- the next likely purchase hotspot is serializer-response cost and any remaining heavy post-save recomputation, not line model validation on create

## Phase 1A Follow-up Result: Sales Mixed 50-User Stress Rerun

Purpose:
- validate the sales mixed profile at the same `50 users / 2 minutes` SaaS-style tier now used for purchase
- compare sales and purchase on the same stress envelope
- identify whether the next sales bottleneck is invoice transaction logic or settings/meta traffic

Command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02 \
  --html perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02.html
```

Result:
- total requests: `731`
- failures: `0`
- aggregate average: `2159.77 ms`
- aggregate median: `1500 ms`
- aggregate p95: `5400 ms`
- aggregate p99: `13000 ms`

Key endpoint metrics:
- `auth/login`
  - average: `348.96 ms`
  - median: `360 ms`
  - p95: `620 ms`
- `auth/me`
  - average: `172.40 ms`
  - median: `130 ms`
  - p95: `380 ms`
- `sales/invoices/lookup [list]`
  - average: `2868.78 ms`
  - median: `2800 ms`
  - p95: `4800 ms`
- `sales/service-invoices/lookup [list]`
  - average: `3242.70 ms`
  - median: `3300 ms`
  - p95: `5100 ms`
- `sales/invoices [draft create]`
  - average: `1451.02 ms`
  - median: `1400 ms`
  - p95: `2300 ms`
- `sales/invoices [draft save]`
  - average: `2444.13 ms`
  - median: `2300 ms`
  - p95: `4100 ms`
- `sales/service-invoices [draft create]`
  - average: `1559.66 ms`
  - median: `1500 ms`
  - p95: `2000 ms`
- `sales/service-invoices [draft save]`
  - average: `2735.11 ms`
  - median: `2400 ms`
  - p95: `4700 ms`
- `sales/invoices [confirm]`
  - average: `1547.15 ms`
  - median: `1500 ms`
  - p95: `2700 ms`
- `sales/invoices [post]`
  - average: `2311.26 ms`
  - median: `2400 ms`
  - p95: `4100 ms`
- `sales/invoices [reverse]`
  - average: `1432.87 ms`
  - median: `1500 ms`
  - p95: `1900 ms`

Observed hotspot:
- `sales/settings [get]`
  - average: `3953.30 ms`
  - median: `3900 ms`
  - p95: `6000 ms`
- `sales/settings [patch]`
  - average: `11421.56 ms`
  - median: `8700 ms`
  - p95: `27000 ms`

Interpretation:
- sales invoice transactional flows are correctness-clean and latency-healthy at this tier
- unlike the earlier purchase pressure pattern, sales mixed does not currently show document lifecycle distress as the primary limiter
- the strongest sales-side bottleneck candidate is now settings assembly and settings mutation, not invoice create/save/confirm/post itself

Status update:
- `sales mixed correctness at 50 users`: `passed`
- `sales mixed latency at 50 users`: `passed`
- `sales settings hotspot isolation`: `next`

## Phase 1A.3 Sales Settings Mutation Probe

Purpose:
- validate low-risk write route behavior under concurrency

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 5 --spawn-rate 1 --run-time 5m \
  --tags write \
  --csv results_phase1_sales_write_probe_5u_5m_2026_08_01 \
  --html results_phase1_sales_write_probe_5u_5m_2026_08_01.html
```

## Phase 1A Executed Result: Sales Write Working Load

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
./venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags sales-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_write_20u_2m_2026_08_02 \
  --html perf/locust/results_phase1_sales_write_20u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_sales_write_20u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_stats.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_stats_history.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02.html)

Final aggregate:
- requests: `1671`
- failures: `0`
- average: `576.45 ms`
- median: `340 ms`
- p95: `2100 ms`
- p99: `3900 ms`
- max: `8640.35 ms`

Key endpoint results:
- `sales/settings [patch]`: `233` requests, `0` failures, avg `1612.48 ms`, median `1400 ms`, p95 `4100 ms`, p99 `7100 ms`, max `8640.35 ms`
- `sales/invoices [post]`: `230` requests, `0` failures, avg `633.71 ms`, median `460 ms`, p95 `1700 ms`, p99 `5200 ms`, max `6245.53 ms`
- `sales/invoices [draft save]`: `104` requests, `0` failures, avg `520.59 ms`, median `500 ms`, p95 `910 ms`, p99 `1100 ms`, max `1152.33 ms`
- `sales/service-invoices [draft save]`: `117` requests, `0` failures, avg `531.82 ms`, median `500 ms`, p95 `1100 ms`, p99 `1100 ms`, max `1195.48 ms`
- `sales/invoices [confirm]`: `231` requests, `0` failures, avg `293.04 ms`, median `220 ms`, p95 `710 ms`, p99 `1100 ms`, max `2609.08 ms`
- `sales/invoices [draft create]`: `105` requests, `0` failures, avg `324.29 ms`, median `280 ms`, p95 `650 ms`, p99 `820 ms`, max `924.46 ms`
- `sales/service-invoices [draft create]`: `118` requests, `0` failures, avg `356.63 ms`, median `310 ms`, p95 `730 ms`, p99 `1100 ms`, max `1548.56 ms`
- `sales/invoices [reverse]`: `229` requests, `0` failures, avg `348.15 ms`, median `280 ms`, p95 `640 ms`, p99 `1000 ms`, max `3920.49 ms`

Findings:
- correctness was stable at this load because the full run finished with `0` failures
- the dominant write hotspot is `sales/settings [patch]`, not invoice draft create or confirm
- sales posting is the second main long-tail mutation path and still needs deeper profiling before higher write tiers
- sales draft create/save behavior is materially healthier than sales settings patch under the same concurrency

Phase 1A status after this run:
- `sales write working load`: `executed`
- `sales correctness under 20-user write pressure`: `passed`
- `sales main latency hotspot identified`: `sales/settings [patch]`
- `sales next deep target after this run`: `sales invoice post`

Follow-up rerun note:
- on `2026-08-02`, a post-optimization rerun was executed using:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
./venv/bin/locust -f perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags sales-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt \
  --html perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt.html
```

- rerun artifacts:
  - [results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_stats.csv)
  - [results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_stats_history.csv)
  - [results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt.html)
  - [results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postdocpreviewopt_failures.csv)
- rerun final aggregate was not accepted as the new baseline because it contained `1` failure on `sales/invoices [post]` and materially lower throughput:
  - aggregate: `1121` requests, `1` failure, avg `1270.83 ms`, median `820 ms`, p95 `4200 ms`, p99 `6400 ms`
  - `sales/settings [patch]`: `156` requests, `0` failures, avg `3461.50 ms`, median `3300 ms`, p95 `7700 ms`, p99 `11000 ms`
  - `sales/invoices [post]`: `151` requests, `1` failure, avg `1384.28 ms`, median `1200 ms`, p95 `3100 ms`, p99 `4000 ms`
- interpretation:
  - the rerun is useful as a defect signal because it surfaced a real `IntegrityError` in `sales/invoices [post]`
  - the rerun is not a fair apples-to-apples performance replacement for the clean baseline above, so the earlier clean run remains the recorded Phase 1A baseline until the post path is stabilized and the scenario is rerun cleanly
  - root cause isolated in code review:
    - `SalesInvoiceService.post(...)` was not reloading the invoice header with `select_for_update()` before posting, unlike the purchase post path and unlike sales confirm/reverse paths
    - that left the sales post flow exposed to duplicate concurrent posting on environments where advisory locking is unavailable or ineffective for this race window
  - local corrective action applied:
    - `Finacc/sales/services/sales_invoice_service.py`
    - `Finacc/sales/tests.py`
    - added a focused regression test to assert `post()` reloads the header with a row lock before status evaluation

## Phase 1A Follow-up Result: Sales Write Rerun After Header Lock Fix

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags sales-write \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock \
  --html Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock.html
```

Artifacts:
- [results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock_stats.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock_stats_history.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postheaderlock.html)

Final aggregate:
- requests: `1252`
- failures: `0`
- average: `1079 ms`
- median: `580 ms`
- p95: `4600 ms`
- p99: `7500 ms`
- max: `9836 ms`

Key endpoint results:
- `sales/settings [patch]`: `160` requests, `0` failures, avg `2610 ms`, median `2300 ms`, p95 `6100 ms`, p99 `9600 ms`, max `9836 ms`
- `sales/invoices [post]`: `170` requests, `0` failures, avg `853 ms`, median `790 ms`, p95 `2000 ms`, p99 `2300 ms`, max `2870 ms`
- `sales/invoices [confirm]`: `170` requests, `0` failures, avg `824 ms`, median `370 ms`, p95 `4100 ms`, p99 `8500 ms`, max `8495 ms`
- `sales/invoices [draft save]`: `88` requests, `0` failures, avg `922 ms`, median `850 ms`, p95 `1800 ms`, p99 `2100 ms`, max `2059 ms`
- `sales/service-invoices [draft save]`: `79` requests, `0` failures, avg `939 ms`, median `990 ms`, p95 `1700 ms`, p99 `2000 ms`, max `2007 ms`

Findings:
- the `sales/invoices [post]` correctness failure observed in the invalid earlier rerun did not reproduce after the header row-lock fix
- the clean rerun confirms the sales post path is materially more stable under concurrency than the invalid rerun suggested
- `sales/settings [patch]` remains the dominant mutation hotspot by latency
- compared with the original clean baseline, throughput is lower and latency is higher on this rerun, so this should be treated as a restored correctness baseline first, not yet a confirmed performance improvement baseline

Phase 1A status after the fix rerun:
- `sales post concurrency defect`: `fixed and rerun cleanly`
- `sales correctness under 20-user write pressure`: `passed after fix rerun`
- `sales remaining primary latency hotspot`: `sales/settings [patch]`

## Phase 1A Follow-up Result: Sales Write Rerun After Series-Batch Optimization

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags sales-write \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch \
  --html Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch.html
```

Artifacts:
- [results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch_stats.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch_stats_history.csv)
- [results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_20u_2m_2026_08_02_postseriesbatch.html)

Final aggregate:
- requests: `1563`
- failures: `0`
- average: `700 ms`
- median: `440 ms`
- p95: `2300 ms`
- p99: `4200 ms`
- max: `6803 ms`

Key endpoint results:
- `sales/settings [patch]`: `200` requests, `0` failures, avg `1147 ms`, median `900 ms`, p95 `3000 ms`, p99 `4400 ms`, max `4378 ms`
- `sales/invoices [post]`: `188` requests, `0` failures, avg `668 ms`, median `620 ms`, p95 `1400 ms`, p99 `1700 ms`, max `1828 ms`
- `sales/invoices [confirm]`: `190` requests, `0` failures, avg `448 ms`, median `290 ms`, p95 `1100 ms`, p99 `3800 ms`, max `3809 ms`
- `sales/invoices [draft save]`: `122` requests, `0` failures, avg `727 ms`, median `700 ms`, p95 `1500 ms`, p99 `1600 ms`, max `1656 ms`
- `sales/service-invoices [draft save]`: `115` requests, `0` failures, avg `740 ms`, median `670 ms`, p95 `1600 ms`, p99 `1700 ms`, max `1687 ms`

Comparison against the previous clean reruns:
- versus `postheaderlock`:
  - aggregate avg improved from `1078 ms` to `700 ms`
  - aggregate p95 improved from `4600 ms` to `2300 ms`
  - `sales/settings [patch]` avg improved from `2604 ms` to `1147 ms`
  - `sales/invoices [post]` avg improved from `848 ms` to `668 ms`
- versus the original clean baseline:
  - aggregate avg regressed from `576 ms` to `700 ms`
  - aggregate p95 regressed slightly from `2100 ms` to `2300 ms`
  - `sales/settings [patch]` improved from `1612 ms` to `1147 ms`
  - `sales/invoices [post]` stayed close at `634 ms` versus `668 ms`

Findings:
- the rerun remained fully clean with `0` failures, so the sales post concurrency fix still holds under the optimized settings path
- batching the sales settings series lookup materially reduced the dominant `sales/settings [patch]` hotspot
- this rerun is now the best post-fix sales-write result because it preserves correctness while recovering most of the lost latency from the earlier post-fix rerun
- the sales module is ready to move forward, with the remaining gap being broader mixed-profile and higher-user write stress rather than an obvious correctness blocker in the current 20-user write pattern

Important:
- `sales-mixed` is the safest module-isolated tag for combined sales read, draft-save, settings, and lifecycle coverage
- generic `write` and `lifecycle` tags are broader and can include non-sales workloads

## Phase 1B.0 Purchase Write Smoke

Purpose:
- validate safe purchase lifecycle pressure on seeded goods and service purchase documents

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 5m \
  --tags purchase-write \
  --csv results_phase1_purchase_write_smoke_2u_5m_2026_08_01 \
  --html results_phase1_purchase_write_smoke_2u_5m_2026_08_01.html
```

Expected evidence:
- purchase confirm/post succeeds or fails explicitly
- goods and service purchase lifecycle routes both remain stable
- no numbering or status corruption is introduced

## Phase 1B.1 Purchase Mixed Read + Write

Purpose:
- measure purchase lifecycle while modern reads are also active

Command:

```bash
cd Finacc/perf/locust
source .venv/bin/activate
locust -f locustfile.py --headless --users 10 --spawn-rate 2 --run-time 10m \
  --tags purchase-modern,purchase-write \
  --csv results_phase1_purchase_mixed_10u_10m_2026_08_01 \
  --html results_phase1_purchase_mixed_10u_10m_2026_08_01.html
```

Current status:
- executable
- lifecycle, note lifecycle, and draft create/save are now all covered for purchase

## Executed Run Log

### Run

- name: `phase1_purchase_write_smoke_enabled_2u_1m_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `1m`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~150ms aggregated`
- max observed latency: `450ms` on `purchase/invoices [confirm]`
- error rate: `0.00%`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Purchase goods and service lifecycle routes both executed successfully.
- Real traffic observed for:
  - `purchase/invoices [confirm]`
  - `purchase/invoices [post]`
  - `purchase/service-invoices [confirm]`
  - `purchase/service-invoices [post]`
- An initial smoke attempt produced only `auth/login` and `auth/me` traffic because `FINACC_ENABLE_LIFECYCLE_TESTS=false` in `perf/locust/.env`.
- For reproducible write runs, either set `FINACC_ENABLE_LIFECYCLE_TESTS=true` in `.env` or override it inline in the run command.

### Run

- name: `phase1_purchase_notes_smoke_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `expected-guard-hit`
- p95: `~170ms aggregated`
- max observed latency: `195ms`
- error rate: `14.29%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This was the first direct purchase note mutation smoke after note lifecycle coverage was added to Locust.
- Note create, confirm, and post all succeeded initially for both goods and service invoice seeds.
- The failures were all explicit duplicate-note business guards, not random stress failures.
- The error shape was consistent:
  - `purchase_duplicate_note_exists`
- Root cause:
  - the run reused a small set of posted invoice seeds
  - once an active note already existed for a given invoice and note type, the backend correctly blocked another create
- Follow-up:
  - Locust was adjusted to retry with `allow_duplicate=true` only after the duplicate guard is returned
  - this preserves normal-path coverage while keeping stress continuity on constrained seed data

### Run

- name: `phase1_purchase_notes_smoke_retry_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~170ms aggregated`
- max observed latency: `187ms`
- error rate: `0.00%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Purchase note lifecycle now runs cleanly under write stress for:
  - goods invoice credit note create, confirm, post
  - goods invoice debit note create, confirm, post
  - service invoice credit note create, confirm, post
  - service invoice debit note create, confirm, post
- The retry-enabled flow keeps the first create attempt realistic and only uses duplicate override when the backend explicitly signals seed reuse.
- This closes the earlier Phase 1 purchase note lifecycle gap.

### Run

- name: `phase1_purchase_write_validseed_5u_90s_2026_08_01`
- date: `2026-08-01`
- users: `5`
- spawn rate: `1`
- duration: `90s`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~4300ms aggregated`
- max observed latency: `4991ms` on `purchase/invoices [post]`
- error rate: `0.00%`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Earlier malformed or zero-total seeded drafts were filtered out in the Locust selector so purchase lifecycle runs only target runnable drafts.
- This run established a clean write baseline before auth-path tuning.

### Run

- name: `phase1_purchase_write_touchcheck_6u_90s_2026_08_01`
- date: `2026-08-01`
- users: `6`
- spawn rate: `2`
- duration: `90s`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- requests: `512`
- failures: `0`
- error rate: `0.00%`
- p95: `~140ms aggregated`
- max observed latency: `395ms` on `purchase/service-invoices [post]`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Backend auth session handling was adjusted so `last_used_at` is not written on every authenticated request.
- Focused authentication tests passed after the change:
  - `Authentication.tests.test_authentication`
  - `24 tests`, `OK`
- Purchase goods and service lifecycle routes remained fully green after the auth-path change:
  - `purchase/invoices [confirm]`
  - `purchase/invoices [post]`
  - `purchase/service-invoices [confirm]`
  - `purchase/service-invoices [post]`
- This improves confidence that the remaining heavy-run instability is tied to higher-concurrency auth/read saturation, not purchase lifecycle correctness.

- Earlier purchase mixed failures were traced to malformed historical draft rows in entity `10`, not to purchase confirm/post logic itself.
- The bad seed pattern was purchase headers whose `doc_code` had been overwritten with voucher-like runtime values such as `PWI298194`, while valid purchase `DocumentType` values remained `PINV`, `PCN`, and `PDN`.
- Locust purchase seed selection was hardened twice:
  - skip malformed lookup rows and only use valid purchase document codes
  - skip zero-total draft rows that represented no-line goods invoices such as `P1-NOLINES-*`
- After that change, all of these routes completed successfully with zero failures:
  - `purchase/invoices [confirm]`
  - `purchase/invoices [post]`
  - `purchase/service-invoices [confirm]`
  - `purchase/service-invoices [post]`
- This rerun is the reliable baseline for further purchase write-stress work.

### Run

- name: `phase1_purchase_write_trace_6u_90s_2026_08_01_postfix1`
- date: `2026-08-01`
- users: `6`
- spawn rate: `2`
- duration: `90s`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~140ms aggregated`
- max observed latency: `218ms` on `purchase/invoices [post]`
- error rate: `0.00%`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- The pre-fix trace run showed goods purchase writes failing with valid business-rule errors:
  - `Cannot confirm: no lines exist.`
  - `Only CONFIRMED documents can be posted.`
- Lookup payload inspection showed the goods draft pool included zero-total no-line drafts such as:
  - `P1-NOLINES-WARN-*`
  - `P1-NOLINES-OFF-*`
- After tightening purchase seed selection to require:
  - valid purchase doc codes
  - positive `grand_total`
- both goods and service purchase lifecycle traffic ran clean at the same load.
- This is the strongest current purchase write-stress baseline because it exercises both modes without depending on malformed or incomplete draft seed rows.

### Run

- name: `phase1_purchase_draft_only_smoke_retry4_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `purchase-draft-write`
- environment: `local`

### Outcome

- status: `pass`
- requests: `125`
- failures: `0`
- error rate: `0.00%`
- p95: `~220ms aggregated`
- max observed latency: `273ms` on `purchase/invoices [draft save]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real purchase draft create plus draft save stress for both:
  - goods purchase invoices
  - service purchase invoices
- The final stable mutation shape was:
  - create from a real seeded purchase detail payload
  - save by mutating safe fields only, while preserving backend-authoritative tax math
- Earlier failed retries were Locust payload-shaping issues, not purchase-service defects:
  - date normalization mismatch on source serializer output
  - synthetic tax split conflicting with derived GST regime
  - synthetic totals conflicting with inclusive-tax lines
- After aligning the stress payload to backend-authoritative math, purchase draft save completed cleanly.
- This closes the earlier Phase 1 purchase create/save gap.

### Run

- name: `phase1_sales_draft_smoke_retry4_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `sales-write`
- environment: `local`

### Outcome

- status: `pass`
- requests: `113`
- failures: `0`
- error rate: `0.00%`
- p95: `~230ms aggregated`
- max observed latency: `234ms` on `sales/service-invoices [draft save]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real sales draft create plus draft save stress for both:
  - goods sales invoices
  - service sales invoices
- The final stable mutation shape was:
  - fetch a real seeded sales detail payload
  - create a fresh draft with serializer-compatible header and line fields
  - patch the created draft with safe header and line mutations
- Earlier failed retries were Locust contract-shaping issues, not sales-service defects:
  - service line payload still used a string discount enum instead of the required integer enum
  - create payload omitted required `doc_code`
- After aligning the write payload with current sales serializer and settings contracts, both draft create and draft save completed cleanly.
- This closes the earlier Phase 1 sales create/save gap.

### Purchase Read Caveat

- A separate `purchase-modern` `20u / 5m` run on `2026-08-01` still showed high failure rates driven by local `auth/login`, `auth/me`, and subsequent `401` cascades after `OperationalError` responses.
- That run should be treated as a local environment or auth-path saturation signal, not as evidence that purchase lookup or purchase lifecycle business logic is broken.
- Before using `20u+` purchase-modern numbers as product truth, rerun that profile behind a more production-like app server and capture the exact auth traceback.

### Run

- name: `phase1_purchase_modern_5u_2m_2026_08_01`
- date: `2026-08-01`
- users: `5`
- spawn rate: `1`
- duration: `2m`
- tags: `purchase-modern`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~390ms aggregated`
- max observed latency: `878ms` on `purchase/purchase-invoices/cross-mode-nav [goods->service]`
- error rate: `0.00%`
- duplicate numbering: `not applicable`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Modern purchase lookup routes stayed stable with zero failures.
- The slowest modern purchase path was not lookup itself, but cross-mode navigation.

### Run

- name: `phase1_purchase_legacy_5u_2m_2026_08_01`
- date: `2026-08-01`
- users: `5`
- spawn rate: `1`
- duration: `2m`
- tags: `purchase-legacy`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~550ms aggregated`
- max observed latency: `720ms` on legacy search endpoints
- error rate: `0.00%`
- duplicate numbering: `not applicable`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Legacy purchase search is materially heavier than the modern lookup endpoints.
- This confirms the modern purchase path is the better operational baseline.

### Run

- name: `phase1_purchase_write_5u_2m_2026_08_01`
- date: `2026-08-01`
- users: `5`
- spawn rate: `1`
- duration: `2m`
- tags: `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~160ms aggregated`
- max observed latency: `331ms` on `purchase/service-invoices [post]`
- error rate: `0.00%`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Purchase write-only load remained very stable under overlap.
- Goods and service confirm/post stayed clean throughout the 5-user run.

### Run

- name: `phase1_purchase_mixed_10u_3m_2026_08_01`
- date: `2026-08-01`
- users: `10`
- spawn rate: `2`
- duration: `3m`
- tags: `purchase-modern`, `purchase-write`
- environment: `local`

### Outcome

- status: `pass`
- p95: `~320ms aggregated`
- max observed latency: `1929ms` on `purchase/purchase-invoices/cross-mode-nav [goods->service]`
- error rate: `0.00%`
- duplicate numbering: `not observed in API run`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Mixed purchase workload completed with zero failures across reads and writes.
- The main pressure point was cross-mode navigation under overlap, not confirm/post.
- Lookup endpoints remained materially faster than cross-mode navigation during the mixed run.

### Run

- name: `phase1_purchase_modern_20u_5m_2026_08_01_postauthtouch`
- date: `2026-08-01`
- users: `20`
- spawn rate: `2`
- duration: `5m`
- tags: `purchase-modern`
- environment: `local`

### Outcome

- status: `pass`
- requests: `2702`
- failures: `0`
- p95: `~850ms aggregated`
- error rate: `0.00%`
- duplicate numbering: `not applicable`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run validated the auth session touch throttling change under heavier purchase-modern read concurrency.
- The previous auth/login `500` and `401` cascade did not recur.
- Purchase behavior was stable, but cross-mode navigation was still the dominant latency hotspot.

### Run

- name: `phase1_purchase_modern_20u_5m_2026_08_01_postcrossopt`
- date: `2026-08-01`
- users: `20`
- spawn rate: `2`
- duration: `5m`
- tags: `purchase-modern`
- environment: `local`

### Outcome

- status: `pass`
- requests: `2933`
- failures: `0`
- p95: `~140ms aggregated`
- error rate: `0.00%`
- duplicate numbering: `not applicable`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- Purchase cross-mode navigation was optimized to avoid materializing the full scoped queryset for numbered vouchers.
- The heaviest hotspot improved sharply:
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
  - before optimization: avg `624ms`, median `310ms`, p95 `2200ms`, max `3241ms`
  - after optimization: avg `62ms`, median `61ms`, p95 `92ms`, max `180ms`
- Service-side cross-mode navigation also improved:
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
  - after optimization: avg `59ms`, median `60ms`, p95 `90ms`, max `164ms`
- Focused Django verification on the current codebase was rerun on `2026-08-01` after the sales-side navigation refactor:
  - sales navigation unit tests passed:
    - `SalesInvoiceViewUnitTests.test_prev_next_orders_by_doc_no_with_id_tiebreaker`
    - `SalesInvoiceViewUnitTests.test_prev_next_passes_line_mode_into_scoped_queries`
    - `SalesComplianceRecoveryUnitTests.test_cross_mode_navigation_view_returns_target`
  - purchase navigation unit tests also passed:
    - `PurchaseInvoiceViewUnitTests.test_prev_next_uses_current_line_mode_scope`
    - `PurchaseInvoiceViewUnitTests.test_prev_next_orders_by_doc_no_with_id_tiebreaker`
    - `PurchaseInvoiceViewUnitTests.test_prev_next_includes_latest_draft_as_next_document`
    - `PurchaseInvoiceViewUnitTests.test_prev_next_falls_forward_to_unnumbered_draft_when_no_higher_sequence_exists`
    - `PurchaseInvoiceConcurrencyHardeningTests.test_cross_mode_navigation_view_returns_target`
- One unrelated pre-existing unit assertion drift remains in `SalesInvoiceViewUnitTests.test_cancel_view_requires_credit_note_permissions_for_locked_period_auto_reversal`; it did not affect navigation verification.
- After this run, purchase modern reads are no longer limited by auth instability or cross-mode navigation latency in the current local stress profile.

## Phase 1C Voucher Write

### Run

- name: `phase1_purchase_modern_5u_2m_2026_08_01_rerun1`
- date: `2026-08-01`
- users: `5`
- spawn rate: `1`
- duration: `2m`
- tags: `purchase-modern`
- environment: `local`

### Outcome

- status: `pass`
- requests: `299`
- failures: `0`
- p95: `~160ms aggregated`
- error rate: `0.00%`
- duplicate numbering: `not applicable`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This rerun confirms purchase modern reads remain stable after the latest navigation verification pass.
- Cross-mode navigation stayed fast across the whole run:
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - avg `70ms`, median `69ms`, p95 `96ms`, max `118ms`
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
    - avg `71ms`, median `75ms`, p95 `95ms`, max `168ms`
- The slowest purchase-modern path in this rerun was list lookup, not navigation:
  - `purchase/purchase-invoices/lookup [list]`
    - avg `123ms`, median `120ms`, p95 `150ms`, max `593ms`
- That single `593ms` outlier is worth watching in heavier mixed-load runs, but it is not currently a failure or cross-mode regression.

### Run

- name: `phase1_purchase_mixed_smoke_3u_45s_2026_08_01`
- date: `2026-08-01`
- users: `3`
- spawn rate: `1`
- duration: `45s`
- tags: `purchase-mixed`
- environment: `local`

### Outcome

- status: `pass`
- requests: `76`
- failures: `0`
- p95: `~250ms aggregated`
- error rate: `0.00%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This was the first validation run of the new explicit `purchase-mixed` Locust workload.
- The workload correctly executed real purchase read traffic in one profile:
  - purchase invoice lookup
  - purchase service invoice lookup
  - goods to service cross-mode navigation
  - service to goods cross-mode navigation
- The earlier multi-tag attempt that only exercised `auth/login` and `auth/me` was a Locust tag-selection limitation, not a product defect.
- No write-path requests were selected in this short smoke window, so the next step is a longer or heavier `purchase-mixed` run to ensure confirm/post, note lifecycle, and draft-save paths are exercised under overlap.
- Two latency spikes are now the main watch items for the next mixed tier:
  - `purchase/purchase-invoices/lookup [list]`
    - avg `132ms`, median `110ms`, p95 `190ms`, max `558ms`
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
    - avg `121ms`, median `57ms`, p95 `860ms`, max `856ms`
- These were not failures, but they are the strongest current candidates for the next deeper purchase mixed-load investigation.

### Run

- name: `phase1_purchase_mixed_smoke_3u_45s_2026_08_01_postlookupopt`
- date: `2026-08-01`
- users: `3`
- spawn rate: `1`
- duration: `45s`
- tags: `purchase-mixed`
- environment: `local`

### Outcome

- status: `pass`
- requests: `79`
- failures: `0`
- p95: `~330ms aggregated`
- error rate: `0.00%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This rerun verified the purchase lookup optimization that:
  - skips `count()` when `include_total=false`
  - reduces purchase seed-id lookup payload from `limit=25` to `limit=5`
- Focused Django verification also passed on `2026-08-01`:
  - `PurchaseInvoiceLookupViewTests`
  - `SalesComplianceRecoveryUnitTests.test_lookup_view_can_skip_total_count`
  - `SalesComplianceRecoveryUnitTests.test_lookup_view_returns_limited_payload`
  - `SalesComplianceRecoveryUnitTests.test_lookup_view_uses_offset_for_next_page`
- The main improvement was on the purchase seed-id helper paths:
  - `purchase/goods-lookup [seed-id]`
    - post optimization: avg `71ms`, median `62ms`, max `100ms`
  - `purchase/service-lookup [seed-id]`
    - post optimization: avg `89ms`, median `93ms`, max `110ms`
- That is materially better than the earlier mixed run where seed-id lookup was one of the dominant hotspots:
  - `purchase/service-lookup [seed-id]`
    - before optimization: avg `1772ms`, median `2500ms`, max `2843ms`
  - `purchase/goods-lookup [seed-id]`
    - before optimization: avg `465ms`, max `1536ms`
- Purchase remained functionally stable with `0` failures, but one latency hotspot still deserves deeper investigation in the next purchase tier:
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - avg `142ms`, median `65ms`, p95 `1300ms`, max `1265ms`
- The list lookup path is now much healthier than the earlier mixed run and no longer looks like the primary bottleneck:
  - `purchase/purchase-invoices/lookup [list]`
    - avg `132ms`, median `110ms`, p95 `330ms`, max `470ms`

### Run

- name: `phase1_purchase_mixed_10u_2m_2026_08_01_deep`
- date: `2026-08-01`
- users: `10`
- spawn rate: `2`
- duration: `2m`
- tags: `purchase-mixed`
- environment: `local`

### Outcome

- status: `pass`
- requests: `982`
- failures: `0`
- p95: `~220ms aggregated`
- p99: `~1600ms aggregated`
- max observed latency: `3049ms`
- error rate: `0.00%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This was the first deeper purchase mixed run with both toggles explicitly enabled:
  - `FINACC_ENABLE_WRITE_TESTS=true`
  - `FINACC_ENABLE_LIFECYCLE_TESTS=true`
- The workload exercised all major purchase mutation categories under overlap:
  - goods invoice draft create/save
  - goods confirm/post
  - goods debit note and credit note create/confirm/post
  - service invoice draft create/save
  - service confirm/post
  - service debit note and credit note create/confirm/post
  - mixed lookup and cross-mode navigation
- Purchase remained functionally stable end to end:
  - no request failures
  - no numbering defects observed
  - no invalid state-transition behavior observed
- The earlier lookup optimization held up well under overlap:
  - `purchase/goods-lookup [seed-id]`
    - avg `79ms`, median `57ms`, max `234ms`
  - `purchase/service-lookup [seed-id]`
    - avg `72ms`, median `62ms`, max `121ms`
- The main remaining latency weakness has shifted away from seed-id fetch and into broader mixed overlap paths:
  - `purchase/purchase-invoices/lookup [list]`
    - avg `113ms`, median `84ms`, p95 `180ms`, p99 `820ms`, max `1611ms`
  - `purchase/purchase-service-invoices/lookup [list]`
    - avg `136ms`, median `95ms`, p95 `210ms`, p99 `1600ms`, max `1561ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - avg `117ms`, median `55ms`, p95 `380ms`, p99 `2700ms`, max `2689ms`
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
    - avg `128ms`, median `52ms`, p95 `100ms`, p98 `2000ms`, max `2285ms`
- The heaviest write-side outliers are now concentrated in service purchase mutation paths:
  - `purchase/service-invoices [draft save]`
    - avg `229ms`, median `140ms`, p95 `260ms`, max `3049ms`
  - `purchase/service-invoices [confirm]`
    - avg `180ms`, median `79ms`, p95 `1100ms`, max `2164ms`
  - `purchase/service-invoices [debit-note create]`
    - avg `202ms`, median `75ms`, p95 `1900ms`, max `1859ms`
  - `purchase/service-invoices [credit-note confirm]`
    - avg `138ms`, median `59ms`, p95 `1400ms`, max `1448ms`
- Goods-side purchase write paths were comparatively healthier, though two still deserve attention:
  - `purchase/invoices [debit-note create]`
    - avg `277ms`, median `79ms`, p95 `2300ms`, max `2329ms`
  - `purchase/invoices [draft save]`
    - avg `205ms`, median `140ms`, p98 `2500ms`, max `2494ms`
- Operational conclusion:
  - purchase correctness under stress is currently strong
  - purchase latency under SaaS-style overlap is still uneven
  - the next best optimization targets are service purchase save/confirm/note-create flows and the mixed cross-mode/list overlap paths

### Run

- name: `phase1_purchase_mixed_10u_90s_2026_08_01_postdraftsyncopt`
- date: `2026-08-01`
- users: `10`
- spawn rate: `2`
- duration: `90s`
- tags: `purchase-mixed`
- environment: `local`

### Outcome

- status: `pass`
- requests: `748`
- failures: `0`
- p95: `~150ms aggregated`
- p99: `~190ms aggregated`
- max observed latency: `246ms`
- error rate: `0.00%`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This rerun validated the draft-save optimization that skips GST-TDS contract-ledger sync for plain draft create/update flows.
- Focused Django verification passed after the change:
  - `PurchaseInvoiceConcurrencyHardeningTests`
  - `PurchaseInvoiceLookupViewTests`
- The earlier multi-second service purchase save spikes did not recur in this rerun.
- Service-side mutation paths improved materially:
  - `purchase/service-invoices [draft save]`
    - avg `139ms`, median `130ms`, p95 `220ms`, max `216ms`
  - `purchase/service-invoices [confirm]`
    - avg `88ms`, median `90ms`, p95 `150ms`, max `153ms`
  - `purchase/service-invoices [debit-note create]`
    - avg `88ms`, median `85ms`, p95 `150ms`, max `148ms`
- Goods-side draft/save and note paths were also stable:
  - `purchase/invoices [draft save]`
    - avg `127ms`, median `120ms`, p95 `180ms`, max `183ms`
  - `purchase/invoices [debit-note create]`
    - avg `77ms`, median `81ms`, p95 `110ms`, max `113ms`
- Mixed lookup and cross-mode navigation now look healthy under this tier:
  - `purchase/purchase-invoices/lookup [list]`
    - avg `99ms`, median `96ms`, p95 `150ms`, max `196ms`
  - `purchase/purchase-service-invoices/lookup [list]`
    - avg `110ms`, median `100ms`, p95 `160ms`, max `246ms`
  - `purchase/purchase-invoices/cross-mode-nav [goods->service]`
    - avg `63ms`, median `62ms`, p95 `92ms`, max `142ms`
  - `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`
    - avg `61ms`, median `57ms`, p95 `95ms`, max `125ms`
- This is the first purchase mixed tier in Phase 1 where both correctness and latency look strong at the same time.

## Phase 1B Follow-up Result: Purchase Mixed Stress Rerun at 20 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_purchase_mixed_20u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_stats.csv)
- [results_phase1_purchase_mixed_20u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_stats_history.csv)
- [results_phase1_purchase_mixed_20u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02.html)

Final aggregate:
- requests: `1744`
- failures: `0`
- average: `260 ms`
- median: `91 ms`
- p95: `870 ms`
- p99: `4700 ms`
- max: `6562 ms`

Key endpoint results:
- `purchase/invoices [confirm]`: `52` requests, `0` failures, avg `204 ms`, median `91 ms`, p95 `630 ms`, p99 `4100 ms`
- `purchase/invoices [post]`: `52` requests, `0` failures, avg `243 ms`, median `62 ms`, p95 `1700 ms`, p99 `2700 ms`
- `purchase/invoices [draft save]`: `54` requests, `0` failures, avg `409 ms`, median `150 ms`, p95 `1000 ms`, p99 `6100 ms`
- `purchase/service-invoices [confirm]`: `56` requests, `0` failures, avg `92 ms`, median `82 ms`, p95 `200 ms`, p99 `300 ms`
- `purchase/service-invoices [post]`: `56` requests, `0` failures, avg `88 ms`, median `78 ms`, p95 `170 ms`, p99 `420 ms`
- `purchase/service-invoices [draft save]`: `65` requests, `0` failures, avg `322 ms`, median `150 ms`, p95 `620 ms`, p99 `6600 ms`
- `purchase/purchase-invoices/lookup [list]`: `251` requests, `0` failures, avg `345 ms`, median `92 ms`, p95 `2700 ms`, p99 `4800 ms`
- `purchase/purchase-service-invoices/lookup [list]`: `120` requests, `0` failures, avg `227 ms`, median `94 ms`, p95 `740 ms`, p99 `3100 ms`

Coverage exercised in this run:
- goods invoice confirm and post
- service invoice confirm and post
- goods draft create and save
- service draft create and save
- goods credit note create, confirm, and post
- goods debit note create, confirm, and post
- service credit note create, confirm, and post
- service debit note create, confirm, and post
- purchase lookup lists
- cross-mode navigation
- seed-detail retrieval

Interpretation:
- this is a strong clean purchase module baseline because it exercises live draft mutation, posting, note flows, and read overlap together at a materially higher concurrency tier than the earlier `5u` and `10u` validation runs
- the earlier `50u` SaaS-style purchase mixed run should still be treated as an escalation run that exposed scaling pressure and not as the current module correctness baseline
- the current purchase module does not show a correctness blocker at `20 users`; the remaining work is higher-tier scalability investigation, especially around list lookups, draft-save spikes, and note override paths

Purchase phase status after this run:
- `purchase correctness under mixed write pressure`: `passed`
- `purchase notes under concurrent mutation`: `passed`
- `purchase cross-mode plus lookup overlap`: `passed`
- `purchase next gap`: `higher-tier scalability profiling beyond 20 users`

Current status:
- strongly automated for voucher write and approval smoke
- payment voucher lifecycle now automated in Locust
- receipt voucher lifecycle now automated in Locust

Current action:
- extend from clean approval smoke into reject and stale-state conflict variants

### Run

- name: `phase1_payment_write_smoke_retry1_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `payment-write`
- environment: `local`

### Outcome

- status: `pass`
- requests: `150`
- failures: `0`
- error rate: `0.00%`
- p95: `~170ms aggregated`
- max observed latency: `199ms` on `payments/meta/voucher-form [seed]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real payment voucher:
  - draft create
  - draft save
  - confirm
  - post
- The stable Phase 1 payment stress path currently uses:
  - live payment form meta
  - real `paid_from`, `paid_to`, and `payment_mode` ids
  - `ADVANCE` payment vouchers with positive `cash_paid_amount`
  - no allocations or settlement-side mutations yet
- The first smoke retry before this pass failed only because the Locust confirm URL had an extra slash before `/confirm/`.
- After fixing the URL join, the full payment write path completed cleanly.

### Run

- name: `phase1_receipt_write_smoke_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `receipt-write`
- environment: `local`

### Outcome

- status: `pass`
- requests: `147`
- failures: `0`
- error rate: `0.00%`
- p95: `~180ms aggregated`
- max observed latency: `271ms` on `receipts/receipt-vouchers [draft create]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real receipt voucher:
  - draft create
  - draft save
  - confirm
  - post
- The stable Phase 1 receipt stress path currently uses:
  - live receipt form meta
  - real `received_in`, `received_from`, and `receipt_mode` ids
  - `ADVANCE` receipt vouchers with positive `cash_received_amount`
  - no allocations or settlement-side mutations yet
- Receipt write coverage is now at parity with payment for the Phase 1 draft-to-post smoke path.

### Run

- name: `phase1_payment_approval_smoke_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `payment-approval`
- environment: `local`

### Outcome

- status: `pass`
- requests: `119`
- failures: `0`
- error rate: `0.00%`
- p95: `~290ms aggregated`
- max observed latency: `2979ms` on `payments/payment-vouchers [approval draft create]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real payment approval workflow:
  - approval-draft create
  - submit
  - approve
- The approval path succeeded with same-user submit then approve under the current local policy.
- The main stress observation is not correctness-related:
  - draft create showed occasional latency spikes up to about `3.0s`
  - submit and approve remained much tighter, roughly sub-`200ms` at the top end in this smoke profile

### Run

- name: `phase1_receipt_approval_smoke_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `receipt-approval`
- environment: `local`

### Outcome

- status: `pass`
- requests: `120`
- failures: `0`
- error rate: `0.00%`
- p95: `~200ms aggregated`
- max observed latency: `2493ms` on `receipts/receipt-vouchers [approval draft create]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real receipt approval workflow:
  - approval-draft create
  - submit
  - approve
- The approval path also succeeded with same-user submit then approve under the current local policy.
- Similar to payments, the dominant latency outlier is draft creation rather than the approval calls themselves.

### Run

- name: `phase1_stale_conflict_smoke_2u_45s_2026_08_01`
- date: `2026-08-01`
- users: `2`
- spawn rate: `1`
- duration: `45s`
- tags: `stale-conflict`
- environment: `local`

### Outcome

- status: `pass`
- requests: `153`
- failures: `0`
- error rate: `0.00%`
- p95: `~190ms aggregated`
- max observed latency: `359ms` on `payments/meta/voucher-form [seed]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run verifies real stale-tab and reject conflict behavior for both payments and receipts:
  - submit then repeat submit
  - approve then repeat approve
  - reject then repeat reject
- The Locust assertions validate backend feedback messages, not just HTTP success:
  - `Already submitted.`
  - `Already approved.`
  - `Already rejected.`
- The conflict path remained clean under smoke load, which raises confidence in idempotent approval handling.

### Run

- name: `phase1_report_write_mixed_smoke_retry1_4u_45s_2026_08_01`
- date: `2026-08-01`
- users: `4`
- spawn rate: `1`
- duration: `45s`
- tags: `report-write-mix`
- environment: `local`

### Outcome

- status: `pass`
- requests: `158`
- failures: `0`
- error rate: `0.00%`
- p95: `~330ms aggregated`
- max observed latency: `2623ms` on `reports/payables/aging [get]`
- duplicate numbering: `not observed`
- state-transition defects: `not observed`
- rollback or cleanup needed: `no`

### Notes

- This run mixes:
  - payables meta and aging
  - bank reconciliation meta and session listing
  - sales draft create/save
  - purchase draft create/save
  - payment voucher draft-to-post
  - receipt voucher draft-to-post
- The mixed profile stayed functionally clean with zero failures.
- The main observation is performance-shaped, not correctness-shaped:
  - report endpoints, especially `payables/aging`, showed the heaviest latency spikes under concurrent writes
  - payment `post` also produced a high single-run spike
- This is enough to close the pure “missing profile” gap, but not enough yet to declare high-load report interference fully de-risked.

## Phase 1D Reports During Active Writes

Current status:
- executable and smoke-verified with a dedicated `report-write-mix` profile
- broader concurrency tiers still remain to be pushed beyond smoke level

Current action:
- expand from smoke to working-load and higher-cardinality report slices once the smoke baseline is documented

## Phase 1D Follow-up Result: Report-Write Mixed Run at 20 Users

Executed on:
- `2026-08-02`

Important note:
- the first `20u` run surfaced a Locust harness issue, not a product defect:
  - `sales/invoices [draft save]`
  - `sales/service-invoices [draft save]`
  - failures were caused by `productDesc` exceeding the serializer's `200` character limit after repeated draft-save mutation in the stress payload builder
- local corrective action applied:
  - `Finacc/perf/locust/locustfile.py`
  - sales draft-save payload mutation now trims `productDesc` before appending the save suffix
- the clean rerun below is the accepted baseline for report-under-write behavior

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags report-write-mix \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim \
  --html Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim.html
```

Artifacts:
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim_stats.csv)
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim_stats_history.csv)
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim.html)

Final aggregate:
- requests: `1649`
- failures: `0`
- average: `375 ms`
- median: `190 ms`
- p95: `1200 ms`
- p99: `3400 ms`
- max: `6410 ms`

Coverage exercised in the clean rerun:
- `reports/payables/meta [get]`
- `reports/payables/aging [get]`
- `bank-reconciliation/meta [get]`
- `bank-reconciliation/sessions [list]`
- `sales` draft create and save
- `purchase` draft create and save
- `payment` voucher create, save, confirm, and post
- `receipt` voucher create, save, confirm, and post

Key endpoint results:
- `reports/payables/aging [get]`: `201` requests, `0` failures, avg `1184 ms`, median `610 ms`, p95 `3600 ms`, p99 `4500 ms`, max `6410 ms`
- `reports/payables/meta [get]`: `133` requests, `0` failures, avg `141 ms`, median `100 ms`, p95 `340 ms`, p99 `450 ms`
- `bank-reconciliation/meta [get]`: `114` requests, `0` failures, avg `207 ms`, median `100 ms`, p95 `420 ms`, p99 `2500 ms`
- `bank-reconciliation/sessions [list]`: `139` requests, `0` failures, avg `184 ms`, median `130 ms`, p95 `450 ms`, p99 `880 ms`
- `payments/payment-vouchers [draft save]`: `66` requests, `0` failures, avg `398 ms`, median `290 ms`, p95 `870 ms`, p99 `2400 ms`
- `receipts/receipt-vouchers [draft save]`: `62` requests, `0` failures, avg `421 ms`, median `270 ms`, p95 `1000 ms`, p99 `2900 ms`
- `sales/invoices [draft save]`: `27` requests, `0` failures, avg `586 ms`, median `570 ms`, p95 `1200 ms`, p99 `1300 ms`
- `purchase/invoices [draft save]`: `36` requests, `0` failures, avg `619 ms`, median `530 ms`, p95 `1300 ms`, p99 `1400 ms`

Interpretation:
- reports remained functionally available while sales, purchase, payment, and receipt writes were active in the same run
- after the Locust payload fix, the profile completed cleanly with zero product failures
- the clear primary bottleneck is now `reports/payables/aging [get]`
- secondary hotspots exist in draft-save style mutation paths, but they are materially less severe than AP aging under this mixed profile
- this closes the “can reports survive concurrent mutation?” confidence gap at a meaningful `20-user` tier

Phase 1D status after the clean rerun:
- `report correctness during active writes`: `passed`
- `cross-module interference`: `passed`
- `primary remaining report hotspot`: `reports/payables/aging [get]`

## Run Result Logging Template

For each executed command, append:

### Run

- name:
- date:
- users:
- spawn rate:
- duration:
- tags:
- environment:

### Outcome

- status: `pass` / `partial` / `fail`
- p95:
- error rate:
- duplicate numbering:
- state-transition defects:
- rollback or cleanup needed:

### Notes

- 

## Current Automation Readiness Summary

| Module | Planned In Phase 1 | Executable Now | Notes |
| --- | --- | --- | --- |
| Sales | Yes | Strong | Lifecycle, settings patch, real draft create/save, and report-write mixed smoke are covered |
| Purchase | Yes | Strong | Modern, legacy, write-only, mixed read+write, auth-path stability, cross-mode navigation optimization, purchase note lifecycle, and purchase draft create/save all executed cleanly |
| Vouchers | Yes | Strong | Payment and receipt voucher create/save/confirm/post plus submit/approve, reject, and stale-state smoke are covered |

## Phase 1C Follow-up Result: Voucher Mixed Stress Escalation at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags voucher-mixed \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_vouchers_mixed_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_vouchers_mixed_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_vouchers_mixed_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_50u_2m_2026_08_02_stats.csv)
- [results_phase1_vouchers_mixed_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_50u_2m_2026_08_02_stats_history.csv)
- [results_phase1_vouchers_mixed_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_50u_2m_2026_08_02.html)

Final aggregate:
- requests: `2624`
- failures: `0`
- average: `1687 ms`
- median: `1600 ms`
- p95: `2900 ms`
- p99: `3500 ms`
- max: `6482 ms`

Key endpoint results:
- `payments/meta/voucher-form [seed]`: `50` requests, `0` failures, avg `553 ms`, median `600 ms`, p95 `820 ms`
- `receipts/meta/voucher-form [seed]`: `50` requests, `0` failures, avg `528 ms`, median `550 ms`, p95 `880 ms`
- `payments/payment-vouchers [draft save]`: `73` requests, `0` failures, avg `2811 ms`, median `2900 ms`, p95 `3400 ms`
- `payments/payment-vouchers [post]`: `70` requests, `0` failures, avg `1856 ms`, median `1900 ms`, p95 `2300 ms`
- `receipts/receipt-vouchers [draft save]`: `80` requests, `0` failures, avg `2866 ms`, median `2900 ms`, p95 `3600 ms`
- `receipts/receipt-vouchers [draft create]`: `82` requests, `0` failures, avg `2437 ms`, median `2300 ms`, p95 `4100 ms`
- `receipts/receipt-vouchers [post]`: `78` requests, `0` failures, avg `2023 ms`, median `2100 ms`, p95 `2400 ms`
- `receipts/receipt-vouchers [reject seed create]`: `76` requests, `0` failures, avg `2435 ms`, median `2300 ms`, p95 `3400 ms`, p99 `6500 ms`
- `receipts/receipt-vouchers [stale seed create]`: `79` requests, `0` failures, avg `2545 ms`, median `2400 ms`, p95 `4200 ms`, p99 `5700 ms`

Interpretation:
- the voucher module remains correctness-stable under a materially higher `50-user` mixed mutation profile
- this run did not expose posting, approval, or stale-state correctness defects
- the bottleneck is now clearly throughput and latency rather than integrity
- receipt-side draft and seed-create paths are the most expensive operations at this tier
- payment-side draft-save is also a meaningful hotspot, but still somewhat better than the heaviest receipt paths

Comparison versus the best recent clean `20-user` voucher run:
- the strongest `20-user` baseline remains `results_phase1_vouchers_mixed_20u_2m_2026_08_02_postcache_real`
- at `20 users`, voucher meta and most mutation endpoints were still mostly sub-second or low hundreds of milliseconds
- at `50 users`, the same workflow family moves into a `1.4s` to `2.9s` median band for many payment and receipt mutation paths
- the system is still stable, but not yet comfortably scaled for a heavier SaaS-style voucher concurrency tier

Voucher phase status after this run:
- `voucher correctness under mixed mutation`: `passed`
- `payment approval/reject/stale-state flows under stress`: `passed`
- `receipt approval/reject/stale-state flows under stress`: `passed`
- `voucher next gap`: `latency reduction for receipt draft/create/save and seed-create-heavy paths`

## Phase 1C Follow-up Result: Voucher Mixed 100-User / 2-Minute Stress Rerun

Command executed:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags voucher-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_vouchers_mixed_100u_2m_2026_08_02 \
  --html perf/locust/results_phase1_vouchers_mixed_100u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_vouchers_mixed_100u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_100u_2m_2026_08_02_stats.csv)
- [results_phase1_vouchers_mixed_100u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_100u_2m_2026_08_02_stats_history.csv)
- [results_phase1_vouchers_mixed_100u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_vouchers_mixed_100u_2m_2026_08_02.html)

Final aggregate:
- requests: `3399`
- failures: `0`
- average: `2165 ms`
- median: `1400 ms`
- p95: `3900 ms`
- p99: `14000 ms`
- max: `113884 ms`

Key endpoint results:
- `payments/meta/voucher-form [seed]`: `92` requests, `0` failures, avg `1102 ms`, median `1100 ms`, p95 `1800 ms`, p99 `1900 ms`
- `payments/payment-vouchers [draft create]`: `115` requests, `0` failures, avg `2213 ms`, median `1700 ms`, p95 `4600 ms`, p99 `9200 ms`
- `payments/payment-vouchers [draft save]`: `113` requests, `0` failures, avg `2648 ms`, median `2400 ms`, p95 `4000 ms`, p99 `5200 ms`
- `payments/payment-vouchers [confirm]`: `113` requests, `0` failures, avg `1348 ms`, median `1300 ms`, p95 `1900 ms`
- `payments/payment-vouchers [post]`: `111` requests, `0` failures, avg `1722 ms`, median `1600 ms`, p95 `2600 ms`
- `payments/payment-vouchers [approval draft create]`: `92` requests, `0` failures, avg `2032 ms`, median `1700 ms`, p95 `4300 ms`, p99 `7500 ms`
- `receipts/meta/voucher-form [seed]`: `100` requests, `0` failures, avg `917 ms`, median `920 ms`, p95 `1500 ms`, p99 `1900 ms`
- `receipts/receipt-vouchers [draft create]`: `120` requests, `0` failures, avg `8142 ms`, median `3200 ms`, p95 `21000 ms`, p99 `108000 ms`
- `receipts/receipt-vouchers [draft save]`: `117` requests, `0` failures, avg `2598 ms`, median `2400 ms`, p95 `4000 ms`, p99 `4800 ms`
- `receipts/receipt-vouchers [confirm]`: `115` requests, `0` failures, avg `1414 ms`, median `1300 ms`, p95 `2100 ms`
- `receipts/receipt-vouchers [post]`: `112` requests, `0` failures, avg `1824 ms`, median `1700 ms`, p95 `2600 ms`
- `receipts/receipt-vouchers [approval draft create]`: `96` requests, `0` failures, avg `6987 ms`, median `2600 ms`, p95 `34000 ms`, p99 `82000 ms`
- `receipts/receipt-vouchers [reject seed create]`: `94` requests, `0` failures, avg `6101 ms`, median `2600 ms`, p95 `21000 ms`, p99 `81000 ms`
- `receipts/receipt-vouchers [stale seed create]`: `103` requests, `0` failures, avg `6137 ms`, median `2700 ms`, p95 `17000 ms`, p99 `89000 ms`

Interpretation:
- voucher correctness remains strong even at the `100-user` mixed tier, with `0` failures across payment, receipt, approval, reject, and stale-state flows
- payment-side flows stayed in a healthy low-seconds band and do not currently look like the primary module risk
- the new risk is concentrated on receipt create-side operations, especially:
  - `receipt draft create`
  - `receipt approval draft create`
  - `receipt reject seed create`
  - `receipt stale seed create`
- the median behavior for those receipt create-side paths is still workable, but the long-tail spikes are too large for stronger SaaS confidence
- the aggregate p95 remains good because most routes are healthy, but the aggregate p99 and max clearly reflect receipt-side outliers

Voucher phase status after this run:
- `voucher correctness under 100-user mixed stress`: `passed`
- `payment voucher high-tier resilience`: `strong`
- `receipt voucher high-tier resilience`: `mixed because of create-side tail spikes`
- `voucher next gap`: `receipt create-path bottleneck investigation and reduction`

## Phase 1C Follow-up Result: Receipt Create-Side Tail Reduction Rerun After Disabled-TCS Skip And Write-Response Navigation Trim

Executed on:
- `2026-08-03`

Code changes validated:
- `receipts/services/receipt_voucher_service.py`
  - runtime TCS sync now returns early when preview is disabled and no existing `TcsComputation` row exists, avoiding unnecessary compliance-row creation on plain receipt drafts.
- `receipts/views/receipt_voucher.py`
  - write responses now receive `skip_preview_numbers` and `skip_navigation` context, so draft create and save no longer perform read-only navigation / preview hydration after write completion.
- `payments/views/payment_voucher.py`
  - matched the same write-response serializer optimization for parity with receipt and payment flows.
- `receipts/tests.py`
  - added regression coverage for disabled runtime-TCS no-op behavior and preservation of existing computation rows when receipt TCS later becomes disabled.

Correctness validation:

```bash
source venv/bin/activate
python3 manage.py test receipts.tests.ReceiptVoucherServiceTests --keepdb
python3 manage.py test receipts.tests.PaymentPostingAdapterTests receipts.tests.ReceiptVoucherReferenceWarningTests --keepdb
```

Result:
- focused receipt and payment voucher regression suites passed cleanly

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags receipt-write receipt-approval receipt-approval-conflict \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav \
  --html perf/locust/results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav.html
```

Artifacts:
- [results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav_stats.csv)
- [results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav_stats_history.csv)
- [results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav.html)

Observed result from `results_phase1_receipts_only_100u_2m_2026_08_02_skip_write_nav_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 3510 | 0 | `1200 ms` | `5300 ms` | `31000 ms` | `2587.15 ms` |
| `receipts/receipt-vouchers [draft create]` | 205 | 0 | `1900 ms` | `30000 ms` | `33000 ms` | `6703.42 ms` |
| `receipts/receipt-vouchers [approval draft create]` | 206 | 0 | `2000 ms` | `30000 ms` | `33000 ms` | `6165.66 ms` |
| `receipts/receipt-vouchers [reject seed create]` | 221 | 0 | `2100 ms` | `29000 ms` | `31000 ms` | `7031.64 ms` |
| `receipts/receipt-vouchers [stale seed create]` | 232 | 0 | `2000 ms` | `32000 ms` | `34000 ms` | `6923.82 ms` |
| `receipts/receipt-vouchers [draft save]` | 204 | 0 | `2200 ms` | `3900 ms` | `4300 ms` | `2416.34 ms` |
| `receipts/receipt-vouchers [confirm]` | 202 | 0 | `1400 ms` | `2200 ms` | `2600 ms` | `1519.84 ms` |
| `receipts/receipt-vouchers [post]` | 201 | 0 | `1700 ms` | `2600 ms` | `3000 ms` | `1823.96 ms` |

Comparison versus the earlier 100-user voucher mixed receipt bottleneck:
- correctness remained fully clean with `0` failures
- the prior receipt create-side outliers in the mixed `voucher-mixed` profile had reached p99 values in the `82s` to `108s` band and a max of `113.884s`
- after the receipt-only follow-up fixes, receipt create-side p99 fell into the `31s` to `34s` band and max settled in the low `35s`
- median create-side behavior also tightened into the `1.9s` to `2.1s` range, while save, confirm, and post remained in a healthy low-seconds band

Interpretation:
- this is a meaningful stability and latency improvement, not just a correctness rerun
- receipt create-side work is still the weakest voucher subpath at high concurrency
- however, it is no longer exhibiting the earlier extreme outlier behavior that blocked stronger voucher confidence
- payment remains the stronger voucher family, and receipt still needs another reduction pass before it can be called truly SaaS-comfortable at this tier

Voucher phase status after this rerun:
- `voucher correctness under targeted 100-user receipt pressure`: `passed`
- `payment voucher high-tier resilience`: `strong`
- `receipt voucher create-side resilience`: `improved but still mixed`
- `voucher next gap`: `another receipt create-path reduction pass, then rerun the full mixed voucher tier if needed`

## Phase 1C Follow-up Result: Voucher Mixed 100-User / 2-Minute Rerun On August 3, 2026

Command executed:

```bash
cd Finacc && source venv/bin/activate && export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true && locust -f perf/locust/locustfile.py --headless --users 100 --spawn-rate 12 --run-time 2m --tags voucher-mixed --host http://127.0.0.1:8000 --csv perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun --html perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun.html
```

Artifacts:
- [results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_stats.csv)
- [results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_stats_history.csv)
- [results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun_failures.csv)
- [results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_rerun.html)

Aggregated result:
- `2142` requests
- `1` failure
- average `4836.15 ms`
- median `4200 ms`
- p95 `11000 ms`
- p99 `18000 ms`
- max `37445.62 ms`

Key payment-voucher results:
- `payments/meta/voucher-form [seed]`: `94` requests, `0` failures, avg `1739.36 ms`, median `1600 ms`, p95 `3700 ms`
- `payments/payment-vouchers [draft create]`: `74` requests, `0` failures, avg `6381.25 ms`, median `5700 ms`, p95 `12000 ms`, p99 `29000 ms`
- `payments/payment-vouchers [draft save]`: `66` requests, `0` failures, avg `7949.14 ms`, median `7900 ms`, p95 `14000 ms`
- `payments/payment-vouchers [submit]`: `62` requests, `0` failures, avg `4183.40 ms`, median `4000 ms`
- `payments/payment-vouchers [approve]`: `62` requests, `0` failures, avg `4390.08 ms`, median `4000 ms`
- `payments/payment-vouchers [post]`: `60` requests, `0` failures, avg `5619.33 ms`, median `5300 ms`
- `payments/payment-vouchers [stale submit]`: `66` requests, `0` failures, avg `3990.61 ms`, median `3900 ms`

Key receipt-voucher results:
- `receipts/meta/voucher-form [seed]`: `97` requests, `0` failures, avg `1923.91 ms`, median `1700 ms`, p95 `4200 ms`
- `receipts/receipt-vouchers [draft create]`: `63` requests, `0` failures, avg `8861.48 ms`, median `7400 ms`, p95 `19000 ms`, p99 `33000 ms`
- `receipts/receipt-vouchers [draft save]`: `55` requests, `0` failures, avg `8057.41 ms`, median `8200 ms`, p95 `13000 ms`
- `receipts/receipt-vouchers [submit]`: `51` requests, `0` failures, avg `4299.56 ms`, median `4100 ms`
- `receipts/receipt-vouchers [approve]`: `49` requests, `0` failures, avg `4707.97 ms`, median `4500 ms`
- `receipts/receipt-vouchers [post]`: `50` requests, `0` failures, avg `5899.73 ms`, median `5600 ms`
- `receipts/receipt-vouchers [stale submit]`: `60` requests, `1` failure, avg `4143.99 ms`, median `3900 ms`, p95 `7300 ms`, p99 `14000 ms`

Failure detail:
- the single failure was `receipts/receipt-vouchers [stale submit]`
- the backend returned a `500 OperationalError` at `/api/receipts/receipt-vouchers/<id>/approval/`
- this means voucher correctness is still broadly strong, but the receipt stale-approval path is not yet perfectly clean at the local `100-user` tier

Interpretation:
- payment remains the stronger voucher family under heavy concurrency
- receipt remains functionally stable across the main draft, confirm, submit, approve, and post flows, but still has heavier create-side latency and one overload-sensitive stale-submit edge
- this rerun keeps vouchers in the `strong but not fully closed at 100-user local stress` bucket rather than the earlier `fully clean` bucket

Status after this rerun:
- `voucher mixed correctness at 100 users`: `mostly passed with 1 narrow stale-submit failure`
- `payment voucher high-tier resilience`: `strong`
- `receipt voucher high-tier resilience`: `mixed`
- `voucher next gap`: `receipt create/stale-approval path hardening before calling 100-user vouchers fully closed`

## Phase 1C Follow-up Result: Receipt Approval Conflict 100-User / 2-Minute Rerun On August 3, 2026

Command executed:

```bash
cd Finacc
source venv/bin/activate
DEBUG=true AUTH_COOKIE_SECURE=false SESSION_COOKIE_SECURE=false CSRF_COOKIE_SECURE=false \
DB_POOL_ENABLED=true DB_POOL_MIN_SIZE=1 DB_POOL_MAX_SIZE=4 DB_POOL_TIMEOUT_SECONDS=15 \
DB_POOL_MAX_WAITING=64 DB_CONN_MAX_AGE=0 \
gunicorn FA.wsgi:application --bind 127.0.0.1:8004 --workers 2 --threads 4 --timeout 120

locust -f perf/locust/locustfile.py --headless \
  --users 100 \
  --spawn-rate 12 \
  --run-time 2m \
  --tags receipt-approval-conflict \
  --host http://127.0.0.1:8004 \
  --csv perf/locust/results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth \
  --html perf/locust/results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html
```

Artifacts:
- [results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats.csv)
- [results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats_history.csv)
- [results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receipt_approval_conflict_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html)

Aggregated result:
- `4393` requests
- `0` failures
- average `2142 ms`
- median `1300 ms`
- p95 `5200 ms`
- p99 `6500 ms`
- max `7300 ms`
- throughput `36.64 req/s`

Key correctness result:
- all auth, seed, reject, stale-submit, and stale-approve conflict paths completed with `0` failures
- the earlier local `receipt stale-submit` overload failure did not reproduce on the corrected pooled local stack

Important local-stack note:
- the earlier failure was strongly influenced by local environment constraints rather than by receipt approval logic alone
- two local-stack corrections mattered:
  - run a WSGI server instead of Django `runserver`
  - use bounded Django/Postgres pooling with `DB_CONN_MAX_AGE=0`
- because login in this local flow relies on secure cookies, plain local `http://127.0.0.1` stress also needed:
  - `AUTH_COOKIE_SECURE=false`
  - `SESSION_COOKIE_SECURE=false`
  - `CSRF_COOKIE_SECURE=false`

Status after this rerun:
- `receipt approval conflict correctness at 100 users`: `clean`
- `voucher stale-state approval path`: `substantially stronger`
- `remaining voucher concern at high local tier`: `tail latency, not correctness`

## Phase 1D Follow-up Result: Financial Reports 50-User / 2-Minute Stress On August 3, 2026

Command executed:

```bash
cd Finacc && source venv/bin/activate && locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 8 --run-time 2m --tags financial-reports --host http://127.0.0.1:8000 --csv perf/locust/results_phase1_financial_reports_50u_2m_2026_08_03 --html perf/locust/results_phase1_financial_reports_50u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_financial_reports_50u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_50u_2m_2026_08_03_stats.csv)
- [results_phase1_financial_reports_50u_2m_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_50u_2m_2026_08_03_stats_history.csv)
- [results_phase1_financial_reports_50u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_50u_2m_2026_08_03.html)

Aggregated result:
- `1516` requests
- `0` failures
- average `1326.22 ms`
- median `970 ms`
- p95 `3800 ms`
- p99 `4500 ms`
- max `5136.02 ms`

Key financial-report results:
- `reports/financial/ledger-summary [get]`: `379` requests, `0` failures, avg `1380.55 ms`, median `1000 ms`, p95 `3600 ms`, p99 `4200 ms`
- `reports/financial/ledger-summary [grouped]`: `189` requests, `0` failures, avg `1661.22 ms`, median `1300 ms`, p95 `4200 ms`, p99 `4700 ms`
- `reports/financial/ledger-summary/csv [export]`: `153` requests, `0` failures, avg `1408.07 ms`, median `990 ms`, p95 `4000 ms`, p99 `4800 ms`
- `reports/financial/trial-balance [get]`: `365` requests, `0` failures, avg `1272.32 ms`, median `970 ms`, p95 `3600 ms`, p99 `4500 ms`
- `reports/financial/trial-balance [grouped]`: `161` requests, `0` failures, avg `1357.79 ms`, median `1100 ms`, p95 `3500 ms`, p99 `4200 ms`
- `reports/financial/trial-balance/csv [export]`: `169` requests, `0` failures, avg `1507.58 ms`, median `1200 ms`, p95 `4000 ms`, p99 `4700 ms`

Interpretation:
- financial-report summary, grouped, and CSV export paths all remained correctness-clean at this concurrency tier
- grouped and export variants are predictably heavier than the plain summary reads, but their tail remained controlled and materially below the earlier voucher and purchase bottlenecks
- this is a strong stress result for the financial-report family on the local environment

Status after this run:
- `financial reports correctness at 50 users`: `passed`
- `financial reports performance at 50 users`: `strong`
- `financial reports next gap`: `decide whether to escalate to 100 users or switch to the next report family`

## Phase 1D Follow-up Result: Report-Heavy 50-User / 2-Minute Mixed Report Stress On August 3, 2026

Command executed:

```bash
cd Finacc && source venv/bin/activate && locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 8 --run-time 2m --tags report-heavy --host http://127.0.0.1:8000 --csv perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03 --html perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_report_heavy_50u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_stats.csv)
- [results_phase1_report_heavy_50u_2m_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_stats_history.csv)
- [results_phase1_report_heavy_50u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03.html)

Current final CSV snapshot:
- `833` requests
- `0` failures
- average `2767.40 ms`
- median `1200 ms`
- p95 `14000 ms`
- p99 `17000 ms`
- max `17468.79 ms`

Key results:
- `reports/payables/aging [get]`: `125` requests, `0` failures, avg `12491.23 ms`, median `13000 ms`, p95 `17000 ms`, p99 `17000 ms`
- `reports/payables/meta [get]`: `85` requests, `0` failures, avg `791.81 ms`, median `820 ms`
- `bank-reconciliation/meta [get]`: `78` requests, `0` failures, avg `1133.41 ms`, median `1100 ms`
- `bank-reconciliation/sessions [list]`: `83` requests, `0` failures, avg `1032.31 ms`, median `1100 ms`
- `reports/financial/ledger-summary [get]`: `81` requests, `0` failures, avg `1344.58 ms`, median `1300 ms`
- `reports/financial/trial-balance [get]`: `85` requests, `0` failures, avg `1258.30 ms`, median `1300 ms`

Interpretation:
- the mixed report family remains correctness-clean at `50 users`
- the financial-report and bank-reconciliation paths stayed in a healthy low-seconds band
- `reports/payables/aging [get]` is now the dominant report bottleneck, with a very large tail compared with every other report endpoint in the same run
- this makes AP aging the clearest next optimization target inside the report family

Status after this run:
- `mixed report correctness at 50 users`: `passed`
- `financial-report subfamily`: `strong`
- `bank-reconciliation subfamily`: `healthy`
- `payables aging subfamily`: `correct but performance-weak`
- `next report gap`: `optimize AP aging before escalating report-heavy further`

## Phase 1B Follow-up Result: Purchase Mixed 100-User / 2-Minute Stress Rerun

Executed on:
- `2026-08-03`

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03 \
  --html perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_stats.csv)
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_stats_history.csv)
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_failures.csv)
- [results_phase1_purchase_mixed_100u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03.html)

Observed result from `results_phase1_purchase_mixed_100u_2m_2026_08_03_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1624 | 2 | `5800 ms` | `15000 ms` | `20000 ms` | `6291.53 ms` |
| `purchase/invoices [draft create]` | 109 | 0 | `9500 ms` | `15000 ms` | `17000 ms` | `9584.12 ms` |
| `purchase/invoices [draft save]` | 36 | 0 | `17000 ms` | `25000 ms` | `25000 ms` | `17274.31 ms` |
| `purchase/invoices [post]` | 55 | 0 | `9300 ms` | `15000 ms` | `16000 ms` | `9359.18 ms` |
| `purchase/purchase-invoices/lookup [list]` | 173 | 1 | `5700 ms` | `8200 ms` | `9100 ms` | `5474.60 ms` |
| `purchase/service-invoices [draft create]` | 96 | 0 | `10000 ms` | `15000 ms` | `18000 ms` | `9988.65 ms` |
| `purchase/service-invoices [draft save]` | 31 | 0 | `18000 ms` | `26000 ms` | `27000 ms` | `19138.43 ms` |
| `purchase/service-invoices [post]` | 51 | 0 | `8700 ms` | `14000 ms` | `14000 ms` | `9119.80 ms` |
| `purchase/purchase-service-invoices/lookup [list]` | 70 | 0 | `5700 ms` | `7700 ms` | `10000 ms` | `5600.24 ms` |

Observed failures:
- `GET purchase/purchase-invoices/lookup [list]`: `1` backend `OperationalError` 500
- `GET purchase/goods-detail [seed]`: `1` backend `OperationalError` 500 on `/api/purchase/purchase-invoices/<id>/`

Interpretation:
- this run is a meaningful purchase comparison tier because it exercised:
  - draft create and save
  - confirm and post
  - credit-note and debit-note flows
  - goods/service detail seed loads
  - lookup and cross-mode navigation reads
- correctness is mostly preserved, but purchase is not yet fully high-tier clean because backend read-side `OperationalError` surfaced under mixed concurrency
- the hottest write costs are still purchase draft save and service draft save
- the immediate defect signal is narrower than “all purchase is failing”:
  - purchase lookup list
  - purchase detail seed fetch
  are the only routes that actually threw at this tier

Comparison versus the strongest recent 50-user purchase mixed rerun:
- 50-user fresh-doc and dropdown-tightening reruns were correctness-clean and latency-credible
- the jump to 100 users exposed two real backend failures rather than only slower latency
- purchase therefore has a stronger 50-user story than 100-user story at the moment

Purchase phase status after this rerun:
- `purchase mixed correctness at 50 users`: `passed`
- `purchase mixed correctness at 100 users`: `partial because of 2 OperationalError failures`

## Phase 1B Stabilization Result: Purchase Mixed 100-User / 2-Minute Rerun After Detail-Read Optimization

Executed on:
- `2026-08-03`

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt \
  --html perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt.html
```

Artifacts:
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt_stats.csv)
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt_stats_history.csv)
- [results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt.html)

Code change before rerun:
- [purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py:274)
  - purchase detail GET now skips preview-number and navigation hydration in serializer context, matching the purchase list-read optimization already present.

Focused regression coverage:
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py:164)
  - added a targeted unit test asserting purchase detail GET serializer context sets `skip_navigation=True` and `skip_preview_numbers=True`

Observed result from `results_phase1_purchase_mixed_100u_2m_2026_08_03_post_detail_opt_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1917 | 0 | `5200 ms` | `9100 ms` | `16000 ms` | `5229.75 ms` |
| `purchase/goods-detail [seed]` | 122 | 0 | `5000 ms` | `6300 ms` | `6700 ms` | `4849.32 ms` |
| `purchase/purchase-invoices/lookup [list]` | 184 | 0 | `5000 ms` | `6100 ms` | `6500 ms` | `4750.82 ms` |
| `purchase/service-detail [seed]` | 152 | 0 | `5100 ms` | `5800 ms` | `6600 ms` | `4922.86 ms` |
| `purchase/purchase-service-invoices/lookup [list]` | 79 | 0 | `5000 ms` | `5900 ms` | `6600 ms` | `4786.15 ms` |
| `purchase/invoices [draft save]` | 30 | 0 | `15000 ms` | `16000 ms` | `16000 ms` | `14996.78 ms` |
| `purchase/service-invoices [draft save]` | 41 | 0 | `15000 ms` | `16000 ms` | `17000 ms` | `15002.92 ms` |

Interpretation:
- the previous 100-user purchase mixed failures did not reproduce
- the formerly suspect read-side routes stayed clean for the full run:
  - purchase detail seed GETs
  - purchase lookup list GETs
- the main remaining purchase tail is draft-save latency, not correctness instability on lookup/detail reads

Purchase phase status after this stabilization rerun:
- `purchase mixed correctness at 100 users`: `passed`
- `purchase earlier detail/lookup instability`: `stabilized`
- `purchase remaining primary tail`: `draft save latency`
- `purchase mixed latency at 100 users`: `mixed`
- `purchase next gap`: `investigate and remove purchase lookup/detail OperationalError under mixed concurrency, then rerun 100-user tier`

## Phase 1B Follow-up Result: Purchase Draft Write 100-User / 2-Minute Rerun After Unchanged Duplicate-Check Skip

Executed on:
- `2026-08-03`

Code changes validated:
- `purchase/services/purchase_invoice_service.py`
  - duplicate supplier-invoice validation now skips the database lookup when the current purchase header already has the same entity, vendor, supplier invoice number, supplier invoice date, and rounded grand total
- `purchase/tests.py`
  - added regression coverage proving unchanged existing invoices do not execute duplicate-check queries

Focused regression command:

```bash
cd Finacc
source venv/bin/activate
python manage.py test purchase.tests.PurchaseDuplicateSupplierInvoiceTests purchase.tests.PurchaseInvoiceRetrieveContextTests --keepdb
```

Regression result:
- `Ran 3 tests in 0.085s`
- `OK`

Stress command:

```bash
cd Finacc
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags purchase-draft-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip \
  --html perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip.html
```

Artifacts:
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip_stats.csv)
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip_stats_history.csv)
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip.html)

Observed result from `results_phase1_purchase_draftwrite_100u_2m_2026_08_03_post_dup_skip_stats.csv`:
- aggregated:
  - `759` requests
  - `15` failures
  - median `11.0s`
  - p95 `37.0s`
  - p99 `40.0s`
- goods draft create:
  - `49` requests
  - `1` failure
  - median `20.0s`
- goods draft save:
  - `47` requests
  - `1` failure
  - median `37.0s`
- service draft create:
  - `55` requests
  - `0` failures
  - median `21.0s`
- service draft save:
  - `52` requests
  - `2` failures
  - median `36.0s`

Observed failure shape:
- failures were `OperationalError` responses spread across:
  - goods detail seed fetch
  - goods lookup seed fetch
  - goods draft create
  - goods draft save
  - service detail seed fetch
  - service draft save

Interpretation:
- the duplicate-check fast path is correct and worth keeping, but it did not remove the dominant higher-tier bottleneck
- under this isolated `100-user` write tier, the local stack hit a broader concurrency ceiling:
  - Django development server
  - local SQLite-style write contention characteristics
- because failures appeared across both read seeding and write mutation routes, this rerun is better treated as an infrastructure-constrained stress result than as a clean application-only comparison

Purchase phase status after this rerun:
- `purchase duplicate-check redundancy`: `reduced`
- `purchase isolated 100-user write correctness on local stack`: `failed because of OperationalError`
- `purchase isolated 100-user write latency on local stack`: `not acceptable`
- `purchase next meaningful step`: `repeat this tier on a production-like Postgres + WSGI/ASGI stack, or keep local work focused on lower-tier code-path optimization only`

## Phase 1B Follow-up Result: Purchase Draft Write 100-User / 2-Minute Rerun On Corrected Pooled Local Stack

Command executed:

```bash
cd Finacc
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true

locust -f perf/locust/locustfile.py --headless \
  --users 100 \
  --spawn-rate 12 \
  --run-time 2m \
  --tags purchase-draft-write \
  --host http://127.0.0.1:8004 \
  --csv perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth \
  --html perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html
```

Artifacts:
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats.csv)
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_stats_history.csv)
- [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth.html)

Aggregated result:
- `1657` requests
- `2` failures
- failure rate `0.12%`
- average `6244 ms`
- median `6900 ms`
- p95 `10000 ms`
- p99 `11000 ms`
- max `11840 ms`
- throughput `13.88 req/s`

Key per-endpoint result:
- `purchase/invoices [draft create]`: `210` requests, `0` failures, avg `6863 ms`, median `7300 ms`
- `purchase/invoices [draft save]`: `197` requests, `0` failures, avg `7753 ms`, median `8000 ms`
- `purchase/service-invoices [draft create]`: `213` requests, `0` failures, avg `7403 ms`, median `7700 ms`
- `purchase/service-invoices [draft save]`: `198` requests, `0` failures, avg `8062 ms`, median `8400 ms`
- `purchase/service-detail [seed]`: `228` requests, `2` failures, avg `6535 ms`, median `7100 ms`

Failure detail:
- both failures came from:
  - `GET purchase/service-detail [seed]`
- Locust classified them as:
  - `Purchase detail seed fetch returned invalid JSON`
- no broad purchase draft create/save correctness break reproduced on the corrected pooled stack

Interpretation:
- this rerun is materially healthier than the earlier local isolated `100-user` write result that collapsed under connection exhaustion
- the dominant old problem was indeed local stack pressure
- however, purchase is still not fully closed at this tier because the service-detail seed path remains slightly fragile under saturation
- the remaining issue is narrow and service-specific, not a general purchase draft mutation failure

Purchase phase status after this rerun:
- `purchase isolated 100-user write correctness on corrected pooled local stack`: `mostly passed with 2 narrow seed failures`
- `purchase isolated 100-user write latency on corrected pooled local stack`: `heavy but usable for continued investigation`
- `purchase next hotspot`: `service invoice detail retrieve path under high concurrent draft pressure`

Root-cause confirmation after log review on `2026-08-03`:
- the dominant failure was not SQLite and not a generic serializer crash
- the local Postgres instance is configured with `max_connections=100`
- the stressed run emitted repeated:
  - `FATAL: sorry, too many clients already`
- a smaller secondary signal also appeared:
  - `deadlock detected`
- this means the isolated `100-user` purchase write tier is currently constrained first by database connection capacity, then by transactional contention under saturation

Defensive follow-up hardening applied after the log review:
- `errorlogger/drf_exception_handler.py`
  - the DRF exception handler no longer re-resolves `request.user` when that property itself raises `OperationalError`
  - this prevents overload-time error handling from triggering another avoidable database lookup attempt
- `errorlogger/tests.py`
  - added focused regression coverage for the overload path

Focused regression command:

```bash
cd Finacc
source venv/bin/activate
python manage.py test errorlogger.tests.DrfExceptionHandlerTests purchase.tests.PurchaseDuplicateSupplierInvoiceTests purchase.tests.PurchaseInvoiceRetrieveContextTests --keepdb
```

Focused regression result:
- `Ran 4 tests`
- `OK`

| Reports with active writes | Yes | Medium-Strong | Dedicated report-write mixed smoke now exists and passed; heavier tiers still remain |

## Phase 1D Follow-up Result: AP Aging Vendor-Scoped Optimization Validation

Executed on:
- `2026-08-02`

Code changes validated:
- `reports/services/payables.py`
  - AP aging now collects scoped vendor IDs first, hydrates full vendor masters only for vendors that actually contribute open balances or unapplied advances, and narrows last-payment lookups to the active vendor set.
- `reports/selectors/payables.py`
  - `all_last_payment_dates(...)` now accepts `vendor_ids` so settlement aggregation can be limited to the report scope.
- `reports/tests_payables.py`
  - added regression coverage to ensure AP aging summary still returns the correct vendor row and last-payment date when unrelated vendors have posted payments.

Correctness validation:

```bash
cd Finacc
./venv/bin/python manage.py test reports.tests_payables --keepdb
```

Result:
- `92/92` tests passed

Focused stress command:

```bash
cd Finacc
./venv/bin/locust -f perf/locust/locustfile.py --headless \
  -u 4 -r 1 -t 45s \
  --tags report-heavy \
  --html perf/locust/results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt.html \
  --csv perf/locust/results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt
```

Artifacts:
- [results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt_stats.csv)
- [results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt_stats_history.csv)
- [results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_smoke_4u_45s_2026_08_02_postapagingvendoropt.html)

Final aggregate:
- requests: `89`
- failures: `0`
- average: `125.69 ms`
- median: `96 ms`
- p95: `250 ms`
- p99: `300 ms`
- max: `297.11 ms`

Key endpoint results:
- `reports/payables/aging [get]`: `31` requests, `0` failures, avg `212.53 ms`, median `210 ms`, p95 `280 ms`, p99 `300 ms`, max `297.11 ms`
- `reports/payables/meta [get]`: `13` requests, `0` failures, avg `82.84 ms`, median `89 ms`, p95 `130 ms`
- `bank-reconciliation/meta [get]`: `20` requests, `0` failures, avg `66.28 ms`, median `68 ms`, p95 `89 ms`
- `bank-reconciliation/sessions [list]`: `17` requests, `0` failures, avg `85.64 ms`, median `88 ms`, p95 `120 ms`

Interpretation:
- the AP aging vendor-scoping change is correctness-safe and materially improves the hotspot under a direct report-heavy smoke workload
- the post-fix AP aging endpoint now stays in the low-hundreds-of-milliseconds band instead of the multi-second envelope seen in the earlier mixed report-write run
- this does not fully replace a heavier mixed-concurrency confirmation run, but it is a strong signal that the main bottleneck was excessive vendor/settlement scope inside AP aging itself

AP aging status after this slice:
- `AP aging correctness after optimization`: `passed`
- `payables report regression suite`: `passed`
- `focused report-heavy stress validation`: `passed`
- `next follow-up`: `rerun the broader report-write mixed tier to confirm the hotspot reduction persists under concurrent writes`

## Phase 1D Follow-up Result: Broad Report-Write Mixed Confirmation After AP Aging Optimization

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
./venv/bin/locust -f perf/locust/locustfile.py --headless \
  -u 20 -r 2 -t 2m \
  --tags report-write-mix \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt \
  --html perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt.html
```

Artifacts:
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt_stats.csv)
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt_stats_history.csv)
- [results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_write_mixed_20u_2m_2026_08_02_postapagingvendoropt.html)

Final aggregate:
- requests: `751`
- failures: `0`
- average: `370 ms`
- median: `130 ms`
- p95: `1100 ms`
- p99: `5100 ms`
- max: `8531 ms`

Key endpoint results:
- `reports/payables/aging [get]`: `234` requests, `0` failures, avg `530 ms`, median `240 ms`, p95 `1700 ms`, p99 `5900 ms`, max `8531 ms`
- `reports/payables/meta [get]`: `152` requests, `0` failures, avg `186 ms`, median `85 ms`, p95 `470 ms`, p99 `3300 ms`
- `bank-reconciliation/meta [get]`: `182` requests, `0` failures, avg `128 ms`, median `72 ms`, p95 `390 ms`, p99 `2100 ms`
- `bank-reconciliation/sessions [list]`: `143` requests, `0` failures, avg `253 ms`, median `98 ms`, p95 `870 ms`, p99 `2600 ms`

Comparison versus the previous clean mixed baseline:
- previous clean baseline artifact: `results_phase1_report_write_mixed_20u_2m_2026_08_02_postsalestrim`
- previous `reports/payables/aging [get]`: avg `1184.09 ms`, median `610 ms`, p95 `3600 ms`, p99 `4500 ms`, max `6410 ms`
- new `reports/payables/aging [get]`: avg `530 ms`, median `240 ms`, p95 `1700 ms`, p99 `5900 ms`, max `8531 ms`

Interpretation:
- the AP aging optimization materially improved the main report hotspot under the same concurrent write workload
- the improvement is strongest in average, median, and p95 latency
- the tail still has a small number of long outliers, so the hotspot is reduced rather than fully eliminated
- correctness remained stable across the entire mixed run with `0` failures

Phase 1D status after the broad confirmation:
- `reports under concurrent writes`: `passed`
- `AP aging hotspot reduction`: `passed`
- `remaining report concern`: `long-tail outliers on AP aging under mixed concurrency`

## Phase 1D Follow-up Result: AP Aging Selector Optimization At 50-User Report-Heavy Tier

Executed on:
- `2026-08-03`

Purpose:
- validate the first selector-side AP aging optimization under the heavier `report-heavy` profile
- measure whether removing correlated settlement subqueries reduces the largest purchase-report bottleneck
- keep the purchase reporting path stable before moving to other module stress passes

Code change verified:
- `VendorBillOpenItem` as-of settlement totals now use filtered aggregate `Sum(...)` instead of correlated `Subquery(...)`
- `VendorAdvanceBalance` adjusted totals now use filtered aggregate `Sum(...)` instead of correlated `Subquery(...)`
- focused AP aging regression slice stayed green after the selector cleanup

Focused regression validation:

```bash
cd Finacc && source venv/bin/activate && python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_report_supports_summary_and_invoice_views \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_overdue_only_excludes_current_vendor_and_invoice_rows \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_credit_limit_exceeded_filters_to_breached_vendors \
  reports.tests_payables.PayableReportAPITests.test_aging_bucket_placement_and_summary_not_paginated \
  --keepdb
```

Observed result:
- `4` tests run
- `0` failures

Artifacts:
- pre-optimization baseline:
  - [results_phase1_report_heavy_50u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_stats.csv)
- post-optimization rerun:
  - [results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt_stats.csv)
  - [results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt_stats_history.csv)
  - [results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_50u_2m_2026_08_03_post_ap_selector_opt.html)

Before versus after on `reports/payables/aging [get]`:
- pre-optimization: `183` requests, `0` failures, avg `13638.99 ms`, median `14000 ms`, p95 `18000 ms`, p99 `19000 ms`, max `19286.65 ms`
- post-optimization: `201` requests, `0` failures, avg `11093.26 ms`, median `14000 ms`, p95 `17000 ms`, p99 `18000 ms`, max `18582.93 ms`

Aggregated run comparison:
- pre-optimization: `1107` requests, `0` failures, avg `3255.75 ms`, median `1300 ms`, p95 `15000 ms`, p99 `18000 ms`
- post-optimization: `1323` requests, `0` failures, avg `2480.37 ms`, median `1100 ms`, p95 `15000 ms`, p99 `16000 ms`

Interpretation:
- the selector rewrite is correctness-safe and measurably faster at the exact same `50-user report-heavy` tier
- improvement is real but partial; AP aging remains the slowest purchase-report endpoint
- the main remaining gap is summary-view compute cost and long-tail latency under mixed reporting pressure, not query correctness

Phase 1D follow-up status:
- `AP aging selector optimization`: `passed`
- `AP aging correctness after selector rewrite`: `passed`
- `remaining purchase reporting bottleneck`: `AP aging summary workload at higher concurrency`

## Phase 1D Follow-up Result: AP Aging Summary Cleanup And Ordered Vendor Streaming

Executed on:
- `2026-08-03`

Purpose:
- reduce the remaining summary-view AP aging overhead without changing aging semantics
- remove redundant summary-only lookups and avoid extra Python sorting work inside each vendor bucket
- verify whether these smaller, safer changes materially improve the `20 users / 1 minute` `report-heavy` tier

Code changes verified:
- summary AP aging now skips the wasted early `last_payment` lookup and fetches it only once after the relevant vendor set is known
- summary open-item rows are now ordered in SQL by `vendor_id`, effective due date, bill date, and row id
- summary AP aging no longer re-sorts each vendor’s invoice list in Python after the selector already returns rows in the correct order

Focused regression validation:

```bash
cd Finacc && source venv/bin/activate && python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_report_supports_summary_and_invoice_views \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_overdue_only_excludes_current_vendor_and_invoice_rows \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_credit_limit_exceeded_filters_to_breached_vendors \
  reports.tests_payables.PayableReportAPITests.test_aging_bucket_placement_and_summary_not_paginated \
  --keepdb
```

Observed result:
- `4` tests run
- `0` failures

Direct builder timing check:
- before SQL ordering cleanup: summary builder elapsed about `0.195 s`
- after SQL ordering cleanup: summary builder elapsed about `0.111 s`

Artifacts:
- summary-cleanup baseline:
  - [results_phase1_report_heavy_20u_1m_2026_08_03_summary_cleanup.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_20u_1m_2026_08_03_summary_cleanup.html)
- ordered-stream rerun:
  - [results_phase1_report_heavy_20u_1m_2026_08_03_summary_ordered.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_20u_1m_2026_08_03_summary_ordered.html)

Comparison on `reports/payables/aging [get]`:
- summary-cleanup run: `54` requests, `0` failures, avg `3682 ms`, median `3900 ms`, p95 `6900 ms`, max `7274 ms`
- ordered-stream rerun: `64` requests, `0` failures, avg `2813 ms`, median `2900 ms`, p95 `4900 ms`, max `5488 ms`

Aggregated run comparison:
- summary-cleanup run: `386` requests, `0` failures, avg `1148 ms`, median `670 ms`
- ordered-stream rerun: `364` requests, `0` failures, avg `909 ms`, median `500 ms`

Interpretation:
- the summary-specific cleanup is correctness-safe and materially faster on the same short concurrent report-heavy slice
- AP aging summary is no longer in the earlier `3.7s-3.9s` band for this tier and now holds around the `2.8s-2.9s` range
- the remaining bottleneck is the summary-mode FIFO credit allocation and bucket accumulation itself, not row ordering or duplicate lookups

Phase 1D follow-up status after summary cleanup:
- `AP aging summary lookup cleanup`: `passed`
- `AP aging ordered vendor streaming`: `passed`
- `remaining purchase reporting bottleneck`: `summary FIFO credit allocation and bucket folding`

## Phase 1D Follow-up Result: AP Aging Summary Direct Accumulator

Executed on:
- `2026-08-03`

Purpose:
- remove the last major summary-only Python overhead in AP aging by avoiding copied allocated-row dict construction
- preserve the same FIFO credit behavior while folding vendor bucket totals in a single pass
- confirm that the summary path can move from multi-second averages into a much stronger steady-state band

Code changes verified:
- summary AP aging no longer routes through `_allocate_vendor_credits(...)` when invoice detail rows are not needed
- summary mode now applies FIFO credit and accumulates `current`, `1-30`, `31-60`, `61-90`, `90+`, and overdue totals directly in one pass
- invoice view still uses the existing detailed allocation path, so invoice-level behavior remains unchanged

Focused regression validation:

```bash
cd Finacc && source venv/bin/activate && python manage.py test \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_report_supports_summary_and_invoice_views \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_overdue_only_excludes_current_vendor_and_invoice_rows \
  reports.tests_payables.PayableReportAPITests.test_ap_aging_credit_limit_exceeded_filters_to_breached_vendors \
  reports.tests_payables.PayableReportAPITests.test_aging_bucket_placement_and_summary_not_paginated \
  --keepdb
```

Observed result:
- `4` tests run
- `0` failures

Direct builder timing check:
- after ordered-stream cleanup: summary builder elapsed about `0.111 s`
- after direct accumulator: summary builder elapsed about `0.066 s`

Artifacts:
- ordered-stream baseline:
  - [results_phase1_report_heavy_20u_1m_2026_08_03_summary_ordered.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_20u_1m_2026_08_03_summary_ordered.html)
- direct-accumulator rerun:
  - [results_phase1_report_heavy_20u_1m_2026_08_03_summary_accumulator.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_report_heavy_20u_1m_2026_08_03_summary_accumulator.html)

Three-step comparison on `reports/payables/aging [get]`:
- summary-cleanup run: `54` requests, `0` failures, avg `3682.74 ms`, median `3900 ms`, p95 `6900 ms`, p99 `7300 ms`, max `7274.96 ms`
- ordered-stream run: `64` requests, `0` failures, avg `2813.94 ms`, median `2900 ms`, p95 `4900 ms`, p99 `5500 ms`, max `5488.47 ms`
- direct-accumulator run: `71` requests, `0` failures, avg `649.30 ms`, median `280 ms`, p95 `3800 ms`, p99 `4000 ms`, max `3999.54 ms`

Aggregated run comparison:
- summary-cleanup run: `381` requests, `0` failures, avg `1156.49 ms`, median `690 ms`, p95 `4800 ms`, p99 `6600 ms`
- ordered-stream run: `364` requests, `0` failures, avg `909.69 ms`, median `500 ms`, p95 `3700 ms`, p99 `4900 ms`
- direct-accumulator run: `474` requests, `0` failures, avg `233.04 ms`, median `110 ms`, p95 `540 ms`, p99 `3600 ms`

Interpretation:
- this is the strongest AP aging summary gain so far and moves the endpoint into a much healthier steady-state band
- average and median latency are now dramatically lower than the earlier summary passes
- the remaining concern is no longer ordinary summary compute cost; it is the occasional long-tail spike still visible in p95 and p99 on the local stack

Phase 1D follow-up status after direct accumulator:
- `AP aging summary direct accumulator`: `passed`
- `AP aging summary correctness after accumulator rewrite`: `passed`
- `remaining purchase reporting concern`: `tail latency spikes under local concurrent report-heavy load`

## Phase 1E Follow-up Result: Subscriptions Correctness and Catalog Efficiency Hardening

Executed on:
- `2026-08-02`

Purpose:
- harden the subscriptions module after the earlier admin-plan-catalog pass
- close the remaining failing subscription cases so the module can move to a cleaner high-confidence state
- verify that subscription plan switches, feature gating, and quota/block-reason snapshots stay in sync

## Phase 1D Follow-up Result: Receivables Reports 20-User / 2-Minute Stress On August 3, 2026

Executed on:
- `2026-08-03`

Purpose:
- close the Phase 1 reporting coverage gap where payables had active Locust stress coverage but receivables did not
- validate that customer outstanding, receivable aging, open items, and collections-history behave cleanly under concurrent load
- establish a real AR reporting baseline before considering any broader payables/receivables combined stress tier

Harness change added before the run:
- `Finacc/perf/locust/locustfile.py`
- new receivables report tasks added for:
  - `reports/receivables/customer-outstanding [get]`
  - `reports/receivables/aging [summary]`
  - `reports/receivables/aging [invoice]`
  - `reports/receivables/open-items [get]`
  - `reports/receivables/collections-history [get]`

Smoke validation:

```bash
source Finacc/venv/bin/activate
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 4 --spawn-rate 2 --run-time 45s \
  --tags receivables-reports \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_receivables_reports_smoke_4u_45s_2026_08_03 \
  --html Finacc/perf/locust/results_phase1_receivables_reports_smoke_4u_45s_2026_08_03.html
```

Smoke result:
- requests: `97`
- failures: `0`
- aggregate average: `51 ms`
- aggregate median: `43 ms`
- max: `271 ms`

Main stress command:

```bash
source Finacc/venv/bin/activate
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 2m \
  --tags receivables-reports \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_receivables_reports_20u_2m_2026_08_03 \
  --html Finacc/perf/locust/results_phase1_receivables_reports_20u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_receivables_reports_smoke_4u_45s_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_smoke_4u_45s_2026_08_03_stats.csv)
- [results_phase1_receivables_reports_smoke_4u_45s_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_smoke_4u_45s_2026_08_03.html)
- [results_phase1_receivables_reports_20u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_20u_2m_2026_08_03_stats.csv)
- [results_phase1_receivables_reports_20u_2m_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_20u_2m_2026_08_03_stats_history.csv)
- [results_phase1_receivables_reports_20u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_20u_2m_2026_08_03.html)

Observed result from `results_phase1_receivables_reports_20u_2m_2026_08_03_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1204 | 0 | `40 ms` | `68 ms` | `140 ms` | `41 ms` |
| `reports/receivables/customer-outstanding [get]` | 321 | 0 | `43 ms` | `65 ms` | `90 ms` | `44 ms` |
| `reports/receivables/aging [summary]` | 373 | 0 | `43 ms` | `62 ms` | `100 ms` | `44 ms` |
| `reports/receivables/aging [invoice]` | 170 | 0 | `46 ms` | `85 ms` | `120 ms` | `49 ms` |
| `reports/receivables/open-items [get]` | 154 | 0 | `25 ms` | `40 ms` | `66 ms` | `27 ms` |
| `reports/receivables/collections-history [get]` | 146 | 0 | `18 ms` | `27 ms` | `69 ms` | `19 ms` |
| `auth/login` | 20 | 0 | `140 ms` | `170 ms` | `170 ms` | `146 ms` |
| `auth/me` | 20 | 0 | `22 ms` | `28 ms` | `28 ms` | `22 ms` |

Interpretation:
- receivables reports are correctness-clean and comfortably fast at the `20-user / 2-minute` tier
- AR does not currently show the same obvious report-family hotspot that AP aging showed before its selector and summary-path optimization passes
- the heaviest receivables endpoint in this run was still light:
  - `reports/receivables/aging [invoice]` averaged only `49 ms`
- this closes the earlier gap where receivables had backend routes and product usage but no direct Locust evidence

Cross-module read:
- purchase transactions remain in the stronger band after the earlier fresh-document and pooled-Gunicorn reruns:
  - `purchase mixed 100-user` correctness clean
  - `purchase draft-write 100-user` correctness clean
- payables remains the heavier report family under stress
- receivables is now validated as materially lighter and already healthy at the current working tier

Phase 1D status after this addition:
- `purchase transaction stress`: `already strong from prior Phase 1 reruns`
- `payables report stress`: `covered and optimized`
- `receivables report stress`: `now covered and passed`
- `remaining reporting next step`: `combined payables + receivables escalation or a higher-tier receivables run if SaaS overlap simulation is needed`

## Phase 1D Follow-up Result: Combined Payables + Receivables Report Stress 50-User / 2-Minute On August 3, 2026

Executed on:
- `2026-08-03`

Purpose:
- validate AP and AR report families together at a heavier concurrent reporting tier
- confirm whether receivables remains stable when mixed with the still-heavier payables aging workload
- produce a cleaner operational-report baseline before switching away from the payables/receivables area

Harness change added before the run:
- `Finacc/perf/locust/locustfile.py`
- shared Locust tag added:
  - `ap-ar-reports`
- this targets:
  - `reports/payables/meta [get]`
  - `reports/payables/aging [get]`
  - `reports/receivables/customer-outstanding [get]`
  - `reports/receivables/aging [summary]`
  - `reports/receivables/aging [invoice]`
  - `reports/receivables/open-items [get]`
  - `reports/receivables/collections-history [get]`

Command:

```bash
source Finacc/venv/bin/activate
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 8 --run-time 2m \
  --tags ap-ar-reports \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_ap_ar_reports_50u_2m_2026_08_03 \
  --html Finacc/perf/locust/results_phase1_ap_ar_reports_50u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_ap_ar_reports_50u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_ap_ar_reports_50u_2m_2026_08_03_stats.csv)
- [results_phase1_ap_ar_reports_50u_2m_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_ap_ar_reports_50u_2m_2026_08_03_stats_history.csv)
- [results_phase1_ap_ar_reports_50u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_ap_ar_reports_50u_2m_2026_08_03.html)

Observed result:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 2749 | 0 | `63 ms` | `1100 ms` | `2300 ms` | `212 ms` |
| `reports/payables/aging [get]` | 663 | 0 | `210 ms` | `1900 ms` | `2800 ms` | `439 ms` |
| `reports/payables/meta [get]` | 410 | 0 | `53 ms` | `970 ms` | `1700 ms` | `165 ms` |
| `reports/receivables/customer-outstanding [get]` | 477 | 0 | `46 ms` | `950 ms` | `1600 ms` | `147 ms` |
| `reports/receivables/aging [summary]` | 427 | 0 | `46 ms` | `1000 ms` | `1900 ms` | `161 ms` |
| `reports/receivables/aging [invoice]` | 246 | 0 | `50 ms` | `530 ms` | `1700 ms` | `139 ms` |
| `reports/receivables/open-items [get]` | 205 | 0 | `25 ms` | `790 ms` | `1800 ms` | `113 ms` |
| `reports/receivables/collections-history [get]` | 221 | 0 | `17 ms` | `260 ms` | `1200 ms` | `69 ms` |
| `auth/login` | 50 | 0 | `190 ms` | `280 ms` | `360 ms` | `199 ms` |
| `auth/me` | 50 | 0 | `44 ms` | `87 ms` | `100 ms` | `47 ms` |

Interpretation:
- the combined AP + AR operational-report family is correctness-clean at the `50-user / 2-minute` tier
- payables aging remains the dominant operational-report hotspot
- receivables does not collapse when mixed with AP:
  - it stays materially lighter than AP aging
  - its medians remain in the `17 ms` to `50 ms` band across the AR endpoints
- the tail expands under the heavier combined tier, but the expansion is still controlled and failure-free

Cross-family conclusion:
- `purchase transactions`: strong from earlier high-tier reruns
- `payables reports`: stable, but still the slowest operational report family
- `receivables reports`: now covered both in isolated and combined stress and remain healthy
- `AP + AR together`: passed

Phase 1D status after the combined pass:
- `combined payables + receivables stress`: `passed`
- `dominant operational reporting hotspot`: `reports/payables/aging [get]`
- `receivables under mixed reporting pressure`: `healthy`
- `next best step`: `switch to the next business module stress area or raise AP aging alone if we want deeper hotspot reduction`

Code changes applied:
- [subscriptions/services.py](/Users/ansh/finacc-angular/finacc-django/Finacc/subscriptions/services.py)
  - removed the unsafe fast-path in `ensure_active_subscription(...)` that could return a stale in-memory subscription after a plan switch
  - made plan change and cancel flows keep the account-side cached subscription reference aligned with the latest subscription object
  - optimized internal plan catalog serialization so healthy plans reuse prefetched limits rather than doing per-plan refresh churn during admin catalog reads
  - tightened `ensure_plan_limit_catalog(...)` so it only touches the database when a plan is actually missing catalog rows or has mismatched limit metadata
- [subscriptions/tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/subscriptions/tests.py)
  - added a regression test guarding against admin internal plan catalog query explosion
  - updated stale fixtures that previously depended on the self-normalizing default `starter` plan for disabled-feature and capped-entity scenarios
  - moved those assertions onto dedicated non-default plans so feature-lock and quota-limit behavior is still covered meaningfully

Behavioral findings:
- the default `starter` plan now intentionally normalizes:
  - core module feature flags to enabled
  - legacy entity cap values such as `1` and `10` back to the default `20`
- several older subscription tests were still expecting the pre-normalization behavior, so those were fixture-drift failures rather than fresh production defects
- the real correctness defect in this slice was stale subscription-state reuse after plan change, which is now corrected

Validation commands executed:

```bash
cd Finacc
./venv/bin/python manage.py test subscriptions.tests.SubscriptionPlanAdminApiTests --keepdb
./venv/bin/python manage.py test subscriptions.tests.SubscriptionServiceTests.test_create_entity_limit_error_exposes_contract_fields subscriptions.tests.SubscriptionServiceTests.test_get_all_plan_limits_returns_catalog_defaults subscriptions.tests.SubscriptionServiceTests.test_subscription_snapshot_exposes_feature_flags subscriptions.tests.SubscriptionAccountAdminApiTests.test_staff_plan_change_keeps_snapshot_and_current_subscription_metadata_in_sync --keepdb
./venv/bin/python manage.py test subscriptions.tests.SubscriptionServiceTests.test_subscription_snapshot_exposes_status_and_limit_block_reasons subscriptions.tests.SubscriptionServiceTests.test_subscription_snapshot_exposes_feature_summary_for_disabled_module subscriptions.tests.SubscriptionServiceTests.test_assert_entity_access_blocks_disabled_feature --keepdb
./venv/bin/python manage.py test subscriptions.tests --keepdb
```

Results:
- targeted admin plan tests: `10/10` passed
- first failing-cluster rerun: `4/4` passed
- second failing-cluster rerun: `3/3` passed
- full subscriptions suite: `64/64` passed

Targeted shell verification:
- internal plan catalog benchmark after the fix: `2 queries` for `7 plans`
- plan-change sync check after account refresh: active subscription correctly resolved the new plan code rather than falling back to the prior `starter` plan

Interpretation:
- the subscriptions module is materially stronger now on both correctness and efficiency
- admin plan catalog reads no longer pay the earlier per-plan refresh/catalog-mutation penalty
- subscription snapshots, feature flags, limit block reasons, and plan changes are now validated against current intended starter-plan behavior
- this is a high-signal cleanup because it removed one real state bug and converted the remaining red tests into accurate fixtures aligned with the current product contract

Subscriptions status after this slice:
- `subscription admin plan catalog efficiency`: `passed`
- `subscription plan-change state sync`: `passed`
- `subscription feature gating correctness`: `passed`
- `subscription quota and block-reason correctness`: `passed`
- `subscription regression suite`: `passed`
- `confidence signal`: `high`

## Recommended Next Execution Slice

Current reality after the latest execution work:

- voucher mixed escalation at `50 users` is already executed and correctness-stable
- report-write mixed confirmation is already executed and correctness-stable
- dedicated financial report peak stress for Trial Balance and Ledger Summary is now executed at `50 users / 15m`
- the main open gap is no longer task availability, but module-wise sequencing and hotspot reduction

Recommended next run order:

1. Purchase higher-tier write escalation
2. Sales higher-tier write escalation
3. Voucher hotspot reduction rerun
4. Financial report tail-latency investigation rerun
5. Multi-tab stale document conflict expansion

What each slice should prove:

1. Purchase higher-tier write escalation
- confirm purchase goods and service draft-save, confirm, post, and note-create paths stay correctness-clean beyond the current `20-user` clean baseline
- measure whether the known purchase lookup and draft-save tail spikes stay acceptable when we raise concurrency again

2. Sales higher-tier write escalation
- push real sales draft create/save, confirm/post, and mixed lookup overlap above the earlier strong smoke tier
- identify whether sales reaches voucher-like mutation latency sooner than purchase or remains healthier

3. Voucher hotspot reduction rerun
- keep the same `voucher-mixed` correctness profile
- focus on receipt draft/create/save and payment draft-save latency after any optimization work

4. Financial report tail-latency investigation rerun
- keep Trial Balance and Ledger Summary functionally covered
- verify whether export/grouped endpoints can bring `p95/p99` down from the current `2.1s / 3.6s` peak baseline

5. Multi-tab stale document conflict expansion
- extend stale-state overlap beyond current approval conflict coverage
- validate edit/save/post collisions on the same transactional document family

Phase-level recommendation:

- treat `purchase` as the next execution module because it already has the strongest clean mixed-write baseline and is the best candidate for a controlled escalation
- treat `sales` as the next module after purchase so we keep parity with the same write-stress pattern
- keep `financial reports` and `vouchers` in a hotspot-reduction loop rather than calling them fully closed at peak scale

## Phase 1B Follow-up Result: Purchase Mixed Stress Escalation at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_stats.csv:1)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_stats_history.csv:1)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02.html:1)

Final aggregate:
- requests: `1443`
- failures: `8`
- error rate: `0.55%`
- average: `2961 ms`
- median: `2700 ms`
- p95: `6600 ms`
- p99: `9000 ms`
- max: `10901 ms`

Key endpoint results:
- `purchase/purchase-invoices/lookup [list]`: `171` requests, `0` failures, avg `3068 ms`, median `3100 ms`, p95 `4300 ms`, p99 `4800 ms`
- `purchase/purchase-service-invoices/lookup [list]`: `95` requests, `0` failures, avg `3232 ms`, median `3100 ms`, p95 `4600 ms`, p99 `5000 ms`
- `purchase/invoices [draft save]`: `42` requests, `3` failures, avg `7403 ms`, median `7800 ms`, p95 `9900 ms`, max `10901 ms`
- `purchase/service-invoices [draft save]`: `46` requests, `5` failures, avg `7703 ms`, median `7500 ms`, p95 `10000 ms`, max `10438 ms`
- `purchase/invoices [draft create]`: `45` requests, `0` failures, avg `4285 ms`, median `4200 ms`
- `purchase/service-invoices [draft create]`: `47` requests, `0` failures, avg `4378 ms`, median `4200 ms`
- `purchase/invoices [post]`: `45` requests, `0` failures, avg `2694 ms`, median `2600 ms`
- `purchase/service-invoices [post]`: `37` requests, `0` failures, avg `2923 ms`, median `2600 ms`

Error signature:
- `PATCH purchase/invoices [draft save]`: `400`
  - `"Posted purchase invoice cannot be edited. Create a purchase return, credit note, debit note, or reversal document instead."`
- `PATCH purchase/service-invoices [draft save]`: `400`
  - `"Posted purchase invoice cannot be edited. Create a purchase return, credit note, debit note, or reversal document instead."`

Observations:
- this tier is not a clean correctness pass like the `20-user` purchase mixed baseline
- the failure pattern is concentrated in goods and service draft-save flows trying to save a document after it has already been posted
- that makes this a high-signal stale-state or overlap problem, not a random infrastructure error
- even where requests succeed, purchase write latency becomes heavy very quickly at this tier
- both lookup lists and draft mutation paths move into multi-second medians under the `50-user` overlap profile

Interpretation:
- purchase remains functionally strong at moderate concurrency, but the `50-user` mixed mutation tier is currently `partial/fail` rather than a pass
- the first blocker is concurrency control around draft-save versus post state transitions
- the second blocker is raw latency on draft-save, create, post, and lookup overlap
- before pushing purchase further, we should decide whether this exact failure is:
  - an expected stale-document rejection that the Locust task should avoid, or
  - a real product concurrency gap that needs better client/server guardrails

Purchase phase status after this run:
- `purchase correctness under mixed write pressure at 20 users`: `passed`
- `purchase mixed mutation at 50 users`: `not clean`
- `purchase primary failure mode`: `draft-save against already-posted document`
- `purchase primary scale hotspot`: `draft save and lookup overlap latency`
- `purchase next gap`: `stale-state handling and higher-tier write latency`

## Phase 1B Follow-up Result: Purchase Draft Write Isolated at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=false \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags purchase-draft-write \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_purchase_draft_isolated_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_purchase_draft_isolated_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_purchase_draft_isolated_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draft_isolated_50u_2m_2026_08_02_stats.csv:1)
- [results_phase1_purchase_draft_isolated_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draft_isolated_50u_2m_2026_08_02_stats_history.csv:1)
- [results_phase1_purchase_draft_isolated_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draft_isolated_50u_2m_2026_08_02.html:1)

Final aggregate:
- requests: `925`
- failures: `0`
- error rate: `0.00%`
- average: `5481.72 ms`
- median: `4900 ms`
- p95: `11000 ms`
- p99: `15000 ms`
- max: `16952.28 ms`
- throughput: `7.76 req/s`

Key endpoint results:
- `purchase/invoices [draft create]`: `116` requests, `0` failures, avg `5823.93 ms`, median `5600 ms`, p95 `8400 ms`, p99 `9000 ms`, max `9178.85 ms`
- `purchase/invoices [draft save]`: `98` requests, `0` failures, avg `10475.26 ms`, median `9900 ms`, p95 `15000 ms`, p99 `16000 ms`, max `16273.16 ms`
- `purchase/service-invoices [draft create]`: `138` requests, `0` failures, avg `5881.91 ms`, median `5600 ms`, p95 `8600 ms`, p99 `9000 ms`, max `9146.91 ms`
- `purchase/service-invoices [draft save]`: `124` requests, `0` failures, avg `10402.05 ms`, median `9900 ms`, p95 `15000 ms`, p99 `15000 ms`, max `16952.28 ms`
- `purchase/goods-lookup [seed-id]`: `46` requests, `0` failures, avg `1762.35 ms`, median `1700 ms`
- `purchase/service-lookup [seed-id]`: `48` requests, `0` failures, avg `1803.04 ms`, median `1900 ms`

Observations:
- isolating the draft lane removed the `posted invoice cannot be edited` failures entirely
- that confirms the earlier `purchase-mixed` failures were driven by overlap between draft-save and lifecycle/post tasks, not by purchase settings or malformed draft-write payloads
- even without overlap failures, purchase draft-write latency is still materially high at this tier
- create latency settled in the `~5.8s` average range for both goods and service purchase drafts
- save latency settled in the `~10.4s` average range with `15s` p95 tails for both goods and service purchase drafts

Interpretation:
- `purchase-draft-write` at `50 users / 2 minutes` is a `functional pass`
- `purchase-mixed` at the same user tier remains a `concurrency-behavior partial/fail`
- purchase therefore has two separate scale truths we should keep distinct:
  - clean isolated draft creation and save still works correctly
  - mixed real-world overlap between draft-edit and posting needs stronger stale-state handling and client/server coordination
- the next purchase work item should prioritize write-path latency reduction on draft create/save before moving to heavier tiers such as `100+` concurrent transactional actors

Purchase phase status after isolated rerun:
- `purchase isolated draft correctness at 50 users`: `passed`
- `purchase isolated draft performance at 50 users`: `heavy tail / needs improvement`
- `purchase mixed overlap correctness at 50 users`: `not yet clean`
- `purchase highest-confidence conclusion`: `correctness is intact in isolation, but overlap handling and write latency are the current scale blockers`

## Phase 1C Result: Sales Draft Write Isolated at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=false \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags sales-draft-write \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_sales_draft_isolated_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_sales_draft_isolated_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_sales_draft_isolated_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_draft_isolated_50u_2m_2026_08_02_stats.csv:1)
- [results_phase1_sales_draft_isolated_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_draft_isolated_50u_2m_2026_08_02_stats_history.csv:1)
- [results_phase1_sales_draft_isolated_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_draft_isolated_50u_2m_2026_08_02.html:1)

Final aggregate:
- requests: `1753`
- failures: `0`
- error rate: `0.00%`
- average: `2688.49 ms`
- median: `2500 ms`
- p95: `4900 ms`
- p99: `6200 ms`
- max: `6817.82 ms`
- throughput: `14.69 req/s`

Key endpoint results:
- `sales/invoices [draft create]`: `254` requests, `0` failures, avg `2691.33 ms`, median `2600 ms`, p95 `3900 ms`, p99 `4100 ms`, max `4254.39 ms`
- `sales/invoices [draft save]`: `240` requests, `0` failures, avg `4409.39 ms`, median `4300 ms`, p95 `6000 ms`, p99 `6300 ms`, max `6817.82 ms`
- `sales/service-invoices [draft create]`: `266` requests, `0` failures, avg `2700.01 ms`, median `2600 ms`, p95 `3800 ms`, p99 `4400 ms`, max `4496.35 ms`
- `sales/service-invoices [draft save]`: `259` requests, `0` failures, avg `4451.38 ms`, median `4400 ms`, p95 `5900 ms`, p99 `6600 ms`, max `6807.68 ms`
- `sales/goods-lookup [seed-id]`: `50` requests, `0` failures, avg `1095.01 ms`, median `1300 ms`
- `sales/service-lookup [seed-id]`: `50` requests, `0` failures, avg `1091.87 ms`, median `1200 ms`

Observations:
- isolated sales draft creation and save remained fully clean at `50 users / 2 minutes`
- sales write latency is materially lower than purchase at the same tier across both goods and service flows
- sales draft create stabilized in the `~2.7s` average band
- sales draft save stabilized in the `~4.4s` average band
- tail latency exists, but it is substantially tighter than the purchase isolated draft lane

Interpretation:
- `sales-draft-write` at `50 users / 2 minutes` is a `functional pass`
- sales currently shows a meaningfully stronger isolated write profile than purchase
- because isolated sales is clean and relatively efficient, the next useful sales step is the mixed overlap profile rather than another isolated escalation
- purchase remains the heavier transactional bottleneck between the two modules

Sales phase status after isolated run:
- `sales isolated draft correctness at 50 users`: `passed`
- `sales isolated draft performance at 50 users`: `good relative to purchase`
- `sales next stress gap`: `mixed read/write overlap behavior at the same tier`
- `cross-module conclusion`: `sales isolated draft writes are currently healthier than purchase isolated draft writes`

## Phase 1C Follow-up Result: Sales Mixed Stress Escalation at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_sales_mixed_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02_stats.csv:1)
- [results_phase1_sales_mixed_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02_stats_history.csv:1)
- [results_phase1_sales_mixed_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02.html:1)

Final aggregate:
- requests: `1459`
- failures: `0`
- error rate: `0.00%`
- average: `2340.60 ms`
- median: `1800 ms`
- p95: `4500 ms`
- p99: `22000 ms`
- max: `54869.47 ms`
- throughput: `12.23 req/s`

Key endpoint results:
- `sales/invoices/lookup [list]`: `301` requests, `0` failures, avg `2714.25 ms`, median `2700 ms`, p95 `3700 ms`, p99 `4000 ms`, max `4493.14 ms`
- `sales/service-invoices/lookup [list]`: `133` requests, `0` failures, avg `2709.06 ms`, median `2600 ms`, p95 `3900 ms`, p99 `4800 ms`, max `4801.05 ms`
- `sales/invoices [draft create]`: `28` requests, `0` failures, avg `1153.47 ms`, median `1100 ms`, p95 `1500 ms`, max `1492.81 ms`
- `sales/invoices [draft save]`: `28` requests, `0` failures, avg `2034.98 ms`, median `1900 ms`, p95 `3200 ms`, max `3265.60 ms`
- `sales/service-invoices [draft create]`: `35` requests, `0` failures, avg `1276.72 ms`, median `1300 ms`, p95 `1700 ms`, max `1777.08 ms`
- `sales/service-invoices [draft save]`: `34` requests, `0` failures, avg `2118.94 ms`, median `2000 ms`, p95 `3100 ms`, max `3337.90 ms`
- `sales/invoices [confirm]`: `59` requests, `0` failures, avg `1091.51 ms`, median `970 ms`
- `sales/invoices [post]`: `58` requests, `0` failures, avg `1886.51 ms`, median `1900 ms`
- `sales/invoices [reverse]`: `57` requests, `0` failures, avg `1220.12 ms`, median `1200 ms`
- `sales/settings [get]`: `188` requests, `0` failures, avg `3533.92 ms`, median `3500 ms`, p95 `4900 ms`, max `5689.80 ms`
- `sales/settings [patch]`: `39` requests, `0` failures, avg `20563.19 ms`, median `16000 ms`, p95 `49000 ms`, p99 `55000 ms`, max `54869.47 ms`

Observations:
- the full mixed sales profile stayed functionally clean at `50 users / 2 minutes`
- unlike purchase mixed stress, sales did not surface stale-state correctness failures in this tier
- sales lookup, cross-mode navigation, draft create/save, confirm, post, and reverse all stayed inside a relatively controlled latency band
- the dominant hotspot is `sales/settings [patch]`, which dramatically inflates aggregate tail latency
- sales settings reads are also heavier than the core invoice write paths, but still far below the patch hotspot

Interpretation:
- `sales-mixed` at `50 users / 2 minutes` is a `clean functional pass`
- the primary sales scale issue at this tier is not document correctness, but configuration mutation latency
- compared with purchase, sales currently has the stronger mixed transactional profile
- purchase remains the first operational module that needs overlap hardening and write-path optimization
- sales should next focus on reducing settings-patch cost if we want cleaner high-percentile behavior at larger scales

Sales phase status after mixed run:
- `sales isolated draft correctness at 50 users`: `passed`
- `sales mixed read/write correctness at 50 users`: `passed`
- `sales primary hotspot at 50 users`: `sales settings patch latency`
- `cross-module conclusion`: `sales is currently more scale-stable than purchase under the same 50-user stress tier`

## Phase 1D Result: Voucher Mixed Stress at 50 Users

Executed on:
- `2026-08-02`

Command executed:

```bash
cd Finacc
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true \
Finacc/venv/bin/locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags voucher-mixed \
  --host http://127.0.0.1:8000 \
  --csv Finacc/perf/locust/results_phase1_voucher_mixed_50u_2m_2026_08_02 \
  --html Finacc/perf/locust/results_phase1_voucher_mixed_50u_2m_2026_08_02.html
```

Artifacts:
- [results_phase1_voucher_mixed_50u_2m_2026_08_02_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_50u_2m_2026_08_02_stats.csv:1)
- [results_phase1_voucher_mixed_50u_2m_2026_08_02_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_50u_2m_2026_08_02_stats_history.csv:1)
- [results_phase1_voucher_mixed_50u_2m_2026_08_02.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_50u_2m_2026_08_02.html:1)

Final aggregate:
- requests: `3241`
- failures: `0`
- error rate: `0.00%`
- average: `1280.52 ms`
- median: `1200 ms`
- p95: `2300 ms`
- p99: `3200 ms`
- max: `5199.60 ms`
- throughput: `27.15 req/s`

Key payment-voucher results:
- `payments/payment-vouchers [approval draft create]`: `113` requests, `0` failures, avg `1418.59 ms`, median `1400 ms`, p95 `2000 ms`, max `3059.51 ms`
- `payments/payment-vouchers [approve]`: `113` requests, `0` failures, avg `1126.35 ms`, median `1100 ms`
- `payments/payment-vouchers [draft create]`: `91` requests, `0` failures, avg `1396.61 ms`, median `1400 ms`, p95 `2100 ms`, max `2516.13 ms`
- `payments/payment-vouchers [draft save]`: `91` requests, `0` failures, avg `2003.96 ms`, median `2000 ms`, p95 `2900 ms`, max `3229.38 ms`
- `payments/payment-vouchers [post]`: `89` requests, `0` failures, avg `1365.90 ms`, median `1300 ms`
- `payments/payment-vouchers [stale approve repeat]`: `102` requests, `0` failures, avg `1164.59 ms`, median `1100 ms`
- `payments/payment-vouchers [stale seed create]`: `109` requests, `0` failures, avg `1498.79 ms`, median `1500 ms`

Key receipt-voucher results:
- `receipts/receipt-vouchers [approval draft create]`: `107` requests, `0` failures, avg `1981.31 ms`, median `1800 ms`, p95 `3400 ms`, max `5199.60 ms`
- `receipts/receipt-vouchers [approve]`: `105` requests, `0` failures, avg `1077.15 ms`, median `1000 ms`
- `receipts/receipt-vouchers [draft create]`: `92` requests, `0` failures, avg `1950.12 ms`, median `1800 ms`, p95 `3100 ms`, max `3529.83 ms`
- `receipts/receipt-vouchers [draft save]`: `90` requests, `0` failures, avg `2245.34 ms`, median `2100 ms`, p95 `3100 ms`, max `3773.62 ms`
- `receipts/receipt-vouchers [post]`: `87` requests, `0` failures, avg `1595.29 ms`, median `1500 ms`
- `receipts/receipt-vouchers [stale approve repeat]`: `112` requests, `0` failures, avg `1074.29 ms`, median `1000 ms`
- `receipts/receipt-vouchers [stale seed create]`: `117` requests, `0` failures, avg `1882.86 ms`, median `1700 ms`, p95 `3200 ms`, max `4109.93 ms`

Observations:
- the voucher mixed profile stayed completely clean at `50 users / 2 minutes`
- approval, reject, submit, post, draft-save, and stale-conflict validation all executed without correctness failures
- both payment and receipt voucher paths showed much tighter percentiles than purchase and sales
- receipt voucher operations are slightly heavier than payment voucher operations, but still within a healthy band
- no single voucher endpoint showed the kind of severe long-tail behavior seen in `sales/settings [patch]`

Interpretation:
- `voucher-mixed` at `50 users / 2 minutes` is a `clean functional and performance pass`
- vouchers are currently the strongest operational module in this Phase 1 stress set
- stale-conflict paths for payment and receipt are holding up well under concurrency, which increases confidence in the approval-state guardrails
- compared with purchase and sales:
  - vouchers are more stable than purchase on mixed concurrency correctness
  - vouchers are more latency-efficient than sales mixed traffic

Voucher phase status after mixed run:
- `voucher mixed correctness at 50 users`: `passed`
- `voucher mixed performance at 50 users`: `strong`
- `payment vs receipt comparison`: `receipt is slightly heavier, but both are healthy`
- `cross-module conclusion`: `vouchers are currently the strongest high-concurrency module in the operational stress matrix`

## 2026-08-02 Purchase Bottleneck Remediation

Area:
- purchase draft update/save path

Change:
- collapsed duplicate header persistence inside `PurchaseInvoiceService.update_with_lines()`
- header edits now persist together with recomputed totals in one final `save(update_fields=...)` call
- removed the earlier unconditional full `instance.save()` that was happening before totals/TDS/tax-summary recomputation

Code:
- [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:2629)
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py:251)

Regression verification:
- command:
  ```bash
  source venv/bin/activate && python manage.py test purchase.tests.PurchaseInvoiceConcurrencyHardeningTests --verbosity 2
  ```
- result: `7/7` passing

Focused smoke rerun:
- name: `phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite`
- command:
  ```bash
  source .venv/bin/activate && \
  FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=false \
  locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 45s \
    --tags purchase-write \
    --csv results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite \
    --html results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite.html
  ```
- artifacts:
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite_stats.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite_stats_history.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postsinglewrite.html)

Immediate outcome:
- zero failures in focused purchase write smoke
- goods draft create/save stayed in a healthy low band:
  - create p95 about `160 ms`
  - save p95 about `180 ms`
- service draft create/save is still the heavier purchase lane:
  - create p95 about `580 ms`
  - save p95 about `330 ms`

Next purchase bottleneck to attack:
- service-invoice draft create/save path remains the main purchase latency hotspot after this duplicate-write removal

### 2026-08-02 Follow-up Purchase Optimization

Change:
- reused the already-fetched purchase policy inside purchase draft create/update flows when applying TDS and GST-TDS
- removed repeated `PurchaseSettingsService.get_policy(...)` lookups within the same purchase mutation cycle

Code:
- [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:453)
- [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:1994)
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py:251)

Regression verification:
- command:
  ```bash
  source venv/bin/activate && python manage.py test purchase.tests.PurchaseInvoiceConcurrencyHardeningTests --verbosity 2
  ```
- result: `7/7` passing

Focused smoke rerun:
- name: `phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse`
- command:
  ```bash
  source .venv/bin/activate && \
  FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=false \
  locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 45s \
    --tags purchase-write \
    --csv results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse \
    --html results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse.html
  ```
- artifacts:
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse_stats.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse_stats_history.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postpolicyreuse.html)

Observed effect versus the immediately previous focused smoke:
- purchase service draft create improved from roughly `p95 580 ms` to roughly `p95 160 ms`
- purchase service draft save improved from roughly `p95 330 ms` to roughly `p95 320 ms`, with a much better median around `150 ms`
- goods draft traffic remained healthy with no correctness regressions
- run stayed at `0` failures

Updated purchase hotspot view:
- largest remaining purchase latency is now the draft save tail, especially service save max/p95 spikes
- the service create bottleneck is no longer the dominant outlier after policy reuse

### 2026-08-02 Purchase Line Persistence Optimization

Change:
- optimized `PurchaseInvoiceService.upsert_lines()` to reduce update-path round trips
- reused already-loaded existing lines
- bulk-deleted dropped lines
- removed the extra aggregate query for max line number
- bulk-created new line rows instead of inserting them one by one

Code:
- [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py:1940)

Regression verification:
- command:
  ```bash
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    purchase.tests.PurchaseApiSmokeTests \
    --keepdb --verbosity 2
  ```
- result: `17/17` passing

Focused smoke rerun:
- name: `phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk`
- command:
  ```bash
  source .venv/bin/activate && \
  FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=false \
  locust -f locustfile.py --headless --users 2 --spawn-rate 1 --run-time 45s \
    --tags purchase-write \
    --csv results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk \
    --html results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk.html
  ```
- artifacts:
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk_stats.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk_stats_history.csv)
  - [results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_smoke_2u_45s_2026_08_02_postlinebulk.html)

Observed effect versus the immediately previous focused smoke:
- purchase service draft save tail improved:
  - p95 moved from about `320 ms` to about `250 ms`
  - max moved from about `319 ms` to about `249 ms`
- purchase service draft create did not improve in this short smoke:
  - p95 moved from about `160 ms` to about `170 ms`
  - median moved from about `110 ms` to about `140 ms`
- goods draft save/create stayed functionally clean
- run stayed at `0` failures

Interpretation:
- this optimization improved the worst-case draft-save tail, which was the target hotspot
- it did not improve the full purchase write profile uniformly in this short 45-second run
- keep the change because it reduced update-path round trips and improved the service save tail without correctness regressions

Updated purchase status after three remediation passes:
- duplicate header write removed: `done`
- repeated policy lookup reuse: `done`
- line update/create round-trip reduction: `done`
- purchase write correctness under focused smoke: `clean`
- remaining purchase performance risk: `moderate`, now mostly broader draft mutation cost rather than a single severe outlier

### 2026-08-02 Purchase Lookup/Nav Index Optimization

Change:
- added targeted composite indexes for the purchase lookup and purchase navigation sort paths
- reduced avoidable frontend total-count work for lookup consumers that only need a bounded option list

Code:
- [purchase_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_core.py)
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py)
- [0051_purchaseinvoiceheader_ix_pur_lookup_sort_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0051_purchaseinvoiceheader_ix_pur_lookup_sort_and_more.py)

Migration and verification:
- commands:
  ```bash
  source venv/bin/activate && python manage.py makemigrations purchase
  source venv/bin/activate && python manage.py migrate purchase
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseInvoiceLookupViewTests \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    --keepdb --verbosity 2
  ```
- result: migration applied cleanly and `10/10` targeted purchase tests passed

Focused purchase-modern rerun:
- name: `phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex`
- command:
  ```bash
  source venv/bin/activate && \
  locust -f perf/locust/locustfile.py --headless --users 20 --spawn-rate 5 --run-time 2m \
    --tags purchase-modern \
    --csv perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex \
    --html perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex.html
  ```
- artifacts:
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex_stats.csv)
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex_stats_history.csv)
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupindex.html)

Observed effect:
- run stayed at `0` failures
- aggregate stayed in a very healthy band:
  - avg about `79.8 ms`
  - p95 about `130 ms`
  - p99 about `230 ms`
- purchase lookup/list endpoints improved sharply:
  - goods lookup list avg about `85 ms`, p95 about `120 ms`, p99 about `190 ms`
  - service lookup list avg about `96 ms`, p95 about `130 ms`, p99 about `180 ms`
- purchase cross-mode nav endpoints also stayed healthy:
  - goods to service avg about `61 ms`, p95 about `86 ms`
  - service to goods avg about `58 ms`, p95 about `84 ms`

Comparison versus the earlier broader mixed pass:
- `phase1_purchase_mixed_20u_2m_2026_08_02_postsingleflight` had:
  - aggregate avg about `134 ms`, p95 about `340 ms`, p99 about `1100 ms`
  - goods lookup list avg about `156 ms`, p95 about `360 ms`, p99 about `2300 ms`
  - service lookup list avg about `137 ms`, p95 about `330 ms`, p99 about `1000 ms`
- this confirms the lookup/nav read slice is materially healthier after the index work

Interpretation:
- this closes a major purchase read-path bottleneck
- it does **not** by itself prove that the full purchase mixed/write workload is solved
- purchase-wide confidence improved for lookup and navigation behavior, while broader draft mutation stress still needs a fresh mixed rerun on the current indexed codebase

### 2026-08-02 Purchase Mixed Rerun After Lookup Indexing

Rerun:
- name: `phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex`
- command:
  ```bash
  source venv/bin/activate && \
  locust -f perf/locust/locustfile.py --headless --users 20 --spawn-rate 5 --run-time 2m \
    --tags purchase-mixed \
    --csv perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex \
    --html perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex.html
  ```
- artifacts:
  - [results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex_stats.csv)
  - [results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex_stats_history.csv)
  - [results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_02_postlookupindex.html)

Outcome:
- `0` failures
- aggregate:
  - avg about `96 ms`
  - median about `76 ms`
  - p95 about `240 ms`
  - p99 about `420 ms`
  - max about `677 ms`

Key purchase endpoints:
- goods lookup list:
  - avg about `98 ms`
  - p95 about `230 ms`
  - p99 about `470 ms`
- service lookup list:
  - avg about `128 ms`
  - p95 about `310 ms`
  - p99 about `630 ms`
- goods to service cross-mode nav:
  - avg about `72 ms`
  - p95 about `230 ms`
  - p99 about `350 ms`
- service to goods cross-mode nav:
  - avg about `70 ms`
  - p95 about `170 ms`
  - p99 about `330 ms`

Comparison versus the previous purchase mixed rerun on the same 20-user profile:
- previous reference: `phase1_purchase_mixed_20u_2m_2026_08_02_postsingleflight`
- aggregate improved from about:
  - avg `134 ms` -> `96 ms`
  - p95 `340 ms` -> `240 ms`
  - p99 `1100 ms` -> `420 ms`
- goods lookup list improved from about:
  - avg `156 ms` -> `98 ms`
  - p95 `360 ms` -> `230 ms`
  - p99 `2300 ms` -> `470 ms`
- service lookup list improved from about:
  - avg `137 ms` -> `128 ms`
  - p95 `330 ms` -> `310 ms`
  - p99 `1000 ms` -> `630 ms`

Interpretation:
- purchase is now substantially healthier under the broader 20-user mixed stress profile
- the largest remaining purchase tail is still the service lookup list family
- there is no active evidence here of a purchase failure-mode bottleneck at 20 concurrent users on the current code
- if we want the next hard confidence step for purchase, the right escalation is either:
  - a `purchase-mixed` 50-user rerun on the current indexed build, or
  - a focused service-lookup optimization pass if we want to shave the remaining tail before scaling up again

### 2026-08-02 Purchase Mixed 50-User Scale Check

Escalation:
- name: `phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex`
- command:
  ```bash
  source venv/bin/activate && \
  locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 10 --run-time 2m \
    --tags purchase-mixed \
    --csv perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex \
    --html perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex.html
  ```
- artifacts:
  - [results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex_stats.csv)
  - [results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex_stats_history.csv)
  - [results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postlookupindex.html)

Outcome:
- `0` request failures
- aggregate latency is not SaaS-healthy at this scale:
  - avg about `1859 ms`
  - median about `1700 ms`
  - p95 about `3700 ms`
  - p99 about `4500 ms`
  - max about `5384 ms`

Hot endpoints under 50-user stress:
- purchase invoice lookup list:
  - avg about `2295 ms`
  - p95 about `3900 ms`
  - p99 about `4700 ms`
  - max about `5244 ms`
- purchase service invoice lookup list:
  - avg about `2535 ms`
  - p95 about `4100 ms`
  - p99 about `4800 ms`
  - max about `5384 ms`
- goods to service cross-mode nav:
  - avg about `1280 ms`
  - p95 about `2300 ms`
  - p99 about `2800 ms`
- service to goods cross-mode nav:
  - avg about `1262 ms`
  - p95 about `2400 ms`
  - p99 about `2800 ms`

Important readout:
- correctness held, but capacity did not
- this means the current purchase implementation is functionally stable yet still materially under-provisioned or under-optimized for a 50-concurrent-user mixed burst
- the lookup index work helped the 20-user module profile, but it did not close the higher-concurrency purchase scale bottleneck

Purchase stress conclusion after this check:
- `20-user mixed`: healthy enough for current phase confidence
- `50-user mixed`: bottleneck still open
- strongest remaining bottlenecks:
  - login and auth/me are already slow at this scale and contribute to the floor
  - purchase lookup list endpoints are the largest purchase-specific tail
  - cross-mode navigation also degrades materially under the same pressure

Next purchase-focused action:
- do not move purchase to "scale-closed" yet
- next work should target:
  - purchase lookup list query shape and payload size
  - auth/session warm-path overhead in Locust journeys
  - database plan review for the purchase lookup and nav endpoints under 50-user concurrency

### 2026-08-02 Purchase Lookup Payload Flattening

Change:
- removed full model serialization from the purchase lookup dropdown endpoints
- purchase lookup now returns flattened rows from `values(...)` plus lightweight Python label mapping
- kept the response contract unchanged while reducing model-instantiation and serializer overhead

Code:
- [purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py)
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py)

Regression verification:
- command:
  ```bash
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseInvoiceLookupViewTests \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    --keepdb --verbosity 2
  ```
- result: `10/10` passing

Focused confirmation runs:
- warm-ish rerun artifacts:
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten_stats.csv)
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten_stats_history.csv)
  - [results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_2m_2026_08_02_postlookupflatten.html)
- confirmation rerun artifacts:
  - [results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun_stats.csv)
  - [results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun_stats_history.csv)
  - [results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_modern_20u_90s_2026_08_02_postlookupflatten_rerun.html)

Observed effect:
- first 20-user rerun showed a noisy auth/login floor, so it was not used as the main comparison signal
- the confirmation rerun was much cleaner and showed the flattened purchase lookups in a healthier band:
  - purchase invoice lookup list avg about `143 ms`, median about `78 ms`, p95 about `490 ms`
  - purchase service lookup list avg about `130 ms`, median about `86 ms`, p95 about `400 ms`
  - goods-to-service cross-mode nav avg about `104 ms`, median about `60 ms`
  - service-to-goods cross-mode nav avg about `115 ms`, median about `63 ms`
- run stayed at `0` failures

Interpretation:
- the flattening change is safe and worth keeping
- it improves the purchase lookup/list hot path itself
- it does **not** close the 50-user purchase scale issue, but it reduces one of the remaining purchase-specific per-request costs before deeper query-plan work

### 2026-08-02 Purchase Subentity-Aware Index Tightening

Change:
- added subentity-aware purchase header indexes so the hot lookup and navigation scans key directly on `entity + entityfinid + subentity`
- new indexes:
  - `ix_pur_lookup_sub` on `(entity, entityfinid, subentity, doc_no, id)`
  - `ix_pur_nav_sub` on `(entity, entityfinid, subentity, doc_type, status, doc_no, id)`

Code and migration:
- [purchase_core.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/models/purchase_core.py)
- [0052_purchaseinvoiceheader_ix_pur_lookup_sub_and_more.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/migrations/0052_purchaseinvoiceheader_ix_pur_lookup_sub_and_more.py)

Validation:
- command:
  ```bash
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseInvoiceLookupViewTests \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    --keepdb --verbosity 2
  ```
- result: `10/10` passing
- post-migration `EXPLAIN` showed:
  - purchase lookup moved onto `ix_pur_lookup_sub`
  - purchase cross-mode nav moved onto `ix_pur_nav_sub`

### 2026-08-02 Purchase Mixed Rerun After Subentity Indexing

Artifacts:
- [results_phase1_purchase_mixed_20u_90s_2026_08_02_postsubentityidx_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_90s_2026_08_02_postsubentityidx_stats.csv)
- [results_phase1_purchase_mixed_20u_90s_2026_08_02_postsubentityidx.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_90s_2026_08_02_postsubentityidx.html)
- [results_phase1_purchase_mixed_50u_90s_2026_08_02_postsubentityidx_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_90s_2026_08_02_postsubentityidx_stats.csv)
- [results_phase1_purchase_mixed_50u_90s_2026_08_02_postsubentityidx.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_90s_2026_08_02_postsubentityidx.html)

20-user rerun:
- `0` failures
- aggregate avg `2792 ms`, median `2700 ms`, p95 `5600 ms`, p99 `6400 ms`, max `7585 ms`
- purchase goods lookup list avg `3048 ms`, median `3300 ms`
- purchase service lookup list avg `3142 ms`, median `3400 ms`
- goods->service cross-mode nav avg `1965 ms`
- service->goods cross-mode nav avg `1885 ms`

50-user rerun:
- `0` failures
- aggregate avg `2784 ms`, median `2700 ms`, p95 `5600 ms`, p99 `6500 ms`, max `7724 ms`
- purchase goods lookup list avg `2941 ms`, median `3100 ms`
- purchase service lookup list avg `3209 ms`, median `3200 ms`
- goods->service cross-mode nav avg `1842 ms`
- service->goods cross-mode nav avg `1862 ms`

Interpretation:
- this confirms the DB plan is now structurally correct for tenant + FY + subentity scoping
- however, purchase mixed flows are still multi-second under concurrent end-to-end stress
- so the remaining bottleneck is no longer "wrong purchase index shape"
- next purchase bottlenecks to target are:
  - lookup response volume and default list size
  - `total_count` cost on lookup pages
  - auth/session warm-path overhead in mixed user journeys
  - frontend request churn during purchase screen boot and navigation

### 2026-08-02 Purchase Lookup Default No-Count Path

Change:
- purchase lookup endpoints now treat `total_count` as opt-in instead of default
- callers must pass `include_total=true` to force a full count
- default lookup behavior now fetches `limit + 1` rows and computes `has_more` without a count query

Code:
- [purchase_invoice.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/views/purchase_invoice.py)
- [tests.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/tests.py)

Validation:
- command:
  ```bash
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseInvoiceLookupViewTests \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    --keepdb --verbosity 2
  ```
- result: `11/11` passing

Stress rerun:
- artifacts:
  - [results_phase1_purchase_mixed_50u_90s_2026_08_02_postdefaultnocount_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_90s_2026_08_02_postdefaultnocount_stats.csv)
  - [results_phase1_purchase_mixed_50u_90s_2026_08_02_postdefaultnocount.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_90s_2026_08_02_postdefaultnocount.html)

Observed effect at `50 users / 90s / purchase-mixed`:
- `0` failures
- aggregate avg `137 ms`, median `56 ms`, p95 `620 ms`, p99 `1700 ms`, max `2517 ms`
- purchase invoice lookup list avg `126 ms`, median `58 ms`, p95 `310 ms`, p99 `1700 ms`
- purchase service invoice lookup list avg `114 ms`, median `57 ms`, p95 `280 ms`, p99 `1500 ms`
- goods->service cross-mode nav avg `82 ms`, median `51 ms`
- service->goods cross-mode nav avg `67 ms`, median `49 ms`
- login/auth are also now in a much healthier band in the same run

Interpretation:
- the default lookup `count()` path was the dominant purchase bottleneck in this mixed stress profile
- purchase is now materially healthier under 50-user concurrent mixed load
- this change should be kept
- next purchase follow-up, if we want even tighter confidence, is:
  - verify UI callers that truly need counts pass `include_total=true`
  - mirror the same no-count default on sales lookup after purchase sign-off

Follow-up purchase write-path tightening:
- date: `2026-08-02`
- validation findings:
  - purchase cross-mode navigation query plan is now healthy on local data
  - PostgreSQL uses:
    - `ix_pur_lookup_sub` on `purchase_purchaseinvoiceheader`
    - `ix_pur_line_hdr_pbeh` on `purchase_purchaseinvoiceline`
  - that means the remaining purchase work is no longer a broad lookup or cross-mode scan problem
  - the next realistic purchase hotspot is write-path overhead during draft create/save

Code improvement:
- batched product master fetch inside purchase line structural validation so multi-line create/save no longer performs one product query per line

## Phase 1B Follow-up Result: Purchase Draft Write Rerun After Batched Line and Charge Persistence

Command:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 10 --run-time 90s \
  --tags purchase-draft-write \
  --csv perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist \
  --html perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist.html
```

Artifacts:
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist_stats.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist_stats_history.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postbatchpersist.html)

Code changes validated before rerun:
- batched line updates with `bulk_update` inside `PurchaseInvoiceService.upsert_lines`
- batched charge inserts and updates with `bulk_create` and `bulk_update` inside `PurchaseInvoiceService.upsert_charges`
- grouped charge deletes into a single queryset delete instead of per-row deletes

Regression validation:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
source venv/bin/activate
python manage.py test \
  purchase.tests.PurchaseApiSmokeTests \
  purchase.tests.PurchaseInvoiceLookupViewTests \
  purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
  purchase.tests_invoice_contract_alignment \
  --keepdb --verbosity 2
```

Result:
- `36/36` purchase regression tests passed after the batching change

Observed result at 50 users for 90 seconds:
- zero failures across `425` requests
- purchase goods draft create improved into roughly the `13s-15s` median band
- purchase service draft create improved into roughly the `14s-16s` median band
- purchase goods draft save remained the dominant bottleneck at roughly `25s` median
- purchase service draft save remained the dominant bottleneck at roughly `26s` median
- seed detail reads stayed around the `7s-7.6s` median band
- aggregate median landed around `7s`, but purchase save tails still drove p95 and p99 up sharply

Interpretation:
- batched persistence did help purchase draft create latency
- the main purchase bottleneck is no longer per-row line or charge save overhead alone
- the next purchase hotspot is inside the deeper draft save orchestration after persistence:
  - duplicate supplier invoice validation
  - totals rebuild over database-fetched rows
  - TDS and GST-TDS recomputation
  - post-save summary and ledger sync side-effects

Purchase stress status after this rerun:
- correctness remains strong
- lookup and navigation performance are healthy
- create latency is improved but still not cheap at this user tier
- save latency is still too high for SaaS-grade comfort and remains the top purchase optimization target before moving on

## Phase 1B Follow-up Result: Purchase Draft Write Rerun After In-Memory Totals Reuse

Command:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 10 --run-time 90s \
  --tags purchase-draft-write \
  --csv perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse \
  --html perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse.html
```

Artifacts:
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse_stats.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse_stats_history.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_posttotalsreuse.html)

Code changes validated before rerun:
- `upsert_charges` now returns authoritative computed charge rows
- purchase create/update totals now reuse already-authoritative in-memory line and charge rows
- database readback for totals is now used only as fallback when lines or charges were not part of the payload

Regression validation:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
source venv/bin/activate
python manage.py test \
  purchase.tests.PurchaseApiSmokeTests \
  purchase.tests.PurchaseInvoiceLookupViewTests \
  purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
  purchase.tests_invoice_contract_alignment \
  --keepdb --verbosity 2
```

Result:
- `36/36` purchase regression tests passed after the totals reuse change

Observed result at 50 users for 90 seconds:
- zero failures across `1023` requests
- purchase goods draft create median settled around `4.2s`
- purchase service draft create median settled around `3.5s`
- purchase goods draft save median settled around `7.7s`
- purchase service draft save median settled around `6.4s`
- purchase goods detail reads settled around `2.2s`
- purchase service detail reads settled around `2.1s`
- aggregate median settled around `3.1s`

Comparison versus the previous purchase draft-write rerun:
- purchase create improved from roughly `13s-16s` down into the `3.5s-4.2s` band
- purchase save improved from roughly `25s-26s` down into the `6.4s-7.7s` band
- the purchase draft-write path moved from a major hotspot to a much healthier operating range at the same 50-user tier

Interpretation:
- the dominant purchase save bottleneck was not only persistence batching
- the extra database readback for totals after already-authoritative recompute was a major cost driver
- purchase draft create and save are now strong enough that the next purchase hotspot should be measured elsewhere before more surgery

Purchase stress status after this rerun:
- purchase lookup, navigation, create, and save are all now in a materially healthier state

## Phase 1B Follow-up Result: Purchase Draft Write Rerun After Draft Tax Summary Skip

Command:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 10 --run-time 90s \
  --tags purchase-draft-write \
  --csv perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip \
  --html perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip.html
```

Artifacts:
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip_stats.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip_stats_history.csv)
- [results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_50u_90s_2026_08_02_postdraftsummaryskip.html)

Code changes validated before rerun:
- purchase draft create and save now skip `rebuild_tax_summary(...)` while the document is still a plain draft
- confirmed and posted purchase documents still rebuild tax summary through the normal path
- explicit operational actions keep their own rebuild behavior intact

Regression validation:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
source venv/bin/activate
python manage.py test \
  purchase.tests.PurchaseApiSmokeTests \
  purchase.tests.PurchaseInvoiceLookupViewTests \
  purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
  purchase.tests_invoice_contract_alignment \
  --keepdb --verbosity 2
```

Result:
- `38/38` purchase regression tests passed after the draft tax summary skip change

Observed result at 50 users for 90 seconds:
- zero failures across `1338` requests
- purchase goods draft create median settled around `2.6s`
- purchase service draft create median settled around `2.7s`
- purchase goods draft save median settled around `4.8s`
- purchase service draft save median settled around `4.8s`
- purchase goods detail reads settled around `1.8s`
- purchase service detail reads settled around `1.8s`
- aggregate median settled around `2.3s`

Comparison versus the previous totals-reuse rerun:
- purchase goods draft create improved from `4.2s` down to `2.6s`
- purchase service draft create improved from `3.5s` down to `2.7s`
- purchase goods draft save improved from `7.7s` down to `4.8s`
- purchase service draft save improved from `6.4s` down to `4.8s`
- aggregate median improved from `3.1s` down to `2.3s`

Interpretation:
- draft tax summary rebuild was still a material cost center on the purchase write path
- purchase draft saves are no longer showing the earlier deep orchestration penalty seen at the same 50-user tier
- the remaining purchase hotspot is now more likely to come from higher-scale contention, posting-side effects, or mixed report overlap rather than ordinary draft-save plumbing

Purchase stress status after this rerun:
- purchase draft create and save are in a much healthier place for the current 50-user stress tier
- purchase remains zero-failure across the optimized isolated write run
- the next best purchase step is not more draft-save surgery first
- the next best purchase step is higher-scale pressure, posting stress, and mixed-load validation to find the new ceiling

## Phase 1B Follow-up Result: Purchase Mixed Stress 50-User Rerun After Purchase Draft Optimizations

Executed on:
- `2026-08-02`

Command executed:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip \
  --html perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip.html
```

Artifacts:
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip_stats.csv)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip_stats_history.csv)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_postdraftsummaryskip.html)

Final aggregate:
- requests: `1497`
- failures: `6`
- error rate: `0.40%`
- average: `2777 ms`
- median: `2300 ms`
- p95: `6700 ms`
- p99: `11000 ms`
- max: `12372 ms`

Key endpoint results:
- `purchase/purchase-invoices/lookup [list]`: `199` requests, `0` failures, avg `2280 ms`, median `2200 ms`, p95 `3800 ms`, p99 `4300 ms`
- `purchase/purchase-service-invoices/lookup [list]`: `107` requests, `0` failures, avg `2354 ms`, median `2300 ms`, p95 `3600 ms`, p99 `4000 ms`
- `purchase/invoices [draft create]`: `52` requests, `0` failures, avg `4732 ms`, median `4700 ms`
- `purchase/service-invoices [draft create]`: `48` requests, `0` failures, avg `4513 ms`, median `3900 ms`
- `purchase/invoices [draft save]`: `52` requests, `2` failures, avg `7953 ms`, median `8300 ms`, p95 `11000 ms`
- `purchase/service-invoices [draft save]`: `45` requests, `4` failures, avg `8204 ms`, median `8500 ms`, p95 `12000 ms`

Error signature:
- `PATCH purchase/invoices [draft save]`: `400`
  - `"Posted purchase invoice cannot be edited. Create a purchase return, credit note, debit note, or reversal document instead."`
- `PATCH purchase/service-invoices [draft save]`: `400`
  - `"Posted purchase invoice cannot be edited. Create a purchase return, credit note, debit note, or reversal document instead."`

Comparison versus the earlier 50-user purchase mixed run:
- aggregate error rate improved from `0.55%` down to `0.40%`
- aggregate median improved from `2700 ms` down to `2300 ms`
- lookup medians improved from roughly `3100 ms` down to `2200-2300 ms`
- draft-save failures did not disappear because the failure mode is still state overlap, not raw draft-save correctness
- draft-save medians are still much heavier in mixed overlap than in the isolated purchase draft-write run

Interpretation:
- the purchase draft-path optimizations materially improved the mixed profile, especially lookup and aggregate latency
- the remaining mixed-tier failure mode is still a product or test-orchestration stale-state race:
  - a draft is saved after another overlapping flow has already posted it
- purchase is no longer primarily blocked by avoidable draft totals or draft summary work
- purchase is now primarily blocked by:
  - stale draft-save versus post overlap under shared-doc mixed traffic
  - high mixed-tier latency once lookup, draft save, notes, confirm, and post all compete together

Purchase stress status after this rerun:
- `purchase isolated draft write at 50 users`: `clean after optimization`
- `purchase mixed overlap at 50 users`: `still partial`
- `purchase primary remaining defect class`: `stale-state save after post`
- `purchase primary remaining performance hotspot`: `mixed draft save under shared document overlap`
- `purchase next best work`: `separate shared-doc stale-state cases from pure throughput cases, then rerun with either per-user fresh docs or explicit stale-state expectations`

## Phase 1B Follow-up Result: Purchase Mixed Fresh-Document Smoke

Executed on:
- `2026-08-02`

Purpose:
- verify that the purchase mixed failure pattern was caused by shared seed document overlap rather than by ordinary purchase draft-save correctness

Command executed:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 20 --spawn-rate 4 --run-time 45s \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke \
  --html perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke.html
```

Artifacts:
- [results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke_stats.csv)
- [results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke_stats_history.csv)
- [results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_45s_2026_08_02_freshdocs_smoke.html)

Locust change validated in this phase:
- purchase mixed lifecycle and note tasks now create fresh purchase drafts per actor before confirm, post, and note mutation
- purchase mixed draft create/save already worked on fresh docs; now the confirm/post and note paths also avoid shared seed document collisions

Final aggregate:
- requests: `726`
- failures: `0`
- error rate: `0.00%`
- average: `405 ms`
- median: `250 ms`
- p95: `1200 ms`
- p99: `1900 ms`
- max: `2700 ms`

Key endpoint results:
- `purchase/invoices [draft create]`: `55` requests, `0` failures, avg `679 ms`, median `600 ms`
- `purchase/invoices [draft save]`: `16` requests, `0` failures, avg `940 ms`, median `560 ms`
- `purchase/service-invoices [draft create]`: `51` requests, `0` failures, avg `534 ms`, median `320 ms`
- `purchase/service-invoices [draft save]`: `21` requests, `0` failures, avg `1249 ms`, median `1300 ms`
- `purchase/purchase-invoices/lookup [list]`: `72` requests, `0` failures, avg `276 ms`, median `180 ms`
- `purchase/purchase-service-invoices/lookup [list]`: `42` requests, `0` failures, avg `303 ms`, median `220 ms`

Interpretation:
- this smoke strongly confirms that the earlier purchase mixed failures were dominated by shared-document stale-state collisions
- once each actor gets a fresh purchase header, the mixed purchase profile becomes clean again at the moderate tier
- the next meaningful purchase rerun should be a full-duration fresh-document mixed escalation, not more draft-save code surgery first

Purchase stress status after this smoke:
- `purchase mixed fresh-doc baseline`: `clean`
- `purchase stale overlap hypothesis`: `confirmed`
- `purchase next best step`: `rerun purchase mixed at higher scale with fresh-doc lifecycle and note paths`

## Phase 1B Follow-up Result: Purchase Mixed 50-User Rerun With Fresh Documents

Executed on:
- `2026-08-02`

Purpose:
- measure the real purchase mixed ceiling after removing shared-document stale collisions from lifecycle and note paths

Command executed:

```bash
cd /Users/ansh/finacc-angular/finacc-django/Finacc
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs \
  --html perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs.html
```

Artifacts:
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs_stats.csv)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs_stats_history.csv)
- [results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_freshdocs.html)

Final aggregate:
- requests: `534`
- failures: `0`
- error rate: `0.00%`
- average: `9322 ms`
- median: `8100 ms`
- p95: `22000 ms`
- p99: `41000 ms`
- max: `47451 ms`

Key endpoint results:
- `auth/login`: `50` requests, `0` failures, avg `9557 ms`, median `9500 ms`
- `auth/me`: `50` requests, `0` failures, avg `5830 ms`, median `5600 ms`
- `purchase/purchase-invoices/lookup [list]`: `55` requests, `0` failures, avg `5352 ms`, median `4600 ms`
- `purchase/purchase-service-invoices/lookup [list]`: `26` requests, `0` failures, avg `4839 ms`, median `4100 ms`
- `purchase/invoices [draft create]`: `33` requests, `0` failures, avg `11649 ms`, median `11000 ms`
- `purchase/service-invoices [draft create]`: `26` requests, `0` failures, avg `11330 ms`, median `11000 ms`
- `purchase/invoices [draft save]`: `5` requests, `0` failures, avg `20418 ms`, median `21000 ms`
- `purchase/service-invoices [draft save]`: `7` requests, `0` failures, avg `19692 ms`, median `22000 ms`
- `purchase/invoices [confirm]`: `25` requests, `0` failures, avg `24252 ms`, median `24000 ms`
- `purchase/service-invoices [confirm]`: `16` requests, `0` failures, avg `21620 ms`, median `20000 ms`

Interpretation:
- the fresh-document isolation worked from a correctness perspective:
  - the earlier stale-state failures disappeared
  - the mixed purchase run is now clean on functional outcomes at the same 50-user tier
- the dominant purchase bottleneck at this tier is now throughput and startup pressure, not stale-state logic
- the biggest observed pressure points are:
  - very slow `auth/login`
  - very slow `auth/me`
  - slow seed lookup and seed detail reads
  - downstream purchase create, save, confirm, and post timings inflated by that initial queueing and by heavier transactional overlap

What this means:
- purchase correctness under 50-user mixed load is now materially better than before
- purchase performance at 50-user mixed load is still not acceptable for SaaS-grade comfort in the current local setup
- the next optimization target should move one layer outward from purchase service code alone:
  - auth startup path
  - seed lookup and detail-read fanout
  - overall DB and request concurrency behavior under 50-user onboarding into the scenario

Purchase stress status after this rerun:
- `purchase mixed correctness at 50 users with fresh docs`: `passed`
- `purchase mixed latency at 50 users with fresh docs`: `still poor`

## Phase 1B Follow-up Result: Purchase Mixed 50-User Rerun After Dropdown and Entitlement Tightening

Purpose:
- verify whether the purchase mixed latency wall at `50 users` was still driven by upstream auth/bootstrap and shared dropdown overhead after:
  - tightening `financial/accounts/simple-v2` to only load serializer-needed fields
  - fixing subscription entitlement cache reads to honor current database state
  - removing default-plan feature auto-reenablement that was mutating intended backend configuration

Command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 5 --run-time 2m \
  --tags purchase-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_after_dropdown_opt \
  --html perf/locust/results_phase1_purchase_mixed_50u_2m_2026_08_02_after_dropdown_opt.html
```

Result:
- total requests: `976`
- failures: `0`
- aggregate average: `1842.23 ms`
- aggregate median: `1500 ms`
- aggregate p95: `4800 ms`
- aggregate p99: `7400 ms`

Key endpoint metrics:
- `auth/login`
  - average: `1909.01 ms`
  - median: `840 ms`
  - p95: `5300 ms`
- `auth/me`
  - average: `566.77 ms`
  - median: `820 ms`
  - p95: `940 ms`
- `purchase/purchase-invoices/lookup [list]`
  - average: `1980.01 ms`
  - median: `1400 ms`
  - p95: `7600 ms`
- `purchase/purchase-service-invoices/lookup [list]`
  - average: `1917.15 ms`
  - median: `1400 ms`
  - p95: `7400 ms`
- `purchase/invoices [draft create]`
  - average: `2210.61 ms`
  - median: `2300 ms`
  - p95: `2700 ms`
- `purchase/invoices [draft save]`
  - average: `4233.55 ms`
  - median: `4200 ms`
  - p95: `4900 ms`
- `purchase/service-invoices [draft create]`
  - average: `2213.82 ms`
  - median: `2200 ms`
  - p95: `2800 ms`
- `purchase/service-invoices [draft save]`
  - average: `4095.17 ms`
  - median: `4100 ms`
  - p95: `4800 ms`
- `purchase/invoices [confirm]`
  - average: `1566.15 ms`
  - median: `1600 ms`
  - p95: `1900 ms`
- `purchase/service-invoices [confirm]`
  - average: `1577.36 ms`
  - median: `1500 ms`
  - p95: `2000 ms`

Comparison versus the earlier `50-user` fresh-document rerun:
- aggregate median improved from `8100 ms` to `1500 ms`
- aggregate p95 improved from `22000 ms` to `4800 ms`
- `auth/login` median improved from `9500 ms` to `840 ms`
- `auth/me` median improved from `5600 ms` to `820 ms`
- purchase goods lookup median improved from `4600 ms` to `1400 ms`
- purchase service lookup median improved from `4100 ms` to `1400 ms`
- purchase goods draft create median improved from `11000 ms` to `2300 ms`
- purchase goods draft save median improved from `21000 ms` to `4200 ms`
- purchase service draft create median improved from `11000 ms` to `2200 ms`
- purchase service draft save median improved from `22000 ms` to `4100 ms`
- purchase goods confirm median improved from `24000 ms` to `1600 ms`
- purchase service confirm median improved from `20000 ms` to `1500 ms`

Interpretation:
- purchase mixed at `50 users` is now both correctness-clean and latency-credible on the current local stack
- this is the first `50-user` purchase mixed tier in Phase 1 that looks healthy enough to treat as a real module confidence upgrade rather than just a failure-investigation rerun
- the earlier severe slowdown was not primarily inherent to purchase draft persistence anymore; it was strongly amplified by upstream auth/bootstrap and shared dropdown/entitlement overhead

Status update:
- `purchase mixed correctness at 50 users with fresh docs`: `passed`
- `purchase mixed latency at 50 users after dropdown and entitlement tightening`: `passed`
- `purchase module stress confidence`: `materially upgraded`

Next best step:
- run the same mixed stress profile for sales at the same `50 users / 2 minutes` tier so sales and purchase are comparable on the same phase baseline
- `purchase stale-state overlap issue`: `neutralized in the stress harness`
- `purchase next main bottleneck`: `auth and seed-fetch saturation followed by heavy mutation latency under queued load`
- zero-failure behavior held at the same 50-user draft-write tier
- purchase is no longer the worst write-path performer in Phase 1
- file:
  - [purchase_invoice_service.py](/Users/ansh/finacc-angular/finacc-django/Finacc/purchase/services/purchase_invoice_service.py)

Validation:
- command:
  ```bash
  source venv/bin/activate && python manage.py test \
    purchase.tests.PurchaseApiSmokeTests \
    purchase.tests.PurchaseInvoiceLookupViewTests \
    purchase.tests.PurchaseInvoiceConcurrencyHardeningTests \
    purchase.tests_invoice_contract_alignment \
    --keepdb --verbosity 2
  ```
- result: `36/36` passing

Interpretation:
- purchase lookup and cross-mode DB access are in a good state after the earlier indexing and no-count fixes
- purchase write-path still needs dedicated concurrency stress follow-up, but the validation stage now does less avoidable DB chatter per invoice

## Phase 1A Follow-up Result: Sales Mixed 30-User Rerun After Current-Doc Batch Optimization

Purpose:
- validate whether batching sales settings current-document-number scope scans improves the `sales/settings` hotspot
- confirm the optimization is correctness-safe before a deeper settings payload refactor

Code change executed:
- `sales/services/sales_settings_service.py`
  - added `_numbered_doc_candidates_by_type_in_scope(...)`
  - added `get_current_doc_numbers_batch(...)`
  - preserved standalone `get_current_doc_no(...)` behavior for unit-test and non-batched callers
- `sales/views/sales_settings_views.py`
  - switched `_current_doc_numbers(...)` from three independent `get_current_doc_no(...)` calls to one batched helper call
- `sales/tests_api.py`
  - updated the settings payload API test to mock the new batch seam

Correctness validation:

```bash
source venv/bin/activate
python manage.py test \
  sales.tests_api.SalesSettingsApiTests \
  sales.tests.SalesInvoiceViewUnitTests.test_get_current_doc_no_falls_back_to_latest_doc_code_when_configured_preview_is_low \
  sales.tests.SalesComplianceRecoveryUnitTests.test_get_current_doc_no_falls_back_to_latest_doc_code_when_configured_preview_is_low \
  --keepdb --verbosity 2
```

Result:
- `6/6` targeted tests passed

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 30 --spawn-rate 5 --run-time 90s \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_doc_batch \
  --html perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_doc_batch.html
```

Observed result from `results_phase1_sales_mixed_30u_90s_2026_08_02_after_doc_batch_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 490 | 0 | `3100 ms` | `9400 ms` | `16000 ms` | `3960.97 ms` |
| `sales/settings [get]` | 64 | 0 | `5600 ms` | `8400 ms` | `9100 ms` | `5718.61 ms` |
| `sales/settings [patch]` | 18 | 0 | `12000 ms` | `19000 ms` | `19000 ms` | `11936.14 ms` |
| `sales/invoices/lookup [list]` | 78 | 0 | `6200 ms` | `10000 ms` | `11000 ms` | `6479.39 ms` |
| `sales/service-invoices/lookup [list]` | 33 | 0 | `5900 ms` | `9800 ms` | `10000 ms` | `6200.46 ms` |

What changed:
- the settings page remains correctness-stable and failure-free after the batching change
- repeated candidate scanning for invoice, credit note, and debit note is no longer duplicated within the settings payload

What did not materially improve:
- `sales/settings [get]` is still heavy at about `5.6 s` median
- `sales/settings [patch]` is still the dominant sales hotspot at about `12.0 s` median

Interpretation:
- document-number candidate rescans were real redundant work, but they were not the primary source of settings latency
- the remaining hotspot is more likely inside the rest of the sales settings payload assembly:
  - seller profile hydration
  - stock policy payload
  - choice catalog assembly
  - full expanded payload rebuild after `PATCH`
  - lock-period and override payload assembly

Status after this rerun:
- correctness: improved

## Phase 1A Follow-up Result: Sales Mixed 30-User Rerun After Settings Payload Fix

Purpose:
- validate the sales settings payload refactor under the same `30 users / 90 seconds` mixed sales profile
- confirm the seller-profile prefetch optimization is correctness-safe after the live regression fix

Regression observed during the first rerun:
- `sales/settings [get]` and `sales/settings [patch]` started returning `500`
- authenticated replay against `/api/sales/settings/?entity_id=10&entityfinid=8&subentity_id=8` reproduced the failure outside Locust
- Django raised `FieldDoesNotExist: EntityContact has no field named 'phoneoffice'`

Root cause:
- `sales/services/sales_settings_service.py`
  - `get_seller_profile(...)` was optimized with `Prefetch(...only(...))`
  - the contact-only field list accidentally included `phoneoffice`, which is not a real `EntityContact` field
- because the settings payload hydrates seller data on both `GET` and `PATCH`, both routes failed immediately

Fix executed:
- `sales/services/sales_settings_service.py`
  - removed the invalid `phoneoffice` field from the optimized contact prefetch
  - kept the narrower `only(...)` projection using valid contact fields only
- validated the fix with:

```bash
python3 -m py_compile Finacc/sales/services/sales_settings_service.py

source venv/bin/activate
python manage.py test \
  sales.tests_api.SalesSettingsApiTests \
  sales.tests_api.SalesChoicesServiceTests \
  --keepdb --verbosity 2
```

Result:
- compile check passed
- `6/6` targeted tests passed
- authenticated live `GET` and `PATCH` replays returned `200`

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true
export FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 30 --spawn-rate 5 --run-time 90s \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_fix \
  --html perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_fix.html
```

Observed result from `results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_fix_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 332 | 0 | `4900 ms` | `15000 ms` | `16000 ms` | `6433.92 ms` |
| `sales/settings [get]` | 30 | 0 | `6400 ms` | `9000 ms` | `11000 ms` | `6482.50 ms` |
| `sales/settings [patch]` | 14 | 0 | `9100 ms` | `11000 ms` | `11000 ms` | `8139.96 ms` |
| `sales/invoices/lookup [list]` | 48 | 0 | `13000 ms` | `15000 ms` | `16000 ms` | `13161.00 ms` |
| `sales/service-invoices/lookup [list]` | 26 | 0 | `14000 ms` | `16000 ms` | `17000 ms` | `13944.61 ms` |

What changed:
- the settings payload path is back to correctness-safe under mixed load
- the prefetch tightening no longer causes runtime model-field explosions
- `sales/settings [patch]` improved versus the earlier document-batch-only rerun

What still remains true:
- settings is still not the dominant latency source anymore; invoice/service lookup lists are now heavier in this 30-user shape
- the mixed sales profile is correct and stable, but still latency-heavy on lookup/list pages

Interpretation:
- the settings path is now safe enough to leave while we move the next optimization pass toward lookup/list endpoints
- the next best sales-side performance target is invoice/service lookup query cost, not settings correctness

Status after this rerun:
- correctness: restored
- sales settings regression: closed
- next performance target: `sales/invoices/lookup [list]` and `sales/service-invoices/lookup [list]`
- duplicate query work: reduced
- primary performance bottleneck: still unresolved

Next recommended optimization target:
- split the sales settings `PATCH` response from the full read payload, or cache/batch the remaining heavyweight payload builders before moving on to the next sales stress tier

## Phase 1A Follow-up Result: Sales Mixed 30-User Rerun After Lookup Ledger Prefetch

Purpose:
- reduce the new top sales mixed bottleneck on invoice lookup list endpoints
- remove per-row lookup serializer database hops caused by `customer.effective_accounting_name`

Root cause isolated:
- `sales/views/sales_invoice_views.py`
  - `SalesInvoiceLookupAPIView._base_queryset()` used `select_related("customer", "subentity")`
  - `SalesInvoiceLookupSerializer` reads `customer.effective_accounting_name`
- `financial/models.py`
  - `effective_accounting_name` resolves through `customer.ledger.name` when a ledger is linked
- result:
  - lookup rows were preloading `customer`, but not `customer__ledger`
  - each lookup row could trigger an extra ledger fetch while serializing the customer display name

Fix executed:
- `sales/views/sales_invoice_views.py`
  - added `customer__ledger` to the lookup queryset `select_related(...)`
  - added `customer__ledger_id` and `customer__ledger__name` to the `only(...)` field set
- `sales/tests.py`
  - added `test_lookup_queryset_selects_customer_related_ledger`

Correctness validation:

```bash
source venv/bin/activate
python manage.py test \
  sales.tests.SalesInvoiceViewUnitTests.test_list_queryset_selects_customer_related_ledger \
  sales.tests.SalesInvoiceViewUnitTests.test_lookup_queryset_selects_customer_related_ledger \
  --keepdb --verbosity 2
```

Result:
- `2/2` targeted tests passed

Stress command:

```bash
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 30 --spawn-rate 5 --run-time 90s \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_sales_lookup_prefetch \
  --html perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_sales_lookup_prefetch.html
```

Observed result from `results_phase1_sales_mixed_30u_90s_2026_08_02_after_sales_lookup_prefetch_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 494 | 0 | `3000 ms` | `7100 ms` | `8800 ms` | `3433.49 ms` |
| `sales/invoices/lookup [list]` | 103 | 0 | `3100 ms` | `5600 ms` | `6600 ms` | `3281.31 ms` |
| `sales/service-invoices/lookup [list]` | 62 | 0 | `3500 ms` | `6400 ms` | `6900 ms` | `3445.31 ms` |
| `sales/settings [get]` | 101 | 0 | `5700 ms` | `8700 ms` | `9400 ms` | `5846.38 ms` |

Before vs after on the two target endpoints:

| Route | Before median | After median | Improvement |
| --- | ---: | ---: | ---: |
| `sales/invoices/lookup [list]` | `13000 ms` | `3100 ms` | about `76%` lower |
| `sales/service-invoices/lookup [list]` | `14000 ms` | `3500 ms` | about `75%` lower |

What changed:
- invoice lookup and service-invoice lookup are no longer the dominant sales mixed bottlenecks
- overall mixed sales latency improved sharply together with the lookup endpoints
- the run stayed fully correct under load with `0` failures

Interpretation:
- the missing `customer__ledger` prefetch was a meaningful N+1 cost in the lookup serializer path
- after fixing that, sales mixed traffic moved back into a much healthier latency band
- `sales/settings [get]` is again the slowest consistently-hit read route in this profile, but it is far less severe than the earlier lookup bottleneck

Status after this rerun:
- correctness: passed
- lookup bottleneck: closed
- next performance target: sales settings read path, then higher-user stress tier

## Phase 1A Follow-up Result: Sales Mixed 30-User Rerun After Settings Document-Type Batch Resolution

Purpose:
- reduce repeated document-type lookup/update work inside the sales settings read payload
- keep the settings response identical while avoiding three independent `ensure_document_type(...)` passes per GET

Root cause isolated:
- `sales/views/sales_settings_views.py`
  - `_series_payload(...)` resolved invoice, credit note, and debit note document types one-by-one
  - each read invoked `ensure_document_type(...)` separately for the three sales document families
- that meant repeated lookup-and-normalize work on every settings GET even though the payload needed all three together

Fix executed:
- `numbering/services/__init__.py`
  - added `ensure_document_types_batch(...)`
  - resolves multiple document types in one query-driven pass and bulk-updates changed rows
- `sales/views/sales_settings_views.py`
  - replaced per-series `ensure_document_type(...)` calls with one batched document-type resolution
  - reused the resolved doc-type map when building numbering series rows

Correctness validation:

```bash
source venv/bin/activate
python manage.py test sales.tests_api.SalesSettingsApiTests --keepdb --verbosity 2
python3 -m py_compile numbering/services/__init__.py sales/views/sales_settings_views.py
```

Result:
- `4/4` targeted API tests passed
- compile checks passed

Stress command:

```bash
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 30 --spawn-rate 5 --run-time 90s \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_doctype_batch \
  --html perf/locust/results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_doctype_batch.html
```

Observed result from `results_phase1_sales_mixed_30u_90s_2026_08_02_after_settings_doctype_batch_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 558 | 0 | `2400 ms` | `5500 ms` | `8100 ms` | `2587.37 ms` |
| `sales/settings [get]` | 96 | 0 | `4600 ms` | `8200 ms` | `8900 ms` | `4625.53 ms` |
| `sales/invoices/lookup [list]` | 116 | 0 | `2100 ms` | `4100 ms` | `4600 ms` | `2246.96 ms` |
| `sales/service-invoices/lookup [list]` | 78 | 0 | `2300 ms` | `4700 ms` | `5100 ms` | `2513.74 ms` |

Before vs after on the settings target:

| Route | Previous median | New median | Improvement |
| --- | ---: | ---: | ---: |
| `sales/settings [get]` | `5700 ms` | `4600 ms` | about `19%` lower |

What changed:
- sales settings GET is materially faster and still fully correct under mixed load
- the overall sales mixed profile improved again, with lower aggregated median and lower tail latency
- lookup/list endpoints also remained in the healthy post-prefetch band during the same rerun

Interpretation:
- repeated document-type resolution was not the whole settings cost, but it was still a meaningful contributor
- after fixing both lookup serializer prefetching and settings doc-type batching, sales mixed at `30 users / 90 seconds` is now in a much healthier state than the earlier runs on August 2, 2026
- the remaining sales settings latency is likely in seller profile hydration, stock policy resolution, or choice/override assembly rather than numbering

Status after this rerun:
- correctness: passed
- settings read bottleneck: reduced
- sales mixed profile: healthy at current tier
- next performance target: optional deeper settings payload trimming, or move to higher-user stress tier

## Phase 1A Follow-up Result: Sales Mixed 50-User / 2-Minute Stress Rerun After Settings + Lookup Optimizations

Purpose:
- validate whether the post-fix sales mixed profile still holds under a higher-user tier
- confirm whether the next bottleneck is lookup traffic, cross-mode navigation, or the sales settings read path

Stress command:

```bash
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 8 --run-time 2m \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02_after_settings_doctype_batch \
  --html perf/locust/results_phase1_sales_mixed_50u_2m_2026_08_02_after_settings_doctype_batch.html
```

Observed result from `results_phase1_sales_mixed_50u_2m_2026_08_02_after_settings_doctype_batch_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 731 | 0 | `4700 ms` | `15000 ms` | `20000 ms` | `5803.66 ms` |
| `sales/settings [get]` | 129 | 0 | `13000 ms` | `20000 ms` | `22000 ms` | `13230.64 ms` |
| `sales/invoices/lookup [list]` | 192 | 0 | `5200 ms` | `7700 ms` | `8600 ms` | `4923.92 ms` |
| `sales/service-invoices/lookup [list]` | 82 | 0 | `5300 ms` | `8800 ms` | `9900 ms` | `5172.73 ms` |
| `sales/invoices/cross-mode-nav [goods->service]` | 76 | 0 | `3500 ms` | `7100 ms` | `7300 ms` | `3612.21 ms` |
| `sales/service-invoices/cross-mode-nav [service->goods]` | 72 | 0 | `3200 ms` | `7300 ms` | `7800 ms` | `3489.11 ms` |

What changed at the higher tier:
- correctness stayed stable with `0` failures across all observed sales-mixed routes
- cross-mode navigation stayed comparatively healthy even at `50 users`
- lookup endpoints remained functional, but their medians moved up into the `5+ second` band
- `sales/settings [get]` became the dominant bottleneck again and stretched into a clearly weak latency range

Interpretation:
- the earlier fixes were real and valuable, because lookup and navigation did not collapse under the higher tier
- however, the current sales settings read path is still too heavy for sustained higher-user mixed traffic
- the aggregate tail is now being shaped primarily by settings GET latency, not by lookup correctness or serializer N+1 failures

Status after this rerun:
- correctness: passed
- higher-tier resilience: partial pass
- lookup/cross-mode behavior: acceptable but not yet strong
- primary bottleneck: `sales/settings [get]`
- next action: trim sales settings payload assembly further before switching modules if the goal is stronger higher-tier sales confidence

## Phase 1A Follow-up Result: Sales Mixed 100-User / 2-Minute Stress Rerun

Purpose:
- validate whether the sales mixed profile remains correctness-safe at a stronger SaaS-style overlap tier
- identify whether the next limiter under `100 users` is settings traffic, draft mutation, lifecycle posting, or lookup pressure

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_100u_2m_2026_08_02 \
  --html perf/locust/results_phase1_sales_mixed_100u_2m_2026_08_02.html
```

Observed result from `results_phase1_sales_mixed_100u_2m_2026_08_02_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1277 | 0 | `4600 ms` | `22000 ms` | `28000 ms` | `6730.38 ms` |
| `sales/settings [get]` | 150 | 0 | `20000 ms` | `28000 ms` | `31000 ms` | `19981.10 ms` |
| `sales/settings [patch]` | 6 | 0 | `48000 ms` | `71000 ms` | `71000 ms` | `48443.12 ms` |
| `sales/invoices [draft create]` | 23 | 0 | `5900 ms` | `9900 ms` | `11000 ms` | `6290.13 ms` |
| `sales/invoices [draft save]` | 20 | 0 | `9700 ms` | `16000 ms` | `16000 ms` | `10350.15 ms` |
| `sales/invoices [confirm]` | 60 | 0 | `6900 ms` | `13000 ms` | `16000 ms` | `7102.79 ms` |
| `sales/invoices [post]` | 57 | 0 | `11000 ms` | `16000 ms` | `19000 ms` | `10978.56 ms` |
| `sales/invoices [reverse]` | 51 | 0 | `5400 ms` | `8800 ms` | `13000 ms` | `5624.43 ms` |
| `sales/invoices/lookup [list]` | 197 | 0 | `5000 ms` | `8700 ms` | `11000 ms` | `5434.41 ms` |
| `sales/service-invoices [draft create]` | 19 | 0 | `5900 ms` | `10000 ms` | `10000 ms` | `6267.83 ms` |
| `sales/service-invoices [draft save]` | 18 | 0 | `9800 ms` | `19000 ms` | `19000 ms` | `10704.65 ms` |
| `sales/service-invoices/lookup [list]` | 96 | 0 | `5000 ms` | `9500 ms` | `10000 ms` | `5562.74 ms` |

What changed at the `100-user` tier:
- correctness remained fully stable with `0` failures across read, draft, lifecycle, and settings routes
- isolated draft-save improvements largely held inside the mixed profile, with draft save still landing around the `~9.7s-9.8s` median band
- invoice and service lookup lists stayed in the `~5s` median range and did not become the main limiter
- `sales/settings [get]` clearly became the dominant mixed-traffic bottleneck, with a `20s` median and `31s` p99
- `sales/settings [patch]` was even heavier, but low-frequency, which means the real day-to-day mixed tail is still mostly driven by settings GET

Interpretation:
- sales at `100 users` is correctness-safe, but not yet latency-healthy as a mixed profile
- the current bottleneck is not draft serializer correctness, lookup integrity, or cross-mode routing
- the strongest next optimization target is the sales settings payload assembly/read path, because it is now shaping the entire aggregate tail
- if settings is trimmed, the mixed sales profile should likely fall much closer to the isolated draft baseline that is already materially healthier

Status after this rerun:
- correctness: passed
- mixed higher-tier resilience: partial pass
- draft path behavior under overlap: acceptable
- lifecycle behavior under overlap: acceptable but still slower on `post`
- primary bottleneck: `sales/settings [get]` and secondarily `sales/settings [patch]`
- next action: optimize sales settings read/patch path before moving sales to an even higher-user tier or switching focus away from this bottleneck

## Phase 1A Follow-up Result: Sales Mixed 100-User / 2-Minute Stress Rerun After Settings Payload Trim

Purpose:
- validate whether the sales settings payload optimization materially reduces the mixed-profile bottleneck at the same `100 users / 2 minutes` tier
- confirm whether sales can move from partial pass to a healthier high-user mixed baseline without any correctness regression

Stress command:

```bash
source venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags sales-mixed \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_mixed_100u_2m_2026_08_02_after_settings_payload_trim \
  --html perf/locust/results_phase1_sales_mixed_100u_2m_2026_08_02_after_settings_payload_trim.html
```

Observed result from `results_phase1_sales_mixed_100u_2m_2026_08_02_after_settings_payload_trim_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1896 | 0 | `2000 ms` | `9800 ms` | `14000 ms` | `3038.63 ms` |
| `sales/settings [get]` | 250 | 0 | `7200 ms` | `13000 ms` | `14000 ms` | `7744.29 ms` |
| `sales/settings [patch]` | 20 | 0 | `28000 ms` | `71000 ms` | `71000 ms` | `31299.43 ms` |
| `sales/invoices [draft create]` | 40 | 0 | `2300 ms` | `3800 ms` | `4900 ms` | `2411.18 ms` |
| `sales/invoices [draft save]` | 40 | 0 | `3700 ms` | `6500 ms` | `6500 ms` | `3924.86 ms` |
| `sales/invoices [confirm]` | 91 | 0 | `1900 ms` | `4800 ms` | `5500 ms` | `2310.38 ms` |
| `sales/invoices [post]` | 90 | 0 | `2800 ms` | `5800 ms` | `7800 ms` | `3554.95 ms` |
| `sales/invoices [reverse]` | 89 | 0 | `1900 ms` | `3700 ms` | `6300 ms` | `2228.83 ms` |
| `sales/invoices/lookup [list]` | 302 | 0 | `2100 ms` | `3800 ms` | `4600 ms` | `2283.12 ms` |
| `sales/service-invoices [draft create]` | 32 | 0 | `2000 ms` | `4200 ms` | `4400 ms` | `2266.51 ms` |
| `sales/service-invoices [draft save]` | 30 | 0 | `3100 ms` | `6400 ms` | `6500 ms` | `3817.13 ms` |
| `sales/service-invoices/lookup [list]` | 156 | 0 | `2300 ms` | `4100 ms` | `4700 ms` | `2381.70 ms` |

What changed relative to the pre-trim `100-user` mixed rerun:
- correctness remained fully stable with `0` failures
- aggregated median dropped from `4600 ms` to `2000 ms`
- aggregated p95 dropped from `22000 ms` to `9800 ms`
- `sales/settings [get]` improved from `20000 ms` median / `28000 ms` p95 / `31000 ms` p99 to `7200 ms` median / `13000 ms` p95 / `14000 ms` p99
- draft create/save, confirm/post, and lookup routes all moved down into a much healthier latency band at the same user tier
- `sales/settings [patch]` remains heavy, but it is a low-frequency administrative path rather than the dominant day-to-day mixed traffic cost

Interpretation:
- the sales settings payload trim was a major win and materially changed the mixed high-user shape of the module
- the primary high-frequency bottleneck is no longer severe enough to dominate the entire sales profile
- sales mixed traffic at `100 users` is now both correctness-safe and directionally healthy for the local stress environment
- any further sales optimization should focus on the lower-frequency settings PATCH path or on pushing the next higher-user tier rather than reworking the now-improved read assembly first

Status after this rerun:
- correctness: passed
- mixed higher-tier resilience: passed
- settings GET bottleneck: materially reduced
- draft and lifecycle under overlap: healthy
- remaining outlier: `sales/settings [patch]`
- next action: either trim the settings PATCH path or move to the next module stress tier with sales retained as a stronger baseline

## Phase 1A Follow-up Result: Sales Draft Write 50-User / 2-Minute Isolated Stress

Purpose:
- remove low-frequency settings reads from the picture
- measure the higher-tier behavior of the true day-to-day sales draft path: seed lookup, draft create, and draft save

Stress command:

```bash
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 8 --run-time 2m \
  --tags sales-draft-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_draft_write_50u_2m_2026_08_02 \
  --html perf/locust/results_phase1_sales_draft_write_50u_2m_2026_08_02.html
```

Observed result from `results_phase1_sales_draft_write_50u_2m_2026_08_02_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 595 | 0 | `6900 ms` | `18000 ms` | `19000 ms` | `8828.45 ms` |
| `sales/invoices [draft create]` | 74 | 0 | `12000 ms` | `18000 ms` | `19000 ms` | `13039.28 ms` |
| `sales/invoices [draft save]` | 55 | 0 | `16000 ms` | `20000 ms` | `21000 ms` | `16236.82 ms` |
| `sales/service-invoices [draft create]` | 73 | 0 | `13000 ms` | `19000 ms` | `19000 ms` | `13649.30 ms` |
| `sales/service-invoices [draft save]` | 49 | 0 | `16000 ms` | `19000 ms` | `20000 ms` | `15629.34 ms` |
| `sales/goods-lookup [seed-id]` | 45 | 0 | `4500 ms` | `6400 ms` | `6900 ms` | `4640.57 ms` |
| `sales/service-lookup [seed-id]` | 47 | 0 | `5100 ms` | `6900 ms` | `7200 ms` | `4993.95 ms` |

Interpretation:
- correctness stayed clean with `0` failures
- the core problem is not settings in this run
- the bottleneck moved directly into draft mutation itself, especially `draft save`
- both goods and service draft flows show the same pattern, which points to shared save-path cost rather than a single invoice family issue

Status after this rerun:
- correctness: passed
- higher-tier draft resilience: weak
- primary bottleneck: sales draft save path
- secondary bottleneck: sales draft create path
- next action: inspect sales create/save serializer and posting-preview/save mutation cost before calling sales write-path strong at SaaS scale

## Phase 1A Follow-up Result: Sales Lifecycle 50-User / 2-Minute Isolated Stress

Purpose:
- isolate confirm, post, and reverse behavior from draft create/save cost
- determine whether the posting workflow is also weak or whether the main problem is concentrated in draft write operations

Stress command:

```bash
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 50 --spawn-rate 8 --run-time 2m \
  --tags sales-lifecycle \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_lifecycle_50u_2m_2026_08_02 \
  --html perf/locust/results_phase1_sales_lifecycle_50u_2m_2026_08_02.html
```

Observed result from `results_phase1_sales_lifecycle_50u_2m_2026_08_02_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 997 | 0 | `4500 ms` | `10000 ms` | `12000 ms` | `5180.56 ms` |
| `sales/invoices [confirm]` | 283 | 0 | `5200 ms` | `11000 ms` | `12000 ms` | `5672.64 ms` |
| `sales/invoices [post]` | 283 | 0 | `7600 ms` | `11000 ms` | `12000 ms` | `6886.50 ms` |
| `sales/invoices [reverse]` | 281 | 0 | `3500 ms` | `9600 ms` | `11000 ms` | `4418.60 ms` |
| `sales/invoices [seed-id]` | 50 | 0 | `3900 ms` | `5500 ms` | `6400 ms` | `3806.51 ms` |

Interpretation:
- correctness stayed clean with `0` failures`
- lifecycle remains meaningfully healthier than draft create/save at the same user tier
- `post` is the slowest lifecycle step, but it is still materially below the draft save band
- this means the stronger sales write-path risk is concentrated in draft mutation, not in the confirm/post/reverse workflow

Status after this rerun:
- correctness: passed
- lifecycle resilience: acceptable
- draft-vs-lifecycle comparison: draft path is the real 50-user sales bottleneck
- next action: prioritize draft create/save optimization ahead of more lifecycle work

## Phase 1A Follow-up Result: Sales Draft Write 100-User / 2-Minute Isolated Stress After Draft-TCS Trim

Purpose:
- validate whether the draft-save bottleneck improved after removing draft-time `withholding_tcs_computation` persistence
- re-measure the true higher-user sales write path with the same isolated pattern: seed lookup, draft create, and draft save

Stress command:

```bash
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags sales-draft-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_draft_write_100u_2m_2026_08_02_after_tcs_skip \
  --html perf/locust/results_phase1_sales_draft_write_100u_2m_2026_08_02_after_tcs_skip.html
```

Observed result from `results_phase1_sales_draft_write_100u_2m_2026_08_02_after_tcs_skip_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1517 | 0 | `6800 ms` | `13000 ms` | `14000 ms` | `6713 ms` |
| `sales/invoices [draft create]` | 199 | 0 | `7700 ms` | `9200 ms` | `9900 ms` | `7732 ms` |
| `sales/invoices [draft save]` | 165 | 0 | `12000 ms` | `14000 ms` | `14000 ms` | `11905 ms` |
| `sales/service-invoices [draft create]` | 201 | 0 | `7700 ms` | `9100 ms` | `10000 ms` | `7768 ms` |
| `sales/service-invoices [draft save]` | 163 | 0 | `12000 ms` | `14000 ms` | `14000 ms` | `11881 ms` |
| `sales/goods-lookup [seed-id]` | 95 | 0 | `3800 ms` | `6000 ms` | `6300 ms` | `4008 ms` |
| `sales/service-lookup [seed-id]` | 94 | 0 | `4000 ms` | `6000 ms` | `6300 ms` | `4283 ms` |

What changed relative to the earlier isolated draft-write run:
- correctness stayed fully clean with `0` failures at `100 users`
- draft create stayed in the `~7.7s` median band
- draft save moved down from the earlier `~16s` median / `~20s` p95 band to roughly `12s` median / `14s` p95
- goods and service write paths improved in parallel, which matches the shared backend save-path changes

Interpretation:
- the draft-side backend trimming is real and measurable
- the draft save path is still the main sales write bottleneck, but it is no longer in the same weak band seen before the recent fixes
- the next strong candidate is the full tax-summary rebuild and repeated header persistence work, not draft TCS statutory sync
- these numbers are still influenced by the fact that this run used local Django `runserver`, so they should be treated as directional relative measurements rather than production-grade absolute latency

Status after this rerun:
- correctness: passed
- higher-tier draft resilience: improved
- draft write bottleneck: still present, but materially reduced
- next action: optimize tax-summary / totals recompute path, then rerun the same isolated sales draft-write tier for another before/after comparison

## Phase 1A Follow-up Result: Sales Draft Write 100-User / 2-Minute Isolated Stress After Header-Write Collapse

Purpose:
- validate whether collapsing draft-only header persistence reduced the isolated sales draft-write path again
- compare the same `100 users / 2 minutes` sales draft profile against the prior draft-TCS-trim rerun

Stress command:

```bash
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
source venv/bin/activate
locust -f perf/locust/locustfile.py --headless \
  --users 100 --spawn-rate 12 --run-time 2m \
  --tags sales-draft-write \
  --host http://127.0.0.1:8000 \
  --csv perf/locust/results_phase1_sales_draft_write_100u_2m_2026_08_02_after_header_collapse \
  --html perf/locust/results_phase1_sales_draft_write_100u_2m_2026_08_02_after_header_collapse.html
```

Observed result from `results_phase1_sales_draft_write_100u_2m_2026_08_02_after_header_collapse_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 1837 | 0 | `5200 ms` | `11000 ms` | `12000 ms` | `5551 ms` |
| `sales/invoices [draft create]` | 245 | 0 | `6300 ms` | `7000 ms` | `7300 ms` | `6242 ms` |
| `sales/invoices [draft save]` | 220 | 0 | `9900 ms` | `12000 ms` | `12000 ms` | `10051 ms` |
| `sales/service-invoices [draft create]` | 255 | 0 | `6300 ms` | `7100 ms` | `7400 ms` | `6215 ms` |
| `sales/service-invoices [draft save]` | 219 | 0 | `10000 ms` | `12000 ms` | `12000 ms` | `10121 ms` |
| `sales/goods-detail [seed]` | 248 | 0 | `4000 ms` | `4700 ms` | `5100 ms` | `3922 ms` |
| `sales/service-detail [seed]` | 256 | 0 | `4100 ms` | `4800 ms` | `5100 ms` | `3936 ms` |

What changed relative to the prior `after_tcs_skip` rerun:
- correctness stayed clean with `0` failures at the same `100-user` tier
- aggregated median dropped from `6800 ms` to `5200 ms`
- goods and service draft create improved from about `7700 ms` median to about `6300 ms`
- goods draft save improved from about `12000 ms` median / `14000 ms` p95 to about `9900 ms` median / `12000 ms` p95
- service draft save improved from about `12000 ms` median / `14000 ms` p95 to about `10000 ms` median / `12000 ms` p95

Interpretation:
- collapsing intermediate draft-only header saves produced another measurable step down in isolated sales write latency
- the draft save path is still the slowest sales write operation, but it is now closer to the `10s` band than the earlier `12s-16s` band
- the next likely backend hotspot is full line/tax recompute work rather than redundant header persistence or draft-time TCS statutory sync
- because this still ran on local Django `runserver`, these numbers remain best used as directional relative measurements rather than production-grade absolute latency

Status after this rerun:
- correctness: passed
- higher-tier draft resilience: improved again
- isolated sales write bottleneck: still draft save, but no longer in the earlier weak band
- next action: keep the sales 100-user tier as the new comparison baseline before moving to broader mixed or next-module stress passes

## Phase 1C Follow-up Result: Purchase Draft Write 100-User / 2-Minute Rerun After JWT Session-Lookup Optimization

Purpose:
- verify whether collapsing the normal JWT auth path from `user lookup + session lookup` into a single `AuthSession -> user` lookup removes the last narrow purchase draft-write failures
- compare directly against the prior isolated pooled-Gunicorn `100 users / 2 minutes` purchase draft-write rerun on `2026-08-03`

What changed before this run:
- `Authentication/jwt.py` now resolves the common access-token path through a single `AuthSession.objects.select_related("user")` lookup when both `sid` and `user_id` are present in the token payload
- focused auth regression coverage was expanded with a query-count guard:
  - `JwtAuthenticationTests.test_valid_token_uses_single_session_backed_query`

Validation before rerun:
- `python Finacc/manage.py test Authentication.tests.test_authentication --keepdb -v 2`
- result: `25 tests`, `OK`

Stress command:

```bash
source Finacc/venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 100 \
  --spawn-rate 12 \
  --run-time 2m \
  --tags purchase-draft-write \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2 \
  --html Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2.html
```

Observed result from `results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2_stats.csv`:

| Route | Requests | Failures | Median | P95 | P99 | Avg |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `Aggregated` | 3469 | 0 | `2400 ms` | `5100 ms` | `6700 ms` | `2723 ms` |
| `purchase/goods-detail [seed]` | 530 | 0 | `2400 ms` | `4800 ms` | `6400 ms` | `2675 ms` |
| `purchase/invoices [draft create]` | 508 | 0 | `2600 ms` | `5000 ms` | `6600 ms` | `2829 ms` |
| `purchase/invoices [draft save]` | 496 | 0 | `2900 ms` | `5300 ms` | `6900 ms` | `3035 ms` |
| `purchase/service-detail [seed]` | 525 | 0 | `2600 ms` | `5000 ms` | `6300 ms` | `2793 ms` |
| `purchase/service-invoices [draft create]` | 514 | 0 | `2800 ms` | `6200 ms` | `6800 ms` | `3031 ms` |
| `purchase/service-invoices [draft save]` | 496 | 0 | `2900 ms` | `5700 ms` | `7000 ms` | `3207 ms` |

Artifacts:
- HTML: [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2.html)
- Stats CSV: [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2_stats.csv)
- History CSV: [results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_draftwrite_100u_2m_2026_08_03_pooled_gunicorn_httpauth_opt2_stats_history.csv)

What changed relative to the immediately previous pooled-Gunicorn rerun:
- failure count improved from `2` down to `0`
- aggregate average improved from about `6244 ms` down to about `2723 ms`
- aggregate median improved from about `6900 ms` down to about `2400 ms`
- aggregate p95 improved from about `10000 ms` down to about `5100 ms`
- throughput improved from about `13.88 req/s` up to about `28.97 req/s`
- the previously weak `purchase/service-detail [seed]` path stayed fully green for `525` requests

Interpretation:
- the remaining isolated purchase draft-write bottleneck was materially tied to auth-path DB pressure, not purchase service serializer correctness
- collapsing the common JWT path to a single session-backed lookup removed the prior narrow failure mode and materially improved latency at the same concurrency tier
- purchase draft create/save for both goods and services is now in a much stronger band on the same pooled local stack

Status after this rerun:
- `purchase isolated 100-user write correctness on corrected pooled local stack`: `passed`
- `purchase isolated 100-user write latency on corrected pooled local stack`: `materially improved`
- `purchase next gap`: `either raise purchase to the next user tier or move to the next module stress target`

## Phase 1C Follow-up Result: Voucher Mixed 100-User / 2-Minute Rerun After JWT Session-Lookup Optimization

Purpose:
- rerun the full voucher mixed workload on the refreshed pooled Gunicorn stack after the JWT auth-path consolidation
- verify whether the earlier voucher instability was primarily stale backend process state or a real remaining module defect
- classify any remaining miss as workflow correctness, stale-state behavior, or infrastructure saturation

Command:

```bash
source Finacc/venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 100 \
  --spawn-rate 12 \
  --run-time 2m \
  --tags voucher-mixed \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt \
  --html Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt.html
```

Artifacts:
- HTML: [results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt.html)
- Stats CSV: [results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_stats.csv)
- History CSV: [results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_stats_history.csv)
- Failures CSV: [results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_voucher_mixed_100u_2m_2026_08_03_pooled_gunicorn_rerun_after_authopt_failures.csv)

Observed result:
- total requests: `2676`
- failures: `1`
- aggregate average: `3703 ms`
- aggregate median: `2500 ms`
- aggregate throughput: `22.47 req/s`
- aggregate p95: `7700 ms`
- aggregate p99: `10000 ms`
- max observed latency: `11206 ms`

Important endpoint samples:
- `payments/payment-vouchers [draft create]`: `87` requests, `0` failures, avg `3506 ms`, median `1800 ms`
- `PATCH payments/payment-vouchers [draft save]`: `84` requests, `0` failures, avg `3618 ms`, median `1700 ms`
- `payments/payment-vouchers [confirm]`: `81` requests, `0` failures, avg `3206 ms`, median `1400 ms`
- `payments/payment-vouchers [post]`: `77` requests, `0` failures, avg `3412 ms`, median `1300 ms`
- `receipts/receipt-vouchers [draft create]`: `74` requests, `0` failures, avg `4123 ms`, median `4400 ms`
- `PATCH receipts/receipt-vouchers [draft save]`: `73` requests, `0` failures, avg `4513 ms`, median `6100 ms`
- `receipts/receipt-vouchers [confirm]`: `68` requests, `0` failures, avg `4161 ms`, median `5900 ms`
- `receipts/receipt-vouchers [post]`: `67` requests, `0` failures, avg `4104 ms`, median `5900 ms`

Only recorded failure:
- `POST payments/payment-vouchers [reject seed create]`
  - error: `Payment reject conflict seed create did not return an id`
  - occurrences: `1`

Failure classification:
- backend log evidence around the same run window showed `psycopg.OperationalError` / `django.db.utils.OperationalError` with:
  - `FATAL: sorry, too many clients already`
- this indicates the remaining miss is best classified as pooled local database connection ceiling pressure, not as payment or receipt voucher workflow corruption
- the voucher business paths themselves remained green across ordinary draft, save, confirm, post, submit, approve, stale-repeat, and reject-repeat validation

Interpretation:
- rerunning vouchers on the refreshed backend clearly improved the signal quality versus the earlier stale-process rerun
- voucher correctness at the 100-user mixed tier is now strong
- the remaining residual risk is infrastructure saturation on the current local pooled stack, especially during seed-create bursts, rather than a core voucher business-rule defect

Status after this rerun:
- `voucher mixed 100-user workflow correctness on refreshed pooled local stack`: `nearly passed`
- `voucher mixed 100-user residual issue`: `single database connection ceiling miss during reject-seed create`
- `voucher module confidence`: `high for correctness, not yet fully clean for pooled-local ceiling resilience`
- `voucher next best step`: `either raise DB/app capacity and rerun for a fully clean 100-user pass, or move to the next module while carrying this as an infra-tier observation`

## Phase 1D Follow-up Result: Financial Reports 100-User / 2-Minute Pooled Gunicorn Escalation

Purpose:
- escalate the already clean financial-report family from the earlier `50 users / 2 minutes` tier to `100 users / 2 minutes`
- verify that trial balance and ledger summary remain correctness-clean under a materially heavier SaaS-style read burst
- capture whether grouped and CSV export variants become the next reporting bottleneck at the higher tier

Command:

```bash
source Finacc/venv/bin/activate
export FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true
locust -f Finacc/perf/locust/locustfile.py --headless \
  --users 100 \
  --spawn-rate 12 \
  --run-time 2m \
  --tags financial-reports \
  --host http://127.0.0.1:8004 \
  --csv Finacc/perf/locust/results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn \
  --html Finacc/perf/locust/results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn.html
```

Artifacts:
- HTML: [results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn.html)
- Stats CSV: [results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn_stats.csv)
- History CSV: [results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_reports_100u_2m_2026_08_03_pooled_gunicorn_stats_history.csv)

Observed result:
- total requests: `3609`
- failures: `0`
- aggregate average: `1323 ms`
- aggregate median: `1100 ms`
- aggregate throughput: `30.12 req/s`
- aggregate p95: `3300 ms`
- aggregate p99: `4600 ms`
- max observed latency: `5282 ms`

Key endpoint results:
- `reports/financial/ledger-summary [get]`: `823` requests, `0` failures, avg `1373 ms`, median `1200 ms`, p95 `3300 ms`, p99 `4500 ms`, max `5011 ms`
- `reports/financial/ledger-summary [grouped]`: `444` requests, `0` failures, avg `1355 ms`, median `1100 ms`, p95 `3400 ms`, p99 `4800 ms`, max `5282 ms`
- `reports/financial/ledger-summary/csv [export]`: `437` requests, `0` failures, avg `1363 ms`, median `1100 ms`, p95 `3300 ms`, p99 `4400 ms`, max `5075 ms`
- `reports/financial/trial-balance [get]`: `853` requests, `0` failures, avg `1333 ms`, median `1100 ms`, p95 `3200 ms`, p99 `4600 ms`, max `5135 ms`
- `reports/financial/trial-balance [grouped]`: `430` requests, `0` failures, avg `1409 ms`, median `1200 ms`, p95 `3400 ms`, p99 `4500 ms`, max `5045 ms`
- `reports/financial/trial-balance/csv [export]`: `422` requests, `0` failures, avg `1390 ms`, median `1100 ms`, p95 `3400 ms`, p99 `4600 ms`, max `5042 ms`

Interpretation:
- the financial-report family remains correctness-clean even after doubling the earlier validated `50-user` tier
- summary, grouped, and CSV export paths all stayed in a healthy low-seconds band without any instability signal
- grouped and export variants are only modestly heavier than the plain summary reads, which is a strong result for the current local pooled stack
- compared with vouchers and mixed write modules, financial reports are no longer a stress-risk leader

Status after this rerun:
- `financial reports correctness at 100 users`: `passed`
- `financial reports performance at 100 users`: `strong`
- `financial reports next gap`: `expand beyond trial balance and ledger summary only if we want full statement-family parity for profit and loss, balance sheet, trading account, and ledger book`

## Phase 1D Follow-up Result: Financial Statement Family 50-User / 2-Minute Stress On August 3, 2026

Purpose:
- close the remaining report-family parity gap by stress-testing:
  - profit and loss
  - balance sheet
  - trading account
  - ledger book
- validate both plain reads and grouped/export variants with live statement metadata seeding

Command:

```bash
source Finacc/venv/bin/activate && locust -f Finacc/perf/locust/locustfile.py --headless --users 50 --spawn-rate 8 --run-time 2m --tags financial-statements --host http://127.0.0.1:8004 --csv Finacc/perf/locust/results_phase1_financial_statements_50u_2m_2026_08_03 --html Finacc/perf/locust/results_phase1_financial_statements_50u_2m_2026_08_03.html
```

Artifacts:
- [results_phase1_financial_statements_50u_2m_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_2026_08_03_stats.csv:1)
- [results_phase1_financial_statements_50u_2m_2026_08_03_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_2026_08_03_failures.csv:1)
- [results_phase1_financial_statements_50u_2m_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_2026_08_03.html:1)

Result:
- total requests: `1544`
- failures: `0`
- aggregate average latency: `1979 ms`
- aggregate median latency: `980 ms`
- p95 latency: `8100 ms`
- p99 latency: `13000 ms`
- max observed latency: `18148 ms`
- throughput: `13.01 req/s`

Key endpoint results:
- `reports/financial/balance-sheet [get]`: `166` requests, `0` failures, avg `1638 ms`, median `990 ms`, p95 `4900 ms`, p99 `13000 ms`, max `13030 ms`
- `reports/financial/balance-sheet [grouped]`: `102` requests, `0` failures, avg `1782 ms`, median `1100 ms`, p95 `6100 ms`, p99 `13000 ms`, max `13082 ms`
- `reports/financial/balance-sheet/csv [export]`: `101` requests, `0` failures, avg `1927 ms`, median `900 ms`, p95 `8700 ms`, p99 `12000 ms`, max `13407 ms`
- `reports/financial/ledger-book [get]`: `180` requests, `0` failures, avg `1586 ms`, median `720 ms`, p95 `7600 ms`, p99 `12000 ms`, max `12133 ms`
- `reports/financial/ledger-book/csv [export]`: `101` requests, `0` failures, avg `1915 ms`, median `810 ms`, p95 `10000 ms`, p99 `11000 ms`, max `11626 ms`
- `reports/financial/profit-loss [get]`: `184` requests, `0` failures, avg `1759 ms`, median `870 ms`, p95 `10000 ms`, p99 `12000 ms`, max `13170 ms`
- `reports/financial/profit-loss [grouped]`: `85` requests, `0` failures, avg `1303 ms`, median `800 ms`, p95 `4500 ms`, p99 `7200 ms`, max `7155 ms`
- `reports/financial/profit-loss/csv [export]`: `104` requests, `0` failures, avg `1666 ms`, median `940 ms`, p95 `5300 ms`, p99 `11000 ms`, max `13577 ms`
- `reports/financial/trading-account [get]`: `197` requests, `0` failures, avg `1547 ms`, median `830 ms`, p95 `5000 ms`, p99 `12000 ms`, max `12976 ms`
- `reports/financial/trading-account [grouped]`: `73` requests, `0` failures, avg `2138 ms`, median `1100 ms`, p95 `12000 ms`, p99 `13000 ms`, max `13446 ms`
- `reports/financial/trading-account/csv [export]`: `101` requests, `0` failures, avg `1670 ms`, median `870 ms`, p95 `7000 ms`, p99 `8300 ms`, max `8472 ms`
- `reports/financial/meta [seed]`: `50` requests, `0` failures, avg `9096 ms`, median `8100 ms`, p95 `17000 ms`, p99 `18000 ms`, max `18148 ms`

Interpretation:
- the previously missing financial statement family is now covered by executable Locust stress automation
- correctness is clean across all four statement families and their grouped/export variants at the `50-user` tier
- steady-state statement endpoints mostly settle into a sub-`2s` median band once the run warms up
- the clear bottleneck is not the statement body routes themselves but the shared `reports/financial/meta [seed]` path used to prepare live statement scope
- if we want to push this family to a higher-user tier, the best next optimization target is statement meta seeding and any expensive account-option assembly behind it

Status after this rerun:
- `financial statement family correctness at 50 users`: `passed`
- `financial statement family performance at 50 users`: `good with one clear hotspot`
- `financial statement family hotspot`: `reports/financial/meta [seed]`
- `financial statement family next gap`: `either optimize statement meta seeding first or escalate the same family to 100 users for upper-tier proof`

## Phase 1D Follow-up Result: Financial Statement Family 50-User / 2-Minute Stress After Financial Meta Cache On August 3, 2026

Purpose:
- validate that the new reports meta cache removes the statement-family seed bottleneck under the same `50-user / 2-minute` tier
- confirm that the optimization improves latency without introducing correctness regressions

Command:

```bash
source Finacc/venv/bin/activate && locust -f Finacc/perf/locust/locustfile.py --headless --users 50 --spawn-rate 8 --run-time 2m --tags financial-statements --host http://127.0.0.1:8004 --csv Finacc/perf/locust/results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03 --html Finacc/perf/locust/results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03.html
```

Artifacts:
- [results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03_stats.csv:1)
- [results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03_failures.csv:1)
- [results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_50u_2m_after_meta_cache_2026_08_03.html:1)

Result:
- total requests: `2878`
- failures: `0`
- aggregate average latency: `159 ms`
- aggregate median latency: `68 ms`
- p95 latency: `670 ms`
- p99 latency: `1900 ms`
- max observed latency: `4165 ms`
- throughput: `24.13 req/s`

Key endpoint results:
- `reports/financial/meta [seed]`: `50` requests, `0` failures, avg `1713 ms`, median `1700 ms`, p95 `3400 ms`, p99 `4200 ms`, max `4165 ms`
- `reports/financial/balance-sheet [get]`: `373` requests, `0` failures, avg `140 ms`, median `81 ms`
- `reports/financial/balance-sheet [grouped]`: `181` requests, `0` failures, avg `117 ms`, median `85 ms`
- `reports/financial/balance-sheet/csv [export]`: `185` requests, `0` failures, avg `156 ms`, median `94 ms`
- `reports/financial/ledger-book [get]`: `367` requests, `0` failures, avg `97 ms`, median `50 ms`
- `reports/financial/ledger-book/csv [export]`: `179` requests, `0` failures, avg `136 ms`, median `53 ms`
- `reports/financial/profit-loss [get]`: `377` requests, `0` failures, avg `117 ms`, median `70 ms`
- `reports/financial/profit-loss [grouped]`: `178` requests, `0` failures, avg `129 ms`, median `68 ms`
- `reports/financial/profit-loss/csv [export]`: `177` requests, `0` failures, avg `132 ms`, median `74 ms`
- `reports/financial/trading-account [get]`: `366` requests, `0` failures, avg `115 ms`, median `56 ms`
- `reports/financial/trading-account [grouped]`: `172` requests, `0` failures, avg `128 ms`, median `57 ms`
- `reports/financial/trading-account/csv [export]`: `175` requests, `0` failures, avg `94 ms`, median `58 ms`

Before/after comparison against the pre-cache `50-user` statement-family tier:
- aggregate average latency improved from `1979 ms` to `159 ms`
- aggregate median latency improved from `980 ms` to `68 ms`
- throughput improved from `13.01 req/s` to `24.13 req/s`
- `reports/financial/meta [seed]` average improved from `9096 ms` to `1713 ms`
- `reports/financial/meta [seed]` max improved from `18148 ms` to `4165 ms`

Interpretation:
- the reports meta cache materially changes the statement-family load profile
- the statement endpoints are now comfortably out of the stress-risk category at this tier
- `reports/financial/meta [seed]` is still the slowest path in the family, but it is no longer a severe bottleneck
- the post-fix run is strong enough to treat the financial statement family as stabilized at `50 users`

Status after this rerun:
- `financial statement family correctness after cache`: `passed`
- `financial statement family performance after cache`: `strong`
- `financial statement family hotspot after cache`: `reports/financial/meta [seed]`, but now materially reduced
- `financial statement family next gap`: `100-user escalation if we want upper-tier proof, otherwise move to the next module`

## Phase 1D Follow-up Result: Financial Statement Family 100-User / 2-Minute Stress After Financial Meta Cache On August 3, 2026

Purpose:
- escalate the same post-cache statement-family workload from `50` to `100` users
- verify whether cached financial meta plus the statement endpoints still hold under a higher concurrent SaaS-style tier
- decide whether this family is ready to be called upper-tier strong or still needs another hardening round

Command:

```bash
source Finacc/venv/bin/activate && locust -f Finacc/perf/locust/locustfile.py --headless --users 100 --spawn-rate 12 --run-time 2m --tags financial-statements --host http://127.0.0.1:8004 --csv Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03 --html Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03.html
```

Artifacts:
- [results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03_stats.csv:1)
- [results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03_failures.csv:1)
- [results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_cache_2026_08_03.html:1)

Result:
- total requests: `2851`
- failures: `1`
- aggregate average latency: `2258 ms`
- aggregate median latency: `1900 ms`
- p95 latency: `6200 ms`
- p99 latency: `7700 ms`
- max observed latency: `9659 ms`
- throughput: `23.89 req/s`

Observed failure:
- `reports/financial/meta [seed]`: `1` failure with `CatchResponseError('Financial meta returned invalid JSON')`

Key endpoint results:
- `auth/login`: `100` requests, `0` failures, avg `1464 ms`, median `1200 ms`, max `5267 ms`
- `auth/me`: `100` requests, `0` failures, avg `1871 ms`, median `900 ms`, max `5339 ms`
- `reports/financial/meta [seed]`: `101` requests, `1` failure, avg `5307 ms`, median `6000 ms`, max `9659 ms`
- `reports/financial/balance-sheet [get]`: `355` requests, `0` failures, avg `2424 ms`, median `2000 ms`
- `reports/financial/balance-sheet [grouped]`: `185` requests, `0` failures, avg `2178 ms`, median `2000 ms`
- `reports/financial/balance-sheet/csv [export]`: `176` requests, `0` failures, avg `2129 ms`, median `1800 ms`
- `reports/financial/ledger-book [get]`: `355` requests, `0` failures, avg `2026 ms`, median `1500 ms`
- `reports/financial/ledger-book/csv [export]`: `165` requests, `0` failures, avg `2271 ms`, median `1900 ms`
- `reports/financial/profit-loss [get]`: `315` requests, `0` failures, avg `2213 ms`, median `1900 ms`
- `reports/financial/profit-loss [grouped]`: `161` requests, `0` failures, avg `2049 ms`, median `1400 ms`
- `reports/financial/profit-loss/csv [export]`: `172` requests, `0` failures, avg `2079 ms`, median `1800 ms`
- `reports/financial/trading-account [get]`: `317` requests, `0` failures, avg `2217 ms`, median `1900 ms`
- `reports/financial/trading-account [grouped]`: `173` requests, `0` failures, avg `2118 ms`, median `2000 ms`
- `reports/financial/trading-account/csv [export]`: `176` requests, `0` failures, avg `2172 ms`, median `1700 ms`

Comparison against the post-cache `50-user` statement-family tier:
- aggregate average latency regressed from `159 ms` to `2258 ms`
- aggregate median latency regressed from `68 ms` to `1900 ms`
- throughput stayed close, moving from `24.13 req/s` to `23.89 req/s`
- `reports/financial/meta [seed]` average regressed from `1713 ms` to `5307 ms`
- `reports/financial/meta [seed]` max regressed from `4165 ms` to `9659 ms`
- correctness moved from `0` failures to `1` meta-seed failure

Interpretation:
- the `50-user` improvement is real, but the `100-user` tier still exposes a concurrency bottleneck
- the statement-family body routes remain functionally correct, yet they inherit much worse latency once the shared meta-seed path slows down
- the primary blocker is still `reports/financial/meta [seed]`, now specifically under heavier concurrent seeding pressure
- auth/session bootstrap also adds measurable warm-up cost, so the next performance round should separate login churn from steady-state report pressure

Status after this escalation:
- `financial statement family correctness at 100 users after cache`: `mostly stable but not fully clean`
- `financial statement family performance at 100 users after cache`: `not yet strong enough`
- `financial statement family primary blocker at 100 users`: `reports/financial/meta [seed]`
- `financial statement family secondary pressure point at 100 users`: `auth/login` and `auth/me` warm-up overhead
- `financial statement family next gap after 100-user run`: `optimize statement meta generation and rerun the same tier before calling this family upper-tier ready`

## Phase 1D Follow-up Result: Financial Statement Family 100-User / 2-Minute Stress After Financial Meta Query Trim On August 3, 2026

Purpose:
- validate the targeted financial-meta optimization that replaced full account-model hydration with a lean values query
- prove whether the same `100-user / 2-minute` statement-family tier can now complete without the earlier meta failure
- measure whether the financial statement family is now strong enough to move beyond the upper-tier blocker status

Code change validated before this run:
- optimized [meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/services/financial/meta.py:1) so `_account_option_payload()` reads only the exact account, ledger, and party-type fields needed for meta assembly
- removed the heavier per-row model hydration path from the financial statement meta seed workflow

Command:

```bash
source Finacc/venv/bin/activate && locust -f Finacc/perf/locust/locustfile.py --headless --users 100 --spawn-rate 12 --run-time 2m --tags financial-statements --host http://127.0.0.1:8004 --csv Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03 --html Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03.html
```

Artifacts:
- [results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03_stats.csv:1)
- [results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03_failures.csv:1)
- [results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_financial_statements_100u_2m_after_meta_query_trim_2026_08_03.html:1)

Result:
- total requests: `4103`
- failures: `0`
- aggregate average latency: `983 ms`
- aggregate median latency: `630 ms`
- p95 latency: `3900 ms`
- p99 latency: `5900 ms`
- max observed latency: `7899 ms`
- throughput: `34.37 req/s`

Key endpoint results:
- `auth/login`: `100` requests, `0` failures, avg `921 ms`, median `910 ms`
- `auth/me`: `100` requests, `0` failures, avg `981 ms`, median `770 ms`
- `reports/financial/meta [seed]`: `100` requests, `0` failures, avg `3788 ms`, median `3400 ms`, max `7899 ms`
- `reports/financial/balance-sheet [get]`: `504` requests, `0` failures, avg `1009 ms`, median `650 ms`
- `reports/financial/balance-sheet [grouped]`: `244` requests, `0` failures, avg `947 ms`, median `650 ms`
- `reports/financial/balance-sheet/csv [export]`: `259` requests, `0` failures, avg `1013 ms`, median `660 ms`
- `reports/financial/ledger-book [get]`: `526` requests, `0` failures, avg `853 ms`, median `540 ms`
- `reports/financial/ledger-book/csv [export]`: `264` requests, `0` failures, avg `947 ms`, median `550 ms`
- `reports/financial/profit-loss [get]`: `520` requests, `0` failures, avg `894 ms`, median `610 ms`
- `reports/financial/profit-loss [grouped]`: `227` requests, `0` failures, avg `911 ms`, median `610 ms`
- `reports/financial/profit-loss/csv [export]`: `253` requests, `0` failures, avg `950 ms`, median `630 ms`
- `reports/financial/trading-account [get]`: `532` requests, `0` failures, avg `843 ms`, median `530 ms`
- `reports/financial/trading-account [grouped]`: `235` requests, `0` failures, avg `858 ms`, median `640 ms`
- `reports/financial/trading-account/csv [export]`: `239` requests, `0` failures, avg `841 ms`, median `520 ms`

Comparison against the earlier failed `100-user` post-cache statement-family tier:
- total requests improved from `2851` to `4103`
- failures improved from `1` to `0`
- aggregate average latency improved from `2258 ms` to `983 ms`
- aggregate median latency improved from `1900 ms` to `630 ms`
- throughput improved from `23.89 req/s` to `34.37 req/s`
- `reports/financial/meta [seed]` average improved from `5307 ms` to `3788 ms`
- `reports/financial/meta [seed]` median improved from `6000 ms` to `3400 ms`
- `reports/financial/meta [seed]` max improved from `9659 ms` to `7899 ms`

Interpretation:
- the targeted financial-meta query trim materially stabilizes the upper-tier statement-family run
- the earlier correctness problem is resolved: the `100-user` tier now completes with `0` failures
- the statement endpoints themselves are now operating in a much stronger band, with most median latencies falling around the `500–650 ms` range
- `reports/financial/meta [seed]` is still the slowest path in the family, but it is now a tolerable hotspot rather than a blocker

Status after this rerun:
- `financial statement family correctness at 100 users after query trim`: `passed`
- `financial statement family performance at 100 users after query trim`: `strong`
- `financial statement family remaining hotspot at 100 users`: `reports/financial/meta [seed]`
- `financial statement family blocker status`: `cleared`
- `financial statement family next step`: `move to the next module stress pass, with optional future tuning for financial meta seed latency`

## Phase 1B Follow-up Result: Purchase 20-User / 2-Minute Mixed And Isolated Write Rerun With Writes Enabled On August 3, 2026

Purpose:
- refresh purchase write-stress evidence on the current local stack with write and lifecycle flags explicitly enabled
- separate real purchase mutation behavior from the earlier auth-only dry run caused by disabled write toggles
- capture the exact current hotspot ordering before raising purchase back to a higher-user tier

Commands:

```bash
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true ./.venv/bin/locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon --html results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon.html

FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true ./.venv/bin/locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_writeon --html results_phase1_purchase_write_20u_2m_2026_08_03_writeon.html
```

Artifacts:
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_writeon.html:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_writeon_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_writeon_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_writeon_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_writeon_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_writeon.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_writeon.html:1)

Result: purchase mixed
- total requests: `870`
- failures: `0`
- aggregate median latency: `1700 ms`
- aggregate average latency: `1819.69 ms`
- p95 latency: `3800 ms`
- p99 latency: `6300 ms`
- max observed latency: `7169.46 ms`

Result: purchase isolated write
- total requests: `968`
- failures: `0`
- aggregate median latency: `1900 ms`
- aggregate average latency: `1956.67 ms`
- p95 latency: `3700 ms`
- p99 latency: `5700 ms`
- max observed latency: `6583.24 ms`

Key isolated-write hotspots:
- `purchase/service-invoices [draft save]`: `28` requests, `0` failures, avg `4181.6 ms`, p95 `6300 ms`, max `6352.4 ms`
- `purchase/invoices [draft save]`: `29` requests, `0` failures, avg `3916.5 ms`, p95 `6200 ms`, max `6583.2 ms`
- `purchase/service-invoices [draft create]`: `95` requests, `0` failures, avg `2487.9 ms`, p95 `4000 ms`, max `4296.0 ms`
- `purchase/invoices [draft create]`: `103` requests, `0` failures, avg `2301.8 ms`, p95 `3800 ms`, max `3994.8 ms`
- `purchase/service-invoices [post]`: `60` requests, `0` failures, avg `2295.0 ms`, p95 `3300 ms`, max `3597.9 ms`
- `purchase/invoices [post]`: `71` requests, `0` failures, avg `2233.7 ms`, p95 `3600 ms`, max `3728.7 ms`

Key mixed-run hotspots:
- `purchase/invoices [draft save]`: `20` requests, `0` failures, avg `5084.2 ms`, p95 `6900 ms`, max `6866.7 ms`
- `purchase/service-invoices [draft save]`: `25` requests, `0` failures, avg `4617.5 ms`, p95 `6800 ms`, max `7169.5 ms`
- `purchase/service-invoices [draft create]`: `65` requests, `0` failures, avg `2568.8 ms`, p95 `3900 ms`, max `4011.2 ms`
- `purchase/invoices [draft create]`: `66` requests, `0` failures, avg `2553.7 ms`, p95 `3900 ms`, max `4423.6 ms`

Interpretation:
- purchase write correctness is clean again on the current stack at the `20-user / 2-minute` working tier
- both goods and service draft-save paths are now the clear latency bottleneck, stronger than confirm/post and stronger than lookup/navigation at this tier
- service-side mutation remains slightly heavier than goods-side mutation, but both are inside the same bottleneck family now: header-plus-line draft persistence under overlap
- because both mixed and isolated runs stayed at `0` failures, the immediate purchase risk is performance headroom rather than transactional correctness

Status after this rerun:
- `purchase write correctness at 20 users on current stack`: `passed`
- `purchase mixed correctness at 20 users on current stack`: `passed`
- `purchase dominant hotspot`: `goods and service draft save`
- `purchase secondary hotspot`: `draft create`
- `purchase next best step`: `raise purchase back to the higher-user comparison tier and reduce draft-save cost before treating purchase as SaaS-grade comfortable`

## Phase 1B Follow-up Result: Purchase 20-User / 2-Minute Rerun After No-Op Draft Upsert Trim On August 3, 2026

Purpose:
- validate whether skipping unchanged line and charge rewrites inside purchase draft save materially lowers the write tail
- compare directly against the immediately previous `20-user / 2-minute` purchase mixed and isolated write reruns
- decide whether the next purchase step should be more micro-optimization or a different bottleneck target

Code change validated before this run:
- unchanged purchase line rows no longer go through `full_clean()` plus `bulk_update()` during draft save
- unchanged purchase charge rows no longer go through `bulk_update()` during draft save
- this change was validated with focused purchase regression tests before rerunning Locust

Commands:

```bash
FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true ./.venv/bin/locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim --html results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim.html

FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true ./.venv/bin/locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim --html results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_after_noop_trim.html:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_after_noop_trim.html:1)

Result: isolated purchase write
- total requests: `600`
- failures: `0`
- aggregate median latency: `2500 ms`
- aggregate average latency: `3328 ms`
- p95 latency: `7600 ms`
- p99 latency: `13000 ms`
- max observed latency: `15179 ms`

Result: purchase mixed
- total requests: `601`
- failures: `0`
- aggregate median latency: `2200 ms`
- aggregate average latency: `2883 ms`
- p95 latency: `7300 ms`
- p99 latency: `11000 ms`
- max observed latency: `14376 ms`

Key write hotspots after the no-op trim:
- `purchase/service-invoices [draft save]`: isolated avg `9127 ms`, median `7100 ms`, p95 `15000 ms`, max `15179 ms`
- `purchase/invoices [draft save]`: isolated avg `7275 ms`, median `5700 ms`, p95 `13000 ms`, max `13005 ms`
- `purchase/service-invoices [draft create]`: isolated avg `4442 ms`, median `3500 ms`, p95 `8400 ms`
- `purchase/invoices [draft create]`: isolated avg `3990 ms`, median `3300 ms`, p95 `7900 ms`
- `purchase/service-invoices [draft save]`: mixed avg `7650 ms`, median `6100 ms`, p95 `12000 ms`, max `12002 ms`
- `purchase/invoices [draft save]`: mixed avg `7589 ms`, median `5800 ms`, p95 `14000 ms`, max `14376 ms`

Comparison against the earlier same-tier purchase rerun immediately before this change:
- correctness stayed `0 failures` in both runs
- latency did **not** improve in a meaningful way
- draft-save remained the dominant hotspot and was actually worse in this rerun
- draft-create, confirm, and post paths also inflated at the same time

Interpretation:
- skipping unchanged upsert rewrites is safe, but it is not the main purchase bottleneck under concurrent draft-save pressure
- the heavier cost is still coming from broader save-path work around draft mutation, not from needless no-op row persistence alone
- likely remaining cost centers are authoritative line recomputation, structural validation, duplicate checks, and downstream header-side recalculation or related save-time side effects

Status after this rerun:
- `purchase no-op upsert trim correctness`: `passed`
- `purchase no-op upsert trim performance effect`: `negligible`
- `purchase primary bottleneck after rerun`: `draft save path beyond row write churn`
- `purchase next best step`: `investigate deeper draft-save computation and validation work before more micro-trims`

## Phase 1B Follow-up Result: Purchase 20-User / 2-Minute Rerun After Policy-Reuse Fix On August 3, 2026

Purpose:
- validate that the purchase policy-reuse optimization is functionally safe after the regression fix
- rerun the same `20-user / 2-minute` purchase write and mixed tiers for apples-to-apples comparison
- check whether reducing repeated purchase policy fetches changes the dominant draft-save hotspot

Code change validated before this run:
- purchase create/update paths now reuse one `PurchaseSettingsService.get_policy(...)` result across tax derivation, line validation, and charge validation
- the initial regression from that refactor was fixed and purchase regression tests were rerun successfully before stress execution

Commands:

```bash
source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix --html results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix.html

source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix --html results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_post_policy_fix.html:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_post_policy_fix.html:1)

Regression-test checkpoint before stress:
- `purchase.tests.PurchaseInvoiceConcurrencyHardeningTests`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_create_goods_invoice_with_new_line_id_null`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_duplicate_supplier_invoice_is_blocked_for_same_vendor_date_and_amount`: `passed`

Result: isolated purchase write
- total requests: `449`
- failures: `0`
- aggregate median latency: `4700 ms`
- aggregate average latency: `4647.31 ms`
- p95 latency: `8300 ms`
- p99 latency: `13000 ms`
- max observed latency: `15135.23 ms`

Result: purchase mixed
- total requests: `456`
- failures: `0`
- aggregate median latency: `3900 ms`
- aggregate average latency: `4173.07 ms`
- p95 latency: `8200 ms`
- p99 latency: `12000 ms`
- max observed latency: `15623.40 ms`

Key write hotspots after the policy-reuse fix:
- `purchase/invoices [draft save]`: isolated avg `12248.84 ms`, median `11000 ms`, p95 `15000 ms`, max `15135.23 ms`
- `purchase/service-invoices [draft save]`: isolated avg `11625.56 ms`, median `11000 ms`, p95 `13000 ms`, max `12945.28 ms`
- `purchase/invoices [draft save]`: mixed avg `10528.42 ms`, median `11000 ms`, p95 `12000 ms`, max `11743.88 ms`
- `purchase/service-invoices [draft save]`: mixed avg `11671.23 ms`, median `11000 ms`, p95 `16000 ms`, max `15623.40 ms`
- `purchase/invoices [draft create]`: isolated avg `6259.45 ms`, mixed avg `6220.60 ms`
- `purchase/service-invoices [draft create]`: isolated avg `6216.33 ms`, mixed avg `6379.79 ms`

Comparison against the immediately previous `after_noop_trim` tier:
- correctness stayed `0 failures` in both write and mixed runs
- latency got worse rather than better on this rerun
- isolated aggregate average moved from `3328.15 ms` to `4647.31 ms`
- isolated purchase draft save moved from `7275.14 ms` to `12248.84 ms`
- isolated purchase service draft save moved from `9127.91 ms` to `11625.56 ms`
- mixed aggregate average moved from `2884.00 ms` to `4173.07 ms`
- mixed purchase draft save moved from `7589.36 ms` to `10528.42 ms`
- mixed purchase service draft save moved from `7650.90 ms` to `11671.23 ms`

Interpretation:
- the policy-reuse change is safe from a correctness point of view, but it is not the primary purchase performance lever
- purchase draft-save remains the clear dominant hotspot
- because the same hotspot persisted and worsened across reruns, the remaining cost is likely elsewhere in the draft mutation path:
  - authoritative recomputation
  - duplicate or status validation
  - totals recalculation
  - draft-summary persistence
  - related side effects triggered during save

Status after this rerun:
- `purchase policy-reuse correctness`: `passed`
- `purchase policy-reuse performance effect`: `no improvement observed`
- `purchase current dominant hotspot`: `goods and service draft save`
- `purchase recommended next step`: `profile and trim the deeper draft-save path instead of further policy-fetch micro-optimization`

## Phase 1C Follow-up Result: Purchase 20-User / 2-Minute Rerun After Lightening Mutation Responses On August 3, 2026

Objective:
- reduce purchase draft-save stress latency by trimming non-essential PATCH response enrichment
- preserve purchase correctness while removing preview-number and navigation work from mutation responses
- rerun the same `20-user / 2-minute` purchase write and mixed tiers for direct comparison

Code change validated before this run:
- purchase retrieve/update view now sets `skip_preview_numbers=True` and `skip_navigation=True` for `PUT` and `PATCH` serializer contexts
- purchase view-context regression test added for PATCH mutation responses
- purchase targeted regression tests and purchase e2e create/duplicate checks rerun successfully before stress execution

Commands:

```bash
source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_light_response --html results_phase1_purchase_write_20u_2m_2026_08_03_light_response.html

source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response --html results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_light_response_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_light_response_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_light_response_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_light_response_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_light_response.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_light_response.html:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_light_response.html:1)

Regression-test checkpoint before stress:
- `purchase.tests.PurchaseInvoiceRetrieveContextTests`: `passed`
- `purchase.tests.PurchaseInvoiceConcurrencyHardeningTests`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_create_goods_invoice_with_new_line_id_null`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_duplicate_supplier_invoice_is_blocked_for_same_vendor_date_and_amount`: `passed`

Result: isolated purchase write
- total requests: `977`
- failures: `0`
- aggregate median latency: `1800 ms`
- aggregate average latency: `1934.45 ms`
- p95 latency: `3600 ms`
- p99 latency: `5700 ms`
- max observed latency: `6141.53 ms`

Result: purchase mixed
- total requests: `920`
- failures: `0`
- aggregate median latency: `1700 ms`
- aggregate average latency: `1728.03 ms`
- p95 latency: `3300 ms`
- p99 latency: `5600 ms`
- max observed latency: `6166.31 ms`

Key draft-save hotspots after response-lightening:

## Phase 1C Follow-up Result: Purchase 20-User / 2-Minute Rerun After Action-Response Trim On August 3, 2026

Objective:
- validate whether trimming purchase action-response enrichment would further reduce purchase write latency
- preserve purchase correctness while removing duplicate serializer-side summary work from confirm and post style responses
- compare directly against the stronger `light_response` purchase baseline from the same day

Code change validated before this run:
- purchase action responses now serialize header data with:
  - `skip_navigation=True`
  - `skip_preview_numbers=True`
  - `skip_gst_tds_contract_summary=True`
- purchase serializer now short-circuits `gst_tds_contract_summary` lookup when that skip flag is set
- targeted serializer-context and purchase regression tests rerun successfully before stress execution

Commands:

```bash
source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim --html results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim.html

source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim --html results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_action_response_trim.html:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_action_response_trim.html:1)

Regression-test checkpoint before stress:
- `purchase.tests.PurchaseInvoiceRetrieveContextTests`: `passed`
- `purchase.tests.PurchaseInvoiceSerializerContextTests`: `passed`
- `purchase.tests.PurchaseInvoiceConcurrencyHardeningTests`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_create_goods_invoice_with_new_line_id_null`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_duplicate_supplier_invoice_is_blocked_for_same_vendor_date_and_amount`: `passed`

Result: isolated purchase write
- total requests: `832`
- failures: `0`
- aggregate median latency: `2300 ms`
- aggregate average latency: `2348.46 ms`
- p95 latency: `4800 ms`
- p99 latency: `6200 ms`
- max observed latency: `7543.01 ms`

Key write endpoints:
- `purchase/invoices [confirm]`: avg `2026.69 ms`
- `purchase/invoices [draft create]`: avg `2954.82 ms`
- `purchase/invoices [draft save]`: avg `5173.15 ms`
- `purchase/invoices [post]`: avg `2704.85 ms`
- `purchase/service-invoices [confirm]`: avg `1870.21 ms`
- `purchase/service-invoices [draft create]`: avg `2852.64 ms`
- `purchase/service-invoices [draft save]`: avg `5456.21 ms`
- `purchase/service-invoices [post]`: avg `2526.46 ms`

Result: purchase mixed
- total requests: `783`
- failures: `0`
- aggregate median latency: `2000 ms`
- aggregate average latency: `2123.04 ms`
- p95 latency: `4300 ms`
- p99 latency: `6300 ms`
- max observed latency: `7473.87 ms`

Key mixed endpoints:
- `purchase/invoices [confirm]`: avg `1960.22 ms`
- `purchase/invoices [draft create]`: avg `2889.93 ms`
- `purchase/invoices [draft save]`: avg `5619.13 ms`
- `purchase/invoices [post]`: avg `2669.98 ms`
- `purchase/service-invoices [confirm]`: avg `2088.59 ms`
- `purchase/service-invoices [draft create]`: avg `3071.13 ms`
- `purchase/service-invoices [draft save]`: avg `5420.97 ms`
- `purchase/service-invoices [post]`: avg `2850.83 ms`

Comparison against the immediately previous `light_response` tier:
- correctness stayed `0 failures` in both write and mixed runs
- isolated aggregate average moved from `1934.45 ms` to `2348.46 ms`
- mixed aggregate average moved from `1728.03 ms` to `2123.04 ms`
- isolated purchase draft save moved from `4356.30 ms` to `5173.15 ms`
- isolated purchase service draft save moved from `4396.05 ms` to `5456.21 ms`
- mixed purchase draft save moved from `4507.46 ms` to `5619.13 ms`
- mixed purchase service draft save moved from `3928.09 ms` to `5420.97 ms`

Interpretation:
- the action-response trim is safe from a correctness point of view, but it is not the next meaningful purchase performance lever
- the earlier response-lightening change captured the useful low-risk response win
- remaining purchase write latency is now dominated by deeper transactional work inside draft create, draft save, confirm, and post paths
- purchase draft save remains the clearest primary hotspot across both goods and service flows

Status after this rerun:
- `purchase action-response correctness`: `passed`
- `purchase action-response performance effect`: `no improvement observed`
- `purchase dominant current hotspot`: `goods and service draft save`
- `purchase recommended next step`: `profile and trim deeper mutation-path work rather than continuing serializer-response micro-optimization`

## Phase 1C Follow-up Result: Purchase 20-User / 2-Minute Rerun After Line Runtime Fast Path On August 3, 2026

Objective:
- reduce purchase draft-save latency by trimming per-line runtime validation cost in authoritative draft mutations
- preserve product-specific line invariants while avoiding expensive `full_clean()` calls on every changed line
- rerun the same isolated purchase-write and purchase-mixed tiers for direct comparison against earlier August 3 purchase baselines

Code change validated before this run:
- purchase line upserts now use a targeted runtime invariant check instead of `full_clean()` for authoritative mutation-path line saves
- retained invariants:
  - batch-managed products require batch number
  - expiry-tracked products require expiry date
  - manufacture date cannot exceed expiry date
- added targeted regression tests for the new line runtime invariant helper
- purchase regression and purchase e2e create/duplicate checks rerun successfully before stress execution

Commands:

```bash
source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath --html results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath.html

source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-mixed --csv results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath --html results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath.html
```

Artifacts:
- [results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath_stats.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath_failures.csv:1)
- [results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_line_runtime_fastpath.html:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath_stats.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath_failures.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath_failures.csv:1)
- [results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_mixed_20u_2m_2026_08_03_line_runtime_fastpath.html:1)

Regression-test checkpoint before stress:
- `purchase.tests.PurchaseInvoiceConcurrencyHardeningTests`: `passed`
- `purchase.tests.PurchaseInvoiceRetrieveContextTests`: `passed`
- `purchase.tests.PurchaseInvoiceSerializerContextTests`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_create_goods_invoice_with_new_line_id_null`: `passed`
- `purchase.tests_e2e_api.PurchaseApiEndToEndTests.test_duplicate_supplier_invoice_is_blocked_for_same_vendor_date_and_amount`: `passed`

Result: isolated purchase write
- total requests: `1224`
- failures: `0`
- aggregate median latency: `1400 ms`
- aggregate average latency: `1477.07 ms`
- p95 latency: `2900 ms`
- p99 latency: `3400 ms`
- max observed latency: `4163.84 ms`

Key write endpoints:
- `purchase/invoices [confirm]`: avg `1226.21 ms`
- `purchase/invoices [draft create]`: avg `1796.52 ms`
- `purchase/invoices [draft save]`: avg `3063.12 ms`
- `purchase/invoices [post]`: avg `1602.35 ms`
- `purchase/service-invoices [confirm]`: avg `1226.32 ms`
- `purchase/service-invoices [draft create]`: avg `1759.84 ms`
- `purchase/service-invoices [draft save]`: avg `2997.36 ms`
- `purchase/service-invoices [post]`: avg `1589.16 ms`

Result: purchase mixed
- total requests: `1085`
- failures: `0`
- aggregate median latency: `1300 ms`
- aggregate average latency: `1328.64 ms`
- p95 latency: `2300 ms`
- p99 latency: `3400 ms`
- max observed latency: `4218.44 ms`

Key mixed endpoints:
- `purchase/invoices [confirm]`: avg `1307.76 ms`
- `purchase/invoices [draft create]`: avg `1827.85 ms`
- `purchase/invoices [draft save]`: avg `3058.78 ms`
- `purchase/invoices [post]`: avg `1716.86 ms`
- `purchase/service-invoices [confirm]`: avg `1183.82 ms`
- `purchase/service-invoices [draft create]`: avg `1738.59 ms`
- `purchase/service-invoices [draft save]`: avg `3158.67 ms`
- `purchase/service-invoices [post]`: avg `1574.60 ms`

Comparison against the immediately previous purchase tiers:
- versus `light_response`:
  - isolated aggregate average improved from `1934.45 ms` to `1477.07 ms`
  - mixed aggregate average improved from `1728.03 ms` to `1328.64 ms`
  - isolated purchase draft save improved from `4356.30 ms` to `3063.12 ms`
  - isolated purchase service draft save improved from `4396.05 ms` to `2997.36 ms`
  - mixed purchase draft save improved from `4507.46 ms` to `3058.78 ms`
  - mixed purchase service draft save improved from `3928.09 ms` to `3158.67 ms`
- versus `action_response_trim`:
  - isolated aggregate average improved from `2348.46 ms` to `1477.07 ms`
  - mixed aggregate average improved from `2123.04 ms` to `1328.64 ms`
  - isolated purchase draft save improved from `5173.15 ms` to `3063.12 ms`
  - isolated purchase service draft save improved from `5456.21 ms` to `2997.36 ms`
  - mixed purchase draft save improved from `5619.13 ms` to `3058.78 ms`
  - mixed purchase service draft save improved from `5420.97 ms` to `3158.67 ms`

Interpretation:
- this change produced the first strong backend-path win after the earlier response-lightening improvement
- purchase draft-save remains the dominant write hotspot, but it is now much closer to the rest of the purchase mutation family
- confirm, post, and draft create also benefited, which indicates the line mutation path was contributing to more than only PATCH draft-save tails
- remaining purchase work should now focus on the next largest contributors:
  - draft save tail beyond `3.0 s`
  - lookup/detail reads inside mixed flows
  - note creation and posting variants

Status after this rerun:
- `purchase line-runtime fast-path correctness`: `passed`
- `purchase line-runtime fast-path performance effect`: `material improvement observed`
- `purchase current purchase tier state`: `substantially stronger and ready for next hotspot pass`
- `purchase recommended next step`: `keep purchase in focus and profile the remaining draft-save tail plus mixed lookup/read costs before moving deeper into payables/receivables stress`
- `purchase/invoices [draft save]`: isolated avg `4356.41 ms`, median `4700 ms`, p95 `6000 ms`, max `6027.65 ms`
- `purchase/service-invoices [draft save]`: isolated avg `4396.50 ms`, median `4400 ms`, p95 `6100 ms`, max `6141.53 ms`
- `purchase/invoices [draft save]`: mixed avg `4507.42 ms`, median `4800 ms`, p95 `5900 ms`, max `6013.00 ms`
- `purchase/service-invoices [draft save]`: mixed avg `3927.96 ms`, median `3700 ms`, p95 `6200 ms`, max `6166.31 ms`

Comparison against the immediately previous `post_policy_fix` tier:
- correctness stayed `0 failures` in both write and mixed runs
- isolated aggregate average improved from `4647.31 ms` to `1934.45 ms`
- mixed aggregate average improved from `4173.07 ms` to `1728.03 ms`
- isolated purchase draft save improved from `12248.84 ms` to `4356.41 ms`
- isolated purchase service draft save improved from `11625.56 ms` to `4396.50 ms`
- mixed purchase draft save improved from `10528.42 ms` to `4507.42 ms`
- mixed purchase service draft save improved from `11671.23 ms` to `3927.96 ms`
- the dominant draft-save bottleneck was reduced by roughly `58%` to `66%` depending on path

Interpretation:
- the purchase stress bottleneck was largely in mutation-response enrichment rather than core tax recomputation
- lightening mutation responses preserved correctness and materially improved throughput and latency
- purchase draft-save is no longer a 10-15 second class hotspot at this tier; it is now a 4-6 second class hotspot
- the next purchase performance pass should focus on the remaining heavy write flows:
  - draft create
  - confirm/post transitions
  - purchase lookup and detail reads inside mixed workflows

Status after this rerun:
- `purchase mutation-response optimization correctness`: `passed`
- `purchase mutation-response optimization performance effect`: `strong improvement observed`
- `purchase current dominant hotspot`: `draft create and confirm/post flows, with draft save now materially reduced`
- `purchase recommended next step`: `continue purchase stress hardening on create/post/read paths before shifting to payables reports`

## Phase 1D Purchase Modern Read Rerun After Lookup/Cross-Mode Trim On August 3, 2026

Objective:
- validate the purchase read-side cleanup after trimming unused lookup joins/fields and narrowing cross-mode header fetch width

Code change summary:
- purchase lookup base queryset no longer carries the unused `subentity` join on the modern lookup path
- purchase lookup no longer pulls unused `vendor__ledger__name` / `subentity__subentityname` columns
- purchase cross-mode scoped header fetch now uses `.only(...)` for just the fields needed for permission and navigation logic

Regression-test checkpoint:
- command:
  - `source venv/bin/activate && python manage.py test purchase.tests.PurchaseInvoiceLookupViewTests purchase.tests.PurchaseInvoiceConcurrencyHardeningTests --keepdb`
- result:
  - `18 tests passed`

Stress command:
- `source ../../venv/bin/activate && locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-modern --csv results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim --html results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim.html`

Artifacts:
- CSV stats:
  - [results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim_stats.csv)
- HTML report:
  - [results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_read_modern_20u_2m_2026_08_03_lookup_trim.html)

Result: purchase modern read
- total requests: `1202`
- failures: `0`
- aggregate average latency: `65.06 ms`
- aggregate median latency: `64 ms`
- p95 latency: `89 ms`
- p99 latency: `150 ms`
- max observed latency: `188.81 ms`

Key purchase-modern endpoints:
- `purchase/purchase-invoices/lookup [list]`: avg `67.20 ms`, median `68 ms`, p95 `88 ms`, p99 `100 ms`, max `136.74 ms`
- `purchase/purchase-service-invoices/lookup [list]`: avg `67.91 ms`, median `68 ms`, p95 `89 ms`, p99 `99 ms`, max `131.91 ms`
- `purchase/purchase-invoices/cross-mode-nav [goods->service]`: avg `59.86 ms`, median `61 ms`, p95 `80 ms`, p99 `91 ms`, max `104.15 ms`
- `purchase/purchase-service-invoices/cross-mode-nav [service->goods]`: avg `59.55 ms`, median `59 ms`, p95 `81 ms`, p99 `99 ms`, max `107.45 ms`
- `purchase/goods-lookup [seed-id]`: avg `57.92 ms`
- `purchase/service-lookup [seed-id]`: avg `58.48 ms`

Interpretation:
- purchase modern reads are now comfortably out of the hotspot class at this tier
- lookup and cross-mode navigation are not materially contributing to the remaining purchase stress pain
- the main remaining purchase bottlenecks are still in write lifecycle operations, especially draft save / create / post families under mixed operational load

Status after this rerun:
- `purchase read-path trim correctness`: `passed`
- `purchase modern read stress state`: `strong`
- `purchase recommended next step`: `continue purchase write-tail hardening or move to payable/receivable stress with purchase modern reads considered healthy`

## Phase 1E Purchase Write Rerun After Mutation Contract-Summary Skip On August 3, 2026

Objective:
- reduce the remaining purchase write tail by skipping non-essential `gst_tds_contract_summary` enrichment on detail and mutation serializer responses

Code change summary:
- purchase detail GET and mutation serializer contexts now set `skip_gst_tds_contract_summary=True`
- this removes contract-ledger summary lookups from draft save / create / post response serialization where they do not change write correctness

Regression-test checkpoint:
- command:
  - `source venv/bin/activate && python manage.py test purchase.tests.PurchaseInvoiceRetrieveContextTests purchase.tests.PurchaseInvoiceSerializerContextTests purchase.tests.PurchaseInvoiceLookupViewTests purchase.tests.PurchaseInvoiceConcurrencyHardeningTests --keepdb`
- result:
  - `21 tests passed`

Stress command:
- `source ../../venv/bin/activate && FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true locust -f locustfile.py --headless --users 20 --spawn-rate 2 --run-time 2m --tags purchase-write --csv results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip --html results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip.html`

Artifacts:
- CSV stats:
  - [results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip_stats.csv)
- HTML report:
  - [results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_20u_2m_2026_08_03_contract_summary_skip.html)

Result: purchase write
- total requests: `1661`
- failures: `0`
- aggregate average latency: `986.98 ms`
- aggregate median latency: `940 ms`
- p95 latency: `1900 ms`
- p99 latency: `2700 ms`
- max observed latency: `3112.08 ms`

Key write endpoints:
- `purchase/invoices [draft save]`: avg `2068.72 ms`, median `2100 ms`, p95 `2900 ms`, p99 `3100 ms`, max `3060.79 ms`
- `purchase/service-invoices [draft save]`: avg `2110.86 ms`, median `2100 ms`, p95 `3100 ms`, p99 `3100 ms`, max `3112.08 ms`
- `purchase/invoices [draft create]`: avg `1177.01 ms`, median `1200 ms`, p95 `1800 ms`, p99 `2000 ms`
- `purchase/service-invoices [draft create]`: avg `1184.18 ms`, median `1100 ms`, p95 `1900 ms`, p99 `2000 ms`
- `purchase/invoices [post]`: avg `1069.88 ms`, median `1100 ms`, p95 `1600 ms`, p99 `1700 ms`
- `purchase/service-invoices [post]`: avg `1035.90 ms`, median `1000 ms`, p95 `1600 ms`, p99 `1700 ms`
- `purchase/goods-detail [seed]`: avg `762.02 ms`
- `purchase/service-detail [seed]`: avg `740.77 ms`

Comparison against the previous `line_runtime_fastpath` purchase write tier:
- aggregate average improved from `1477.07 ms` to `986.98 ms`
- aggregate median improved from `1400 ms` to `940 ms`
- `purchase/invoices [draft save]` improved from `3063.12 ms` to `2068.72 ms`
- `purchase/service-invoices [draft save]` improved from `2997.36 ms` to `2110.86 ms`
- `purchase/invoices [draft create]` improved from `1796.52 ms` to `1177.01 ms`
- `purchase/service-invoices [draft create]` improved from `1759.84 ms` to `1184.18 ms`
- `purchase/invoices [post]` improved from `1602.35 ms` to `1069.88 ms`
- `purchase/service-invoices [post]` improved from `1589.16 ms` to `1035.90 ms`
- `purchase/goods-detail [seed]` improved from `1143.55 ms` to `762.02 ms`
- `purchase/service-detail [seed]` improved from `1116.26 ms` to `740.77 ms`

Interpretation:
- the mutation-response payload still matters materially on purchase write stress
- purchase draft save remains the tallest write endpoint, but it has moved from the `~3.0 s` class into the `~2.1 s` class at this tier
- purchase create and post families also benefited, which indicates the trimmed serializer path was contributing broadly to write latency rather than only to PATCH draft-save
- purchase detail seed endpoints improved too, which is helpful because the write workload continuously opens newly created documents

Status after this rerun:
- `purchase mutation contract-summary trim correctness`: `passed`
- `purchase write-tier state`: `substantially stronger`
- `purchase remaining dominant write hotspot`: `draft save`
- `purchase recommended next step`: `profile and trim the remaining full-detail serializer / line payload cost on mutation responses or optimize the update pipeline itself`

Payment voucher/AP mismatch audit hardening:
- added command:
  - `source venv/bin/activate && python manage.py audit_payment_voucher_settlements --entity-id 10 --subentity-id 8`
- purpose:
  - audit posted payment vouchers against:
    - voucher settlement support
    - saved payment allocations
    - linked AP payment settlement totals
    - linked vendor advance balance totals
- implementation:
  - new service: `payments/services/payment_voucher_repair.py`
  - new command: `payments/management/commands/audit_payment_voucher_settlements.py`

Refined dry-run result for entity `10`, subentity `8`:
- scanned vouchers: `1770`
- flagged vouchers: `12`
- repaired vouchers: `0`
- allocation repairs: `0`

Confirmed mismatch classes:
- `AGAINST_BILL` distribution mismatch:
  - repeated pattern:
    - support `736.00`
    - allocation `348.00`
    - AP settlement `348.00`
  - example voucher:
    - `PPV-PPV-2026-01832-DBGMANUAL03956`
  - interpretation:
    - header settlement support does not match the distributed total across allocations and linked advance balance
    - not auto-repairable from first principles
- `ON_ACCOUNT` distribution mismatch:
  - repeated pattern:
    - support `133.40`
    - allocation `0.00`
    - AP settlement `0.00`
    - linked advance balance missing
  - example voucher:
    - `PPV-PPV-2026-1494`
  - interpretation:
    - posted on-account voucher support exists without a linked vendor advance balance
    - this is a separate lifecycle issue from the against-bill cash-allocation mismatch

Status:
- the audit is now precise enough to isolate real posted-data issues instead of flagging normal `ADVANCE` / `ON_ACCOUNT` behavior
- no auto-apply action was executed because the currently flagged rows are business-ambiguous and need targeted manual or scripted business-rule repair

Payables close-pack burst hardening on `2026-08-03`:
- scope:
  - targeted the repeated `payables close-pack` concurrency failure path found during Phase 1 operational report stress
- code changes:
  - added short-TTL scoped cache for the internal close-pack reconciliation payload
  - removed reconciliation trace expansion from the close-pack internal path because the close-pack summary/validation flow does not consume it
  - added short-TTL scoped cache for the full close-pack payload keyed by:
    - entity
    - FY
    - subentity
    - as-of date
    - included sections
    - top-vendor / exception / expanded-validation flags
- verification:
  - focused Django tests passed:
    - `test_payables_close_pack_composes_existing_control_sections`
    - `test_payables_close_pack_reuses_cached_reconciliation_for_same_scope`
    - `test_ap_gl_reconciliation_report_matches_when_gl_balance_aligns`
    - `test_ap_gl_reconciliation_report_flags_mismatch_without_gl_balance`
- before/after in-process concurrency probe:
  - previous 5-thread same-scope `build_payables_close_pack(...)`: about `19.656 s` total
  - current 5-thread same-scope `build_payables_close_pack(...)`: about `3.661 s` total
  - per-thread completion after hardening:
    - `3.605 s`
    - `3.639 s`
    - `3.627 s`
    - `3.654 s`
    - `3.637 s`
- interpretation:
  - identical close-pack bursts are now collapsing to shared work instead of recomputing the same heavy pack multiple times in parallel
  - this materially reduces the probability of the earlier timeout / `500` behavior seen in payables operational stress
  - remaining next candidate inside payables operational stress is `vendor-ledger` / `note-register` tail latency rather than `close-pack` collapse

Payables vendor-ledger and note-register burst hardening on `2026-08-03`:
- scope:
  - targeted the next same-scope concurrency tails after close-pack:
    - `vendor-ledger`
    - `vendor note-register`
- code changes:
  - added short-TTL scoped cache for `vendor-ledger` payloads
  - added short-TTL scoped cache for `vendor note-register` payloads
  - cache keys include:
    - entity
    - FY
    - subentity
    - vendor
    - date window
    - paging
    - sort
    - trace and UI feature toggles
- verification:
  - focused Django tests passed:
    - `test_vendor_ledger_statement_reuses_cached_payload_for_same_scope`
    - `test_vendor_note_register_reuses_cached_payload_for_same_scope`
- before/after in-process probes:
  - `vendor-ledger`
    - previous single run: about `4.526 s`
    - current single run: about `1.771 s`
    - previous 5-thread same-scope burst: about `39.454 s`
    - current 5-thread same-scope burst: cache-hit class, about `0.002 s` total after warm cache
  - `note-register`
    - previous single run: about `0.946 s`
    - current single run: about `0.785 s`
    - previous 5-thread same-scope burst: about `21.892 s`
    - current 5-thread same-scope burst: cache-hit class, about `0.002 s` total after warm cache
- interpretation:
  - repeated payables operational report opens with identical scope are now effectively burst-collapsed
  - the biggest payables operational same-filter concurrency regressions are materially reduced
  - next best step is cross-module stress progression into receivables, not more same-pattern payables caching

Receivables first stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py --headless --users 50 --spawn-rate 5 --run-time 45s --tags receivables-reports --csv perf/locust/results_phase1_receivables_reports_50u_45s_2026_08_03 --html perf/locust/results_phase1_receivables_reports_50u_45s_2026_08_03.html`
- result:
  - total requests: `1035`
  - failures: `0`
  - aggregate average: about `165 ms`
  - aggregate median: about `57 ms`
  - aggregate p95: about `560 ms`
  - aggregate p99: about `2300 ms`
- key endpoints:
  - `reports/receivables/customer-outstanding [get]`
    - requests: `283`
    - avg: about `175 ms`
    - median: about `56 ms`
    - p95: about `620 ms`
    - p99: about `2400 ms`
  - `reports/receivables/aging [summary]`
    - requests: `273`
    - avg: about `172 ms`
    - median: about `63 ms`
    - p95: about `690 ms`
    - p99: about `2500 ms`
  - `reports/receivables/open-items [get]`
    - requests: `127`
    - avg: about `138 ms`
    - median: about `39 ms`
    - p95: about `530 ms`
    - p99: about `1900 ms`
  - `reports/receivables/collections-history [get]`
    - requests: `124`
    - avg: about `167 ms`
    - median: about `33 ms`
    - p95: about `640 ms`
    - p99: about `2300 ms`
  - `reports/receivables/aging [invoice]`
    - requests: `128`
    - avg: about `169 ms`
    - median: about `72 ms`
    - p95: about `540 ms`
    - p99: about `2000 ms`
- interpretation:
  - receivables is currently stable at this tier with zero functional failures
  - latency is acceptable at the median, but there is still a visible long-tail spike band on heavier report paths
  - compared with the pre-hardening payables operational path, receivables is in a stronger starting state
  - if we keep optimizing, the first candidates are:
    - `customer-outstanding`
    - `aging [summary]`
    - `collections-history`

Voucher mixed write/approval stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true venv/bin/locust -f perf/locust/locustfile.py --headless --users 20 --spawn-rate 4 --run-time 45s --tags voucher-mixed --csv perf/locust/results_phase1_voucher_mixed_20u_45s_2026_08_03 --html perf/locust/results_phase1_voucher_mixed_20u_45s_2026_08_03.html`
- scope exercised:
  - payment vouchers:
    - draft create
    - draft save
    - confirm
    - post
    - submit
    - approve
    - reject
    - stale submit/approve/reject replay paths
  - receipt vouchers:
    - draft create
    - draft save
    - confirm
    - post
    - submit
    - approve
    - reject
    - stale submit/approve/reject replay paths
- result:
  - total requests: `1548`
  - failures: `0`
  - aggregate average: about `65 ms`
  - aggregate median: about `52 ms`
  - aggregate p95: about `140 ms`
  - aggregate p99: about `260 ms`
- notable write endpoints:
  - `payments/payment-vouchers [draft create]`
    - avg: about `86 ms`
    - p99: about `540 ms`
  - `payments/payment-vouchers [draft save]`
    - avg: about `102 ms`
    - p99: about `410 ms`
  - `payments/payment-vouchers [post]`
    - avg: about `81 ms`
    - p99: about `200 ms`
  - `receipts/receipt-vouchers [draft create]`
    - avg: about `66 ms`
    - p99: about `140 ms`
  - `receipts/receipt-vouchers [draft save]`
    - avg: about `92 ms`
    - p99: about `270 ms`
  - `receipts/receipt-vouchers [post]`
    - avg: about `80 ms`
    - p99: about `430 ms`
- interpretation:
  - payment and receipt voucher workflows are stable at this tier with zero functional regressions
  - approval-state stale conflict handling stayed consistent under load
  - no immediate stress defect surfaced here, so this module is currently in a stronger state than the pre-hardening payables operational path

Sales write stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true venv/bin/locust -f perf/locust/locustfile.py --headless --users 30 --spawn-rate 5 --run-time 45s --tags sales-write --csv perf/locust/results_phase1_sales_write_30u_45s_2026_08_03 --html perf/locust/results_phase1_sales_write_30u_45s_2026_08_03.html`
- artifacts:
  - [results_phase1_sales_write_30u_45s_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_30u_45s_2026_08_03_stats.csv)
  - [results_phase1_sales_write_30u_45s_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_30u_45s_2026_08_03_stats_history.csv)
  - [results_phase1_sales_write_30u_45s_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_sales_write_30u_45s_2026_08_03.html)
- result:
  - total requests: `1385`
  - failures: `0`
  - aggregate average: about `159 ms`
  - aggregate median: about `130 ms`
  - aggregate p95: about `360 ms`
  - aggregate p99: about `670 ms`
- notable endpoints:
  - `sales/invoices [draft create]`
    - requests: `98`
    - avg: about `130 ms`
    - median: about `100 ms`
    - p95: about `280 ms`
    - p99: about `530 ms`
  - `sales/invoices [draft save]`
    - requests: `98`
    - avg: about `182 ms`
    - median: about `150 ms`
    - p95: about `350 ms`
    - p99: about `610 ms`
  - `sales/invoices [confirm]`
    - requests: `172`
    - avg: about `125 ms`
    - median: about `80 ms`
    - p95: about `270 ms`
    - p99: about `980 ms`
  - `sales/invoices [post]`
    - requests: `172`
    - avg: about `195 ms`
    - median: about `170 ms`
    - p95: about `370 ms`
    - p99: about `730 ms`
  - `sales/invoices [reverse]`
    - requests: `172`
    - avg: about `153 ms`
    - median: about `130 ms`
    - p95: about `300 ms`
    - p99: about `550 ms`
  - `sales/service-invoices [draft create]`
    - requests: `94`
    - avg: about `152 ms`
    - median: about `120 ms`
    - p95: about `330 ms`
    - p99: about `940 ms`
  - `sales/service-invoices [draft save]`
    - requests: `94`
    - avg: about `205 ms`
    - median: about `170 ms`
    - p95: about `350 ms`
    - p99: about `930 ms`
  - `sales/settings [patch]`
    - requests: `170`
    - avg: about `184 ms`
    - median: about `150 ms`
    - p95: about `340 ms`
    - p99: about `980 ms`
- interpretation:
  - the current sales write profile is clean at this `30-user / 45-second` tier with zero failures
  - draft save and post remain the slowest common sales mutations, but they are in a healthy sub-second tail band here
  - the older sales settings mutation hotspot is no longer dominating this working tier
  - sales is currently in a stronger state than the earlier pre-hardening purchase and payables bottleneck phases

Purchase write stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 FINACC_ENABLE_WRITE_TESTS=true FINACC_ENABLE_LIFECYCLE_TESTS=true venv/bin/locust -f perf/locust/locustfile.py --headless --users 30 --spawn-rate 5 --run-time 45s --tags purchase-write --csv perf/locust/results_phase1_purchase_write_30u_45s_2026_08_03 --html perf/locust/results_phase1_purchase_write_30u_45s_2026_08_03.html`
- artifacts:
  - [results_phase1_purchase_write_30u_45s_2026_08_03_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_30u_45s_2026_08_03_stats.csv)
  - [results_phase1_purchase_write_30u_45s_2026_08_03_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_30u_45s_2026_08_03_stats_history.csv)
  - [results_phase1_purchase_write_30u_45s_2026_08_03.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_purchase_write_30u_45s_2026_08_03.html)
- result:
  - total requests: `2340`
  - failures: `0`
  - aggregate average: about `145 ms`
  - aggregate median: about `110 ms`
  - aggregate p95: about `330 ms`
  - aggregate p99: about `480 ms`
- notable endpoints:
  - `purchase/invoices [draft create]`
    - requests: `227`
    - avg: about `154 ms`
    - median: about `120 ms`
    - p95: about `340 ms`
    - p99: about `460 ms`
  - `purchase/invoices [draft save]`
    - requests: `77`
    - avg: about `151 ms`
    - median: about `100 ms`
    - p95: about `350 ms`
    - p99: about `700 ms`
  - `purchase/invoices [confirm]`
    - requests: `149`
    - avg: about `128 ms`
    - median: about `93 ms`
    - p95: about `310 ms`
    - p99: about `360 ms`
  - `purchase/invoices [post]`
    - requests: `148`
    - avg: about `153 ms`
    - median: about `130 ms`
    - p95: about `320 ms`
    - p99: about `410 ms`
  - `purchase/service-invoices [draft create]`
    - requests: `239`
    - avg: about `164 ms`
    - median: about `130 ms`
    - p95: about `360 ms`
    - p99: about `600 ms`
  - `purchase/service-invoices [draft save]`
    - requests: `67`
    - avg: about `163 ms`
    - median: about `140 ms`
    - p95: about `310 ms`
    - p99: about `620 ms`
  - `purchase/service-invoices [post]`
    - requests: `169`
    - avg: about `163 ms`
    - median: about `120 ms`
    - p95: about `410 ms`
    - p99: about `580 ms`
  - purchase note paths also stayed clean:
    - goods credit-note create/post/confirm
    - goods debit-note create/post/confirm
    - service credit-note create/post/confirm
    - service debit-note create/post/confirm
- interpretation:
  - the current purchase write profile is clean at this `30-user / 45-second` tier with zero failures
  - purchase and purchase-note mutations are now operating in the same generally healthy band as the refreshed sales write profile
  - draft save remains the slowest common purchase mutation, but it is no longer behaving like a stress defect at this tier
  - purchase is now in a materially stronger state than the earlier pre-hardening baselines that originally drove the Phase 1 work

Payables report stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r10 --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r10.html`
- artifacts:
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r10_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r10_stats.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r10_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r10_stats_history.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r10.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r10.html)
- result:
  - total requests: `1580`
  - failures: `0`
  - aggregate average: about `840 ms`
  - aggregate median: about `740 ms`
  - aggregate p95: about `1900 ms`
  - aggregate p99: about `2300 ms`
- key endpoints:
  - `reports/payables/aging [get]`
    - requests: `798`
    - avg: about `1010 ms`
    - median: about `930 ms`
    - p95: about `2000 ms`
    - p99: about `2500 ms`
    - max: about `2584 ms`
  - `reports/payables/meta [get]`
    - requests: `582`
    - avg: about `748 ms`
    - median: about `630 ms`
    - p95: about `1800 ms`
    - p99: about `2200 ms`
    - max: about `2428 ms`
- interpretation:
  - payables remains correctness-safe at this `100-user / 45-second` tier with zero failures
  - compared with the now-clean sales and purchase write baselines, the payable report family is still materially heavier in latency
  - the main current payables stress risk is no longer crashes or timeouts; it is sustained sub-second-to-multi-second tail cost under higher concurrent read pressure
  - `reports/payables/aging [get]` remains the lead candidate if we want another report-side optimization pass

Receivables report stress pass on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 45s --tags receivables-reports --csv perf/locust/results_phase1_receivables_reports_100u_45s_2026_08_03_r2 --html perf/locust/results_phase1_receivables_reports_100u_45s_2026_08_03_r2.html`
- artifacts:
  - [results_phase1_receivables_reports_100u_45s_2026_08_03_r2_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_100u_45s_2026_08_03_r2_stats.csv)
  - [results_phase1_receivables_reports_100u_45s_2026_08_03_r2_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_100u_45s_2026_08_03_r2_stats_history.csv)
  - [results_phase1_receivables_reports_100u_45s_2026_08_03_r2.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_receivables_reports_100u_45s_2026_08_03_r2.html)
- result:
  - total requests: `2213`
  - failures: `0`
  - aggregate average: about `59 ms`
  - aggregate median: about `38 ms`
  - aggregate p95: about `200 ms`
  - aggregate p99: about `350 ms`
- key endpoints:
  - `reports/receivables/customer-outstanding [get]`
    - requests: `611`
    - avg: about `51 ms`
    - median: about `37 ms`
    - p95: about `130 ms`
    - p99: about `330 ms`
    - max: about `376 ms`
  - `reports/receivables/aging [summary]`
    - requests: `572`
    - avg: about `54 ms`
    - median: about `42 ms`
    - p95: about `130 ms`
    - p99: about `270 ms`
    - max: about `380 ms`
  - `reports/receivables/aging [invoice]`
    - requests: `261`
    - avg: about `58 ms`
    - median: about `45 ms`
    - p95: about `140 ms`
    - p99: about `320 ms`
    - max: about `366 ms`
  - `reports/receivables/collections-history [get]`
    - requests: `309`
    - avg: about `28 ms`
    - median: about `20 ms`
    - p95: about `71 ms`
    - p99: about `140 ms`
    - max: about `220 ms`
  - `reports/receivables/open-items [get]`
    - requests: `260`
    - avg: about `38 ms`
    - median: about `26 ms`
    - p95: about `100 ms`
    - p99: about `250 ms`
    - max: about `380 ms`
- interpretation:
  - receivables is fully healthy at this `100-user / 45-second` tier with zero failures and a low-latency profile
  - compared directly against payables on the same day and same concurrency, receivables is materially stronger
  - the AP vs AR comparison now points to payables as the remaining report-side optimization priority, not receivables

AP aging summary correctness and cache hardening on `2026-08-03`:
- code changes:
  - added short-TTL AP aging caching controls in [settings.py](/Users/ansh/finacc-angular/finacc-django/Finacc/FA/settings.py)
    - `PAYABLES_AP_AGING_CACHE_ENABLED`
    - `PAYABLES_AP_AGING_CACHE_TTL_SECONDS`
  - added user-agnostic AP aging cache wrapper in [payables.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/services/payables.py)
  - corrected AP summary selector as-of settlement logic in [payables.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/selectors/payables.py)
    - summary mode now reconstructs `outstanding_asof` using `original_amount - settled_asof_lines`
    - this aligns summary mode with invoice mode and fixes the stale outstanding mismatch surfaced by the AP aging tests
  - added cache reuse regression coverage in [tests_payables.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/tests_payables.py)
- focused verification:
  - `venv/bin/python manage.py test --keepdb reports.tests_payables.PayableReportAPITests.test_ap_aging_report_supports_summary_and_invoice_views reports.tests_payables.PayableReportAPITests.test_ap_aging_summary_scopes_last_payment_dates_to_relevant_vendors reports.tests_payables.PayableReportAPITests.test_ap_aging_report_reuses_cached_payload_for_same_scope`
  - `venv/bin/python manage.py test --keepdb reports.tests_payables.PayableReportAPITests.test_ap_aging_overdue_only_excludes_current_vendor_and_invoice_rows reports.tests_payables.PayableReportAPITests.test_vendor_outstanding_and_invoice_aging_apply_pagination`
  - all passed

Payables report 100-user rerun after AP aging hardening on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache.html`
- artifacts:
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache_stats.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache_stats_history.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r11_after_ap_aging_cache.html)
- result:
  - total requests: `1631`
  - failures: `0`
  - aggregate average: about `746 ms`
  - aggregate median: about `480 ms`
  - aggregate p95: about `2400 ms`
  - aggregate p99: about `2900 ms`
- key endpoints:
  - `reports/payables/aging [get]`
    - requests: `845`
    - avg: about `852 ms`
    - median: about `600 ms`
    - p95: about `2500 ms`
    - p99: about `2900 ms`
    - max: about `3214 ms`
  - `reports/payables/meta [get]`
    - requests: `586`
    - avg: about `660 ms`
    - median: about `420 ms`
    - p95: about `2400 ms`
    - p99: about `2900 ms`
    - max: about `3127 ms`
- comparison versus pre-fix `r10` baseline:
  - aggregate median improved from about `740 ms` to about `480 ms`
  - aggregate average improved from about `840 ms` to about `746 ms`
  - `reports/payables/aging [get]` average improved from about `1010 ms` to about `852 ms`
  - but high-percentile tail remained broadly heavy and did not collapse the way payables operational same-scope caching did
- interpretation:
  - the AP aging summary correctness defect is fixed
  - payables remains functionally clean at `100 users`
  - the remaining payables bottleneck is now better classified as a broader read-path / auth-meta / mixed report overhead issue, not only an AP-aging summary-build issue
  - next best step is to profile `reports/payables/meta [get]` plus request-level auth/session overhead and then rerun the same tier

Payables meta-cache validation and 100-user rerun on `2026-08-03`:
- code changes:
  - added short-TTL payables meta caching controls in [settings.py](/Users/ansh/finacc-angular/finacc-django/Finacc/FA/settings.py)
    - `PAYABLES_META_CACHE_ENABLED`
    - `PAYABLES_META_CACHE_TTL_SECONDS`
  - added shared-payload cache wrapper in [payables_meta.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/services/payables_meta.py)
    - keeps `user_preferences` live per request
    - caches only the shared report metadata payload by scope and permission set
  - added regression coverage in [tests_payables.py](/Users/ansh/finacc-angular/finacc-django/Finacc/reports/tests_payables.py)
- focused verification:
  - `venv/bin/python manage.py test --keepdb reports.tests_payables.PayableReportAPITests.test_report_preferences_api_persists_and_meta_echoes_saved_state reports.tests_payables.PayableReportAPITests.test_payables_meta_reuses_cached_shared_payload_and_keeps_user_preferences_live`
  - `venv/bin/python manage.py test --keepdb reports.tests_payables.PayableReportAPITests.test_ap_aging_report_reuses_cached_payload_for_same_scope`
  - all passed

Payables report 100-user rerun after meta caching on `2026-08-03`:
- command:
  - `LOCUST_HOST=http://127.0.0.1:8010 venv/bin/locust -f perf/locust/locustfile.py --headless --users 100 --spawn-rate 10 --run-time 45s --tags payables-reports --csv perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache --html perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache.html`
- artifacts:
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache_stats.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache_stats.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache_stats_history.csv](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache_stats_history.csv)
  - [results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache.html](/Users/ansh/finacc-angular/finacc-django/Finacc/perf/locust/results_phase1_payables_reports_100u_45s_2026_08_03_r12_after_meta_cache.html)
- result:
  - total requests: `1596`
  - failures: `0`
  - aggregate average: about `784 ms`
  - aggregate median: about `520 ms`
  - aggregate p95: about `2300 ms`
  - aggregate p99: about `3200 ms`
- key endpoints:
  - `reports/payables/aging [get]`
    - requests: `879`
    - avg: about `903 ms`
    - median: about `650 ms`
    - p95: about `2400 ms`
    - p99: about `3200 ms`
    - max: about `3437 ms`
  - `reports/payables/meta [get]`
    - requests: `517`
    - avg: about `679 ms`
    - median: about `410 ms`
    - p95: about `2200 ms`
    - p99: about `3100 ms`
    - max: about `3400 ms`
- comparison versus prior payables runs:
  - versus the original `r10` baseline:
    - aggregate average improved from about `840 ms` to about `784 ms`
    - aggregate median improved from about `740 ms` to about `520 ms`
    - `reports/payables/meta [get]` average improved from about `748 ms` to about `679 ms`
  - versus the AP-aging-only `r11` rerun:
    - aggregate average regressed from about `746 ms` to about `784 ms`
    - aggregate median regressed from about `480 ms` to about `520 ms`
    - `reports/payables/meta [get]` average changed only slightly from about `660 ms` to about `679 ms`
- interpretation:
  - `payables/meta` caching is behaviorally correct and does help relative to the older pre-hardening baseline
  - it does not materially collapse the stressed tail by itself
  - `reports/payables/aging [get]` remains the dominant purchase-report bottleneck at this tier
  - the next purchase stress-hardening step should stay focused on AP-aging read cost and request-overhead trimming rather than shifting modules prematurely
