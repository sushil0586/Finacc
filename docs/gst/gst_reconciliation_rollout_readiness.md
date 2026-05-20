# GST Reconciliation Controlled Rollout Readiness

Date: 2026-05-20

## Purpose

Use this document to move GST Reconciliation into controlled pilot usage without changing old GST flows.

This phase is about:
- deployment readiness
- permission-safe exposure
- rollback safety
- supportability
- pilot-user discipline

## Scope

This rollout applies only to:
- the new `/gst-reconciliation` workspace
- the new `gst_reconciliation` backend APIs
- pilot users with explicit GST reconciliation permissions

This rollout does **not** replace:
- old purchase statutory screens
- old GST reports
- existing GSTR-1 / GSTR-3B report workflows

## Final Rollout Checklist

### 1. Deployment steps

1. Deploy backend code containing:
   - `gst_reconciliation` app
   - RBAC menu/permission migrations
   - performance migration `0005_perf_indexes`
2. Run migrations:

```bash
python manage.py migrate
```

3. Verify app is installed:
   - `gst_reconciliation.apps.GstReconciliationConfig`
4. Restart backend workers / application pods.
5. Confirm Angular build contains `/gst-reconciliation` route.

### 2. Migrations to verify

Required reconciliation migrations:
- `gst_reconciliation/0001_initial`
- `gst_reconciliation/0002_gstreconciliationitem_match_confidence_score_and_more`
- `gst_reconciliation/0003_gstreconciliationitem_accepted_mismatch_at_and_more`
- `gst_reconciliation/0004_gstreconciliationitem_assigned_by_and_more`
- `gst_reconciliation/0005_perf_indexes`

Required RBAC migrations:
- `rbac/0107_add_gst_reconciliation_workspace_menu`
- `rbac/0123_merge_gst_reconciliation_workspace_menu`

### 3. RBAC permissions

Verify these permissions exist:
- `gst.reconciliation.view`
- `gst.reconciliation.review`
- `gst.reconciliation.manage`

Recommended pilot assignment:
- pilot reviewers: `view` + `review`
- pilot admin / support lead: `view` + `review` + `manage`
- do not assign to all finance users by default

### 4. Menu visibility

The menu entry should appear only when:
- backend RBAC menu tree includes `compliance.gst_reconciliation`
- user has `gst.reconciliation.view`

Direct route should still work for authorized users:
- `/gst-reconciliation`

### 5. Seed / demo cleanup

If demo data was created using:

```bash
python manage.py seed_gst_reconciliation_demo ...
```

Do not leave demo runs in production entities.

Recommended:
- use only UAT or sandbox entities for seeded demo runs
- delete or deactivate demo runs before pilot user onboarding

### 6. Environment settings

Current production-review settings:
- `GST_RECON_CACHE_ENABLED=True`
- `GST_RECON_CACHE_TTL_SECONDS=60`
- `GST_RECON_PERF_LOGGING=False`
- `GST_RECON_ASYNC_MATCH_ENABLED=False`
- `GST_RECON_ASYNC_MATCH_HANDLER=''`

Recommended pilot defaults:
- keep cache enabled
- keep async matching disabled unless a real background runner exists
- keep perf logging off by default, enable temporarily for incident analysis

### 7. Rollback plan

If pilot must be rolled back:

1. Remove pilot user permissions:
   - `gst.reconciliation.view`
   - `gst.reconciliation.review`
   - `gst.reconciliation.manage`
2. Hide menu by removing permission assignment.
3. Keep route deployed, but inaccessible to ordinary users.
4. Do not roll back old GST reports or purchase statutory flow.
5. If needed, disable pilot operational usage by internal instruction while preserving data for analysis.

Recommended rollback approach:
- access rollback first
- code rollback only if there is a critical defect

## Production Configuration Review

### `GST_RECON_ASYNC_MATCH_ENABLED`

Current recommendation:
- `False` for pilot

Reason:
- async hook exists, but background execution wiring is not part of controlled rollout baseline

### `GST_RECON_ASYNC_MATCH_HANDLER`

Current recommendation:
- blank unless a real handler is deployed and validated

### Logging settings

Optional performance logger namespace:
- `gst_reconciliation.performance`

Enable only during focused investigation or benchmark windows.

### Benchmark command usage

Use for large-run validation:

```bash
python manage.py benchmark_gst_reconciliation --run-id <run_id> --explain
```

Or create a seeded benchmark run:

```bash
python manage.py benchmark_gst_reconciliation --entity <entity_id> --entityfinid <entityfinid_id> --user <user_id> --items 5000 --return-period 2026-04 --explain
```

### Timing header visibility

Current behavior:
- hot GST reconciliation APIs may return `X-GST-Recon-Timing-Ms`

Pilot note:
- safe for internal testing
- if external exposure is a concern later, this can be revisited before wider rollout

## Monitoring Checklist

Watch for:
- slow APIs on:
  - run summary
  - supplier analytics
  - reviewer queue
  - item grid
  - import APIs
- failed imports
- bulk action failures
- permission denials
- action-log growth
- run closure errors

Recommended review points:
- app logs
- reverse proxy timings
- database slow query logs
- pilot issue tracker

## Final Regression Checklist

Verify all of the following before pilot enablement:

### Old flows
- old purchase statutory flow still works
- old GST reports still work
- old GSTR-1 export still works
- old GSTR-3B summary still works

### New reconciliation flow
- `/gst-reconciliation` route opens for authorized users
- GSTR-2B import works
- matching works
- manual match works
- manual unmatch works
- ignore works
- accept mismatch works
- bulk actions work
- closed runs cannot be modified
- imported rows remain immutable
- permissions block unauthorized cross-entity access

## Known Limitations

- async matching hook exists but is not wired to a production background worker by default
- no archival / retention policy exists yet for long-term reconciliation action-log growth
- reviewer picker is still UI-side, not a dedicated reconciliation reviewer service
- no telemetry dashboard exists yet; timing and perf logging are available through API headers and logs

## Release Recommendation

Status recommendation:
- ready for controlled internal pilot
- not yet ready for unrestricted broad rollout

Go live with:
- limited user list
- limited entities
- real support ownership
- issue tracking discipline
