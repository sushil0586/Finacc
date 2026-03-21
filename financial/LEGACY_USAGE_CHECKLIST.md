# Legacy Usage Remaining Checklist

Generated on 2026-03-21.

## Scope
- Apps reviewed: `financial`, `reports`, `payments`, `receipts`, `vouchers`, `sales`, `purchase`, `posting`, `entity`, `Authentication`, `subscriptions`, `rbac`.
- Goal: ensure runtime flows use normalized account profiles (`compliance_profile`, `commercial_profile`, `AccountAddress`) instead of legacy account columns.

## Remaining Legacy Column Touchpoints

### 1) Transitional service path (intentional)
- `financial/services.py:115`
- `financial/services.py:133`
- `financial/services.py:154`
- `financial/services.py:177`
- `financial/services.py:296`

These are intentionally retained only for:
- `ensure_normalized_profiles_for_account(..., use_legacy_fallback=True)`
- backfill/repair workflows
- optional bootstrap compatibility mode (`--sync-legacy-profiles`)

### 2) Test assertions and backfill test data (intentional)
- `financial/tests.py:215`
- `financial/tests_backfill_command.py:28`

These validate that:
- new API writes do not populate legacy columns
- legacy data can still be repaired by backfill command

### 3) Historical migration script (immutable)
- `financial/migrations/0008_accountaddress_accountcommercialprofile_and_more.py:20`

This is historical and should not be edited.

## Runtime Status
- No direct runtime report/service usage found for `customer.gstno` / `vendor.gstno` style access in active code paths.
- Active runtime paths are normalized-profile-first.
- Canonical financial endpoints are stable and validated.

## Recommendation
- Keep current transitional service fallback until all legacy data is verified backfilled.
- After final data freeze, remove fallback branch from `financial/services.py` in one controlled migration window.
