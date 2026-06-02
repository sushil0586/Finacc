# GST Reconciliation Performance And UAT Hardening

## Goal
Use this checklist during internal UAT for large GST reconciliation runs and reviewer concurrency testing.

## Performance hooks now available
- Response timing header: `X-GST-Recon-Timing-Ms`
- Optional payload timing field: `timing_ms`
- Perf logger namespace: `gst_reconciliation.performance`
- Optional cache controls:
  - `GST_RECON_CACHE_ENABLED`
  - `GST_RECON_CACHE_TTL_SECONDS`
- Optional timing log control:
  - `GST_RECON_PERF_LOGGING`
- Optional async matching hook:
  - `GST_RECON_ASYNC_MATCH_ENABLED`
  - `GST_RECON_ASYNC_MATCH_HANDLER`

## Large-run benchmark command
Use:

```bash
python manage.py benchmark_gst_reconciliation --entity <entity_id> --entityfinid <entityfinid_id> --user <user_id> --items 5000 --return-period 2026-04 --explain
```

Or benchmark an existing run:

```bash
python manage.py benchmark_gst_reconciliation --run-id <run_id> --explain
```

The command reports:
- run summary timing
- supplier analytics timing
- reviewer queue summary timing
- page-slice timing
- query counts
- optional database explain-plan output

## UAT scenarios

### 1. Large import run
- Import a `GSTR-2B` file with at least `5,000` rows.
- Verify import response time and `X-GST-Recon-Timing-Ms`.
- Open the generated run and record:
  - summary timing
  - supplier analytics timing
  - reviewer queue timing

### 2. Large-run pagination
- Open the item grid for a run with at least `5,000` items.
- Test page sizes `25`, `50`, `100`, `200`.
- Test server-side ordering:
  - `-updated_at`
  - `-match_confidence_score`
  - `invoice_date`
- Verify page-to-page latency remains acceptable.

### 3. Reviewer queue
- Load:
  - all unresolved items
  - assigned-only queue
  - unassigned-only queue
- Record timings with and without filters:
  - reviewer
  - supplier GSTIN
  - mismatch reason
  - low confidence

### 4. Bulk actions
- Select `100+` items and test:
  - assign
  - ignore
  - reopen
  - accept mismatch
  - unmatch
  - mark reviewed
- Record API timing and confirm partial failures are reported safely.

### 5. Concurrent reviewers
- Assign items to reviewer A.
- Attempt mutation from reviewer B.
- Verify permission denial.
- Reopen from assigned reviewer and re-test queue counts.

### 6. Activity log growth
- Perform repeated manual operations on the same run.
- Verify item detail still loads acceptably.
- Confirm action log payload is capped and includes `action_log_meta`.

## Explain-plan review
Check explain plans for:
- item grid unresolved queue query
- supplier analytics grouped query
- run summary count query
- action-log fetch by item

Red flags:
- sequential scan on `gst_reconciliation_item` for run-scoped queue access
- repeated nested loops on mismatch reasons for grouped analytics
- sort-heavy plans without using run-scoped indexes

## Reviewer productivity metrics
Review run summary output for:
- `assigned_count`
- `reviewed_count`
- `resolved_count`
- `avg_resolution_hours`

Use these during UAT to compare:
- first-day reviewer throughput
- low-confidence queue aging
- unresolved carry-over between days

## UAT issue tracking hooks
When logging issues, capture:
- run id
- endpoint
- `X-GST-Recon-Timing-Ms`
- page size
- filter set
- user role
- item count in run
- screenshot / request payload if relevant

Recommended defect tags:
- `GST-RECON-PERF`
- `GST-RECON-QUEUE`
- `GST-RECON-BULK`
- `GST-RECON-CACHE`
- `GST-RECON-CONCURRENCY`

## Remaining scale recommendations
- Move long-running matching to async in production if runs exceed the acceptable request-time budget.
- Add log retention/archival policy for reconciliation action logs.
- Consider materialized daily aggregates if supplier analytics becomes a dashboard hotspot.
