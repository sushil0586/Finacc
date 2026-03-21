# Legacy Usage Remaining Checklist

Generated on 2026-03-21.

## Scope
- Apps reviewed: `financial`, `reports`, `payments`, `receipts`, `vouchers`, `sales`, `purchase`, `posting`, `entity`, `Authentication`, `subscriptions`, `rbac`.
- Goal: runtime flows use normalized account profiles (`compliance_profile`, `commercial_profile`, `AccountAddress`) instead of legacy account columns.

## Remaining Legacy Column Touchpoints

### 1) Historical migration script (immutable)
- `financial/migrations/0008_accountaddress_accountcommercialprofile_and_more.py`

### 2) Test-only setup/assertion (intentional)
- `financial/tests.py`
- `financial/tests_backfill_command.py`

## Runtime Status
- Transitional legacy hydration fallback has been removed from `financial/services.py`.
- `bootstrap_financial_foundation` no longer supports legacy profile sync mode.
- `backfill_account_profiles` now backfills missing normalized compliance/commercial rows only.
- No direct runtime reads/writes of legacy account profile columns found outside migrations/tests.

## Recommendation
- Keep legacy columns physically present until a separate DB migration cycle.
- After one stable release, plan DB migration to drop legacy profile columns from `financial.account`.
